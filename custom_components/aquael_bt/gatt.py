"""Active GATT access for Aquael BT devices."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from bleak import BleakClient
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

FLOW_HEATER_TARGET_UUID = "b3a10002-8df0-11ee-b9d1-0242ac120002"
FLOW_HEATER_POWER_UUID = "b3a10004-8df0-11ee-b9d1-0242ac120002"


class AquaelGattCoordinator(DataUpdateCoordinator[dict[str, float | int]]):
    """Read the actively connected settings of an Aquael device."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Aquael BT GATT {address}",
            update_interval=timedelta(minutes=1),
        )
        self.address = address

    async def _async_update_data(self) -> dict[str, float | int]:
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            if self.data:
                _LOGGER.debug("Keeping last Aquael GATT values: no connectable BLE path")
                return self.data
            raise UpdateFailed("Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar")

        try:
            async with BleakClient(ble_device, timeout=15.0) as client:
                target_raw = await client.read_gatt_char(FLOW_HEATER_TARGET_UUID)
                power_raw = await client.read_gatt_char(FLOW_HEATER_POWER_UUID)
        except Exception as err:
            if self.data:
                _LOGGER.debug("Keeping last Aquael GATT values after read failure: %s", err)
                return self.data
            raise UpdateFailed(f"Bluetooth-GATT-Lesen fehlgeschlagen: {err}") from err

        if len(target_raw) < 4 or len(power_raw) < 4:
            if self.data:
                _LOGGER.debug("Keeping last Aquael GATT values after invalid data length")
                return self.data
            raise UpdateFailed("Unerwartete GATT-Datenlänge")

        return {
            "target_temperature": int.from_bytes(target_raw[:4], "little") / 100.0,
            "heating_power_limit": int.from_bytes(power_raw[:4], "little"),
        }

    async def async_write_uint32(self, characteristic: str, value: int) -> None:
        """Write one unsigned 32-bit little-endian setting."""
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise UpdateFailed("Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar")

        payload = int(value).to_bytes(4, "little", signed=False)
        last_error: Exception | None = None
        for attempt in range(3):
            # Resolve the best connectable path again for every attempt; proxies can
            # change while the heater disconnects and starts advertising again.
            ble_device = async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                last_error = RuntimeError(
                    "Kein verbindbarer Bluetooth-Pfad zum Gerät verfügbar"
                )
            else:
                try:
                    async with BleakClient(ble_device, timeout=15.0) as client:
                        await client.write_gatt_char(
                            characteristic, payload, response=True
                        )
                    last_error = None
                    break
                except Exception as err:
                    last_error = err

            if attempt < 2:
                await asyncio.sleep(2.0)

        if last_error is not None:
            raise UpdateFailed(
                f"Bluetooth-GATT-Schreiben nach 3 Versuchen fehlgeschlagen: {last_error}"
            ) from last_error

        # Keep the UI stable while the heater disconnects/re-advertises after a write.
        if self.data:
            if characteristic == FLOW_HEATER_TARGET_UUID:
                self.async_set_updated_data({**self.data, "target_temperature": value / 100.0})
            elif characteristic == FLOW_HEATER_POWER_UUID:
                self.async_set_updated_data({**self.data, "heating_power_limit": value})
        await self.async_request_refresh()
