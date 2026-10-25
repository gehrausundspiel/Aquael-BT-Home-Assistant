"""Active GATT access for Aquael BT devices."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address, async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .parser import parse_advertisement

_LOGGER = logging.getLogger(__name__)

FLOW_HEATER_HEATING_UUID = "b3a10001-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_TARGET_UUID = "b3a10002-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_NIGHT_TARGET_UUID = "b3a10003-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_POWER_UUID = "b3a10004-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_SETTINGS_UUID = "b3a100ee-8df0-11ee-b9d1-0242ac120002"

FLOW_HEATER_DAY_NIGHT_MODE_UUID = "b3a20001-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_SUNRISE_UUID = "b3a20002-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_SUNSET_UUID = "b3a20003-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_TRANSITION_UUID = "b3a20004-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_DAY_NIGHT_SETTINGS_UUID = "b3a200ee-8df0-11ee-b9d1-0242ac120002"

ULTRAMAX_FILTRATION_UUID = "19b10001-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_WAVE_MODE_UUID = "19b10002-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_DAY_FLOW_UUID = "19b10003-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_DAY_MIN_FLOW_UUID = "19b10004-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_NIGHT_FLOW_UUID = "19b10005-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_NIGHT_MIN_FLOW_UUID = "19b10006-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_WAVE_PERIOD_UUID = "19b10007-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_SETTINGS_UUID = "19b100ee-98b5-11ed-a8fc-0242ac120002"

ULTRAMAX_DAY_NIGHT_MODE_UUID = "19b20001-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_SUNRISE_UUID = "19b20002-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_SUNSET_UUID = "19b20003-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_TRANSITION_UUID = "19b20004-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_DAY_NIGHT_SETTINGS_UUID = "19b200ee-98b5-11ed-a8fc-0242ac120002"

ULTRAMAX_FEEDING_ENABLED_UUID = "19b30001-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_FEEDING_SLOTS_UUID = "19b30002-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_FEEDING_TIME_UUIDS = (
    "19b30003-98b5-11ed-a8fc-0242ac120002",
    "19b30004-98b5-11ed-a8fc-0242ac120002",
    "19b30005-98b5-11ed-a8fc-0242ac120002",
    "19b30006-98b5-11ed-a8fc-0242ac120002",
)
ULTRAMAX_FEEDING_FLOW_UUID = "19b30007-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_FEEDING_SETTINGS_UUID = "19b300ee-98b5-11ed-a8fc-0242ac120002"
ULTRAMAX_FEEDING_SLOT_COUNT = 4

ULTRAMAX_FLOW_SCALE = 4096


def parse_ultramax_feeding(raw: bytes) -> dict[str, float | int | bool]:
    """Decode the 25-byte ULTRAMAX Fish feeding block (19b300ee).

    Layout (little-endian), verified against the Aquael app:
      byte 0      feeding enabled (bool)
      bytes 1-4   one byte per feeding time: enabled (bool) for time 1..4
      bytes 5-20  feeding time 1..4, seconds after midnight
      bytes 21-24 water flow during feeding, raw (4096 = 100 %)
    """
    if len(raw) < 25:
        raise ValueError("Unexpected ULTRAMAX feeding GATT data length")
    data: dict[str, float | int | bool] = {
        "feeding_enabled": raw[0] != 0,
    }
    for index in range(ULTRAMAX_FEEDING_SLOT_COUNT):
        data[f"feeding_time_{index + 1}_enabled"] = raw[1 + index] != 0
    for index in range(ULTRAMAX_FEEDING_SLOT_COUNT):
        start = 5 + index * 4
        data[f"feeding_time_{index + 1}_seconds"] = int.from_bytes(
            raw[start : start + 4], "little"
        )
    flow_raw = int.from_bytes(raw[21:25], "little")
    data["feeding_flow_raw"] = flow_raw
    data["feeding_flow_percent"] = flow_raw * 100.0 / ULTRAMAX_FLOW_SCALE
    return data


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
                    settings_raw = await client.read_gatt_char(FLOW_HEATER_SETTINGS_UUID)
                    day_night_raw = await client.read_gatt_char(
                        FLOW_HEATER_DAY_NIGHT_SETTINGS_UUID
                    )
                    if len(settings_raw) < 13 or len(day_night_raw) < 13:
                        raise ValueError("Unerwartete Flow-Heater-GATT-Datenlänge")

                    return {
                        "heating": settings_raw[0] != 0,
                        "target_temperature": int.from_bytes(
                            settings_raw[1:5], "little"
                        )
                        / 100.0,
                        "night_target_temperature": int.from_bytes(
                            settings_raw[5:9], "little"
                        )
                        / 100.0,
                        "heating_power_limit": int.from_bytes(
                            settings_raw[9:13], "little"
                        ),
                        "day_night_mode": day_night_raw[0] != 0,
                        "sunrise_seconds": int.from_bytes(
                            day_night_raw[1:5], "little"
                        ),
                        "sunset_seconds": int.from_bytes(
                            day_night_raw[5:9], "little"
                        ),
                        "transition_seconds": int.from_bytes(
                            day_night_raw[9:13], "little"
                        ),
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

                    data: dict[str, float | int | bool] = {
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

                    # Fish feeding is optional: older firmware may not expose it.
                    try:
                        feeding_raw = await client.read_gatt_char(
                            ULTRAMAX_FEEDING_SETTINGS_UUID
                        )
                        data.update(parse_ultramax_feeding(bytes(feeding_raw)))
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.debug("ULTRAMAX feeding settings not available: %s", err)
                    return data

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
            if characteristic == FLOW_HEATER_HEATING_UUID:
                updated["heating"] = payload[0] != 0
            elif characteristic == FLOW_HEATER_TARGET_UUID:
                updated["target_temperature"] = raw_value / 100.0
            elif characteristic == FLOW_HEATER_NIGHT_TARGET_UUID:
                updated["night_target_temperature"] = raw_value / 100.0
            elif characteristic == FLOW_HEATER_POWER_UUID:
                updated["heating_power_limit"] = raw_value
            elif characteristic == FLOW_HEATER_DAY_NIGHT_MODE_UUID:
                updated["day_night_mode"] = payload[0] != 0
            elif characteristic == FLOW_HEATER_SUNRISE_UUID:
                updated["sunrise_seconds"] = raw_value
            elif characteristic == FLOW_HEATER_SUNSET_UUID:
                updated["sunset_seconds"] = raw_value
            elif characteristic == FLOW_HEATER_TRANSITION_UUID:
                updated["transition_seconds"] = raw_value
            elif characteristic == ULTRAMAX_FILTRATION_UUID:
                updated["filtration"] = payload[0] != 0
            elif characteristic == ULTRAMAX_WAVE_MODE_UUID:
                updated["wave_mode_raw"] = raw_value
            elif characteristic == ULTRAMAX_DAY_FLOW_UUID:
                updated["day_flow_raw"] = raw_value
                updated["day_flow_percent"] = raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
            elif characteristic == ULTRAMAX_DAY_MIN_FLOW_UUID:
                updated["day_min_flow_raw"] = raw_value
                updated["day_min_flow_percent"] = raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
            elif characteristic == ULTRAMAX_NIGHT_FLOW_UUID:
                updated["night_flow_raw"] = raw_value
                updated["night_flow_percent"] = raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
            elif characteristic == ULTRAMAX_NIGHT_MIN_FLOW_UUID:
                updated["night_min_flow_raw"] = raw_value
                updated["night_min_flow_percent"] = raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
            elif characteristic == ULTRAMAX_WAVE_PERIOD_UUID:
                updated["wave_period_seconds"] = raw_value
            elif characteristic == ULTRAMAX_DAY_NIGHT_MODE_UUID:
                updated["day_night_mode"] = payload[0] != 0
            elif characteristic == ULTRAMAX_SUNRISE_UUID:
                updated["sunrise_seconds"] = raw_value
            elif characteristic == ULTRAMAX_SUNSET_UUID:
                updated["sunset_seconds"] = raw_value
            elif characteristic == ULTRAMAX_TRANSITION_UUID:
                updated["transition_seconds"] = raw_value
            elif characteristic == ULTRAMAX_FEEDING_ENABLED_UUID:
                updated["feeding_enabled"] = payload[0] != 0
            elif characteristic == ULTRAMAX_FEEDING_SLOTS_UUID:
                for index in range(ULTRAMAX_FEEDING_SLOT_COUNT):
                    updated[f"feeding_time_{index + 1}_enabled"] = (
                        len(payload) > index and payload[index] != 0
                    )
            elif characteristic in ULTRAMAX_FEEDING_TIME_UUIDS:
                slot = ULTRAMAX_FEEDING_TIME_UUIDS.index(characteristic) + 1
                updated[f"feeding_time_{slot}_seconds"] = raw_value
            elif characteristic == ULTRAMAX_FEEDING_FLOW_UUID:
                updated["feeding_flow_raw"] = raw_value
                updated["feeding_flow_percent"] = raw_value * 100.0 / ULTRAMAX_FLOW_SCALE
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


async def async_get_gatt_coordinator(
    hass: HomeAssistant, entry: ConfigEntry
) -> AquaelGattCoordinator | None:
    """Return one shared active GATT coordinator per config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    coordinators = domain_data.setdefault("gatt_coordinators", {})
    locks = domain_data.setdefault("gatt_locks", {})

    existing = coordinators.get(entry.entry_id)
    if existing is not None:
        return existing

    lock = locks.setdefault(entry.entry_id, asyncio.Lock())
    async with lock:
        existing = coordinators.get(entry.entry_id)
        if existing is not None:
            return existing

        address = entry.unique_id
        if address is None:
            return None

        service_info = async_last_service_info(hass, address, connectable=False)
        parsed = parse_advertisement(service_info) if service_info else None
        if parsed is None:
            return None

        coordinator = AquaelGattCoordinator(hass, address, parsed.device_type)

        # One initial read for all entities. A failed BLE attempt does not block
        # platform setup; normal coordinator polling retries later. Publish the
        # coordinator only after this read, so platforms waiting on the lock get
        # populated data instead of an empty coordinator.
        await coordinator.async_refresh()
        coordinators[entry.entry_id] = coordinator
        return coordinator


def remove_gatt_coordinator(hass: HomeAssistant, entry_id: str) -> None:
    """Forget the shared GATT coordinator for an unloaded config entry."""
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return
    domain_data.get("gatt_coordinators", {}).pop(entry_id, None)
    domain_data.get("gatt_locks", {}).pop(entry_id, None)
