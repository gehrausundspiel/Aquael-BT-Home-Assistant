"""Number entities for Aquael BT."""

from __future__ import annotations

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
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
    FLOW_HEATER_POWER_UUID,
    FLOW_HEATER_TARGET_UUID,
    ULTRAMAX_DAY_FLOW_UUID,
    ULTRAMAX_DAY_MIN_FLOW_UUID,
    ULTRAMAX_FLOW_SCALE,
    ULTRAMAX_NIGHT_FLOW_UUID,
    ULTRAMAX_NIGHT_MIN_FLOW_UUID,
    ULTRAMAX_TRANSITION_UUID,
    ULTRAMAX_WAVE_PERIOD_UUID,
)
from .parser import parse_advertisement


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up writable Aquael settings."""
    address = entry.unique_id
    if address is None:
        return

    service_info = async_last_service_info(hass, address, connectable=False)
    parsed = parse_advertisement(service_info) if service_info else None
    if parsed is None:
        return

    coordinator = AquaelGattCoordinator(hass, address, parsed.device_type)

    if parsed.device_type == DEVICE_TYPE_FLOW_HEATER:
        await coordinator.async_config_entry_first_refresh()

    if parsed.device_type == DEVICE_TYPE_FLOW_HEATER:
        async_add_entities([
            AquaelTargetTemperatureNumber(coordinator, address),
            AquaelHeatingPowerNumber(coordinator, address),
        ])
    elif parsed.device_type == DEVICE_TYPE_ULTRAMAX:
        async_add_entities([
            AquaelUltramaxDayFlowNumber(coordinator, address),
            AquaelUltramaxDayMinFlowNumber(coordinator, address),
            AquaelUltramaxNightFlowNumber(coordinator, address),
            AquaelUltramaxNightMinFlowNumber(coordinator, address),
            AquaelUltramaxWavePeriodNumber(coordinator, address),
            AquaelUltramaxTransitionTimeNumber(coordinator, address),
        ])


class AquaelNumberEntity(CoordinatorEntity[AquaelGattCoordinator], NumberEntity):
    """Base class for Aquael settings."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AquaelGattCoordinator, address: str, model: str) -> None:
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


class AquaelTargetTemperatureNumber(AquaelNumberEntity):
    _attr_translation_key = "target_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 18.0
    _attr_native_max_value = 32.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_FLOW_HEATER)
        self._attr_unique_id = f"{address}_target_temperature"

    @property
    def native_value(self) -> float | None:
        return float(self.coordinator.data["target_temperature"]) if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_uint32(FLOW_HEATER_TARGET_UUID, round(value * 100))


class AquaelHeatingPowerNumber(AquaelNumberEntity):
    _attr_translation_key = "heating_power"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 50
    _attr_native_max_value = 500
    _attr_native_step = 50
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_FLOW_HEATER)
        self._attr_unique_id = f"{address}_heating_power"

    @property
    def native_value(self) -> float | None:
        return float(self.coordinator.data["heating_power_limit"]) if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_uint32(FLOW_HEATER_POWER_UUID, round(value))


class AquaelUltramaxFlowBase(AquaelNumberEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    data_key: str
    characteristic: str

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return round(float(self.coordinator.data[self.data_key]))

    async def async_set_native_value(self, value: float) -> None:
        raw = round(value * ULTRAMAX_FLOW_SCALE / 100)
        await self.coordinator.async_write_uint32(self.characteristic, raw)


class AquaelUltramaxDayFlowNumber(AquaelUltramaxFlowBase):
    _attr_translation_key = "day_flow"
    data_key = "day_flow_percent"
    characteristic = ULTRAMAX_DAY_FLOW_UUID

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_flow"


class AquaelUltramaxDayMinFlowNumber(AquaelUltramaxFlowBase):
    _attr_translation_key = "day_min_flow"
    data_key = "day_min_flow_percent"
    characteristic = ULTRAMAX_DAY_MIN_FLOW_UUID

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_day_min_flow"


class AquaelUltramaxNightFlowNumber(AquaelUltramaxFlowBase):
    _attr_translation_key = "night_flow"
    data_key = "night_flow_percent"
    characteristic = ULTRAMAX_NIGHT_FLOW_UUID

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_night_flow"


class AquaelUltramaxNightMinFlowNumber(AquaelUltramaxFlowBase):
    _attr_translation_key = "night_min_flow"
    data_key = "night_min_flow_percent"
    characteristic = ULTRAMAX_NIGHT_MIN_FLOW_UUID

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_night_min_flow"


class AquaelUltramaxWavePeriodNumber(AquaelNumberEntity):
    _attr_translation_key = "wave_period"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_wave_period"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return float(self.coordinator.data["wave_period_seconds"])

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_uint32(
            ULTRAMAX_WAVE_PERIOD_UUID, round(value)
        )


class AquaelUltramaxTransitionTimeNumber(AquaelNumberEntity):
    _attr_translation_key = "transition_time"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_transition_time"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return round(float(self.coordinator.data["transition_seconds"]) / 60.0)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_uint32(
            ULTRAMAX_TRANSITION_UUID, round(value * 60)
        )
