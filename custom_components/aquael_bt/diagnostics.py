"""Diagnostics support for Aquael BT."""

from __future__ import annotations

import asyncio
from typing import Any

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
    async_last_service_info,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _decode_value(value: bytes) -> dict[str, Any]:
    """Return raw and common little-endian interpretations."""
    decoded: dict[str, Any] = {
        "length": len(value),
        "hex": value.hex(),
    }
    if len(value) >= 1:
        decoded["uint8"] = value[0]
    if len(value) >= 2:
        decoded["uint16_le"] = int.from_bytes(value[:2], "little")
    if len(value) >= 4:
        decoded["uint32_le"] = int.from_bytes(value[:4], "little")
    return decoded


async def _read_gatt_snapshot(
    hass: HomeAssistant, address: str
) -> dict[str, Any]:
    """Read all readable GATT characteristics without writing anything."""
    ble_device = async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        return {
            "error": "Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar",
            "services": [],
        }

    client: BleakClient | None = None
    try:
        async with asyncio.timeout(20):
            client = await establish_connection(
                BleakClient,
                ble_device,
                address,
                max_attempts=3,
            )

        services_out: list[dict[str, Any]] = []
        for service in client.services:
            service_out: dict[str, Any] = {
                "uuid": str(service.uuid),
                "handle": service.handle,
                "characteristics": [],
            }

            for characteristic in service.characteristics:
                properties = sorted(str(prop) for prop in characteristic.properties)
                char_out: dict[str, Any] = {
                    "uuid": str(characteristic.uuid),
                    "handle": characteristic.handle,
                    "properties": properties,
                }

                if "read" in properties:
                    try:
                        async with asyncio.timeout(5):
                            raw = bytes(
                                await client.read_gatt_char(characteristic)
                            )
                        char_out["value"] = _decode_value(raw)
                    except Exception as err:
                        char_out["read_error"] = (
                            f"{type(err).__name__}: {err}"
                        )

                service_out["characteristics"].append(char_out)

            services_out.append(service_out)

        return {"services": services_out}
    except Exception as err:
        return {
            "error": f"{type(err).__name__}: {err}",
            "services": [],
        }
    finally:
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except Exception:
                pass


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for an Aquael BT config entry."""
    address = entry.unique_id
    if address is None:
        return {"error": "Config Entry hat keine Bluetooth-Adresse"}

    service_info = async_last_service_info(
        hass, address, connectable=False
    )

    advertisement: dict[str, Any] | None = None
    if service_info is not None:
        advertisement = {
            "name": service_info.name,
            "address": service_info.address,
            "rssi": service_info.rssi,
            "manufacturer_data": {
                str(key): bytes(value).hex()
                for key, value in service_info.manufacturer_data.items()
            },
            "service_data": {
                uuid: bytes(value).hex()
                for uuid, value in service_info.service_data.items()
            },
            "service_uuids": list(service_info.service_uuids),
            "source": service_info.source,
            "connectable": service_info.connectable,
            "time": getattr(service_info, "time", None),
            "tx_power": service_info.tx_power,
        }

    return {
        "entry": {
            "title": entry.title,
            "unique_id": address,
            "version": entry.version,
        },
        "last_advertisement": advertisement,
        "gatt": await _read_gatt_snapshot(hass, address),
    }
