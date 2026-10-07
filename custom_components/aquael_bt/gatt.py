"""Active GATT access for Aquael BT devices."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

FLOW_HEATER_TARGET_UUID = "b3a10002-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_POWER_UUID = "b3a10004-8df0-11ee-b9d1-0242ac120002"

ULTRAMAX_FILTRATION_UUID = "19b10001-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_DAY_FLOW_UUID = "19b10003-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_NIGHT_FLOW_UUID = "19b10005-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_SETTINGS_UUID = "19b100ee-98b5-11ed-a8fc-0242ac120002"

ULTRAMAX_DAY_NIGHT_MODE_UUID = "19b20001-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_SUNRISE_UUID = "19b20002-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_SUNSET_UUID = "19b20003-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_TRANSITION_UUID = "19b20004-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_DAY_NIGHT_SETTINGS_UUID = "19b200ee-98b5-11ed-a8fc-0242ac120002"

ULTRAMAX_FLOW_SCALE = 4096


class AquaelGattCoordinator(DataUpdateCoordinator[dict[str, float | int | bool]]):
    """Read actively connected settings of an Aquael device."""

    def __init__(self, hass: HomeAssistant, address: str, device_type: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Aquael BT GATT {address}",
            update_interval=timedelta(minutes=1),
        )
        self.address = address
        self.device_type = device_type

    async def _async_connect(self) -> BleakClient:
        """Connect through Home Assistant's recommended retry connector."""
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise RuntimeError("Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar")
        return await establish_connection(
            BleakClient,
            ble_device,
            self.address,
            max_attempts=3,
        )

    async def _async_update_data(self) -> dict[str, float | int | bool]:
        try:
            client = await self._async_connect()
            try:
                if self.device_type == 0x04:
                    target_raw = await client.read_gatt_char(FLOW_HEATER_TARGET_UUID)
                    power_raw = await client.read_gatt_char(FLOW_HEATER_POWER_UUID)
                    if len(target_raw) < 4 or len(power_raw) < 4:
                        raise ValueError("Unerwartete GATT-Datenlänge")
                    return {
                        "target_temperature": int.from_bytes(target_raw[:4], "little") / 100.0,
                        "heating_power_limit": int.from_bytes(power_raw[:4], "little"),
                    }

                if self.device_type == 0x07:
                    settings_raw = await client.read_gatt_char(ULTRAMAX_SETTINGS_UUID)
                    day_night_raw = await client.read_gatt_char(
                        ULTRAMAX_DAY_NIGHT_SETTINGS_UUID
                    )
                    if len(settings_raw) < 25 or len(day_night_raw) < 13:
                        raise ValueError("Unerwartete ULTRAMAX-GATT-Datenlänge")

                    wave_mode_raw = int.from_bytes(settings_raw[1:5], "little")
                    day_flow_raw = int.from_bytes(settings_raw[5:9], "little")
                    day_min_flow_raw = int.from_bytes(settings_raw[9:13], "little")
                    night_flow_raw = int.from_bytes(settings_raw[13:17], "little")
                    night_min_flow_raw = int.from_bytes(settings_raw[17:21], "little")
                    wave_period_seconds = int.from_bytes(settings_raw[21:25], "little")

                    return {
                        "filtration": settings_raw[0] != 0,
                        "wave_mode_raw": wave_mode_raw,
                        "day_flow_raw": day_flow_raw,
                        "day_flow_percent": day_flow_raw * 100.0 / ULTRAMAX_FLOW_SCALE,
                        "day_min_flow_raw": day_min_flow_raw,
                        "day_min_flow_percent": day_min_flow_raw * 100.0 / ULTRAMAX_FLOW_SCALE,
                        "night_flow_raw": night_flow_raw,
                        "night_flow_percent": night_flow_raw * 100.0 / ULTRAMAX_FLOW_SCALE,
                        "night_min_flow_raw": night_min_flow_raw,
                        "night_min_flow_percent": night_min_flow_raw * 100.0 / ULTRAMAX_FLOW_SCALE,
                        "wave_period_seconds": wave_period_seconds,
                        "day_night_mode": day_night_raw[0] != 0,
                        "sunrise_seconds": int.from_bytes(day_night_raw[1:5], "little"),
                        "sunset_seconds": int.from_bytes(day_night_raw[5:9], "little"),
                        "transition_seconds": int.from_bytes(day_night_raw[9:13], "little"),
                    }

                raise ValueError(
                    f"Nicht unterstützter Aquael-Gerätetyp: {self.device_type:#x}"
                )
            finally:
                await client.disconnect()
        except Exception as err:
            if self.data:
                _LOGGER.debug(
                    "Keeping last Aquael GATT values after read failure: %s", err
                )
                return self.data
            raise UpdateFailed(f"Bluetooth-GATT-Lesen fehlgeschlagen: {err}") from err

    async def async_write(self, characteristic: str, payload: bytes) -> None:
        """Write a GATT setting with retry."""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                client = await self._async_connect()
                try:
                    await client.write_gatt_char(
                        characteristic, payload, response=True
                    )
                finally:
                    await client.disconnect()
                last_error = None
                break
            except Exception as err:
                last_error = err
                if attempt < 2:
                    await asyncio.sleep(2.0)

        if last_error is not None:
            raise UpdateFailed(
                f"Bluetooth-GATT-Schreiben nach 3 Versuchen fehlgeschlagen: {last_error}"
            ) from last_error

        if self.data:
            updated = dict(self.data)
            raw_value = int.from_bytes(payload, "little")
            if characteristic == FLOW_HEATER_TARGET_UUID:
                updated["target_temperature"] = raw_value / 100.0
            elif characteristic == FLOW_HEATER_POWER_UUID:
                updated["heating_power_limit"] = raw_value
            elif characteristic == ULTRAMAX_FILTRATION_UUID:
                updated["filtration"] = payload[0] != 0
            elif characteristic == ULTRAMAX_DAY_FLOW_UUID:
                updated["day_flow_raw"] = raw_value
                updated["day_flow_percent"] = (
                    raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
                )
            elif characteristic == ULTRAMAX_NIGHT_FLOW_UUID:
                updated["night_flow_raw"] = raw_value
                updated["night_flow_percent"] = (
                    raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
                )
            elif characteristic == ULTRAMAX_DAY_NIGHT_MODE_UUID:
                updated["day_night_mode"] = payload[0] != 0
            elif characteristic == ULTRAMAX_SUNRISE_UUID:
                updated["sunrise_seconds"] = raw_value
            elif characteristic == ULTRAMAX_SUNSET_UUID:
                updated["sunset_seconds"] = raw_value
            elif characteristic == ULTRAMAX_TRANSITION_UUID:
                updated["transition_seconds"] = raw_value
            self.async_set_updated_data(updated)
        await self.async_request_refresh()

    async def async_write_uint32(self, characteristic: str, value: int) -> None:
        """Write one unsigned 32-bit little-endian setting."""
        await self.async_write(
            characteristic, int(value).to_bytes(4, "little", signed=False)
        )

    async def async_write_bool(self, characteristic: str, value: bool) -> None:
        """Write one boolean byte setting."""
        await self.async_write(characteristic, b"\x01" if value else b"\x00")
