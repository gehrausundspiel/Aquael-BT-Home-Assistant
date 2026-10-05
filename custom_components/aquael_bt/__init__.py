"""Aquael BT integration."""

import logging

from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .parser import parse_advertisement

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.TIME,
]

type AquaelConfigEntry = ConfigEntry[PassiveBluetoothProcessorCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AquaelConfigEntry) -> bool:
    """Set up Aquael BT from a config entry."""
    address = entry.unique_id
    assert address is not None

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=parse_advertisement,
        connectable=False,
    )
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AquaelConfigEntry) -> bool:
    """Unload an Aquael BT config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
