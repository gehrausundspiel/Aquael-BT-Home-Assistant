"""Time entities for Aquael BT."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    DEVICE_TYPE_ULTRAMAX,
    DOMAIN,
    MANUFACTURER,
    MODEL_FLOW_HEATER,
    MODEL_ULTRAMAX,
)
from .gatt import (
    AquaelGattCoordinator,
    async_get_gatt_coordinator,
    FLOW_HEATER_SUNRISE_UUID,
    FLOW_HEATER_SUNSET_UUID,
    ULTRAMAX_SUNRISE_UUID,
    ULTRAMAX_SUNSET_UUID,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Aquael time settings."""
    address = entry.unique_id
    if address is None:
        return

    coordinator = await async_get_gatt_coordinator(hass, entry)
    if coordinator is None:
        return

    if coordinator.device_type == DEVICE_TYPE_FLOW_HEATER:
        async_add_entities([
            AquaelSunriseTime(
                coordinator, address, MODEL_FLOW_HEATER, FLOW_HEATER_SUNRISE_UUID
            ),
            AquaelSunsetTime(
                coordinator, address, MODEL_FLOW_HEATER, FLOW_HEATER_SUNSET_UUID
            ),
        ])
    elif coordinator.device_type == DEVICE_TYPE_ULTRAMAX:
        async_add_entities([
            AquaelSunriseTime(
                coordinator, address, MODEL_ULTRAMAX, ULTRAMAX_SUNRISE_UUID
            ),
            AquaelSunsetTime(
                coordinator, address, MODEL_ULTRAMAX, ULTRAMAX_SUNSET_UUID
            ),
        ])


class AquaelTime(CoordinatorEntity[AquaelGattCoordinator], TimeEntity):
    """Base class for Aquael time settings."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AquaelGattCoordinator,
        address: str,
        model: str,
        characteristic: str,
    ) -> None:
        super().__init__(coordinator)
        self._address = address
        self._model = model
        self._characteristic = characteristic

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={("bluetooth", self._address)},
            identifiers={(DOMAIN, self._address)},
            manufacturer=MANUFACTURER,
            model=self._model,
            name=self._model,
        )

    @staticmethod
    def _time_from_seconds(value: int) -> time | None:
        if not 0 <= value < 24 * 60 * 60:
            return None
        hours, remainder = divmod(value, 3600)
        minutes, seconds = divmod(remainder, 60)
        return time(hour=hours, minute=minutes, second=seconds)

    @staticmethod
    def _seconds_from_time(value: time) -> int:
        return value.hour * 3600 + value.minute * 60 + value.second


class AquaelSunriseTime(AquaelTime):
    """Aquael sunrise start."""

    _attr_translation_key = "sunrise"

    def __init__(
        self,
        coordinator: AquaelGattCoordinator,
        address: str,
        model: str,
        characteristic: str,
    ) -> None:
        super().__init__(coordinator, address, model, characteristic)
        self._attr_unique_id = f"{address}_sunrise"

    @property
    def native_value(self) -> time | None:
        if not self.coordinator.data:
            return None
        return self._time_from_seconds(int(self.coordinator.data["sunrise_seconds"]))

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_write_uint32(
            self._characteristic, self._seconds_from_time(value)
        )


class AquaelSunsetTime(AquaelTime):
    """Aquael sunset end."""

    _attr_translation_key = "sunset"

    def __init__(
        self,
        coordinator: AquaelGattCoordinator,
        address: str,
        model: str,
        characteristic: str,
    ) -> None:
        super().__init__(coordinator, address, model, characteristic)
        self._attr_unique_id = f"{address}_sunset"

    @property
    def native_value(self) -> time | None:
        if not self.coordinator.data:
            return None
        return self._time_from_seconds(int(self.coordinator.data["sunset_seconds"]))

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_write_uint32(
            self._characteristic, self._seconds_from_time(value)
        )
