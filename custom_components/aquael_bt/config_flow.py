"""Config flow for Aquael BT."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    DOMAIN,
    MODEL_FLOW_HEATER,
    SERVICE_DATA_UUID,
)


class AquaelBTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Aquael BT."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle Bluetooth discovery."""
        payload = discovery_info.service_data.get(SERVICE_DATA_UUID)
        if payload is None or len(payload) < 11 or payload[0:2] != b"AQ":
            return self.async_abort(reason="not_supported")

        if payload[10] != DEVICE_TYPE_FLOW_HEATER:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": MODEL_FLOW_HEATER}
        return self.async_create_entry(
            title=discovery_info.name or MODEL_FLOW_HEATER,
            data={},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Direct users to Bluetooth discovery."""
        return self.async_abort(reason="bluetooth_required")
