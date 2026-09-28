"""Config flow for Aquael BT."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    DOMAIN,
    MODEL_FLOW_HEATER,
    SERVICE_DATA_UUID,
)

CONF_DEVICE = "device"


def _supported_flow_heater(
    service_info: BluetoothServiceInfoBleak,
) -> bool:
    """Return whether an advertisement is a supported Flow Heater BT."""
    payload = service_info.service_data.get(SERVICE_DATA_UUID)
    return (
        payload is not None
        and len(payload) >= 11
        and payload[0:2] == b"AQ"
        and payload[10] == DEVICE_TYPE_FLOW_HEATER
    )


class AquaelBTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aquael BT."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle automatic Bluetooth discovery."""
        if not _supported_flow_heater(discovery_info):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": MODEL_FLOW_HEATER}
        return self.async_create_entry(
            title=discovery_info.name or MODEL_FLOW_HEATER,
            data={CONF_DEVICE: discovery_info.address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow selection from currently visible supported devices."""
        discovered = bluetooth.async_discovered_service_info(self.hass)
        devices = {
            info.address: (
                f"{info.name or MODEL_FLOW_HEATER} — {info.address}"
            )
            for info in discovered
            if _supported_flow_heater(info)
            and not self._async_in_progress_by_unique_id_match(info.address)
        }

        configured = {
            entry.unique_id
            for entry in self._async_current_entries()
            if entry.unique_id is not None
        }
        devices = {
            address: label
            for address, label in devices.items()
            if address not in configured
        }

        if user_input is not None:
            address = user_input[CONF_DEVICE]
            if address not in devices:
                return self.async_abort(reason="device_not_found")

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            info = next(
                item for item in discovered if item.address == address
            )
            return self.async_create_entry(
                title=info.name or MODEL_FLOW_HEATER,
                data={CONF_DEVICE: address},
            )

        if not devices:
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=address,
                                label=label,
                            )
                            for address, label in devices.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
