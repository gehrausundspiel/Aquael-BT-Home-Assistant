"""Select entities for Aquael BT."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_ULTRAMAX, DOMAIN, MANUFACTURER, MODEL_ULTRAMAX
from .gatt import AquaelGattCoordinator, ULTRAMAX_WAVE_MODE_UUID, async_get_gatt_coordinator

WAVE_MODES: dict[str, int] = {
    "Konstant": 0,
    "Pulswelle": 1,
    "Sinuswelle": 2,
    "Modus 4": 3,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up ULTRAMAX select settings."""
    address = entry.unique_id
    if address is None:
        return

    coordinator = await async_get_gatt_coordinator(hass, entry)
    if coordinator is None or coordinator.device_type != DEVICE_TYPE_ULTRAMAX:
        return

    async_add_entities([AquaelUltramaxWaveModeSelect(coordinator, address)])


class AquaelUltramaxWaveModeSelect(
    CoordinatorEntity[AquaelGattCoordinator], SelectEntity
):
    """ULTRAMAX wave mode selector."""

    _attr_has_entity_name = True
    _attr_translation_key = "wave_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(WAVE_MODES)

    def __init__(self, coordinator: AquaelGattCoordinator, address: str) -> None:
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{address}_wave_mode"

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
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        raw = int(self.coordinator.data["wave_mode_raw"])
        return next((name for name, value in WAVE_MODES.items() if value == raw), None)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write_uint32(
            ULTRAMAX_WAVE_MODE_UUID, WAVE_MODES[option]
        )
