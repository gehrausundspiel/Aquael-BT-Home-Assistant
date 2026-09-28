"""Switch entities for Aquael BT."""

from __future__ import annotations

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_ULTRAMAX, DOMAIN, MANUFACTURER, MODEL_ULTRAMAX
from .gatt import AquaelGattCoordinator, ULTRAMAX_FILTRATION_UUID
from .parser import parse_advertisement


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ULTRAMAX switches."""
    address = entry.unique_id
    if address is None:
        return

    service_info = async_last_service_info(hass, address, connectable=False)
    parsed = parse_advertisement(service_info) if service_info else None
    if parsed is None or parsed.device_type != DEVICE_TYPE_ULTRAMAX:
        return

    coordinator = AquaelGattCoordinator(hass, address, parsed.device_type)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities([AquaelUltramaxFiltrationSwitch(coordinator, address)])


class AquaelUltramaxFiltrationSwitch(CoordinatorEntity[AquaelGattCoordinator], SwitchEntity):
    """ULTRAMAX filtration switch."""

    _attr_has_entity_name = True
    _attr_translation_key = "filtration"

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{address}_filtration"

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
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data["filtration"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_FILTRATION_UUID, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_bool(ULTRAMAX_FILTRATION_UUID, False)
