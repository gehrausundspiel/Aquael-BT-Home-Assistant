"""Config flow for Aquael BT."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    DOMAIN,
    MODEL_FLOW_HEATER,
    SERVICE_DATA_UUID,
)


def _supported_flow_heater(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return whether an advertisement is a supported Flow Heater BT."""
    payload = service_info.service_data.get(SERVICE_DATA_UUID)
    return (
        payload is not None
        and len(payload) >= 11
        and payload[0:2] == b"AQ"
        and payload[10] == DEVICE_TYPE_FLOW_HEATER
    )


def _title(service_info: BluetoothServiceInfoBleak) -> str:
    """Return a useful device title."""
    return f"{service_info.name or MODEL_FLOW_HEATER} — {service_info.address}"


class AquaelBTConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aquael BT."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery."""
        if not _supported_flow_heater(discovery_info):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return self.async_create_entry(
            title=discovery_info.name or MODEL_FLOW_HEATER,
            data={CONF_ADDRESS: discovery_info.address},
        )

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup by selecting a discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            discovery_info = self._discovered_devices.get(address)
            if discovery_info is None:
                return self.async_abort(reason="device_not_found")

            return self.async_create_entry(
                title=discovery_info.name or MODEL_FLOW_HEATER,
                data={CONF_ADDRESS: address},
            )

        current_addresses = self._async_current_ids(include_ignore=False)

        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if _supported_flow_heater(discovery_info):
                self._discovered_devices[address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        devices = {
            address: _title(discovery_info)
            for address, discovery_info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(devices)}),
        )
