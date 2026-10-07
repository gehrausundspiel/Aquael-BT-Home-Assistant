"""Switch entities for Aquael BT."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    FLOW_HEATER_DAY_NIGHT_MODE_UUID,
    FLOW_HEATER_HEATING_UUID,
    ULTRAMAX_DAY_NIGHT_MODE_UUID,
    ULTRAMAX_FILTRATION_UUID,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Aquael switches."""
    address = entry.unique_id
    if address is None:
        return

    coordinator = await async_get_gatt_coordinator(hass, entry)
    if coordinator is None:
        return

    if coordinator.device_type == DEVICE_TYPE_FLOW_HEATER:
        async_add_entities([
            AquaelFlowHeaterHeatingSwitch(coordinator, address),
            AquaelFlowHeaterDayNightModeSwitch(coordinator, address),
        ])
    elif coordinator.device_type == DEVICE_TYPE_ULTRAMAX:
        async_add_entities([
            AquaelUltramaxFiltrationSwitch(coordinator, address),
            AquaelUltramaxDayNightModeSwitch(coordinator, address),
        ])


class AquaelSwitch(CoordinatorEntity[AquaelGattCoordinator], SwitchEntity):
    """Base class for Aquael switches."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AquaelGattCoordinator,
        address: str,
        model: str,
    ) -> None:
        super().__init__(coordinator)
        self._address = address
        self._model = model

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={("bluetooth", self._address)},
            identifiers={(DOMAIN, self._address)},
            manufacturer=MANUFACTURER,
            model=self._model,
            name=self._model,
        )


class AquaelFlowHeaterHeatingSwitch(AquaelSwitch):
    _attr_translation_key = "heating"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_FLOW_HEATER)
        self._attr_unique_id = f"{address}_heating"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data["heating"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(FLOW_HEATER_HEATING_UUID, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(FLOW_HEATER_HEATING_UUID, False)


class AquaelFlowHeaterDayNightModeSwitch(AquaelSwitch):
    _attr_translation_key = "day_night_mode"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_FLOW_HEATER)
        self._attr_unique_id = f"{address}_day_night_mode"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data["day_night_mode"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(FLOW_HEATER_DAY_NIGHT_MODE_UUID, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(FLOW_HEATER_DAY_NIGHT_MODE_UUID, False)


class AquaelUltramaxFiltrationSwitch(AquaelSwitch):
    """ULTRAMAX filtration switch."""

    _attr_translation_key = "filtration"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_filtration"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data["filtration"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_FILTRATION_UUID, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_FILTRATION_UUID, False)


class AquaelUltramaxDayNightModeSwitch(AquaelSwitch):
    """ULTRAMAX Day & Night mode switch."""

    _attr_translation_key = "day_night_mode"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_day_night_mode"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data["day_night_mode"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_DAY_NIGHT_MODE_UUID, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_DAY_NIGHT_MODE_UUID, False)
