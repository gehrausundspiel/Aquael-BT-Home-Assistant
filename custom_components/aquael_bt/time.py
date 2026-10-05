"""Time entities for Aquael BT."""

from __future__ import annotations

from datetime import time

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_ULTRAMAX, DOMAIN, MANUFACTURER, MODEL_ULTRAMAX
from .gatt import (
    AquaelGattCoordinator,
    ULTRAMAX_SUNRISE_UUID,
    ULTRAMAX_SUNSET_UUID,
)
from .parser import parse_advertisement


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ULTRAMAX time settings."""
    address = entry.unique_id
    if address is None:
        return

    service_info = async_last_service_info(hass, address, connectable=False)
    parsed = parse_advertisement(service_info) if service_info else None
    if parsed is None or parsed.device_type != DEVICE_TYPE_ULTRAMAX:
        return

    coordinator = AquaelGattCoordinator(hass, address, parsed.device_type)
    async_add_entities([
        AquaelUltramaxSunriseTime(coordinator, address),
        AquaelUltramaxSunsetTime(coordinator, address),
    ])


class AquaelUltramaxTime(CoordinatorEntity[AquaelGattCoordinator], TimeEntity):
    """Base class for ULTRAMAX time settings."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator)
        self._address = address

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={("bluetooth", self._address)},
            identifiers={(DOMAIN, self._address)},
            manufacturer=MANUFACTURER,
            model=MODEL_ULTRAMAX,
            name=MODEL_ULTRAMAX,
        )

    def _time_from_seconds(self, value: int) -> time | None:
        if not 0 <= value < 24 * 60 * 60:
            return None
        hours, remainder = divmod(value, 3600)
        minutes, seconds = divmod(remainder, 60)
        return time(hour=hours, minute=minutes, second=seconds)

    @staticmethod
    def _seconds_from_time(value: time) -> int:
        return value.hour * 3600 + value.minute * 60 + value.second


class AquaelUltramaxSunriseTime(AquaelUltramaxTime):
    """ULTRAMAX sunrise start."""

    _attr_translation_key = "sunrise"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._attr_unique_id = f"{address}_sunrise"

    @property
    def native_value(self) -> time | None:
        if not self.coordinator.data:
            return None
        return self._time_from_seconds(int(self.coordinator.data["sunrise_seconds"]))

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_write_uint32(
            ULTRAMAX_SUNRISE_UUID, self._seconds_from_time(value)
        )


class AquaelUltramaxSunsetTime(AquaelUltramaxTime):
    """ULTRAMAX sunset end."""

    _attr_translation_key = "sunset"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._attr_unique_id = f"{address}_sunset"

    @property
    def native_value(self) -> time | None:
        if not self.coordinator.data:
            return None
        return self._time_from_seconds(int(self.coordinator.data["sunset_seconds"]))

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_write_uint32(
            ULTRAMAX_SUNSET_UUID, self._seconds_from_time(value)
        )
