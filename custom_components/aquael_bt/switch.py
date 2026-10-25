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
    ULTRAMAX_FEEDING_ENABLED_UUID,
    ULTRAMAX_FEEDING_SLOT_COUNT,
    ULTRAMAX_FEEDING_SLOTS_UUID,
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
            AquaelUltramaxFishFeedingSwitch(coordinator, address),
            *(
                AquaelUltramaxFeedingTimeSwitch(coordinator, address, slot)
                for slot in range(1, ULTRAMAX_FEEDING_SLOT_COUNT + 1)
            ),
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


class AquaelUltramaxFishFeedingSwitch(AquaelSwitch):
    """ULTRAMAX Fish feeding mode switch."""

    _attr_translation_key = "fish_feeding"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._attr_unique_id = f"{address}_fish_feeding"

    @property
    def available(self) -> bool:
        return super().available and "feeding_enabled" in (self.coordinator.data or {})

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or "feeding_enabled" not in self.coordinator.data:
            return None
        return bool(self.coordinator.data["feeding_enabled"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_FEEDING_ENABLED_UUID, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_FEEDING_ENABLED_UUID, False)


class AquaelUltramaxFeedingTimeSwitch(AquaelSwitch):
    """Enable or disable one of the four ULTRAMAX feeding times.

    19b30002 holds one byte per feeding time (01 = enabled), e.g.
    ``01 01 00 00`` for times 1 and 2. All four bytes are written at once.
    """

    _attr_translation_key = "feeding_time_enabled"

    def __init__(
        self, coordinator: AquaelGattCoordinator, address: str, slot: int
    ) -> None:
        super().__init__(coordinator, address, MODEL_ULTRAMAX)
        self._slot = slot
        self._data_key = f"feeding_time_{slot}_enabled"
        self._attr_unique_id = f"{address}_feeding_time_{slot}_enabled"
        self._attr_translation_placeholders = {"slot": str(slot)}

    @property
    def available(self) -> bool:
        return super().available and self._data_key in (self.coordinator.data or {})

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or self._data_key not in self.coordinator.data:
            return None
        return bool(self.coordinator.data[self._data_key])

    async def _async_set(self, enabled: bool) -> None:
        data = self.coordinator.data or {}
        payload = bytes(
            1 if (enabled if slot == self._slot else data.get(f"feeding_time_{slot}_enabled"))
            else 0
            for slot in range(1, ULTRAMAX_FEEDING_SLOT_COUNT + 1)
        )
        await self.coordinator.async_write(ULTRAMAX_FEEDING_SLOTS_UUID, payload)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(False)
