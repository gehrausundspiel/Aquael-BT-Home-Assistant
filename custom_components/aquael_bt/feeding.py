"""Optional ULTRAMAX feeding controls, isolated from the existing settings."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from datetime import time

from bleak import BleakClient
from bleak.exc import BleakCharacteristicNotFoundError
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed

from .const import DEVICE_TYPE_ULTRAMAX, DOMAIN, MANUFACTURER, MODEL_ULTRAMAX
from .gatt import ULTRAMAX_FLOW_SCALE, AquaelGattCoordinator

FEEDING_ENABLED_UUID = "19b30001-98b5-11ed-a8fc-0242ac120002"
FEEDING_SLOTS_UUID = "19b30002-98b5-11ed-a8fc-0242ac120002"
FEEDING_TIME_UUIDS = tuple(
    f"19b3000{index}-98b5-11ed-a8fc-0242ac120002" for index in range(3, 7)
)
FEEDING_FLOW_UUID = "19b30007-98b5-11ed-a8fc-0242ac120002"
FEEDING_SETTINGS_UUID = "19b300ee-98b5-11ed-a8fc-0242ac120002"
FEEDING_SLOT_COUNT = 4

type FeedingData = dict[str, float | int | bool]


def parse_ultramax_feeding(raw: bytes) -> FeedingData:
    """Decode the feeding block described in docs/ULTRAMAX_PROTOCOL.md."""
    if len(raw) < 25:
        raise ValueError("Unexpected ULTRAMAX feeding GATT data length")
    result: FeedingData = {"feeding_enabled": raw[0] != 0}
    for index in range(FEEDING_SLOT_COUNT):
        result[f"feeding_time_{index + 1}_enabled"] = raw[1 + index] != 0
        start = 5 + index * 4
        seconds = int.from_bytes(raw[start : start + 4], "little")
        if not 0 <= seconds < 86400:
            raise ValueError("Invalid ULTRAMAX feeding time")
        result[f"feeding_time_{index + 1}_seconds"] = seconds
    flow = int.from_bytes(raw[21:25], "little")
    if flow > ULTRAMAX_FLOW_SCALE:
        raise ValueError("Invalid ULTRAMAX feeding flow")
    result["feeding_flow_raw"] = flow
    result["feeding_flow_percent"] = flow * 100.0 / ULTRAMAX_FLOW_SCALE
    return result


class AquaelFeedingCoordinator(AquaelGattCoordinator):
    """Poll only the optional feeding service and serialize feeding writes.

    This is a separate instance: normal filter/heater data and their polling
    remain untouched. Only the existing Bluetooth connection helper is reused.
    """

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(hass, address, DEVICE_TYPE_ULTRAMAX)
        self.name = f"Aquael BT feeding {address}"
        self._io_lock = asyncio.Lock()

    async def _async_read(self, client: BleakClient) -> FeedingData:
        return parse_ultramax_feeding(
            bytes(await client.read_gatt_char(FEEDING_SETTINGS_UUID))
        )

    async def _async_update_data(self) -> FeedingData:
        async with self._io_lock:
            try:
                client = await self._async_connect()
                try:
                    return await self._async_read(client)
                finally:
                    await client.disconnect()
            except BleakCharacteristicNotFoundError:
                # Older firmware can lack this optional service. Its absence
                # must not affect the normal filter controls.
                return {}
            except Exception as err:
                raise UpdateFailed(f"Unable to read ULTRAMAX feeding: {err}") from err

    async def _async_set(
        self,
        characteristic: str,
        key: str,
        value: float | int | bool,
        payload: Callable[[FeedingData], bytes],
    ) -> None:
        # Hold one lock for reading the device, building the complete payload,
        # writing it, and updating the cache. Locking only the write is too late.
        async with self._io_lock:
            for attempt in range(3):
                try:
                    client = await self._async_connect()
                    try:
                        # Always use fresh device data, including changes made
                        # in the Aquael app since our last periodic update.
                        data = await self._async_read(client)
                        await client.write_gatt_char(
                            characteristic, payload(data), response=True
                        )
                    finally:
                        await client.disconnect()
                    data[key] = value
                    if key == "feeding_flow_raw":
                        data["feeding_flow_percent"] = (
                            int(value) * 100.0 / ULTRAMAX_FLOW_SCALE
                        )
                    self.async_set_updated_data(data)
                    return
                except Exception as err:
                    if attempt == 2:
                        raise UpdateFailed(
                            f"Unable to write ULTRAMAX feeding after 3 attempts: {err}"
                        ) from err
                    await asyncio.sleep(2)

    async def async_set_enabled(self, enabled: bool) -> None:
        await self._async_set(
            FEEDING_ENABLED_UUID,
            "feeding_enabled",
            enabled,
            lambda _: b"\x01" if enabled else b"\x00",
        )

    async def async_set_slot_enabled(self, slot: int, enabled: bool) -> None:
        if not 1 <= slot <= FEEDING_SLOT_COUNT:
            raise ValueError("Feeding slot must be between 1 and 4")
        await self._async_set(
            FEEDING_SLOTS_UUID,
            f"feeding_time_{slot}_enabled",
            enabled,
            lambda data: bytes(
                int(enabled if index == slot else data[f"feeding_time_{index}_enabled"])
                for index in range(1, FEEDING_SLOT_COUNT + 1)
            ),
        )

    async def async_set_time(self, slot: int, value: time) -> None:
        if not 1 <= slot <= FEEDING_SLOT_COUNT:
            raise ValueError("Feeding slot must be between 1 and 4")
        seconds = value.hour * 3600 + value.minute * 60 + value.second
        await self._async_set(
            FEEDING_TIME_UUIDS[slot - 1],
            f"feeding_time_{slot}_seconds",
            seconds,
            lambda _: seconds.to_bytes(4, "little"),
        )

    async def async_set_flow(self, value: float) -> None:
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Feeding flow must be between 0 and 100 percent")
        raw = round(value * ULTRAMAX_FLOW_SCALE / 100)
        await self._async_set(
            FEEDING_FLOW_UUID,
            "feeding_flow_raw",
            raw,
            lambda _: raw.to_bytes(4, "little"),
        )


async def async_get_feeding_coordinator(
    hass: HomeAssistant, entry: ConfigEntry
) -> AquaelFeedingCoordinator:
    """Share one independent feeding coordinator across its three platforms."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    coordinators = domain_data.setdefault("feeding_coordinators", {})
    locks = domain_data.setdefault("feeding_locks", {})
    if entry.entry_id in coordinators:
        return coordinators[entry.entry_id]
    async with locks.setdefault(entry.entry_id, asyncio.Lock()):
        if entry.entry_id in coordinators:
            return coordinators[entry.entry_id]
        assert entry.unique_id is not None
        coordinator = AquaelFeedingCoordinator(hass, entry.unique_id)

        def cleanup() -> None:
            coordinators.pop(entry.entry_id, None)
            locks.pop(entry.entry_id, None)

        entry.async_on_unload(cleanup)
        await coordinator.async_refresh()
        coordinators[entry.entry_id] = coordinator
        return coordinator


class AquaelFeedingEntity(CoordinatorEntity[AquaelFeedingCoordinator]):
    """Common identity and availability for additional feeding entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AquaelFeedingCoordinator, address: str) -> None:
        super().__init__(coordinator)
        self._address = address
        self._data_key = ""

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={("bluetooth", self._address)},
            identifiers={(DOMAIN, self._address)},
            manufacturer=MANUFACTURER,
            model=MODEL_ULTRAMAX,
            name=MODEL_ULTRAMAX,
        )

    @property
    def available(self) -> bool:
        return super().available and self._data_key in (self.coordinator.data or {})


class AquaelFeedingSwitch(AquaelFeedingEntity, SwitchEntity):
    """Enable feeding mode or one of its four time slots."""

    def __init__(
        self,
        coordinator: AquaelFeedingCoordinator,
        address: str,
        slot: int | None = None,
    ) -> None:
        super().__init__(coordinator, address)
        self._slot = slot
        if slot is None:
            self._data_key = "feeding_enabled"
            self._attr_translation_key = "fish_feeding"
            self._attr_unique_id = f"{address}_fish_feeding"
        else:
            self._data_key = f"feeding_time_{slot}_enabled"
            self._attr_translation_key = "feeding_time_enabled"
            self._attr_translation_placeholders = {"slot": str(slot)}
            self._attr_unique_id = f"{address}_feeding_time_{slot}_enabled"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        return bool(data[self._data_key]) if self._data_key in data else None

    async def _async_set(self, enabled: bool) -> None:
        if self._slot is None:
            await self.coordinator.async_set_enabled(enabled)
        else:
            await self.coordinator.async_set_slot_enabled(self._slot, enabled)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(False)


class AquaelFeedingFlowNumber(AquaelFeedingEntity, NumberEntity):
    """Filter flow during feeding, including values below the normal minimum."""

    _attr_translation_key = "feeding_flow"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AquaelFeedingCoordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._data_key = "feeding_flow_percent"
        self._attr_unique_id = f"{address}_feeding_flow"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        return round(float(data[self._data_key])) if self._data_key in data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_flow(value)


class AquaelFeedingTime(AquaelFeedingEntity, TimeEntity):
    """One of the four feeding start times."""

    _attr_translation_key = "feeding_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: AquaelFeedingCoordinator, address: str, slot: int
    ) -> None:
        super().__init__(coordinator, address)
        self._slot = slot
        self._data_key = f"feeding_time_{slot}_seconds"
        self._attr_translation_placeholders = {"slot": str(slot)}
        self._attr_unique_id = f"{address}_feeding_time_{slot}"

    @property
    def native_value(self) -> time | None:
        data = self.coordinator.data or {}
        if self._data_key not in data:
            return None
        seconds = int(data[self._data_key])
        return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_time(self._slot, value)


async def async_get_feeding_numbers(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[AquaelFeedingFlowNumber]:
    coordinator = await async_get_feeding_coordinator(hass, entry)
    assert entry.unique_id is not None
    return [AquaelFeedingFlowNumber(coordinator, entry.unique_id)]


async def async_get_feeding_switches(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[AquaelFeedingSwitch]:
    coordinator = await async_get_feeding_coordinator(hass, entry)
    assert entry.unique_id is not None
    return [
        AquaelFeedingSwitch(coordinator, entry.unique_id),
        *(
            AquaelFeedingSwitch(coordinator, entry.unique_id, slot)
            for slot in range(1, FEEDING_SLOT_COUNT + 1)
        ),
    ]


async def async_get_feeding_times(
    hass: HomeAssistant, entry: ConfigEntry
) -> list[AquaelFeedingTime]:
    coordinator = await async_get_feeding_coordinator(hass, entry)
    assert entry.unique_id is not None
    return [
        AquaelFeedingTime(coordinator, entry.unique_id, slot)
        for slot in range(1, FEEDING_SLOT_COUNT + 1)
    ]
