"""Number entities for Aquael BT."""

from __future__ import annotations

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_FLOW_HEATER, DOMAIN, MANUFACTURER, MODEL_FLOW_HEATER
from .gatt import (
    AquaelGattCoordinator,
    FLOW_HEATER_POWER_UUID,
    FLOW_HEATER_TARGET_UUID,
)
from .parser import parse_advertisement


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable Flow Heater settings."""
    address = entry.unique_id
    if address is None:
        return

    service_info = async_last_service_info(hass, address, connectable=False)
    parsed = parse_advertisement(service_info) if service_info else None
    if parsed is None or parsed.device_type != DEVICE_TYPE_FLOW_HEATER:
        return

    coordinator = AquaelGattCoordinator(hass, address)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        [
            AquaelTargetTemperatureNumber(coordinator, address),
            AquaelHeatingPowerNumber(coordinator, address),
        ]
    )


class AquaelNumberEntity(CoordinatorEntity[AquaelGattCoordinator], NumberEntity):
    """Base class for Flow Heater settings."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator)
        self._address = address

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            manufacturer=MANUFACTURER,
            model=MODEL_FLOW_HEATER,
            name=MODEL_FLOW_HEATER,
        )


class AquaelTargetTemperatureNumber(AquaelNumberEntity):
    """Configured target water temperature."""

    _attr_translation_key = "target_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 18.0
    _attr_native_max_value = 32.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._attr_unique_id = f"{address}_target_temperature"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return float(self.coordinator.data["target_temperature"])

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_uint32(
            FLOW_HEATER_TARGET_UUID, round(value * 100)
        )


class AquaelHeatingPowerNumber(AquaelNumberEntity):
    """Configured maximum heater power."""

    _attr_translation_key = "heating_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 50
    _attr_native_max_value = 500
    _attr_native_step = 50
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address)
        self._attr_unique_id = f"{address}_heating_power"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return float(self.coordinator.data["heating_power_limit"])

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_uint32(
            FLOW_HEATER_POWER_UUID, round(value)
        )
