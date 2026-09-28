"""Active GATT access for Aquael BT devices."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from bleak import BleakClient
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

FLOW_HEATER_TARGET_UUID = "b3a10002-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_POWER_UUID = "b3a10004-8df0-11ee-b9d1-0242ac120002"

ULTRAMAX_FILTRATION_UUID = "19b10001-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_FLOW_UUID = "19b10003-98b5-11ed-a8fc-0242ac120002"
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

    async def _async_update_data(self) -> dict[str, float | int | bool]:
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            if self.data:
                _LOGGER.debug("Keeping last Aquael GATT values: no connectable BLE path")
                return self.data
            raise UpdateFailed("Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar")

        try:
            async with BleakClient(ble_device, timeout=15.0) as client:
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
                    filtration_raw = await client.read_gatt_char(ULTRAMAX_FILTRATION_UUID)
                    flow_raw = await client.read_gatt_char(ULTRAMAX_FLOW_UUID)
                    if len(filtration_raw) < 1 or len(flow_raw) < 4:
                        raise ValueError("Unerwartete GATT-Datenlänge")
                    raw_flow = int.from_bytes(flow_raw[:4], "little")
                    return {
                        "filtration": filtration_raw[0] != 0,
                        "flow_percent": raw_flow * 100.0 / ULTRAMAX_FLOW_SCALE,
                    }

                raise ValueError(f"Nicht unterstützter Aquael-Gerätetyp: {self.device_type:#x}")
        except Exception as err:
            if self.data:
                _LOGGER.debug("Keeping last Aquael GATT values after read failure: %s", err)
                return self.data
            raise UpdateFailed(f"Bluetooth-GATT-Lesen fehlgeschlagen: {err}") from err

    async def async_write(self, characteristic: str, payload: bytes) -> None:
        """Write a GATT setting with retry."""
        last_error: Exception | None = None
        for attempt in range(3):
            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                last_error = RuntimeError(
                    "Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar"
                )
            else:
                try:
                    async with BleakClient(ble_device, timeout=15.0) as client:
                        await client.write_gatt_char(characteristic, payload, response=True)
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
            if characteristic == FLOW_HEATER_TARGET_UUID:
                updated["target_temperature"] = int.from_bytes(payload, "little") / 100.0
            elif characteristic == FLOW_HEATER_POWER_UUID:
                updated["heating_power_limit"] = int.from_bytes(payload, "little")
            elif characteristic == ULTRAMAX_FILTRATION_UUID:
                updated["filtration"] = payload[0] != 0
            elif characteristic == ULTRAMAX_FLOW_UUID:
                updated["flow_percent"] = int.from_bytes(payload, "little") * 100.0 / ULTRAMAX_FLOW_SCALE
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
