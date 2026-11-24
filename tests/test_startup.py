"""Regression tests for delayed Bluetooth discovery during startup.

Run with Python 3.14 and the dependencies in requirements-test.txt:
    python -m unittest discover -s tests -v
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.aquael_bt import async_setup_entry
from custom_components.aquael_bt.const import SERVICE_DATA_UUID
from custom_components.aquael_bt.gatt import async_get_gatt_coordinator

INTEGRATION = "custom_components.aquael_bt"
ADDRESS = "AA:BB:CC:DD:EE:FF"


def advertisement(device_type=0x07, payload=None):
    """Build a supported advertisement without connecting to hardware."""
    if payload is None:
        data = bytearray(18)
        data[:2] = b"AQ"
        data[10] = device_type
        payload = bytes(data)
    return SimpleNamespace(
        address=ADDRESS,
        service_data={SERVICE_DATA_UUID: payload},
        rssi=-60,
    )


class StartupTests(unittest.IsolatedAsyncioTestCase):
    """Exercise setup retries and concurrent platform initialization."""

    def setUp(self):
        self.hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()),
        )
        self.entry = SimpleNamespace(
            unique_id=ADDRESS,
            entry_id="test-aquael",
            async_on_unload=MagicMock(),
        )

    async def test_delayed_advertisement_retries_before_loading_platforms(self):
        """A proxy starting late must not leave an entry with missing entities."""
        with (
            patch(
                f"{INTEGRATION}.async_last_service_info", return_value=None, create=True
            ),
            patch(f"{INTEGRATION}.PassiveBluetoothProcessorCoordinator") as factory,
        ):
            with self.assertRaises(ConfigEntryNotReady):
                await async_setup_entry(self.hass, self.entry)

            self.hass.config_entries.async_forward_entry_setups.assert_not_awaited()
            self.entry.async_on_unload.assert_not_called()
            factory.assert_not_called()

        # Home Assistant retries the entry once an advertisement has arrived.
        with (
            patch(
                f"{INTEGRATION}.async_last_service_info",
                return_value=advertisement(),
                create=True,
            ),
            patch(f"{INTEGRATION}.PassiveBluetoothProcessorCoordinator") as factory,
        ):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
            self.assertIs(self.entry.runtime_data, factory.return_value)
            self.hass.config_entries.async_forward_entry_setups.assert_awaited_once()
            factory.return_value.async_start.assert_called_once()

    async def test_invalid_advertisement_also_retries(self):
        """A truncated or unsupported packet is not enough for platform setup."""
        for info in (
            advertisement(payload=b"AQ"),
            advertisement(device_type=0xFF),
            advertisement(payload=b"XX" + bytes(16)),
        ):
            with (
                self.subTest(info=info),
                patch(
                    f"{INTEGRATION}.async_last_service_info",
                    return_value=info,
                    create=True,
                ),
                patch(f"{INTEGRATION}.PassiveBluetoothProcessorCoordinator"),
                self.assertRaises(ConfigEntryNotReady),
            ):
                await async_setup_entry(self.hass, self.entry)
        self.hass.config_entries.async_forward_entry_setups.assert_not_awaited()

    async def test_flow_heater_still_starts(self):
        """The shared setup change must also accept a Flow Heater advertisement."""
        with (
            patch(
                f"{INTEGRATION}.async_last_service_info",
                return_value=advertisement(device_type=0x04),
                create=True,
            ),
            patch(f"{INTEGRATION}.PassiveBluetoothProcessorCoordinator"),
        ):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
        self.hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    async def test_parallel_platforms_wait_for_initial_read(self):
        """All platforms receive the same coordinator after its initial read."""
        reading = asyncio.Event()
        finish_read = asyncio.Event()
        second_started = asyncio.Event()
        coordinator = SimpleNamespace(data=None)

        async def refresh():
            reading.set()
            await finish_read.wait()
            coordinator.data = {"filtration": True}

        coordinator.async_refresh = AsyncMock(side_effect=refresh)

        async def get_second():
            second_started.set()
            return await async_get_gatt_coordinator(self.hass, self.entry)

        with (
            patch(
                f"{INTEGRATION}.gatt.async_last_service_info",
                return_value=advertisement(),
            ),
            patch(
                f"{INTEGRATION}.gatt.AquaelGattCoordinator",
                return_value=coordinator,
            ) as factory,
        ):
            first = asyncio.create_task(
                async_get_gatt_coordinator(self.hass, self.entry)
            )
            await asyncio.wait_for(reading.wait(), timeout=1)
            second = asyncio.create_task(get_second())
            try:
                await asyncio.wait_for(second_started.wait(), timeout=1)
                self.assertFalse(second.done(), "Coordinator escaped before its read")
            finally:
                finish_read.set()
                results = await asyncio.wait_for(
                    asyncio.gather(first, second), timeout=1
                )

            self.assertIs(results[0], coordinator)
            self.assertIs(results[1], coordinator)
            self.assertEqual(results[1].data, {"filtration": True})
            factory.assert_called_once()
            coordinator.async_refresh.assert_awaited_once()

    async def test_failed_initial_read_keeps_coordinator_for_polling(self):
        """A temporary GATT failure must not prevent later periodic recovery."""
        coordinator = SimpleNamespace(data=None, async_refresh=AsyncMock())
        with (
            patch(
                f"{INTEGRATION}.gatt.async_last_service_info",
                return_value=advertisement(),
            ),
            patch(
                f"{INTEGRATION}.gatt.AquaelGattCoordinator",
                return_value=coordinator,
            ) as factory,
        ):
            result = await async_get_gatt_coordinator(self.hass, self.entry)
            again = await async_get_gatt_coordinator(self.hass, self.entry)
        self.assertIs(result, coordinator)
        self.assertIs(again, coordinator)
        factory.assert_called_once()
        coordinator.async_refresh.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
