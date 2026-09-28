"""Aquael BT integration."""

import logging

from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .parser import parse_advertisement

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

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

    # Remove duplicate legacy devices created by v0.1.5. The entities will be
    # re-associated with the canonical Bluetooth device on platform setup.
    device_registry = dr.async_get(hass)
    matching_devices = [
        device
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if (DOMAIN, address) in device.identifiers
        or ("bluetooth", address) in device.connections
    ]
    if len(matching_devices) > 1:
        canonical = next(
            (
                device
                for device in matching_devices
                if ("bluetooth", address) in device.connections
            ),
            matching_devices[0],
        )
        for device in matching_devices:
            if device.id != canonical.id:
                device_registry.async_remove_device(device.id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AquaelConfigEntry) -> bool:
    """Unload an Aquael BT config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
