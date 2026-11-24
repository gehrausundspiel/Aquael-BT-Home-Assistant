"""Feeding regressions using real HA classes and a simulated GATT device."""

import asyncio
import unittest
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakCharacteristicNotFoundError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.aquael_bt import feeding, number, switch
from custom_components.aquael_bt import time as time_platform
from custom_components.aquael_bt.const import DOMAIN

ADDRESS = "AA:BB:CC:DD:EE:FF"


class FeedingDevice:
    """Represent the optional service independently of the coordinator cache."""

    def __init__(self):
        self.enabled = False
        self.slots = [False, False, True, False]
        self.times = [28800, 39600, 50400, 64800]
        self.flow = 1638
        self.writes = []
        self.reads = 0
        self.missing = False
        self.fail_writes = 0
        self.disconnect = AsyncMock()

    def payload(self):
        return (
            bytes([self.enabled, *self.slots])
            + b"".join(value.to_bytes(4, "little") for value in self.times)
            + self.flow.to_bytes(4, "little")
        )

    async def read_gatt_char(self, characteristic):
        if characteristic != feeding.FEEDING_SETTINGS_UUID:
            raise AssertionError("Feeding must not read the existing control services")
        self.reads += 1
        await asyncio.sleep(0)
        if self.missing:
            raise BleakCharacteristicNotFoundError(characteristic)
        return self.payload()

    async def write_gatt_char(self, characteristic, payload, *, response):
        await asyncio.sleep(0)
        if self.fail_writes:
            self.fail_writes -= 1
            raise OSError("Simulated Bluetooth interruption")
        if not response:
            raise AssertionError("A write must request a GATT response")
        self.writes.append((characteristic, payload))
        if characteristic == feeding.FEEDING_SLOTS_UUID:
            if len(payload) != 4 or any(value not in (0, 1) for value in payload):
                raise AssertionError("Slots require four booleans, not a bitmask")
            self.slots = list(map(bool, payload))
        elif characteristic == feeding.FEEDING_ENABLED_UUID:
            self.enabled = bool(payload[0])
        elif characteristic == feeding.FEEDING_FLOW_UUID:
            self.flow = int.from_bytes(payload, "little")
        elif characteristic in feeding.FEEDING_TIME_UUIDS:
            self.times[feeding.FEEDING_TIME_UUIDS.index(characteristic)] = (
                int.from_bytes(payload, "little")
            )
        else:
            raise AssertionError("Feeding must not write the existing control services")


class FeedingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = HomeAssistant("/private/tmp/aquael-feeding-test-config")
        # The test has no loaded config entry; production setup provides it.
        with patch("homeassistant.helpers.frame.report_usage"):
            self.coordinator = feeding.AquaelFeedingCoordinator(self.hass, ADDRESS)
        self.device = FeedingDevice()
        self.coordinator._async_connect = AsyncMock(return_value=self.device)

    async def asyncTearDown(self):
        await self.coordinator.async_shutdown()

    async def test_parallel_slot_changes_preserve_each_other_and_other_slots(self):
        self.coordinator.data = feeding.parse_ultramax_feeding(self.device.payload())
        # Simulate an additional change in the Aquael app after the cached read.
        self.device.slots[3] = True
        await asyncio.gather(
            self.coordinator.async_set_slot_enabled(1, True),
            self.coordinator.async_set_slot_enabled(2, True),
        )
        self.assertEqual(self.device.slots, [True, True, True, True])
        self.assertEqual(self.device.writes[0][1], b"\x01\x00\x01\x01")
        self.assertEqual(self.device.writes[1][1], b"\x01\x01\x01\x01")
        for slot in range(1, 5):
            self.assertTrue(self.coordinator.data[f"feeding_time_{slot}_enabled"])

    async def test_polling_during_parallel_writes_does_not_restore_old_flags(self):
        await asyncio.gather(
            self.coordinator.async_set_slot_enabled(1, True),
            self.coordinator.async_refresh(),
            self.coordinator.async_set_slot_enabled(2, True),
        )
        self.assertEqual(self.device.slots, [True, True, True, False])
        self.assertTrue(self.coordinator.data["feeding_time_1_enabled"])
        self.assertTrue(self.coordinator.data["feeding_time_2_enabled"])

    async def test_mode_time_and_low_flow_only_write_feeding_characteristics(self):
        await self.coordinator.async_set_enabled(True)
        await self.coordinator.async_set_time(3, time(14, 30))
        await self.coordinator.async_set_flow(45)
        self.assertTrue(self.device.enabled)
        self.assertEqual(self.device.times, [28800, 39600, 52200, 64800])
        self.assertEqual(self.device.flow, 1843)
        self.assertEqual(self.device.slots, [False, False, True, False])
        self.assertEqual(
            [uuid for uuid, _ in self.device.writes],
            [
                feeding.FEEDING_ENABLED_UUID,
                feeding.FEEDING_TIME_UUIDS[2],
                feeding.FEEDING_FLOW_UUID,
            ],
        )

    async def test_missing_service_leaves_only_feeding_unavailable(self):
        self.device.missing = True
        await self.coordinator.async_refresh()
        self.assertEqual(self.coordinator.data, {})
        entities = [
            feeding.AquaelFeedingSwitch(self.coordinator, ADDRESS),
            feeding.AquaelFeedingFlowNumber(self.coordinator, ADDRESS),
            feeding.AquaelFeedingTime(self.coordinator, ADDRESS, 1),
        ]
        self.assertTrue(all(not entity.available for entity in entities))
        self.device.missing = False
        await self.coordinator.async_refresh()
        self.assertTrue(all(entity.available for entity in entities))

    async def test_failed_write_keeps_device_and_cache_unchanged(self):
        before = feeding.parse_ultramax_feeding(self.device.payload())
        self.coordinator.data = dict(before)
        self.device.fail_writes = 3
        with (
            patch.object(feeding.asyncio, "sleep", new=AsyncMock()),
            self.assertRaises(UpdateFailed),
        ):
            await self.coordinator.async_set_slot_enabled(1, True)
        self.assertEqual(self.coordinator.data, before)
        self.assertEqual(self.device.slots, [False, False, True, False])
        self.assertEqual(self.device.writes, [])

    async def test_transient_write_failure_retries_the_complete_transaction(self):
        self.device.fail_writes = 1
        with patch.object(feeding.asyncio, "sleep", new=AsyncMock()):
            await self.coordinator.async_set_slot_enabled(1, True)
        self.assertEqual(self.device.reads, 2)
        self.assertEqual(self.device.slots, [True, False, True, False])
        self.assertTrue(self.coordinator.data["feeding_time_1_enabled"])

    async def test_input_validation_does_not_connect_to_device(self):
        for value in [-1, 101, float("nan"), float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.coordinator.async_set_flow(value)
        for slot in [0, 5]:
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                await self.coordinator.async_set_slot_enabled(slot, True)
        self.coordinator._async_connect.assert_not_awaited()

    async def test_entity_values_and_original_pr_unique_ids(self):
        await self.coordinator.async_refresh()
        flow = feeding.AquaelFeedingFlowNumber(self.coordinator, ADDRESS)
        slot = feeding.AquaelFeedingSwitch(self.coordinator, ADDRESS, 3)
        start = feeding.AquaelFeedingTime(self.coordinator, ADDRESS, 1)
        self.assertEqual(flow.native_value, 40)
        self.assertEqual(flow.unique_id, f"{ADDRESS}_feeding_flow")
        self.assertTrue(slot.is_on)
        self.assertEqual(slot.unique_id, f"{ADDRESS}_feeding_time_3_enabled")
        self.assertEqual(start.native_value, time(8))
        self.assertEqual(start.unique_id, f"{ADDRESS}_feeding_time_1")

    async def test_all_platforms_share_one_feeding_coordinator(self):
        entry = SimpleNamespace(
            unique_id=ADDRESS, entry_id="test-feeding", async_on_unload=MagicMock()
        )
        base = SimpleNamespace(device_type=0x07)
        modules = [number, switch, time_platform]
        callbacks = [MagicMock() for _ in modules]
        with (
            patch.object(
                number, "async_get_gatt_coordinator", AsyncMock(return_value=base)
            ),
            patch.object(
                switch, "async_get_gatt_coordinator", AsyncMock(return_value=base)
            ),
            patch.object(
                time_platform,
                "async_get_gatt_coordinator",
                AsyncMock(return_value=base),
            ),
            patch.object(
                feeding, "AquaelFeedingCoordinator", return_value=self.coordinator
            ) as factory,
        ):
            await asyncio.gather(
                *(
                    module.async_setup_entry(self.hass, entry, callback)
                    for module, callback in zip(modules, callbacks, strict=True)
                )
            )
        counts = [
            sum(len(call.args[0]) for call in callback.call_args_list)
            for callback in callbacks
        ]
        self.assertEqual(counts, [7, 7, 6])
        factory.assert_called_once()
        self.assertEqual(self.device.reads, 1)
        entry.async_on_unload.call_args.args[0]()
        self.assertEqual(self.hass.data[DOMAIN]["feeding_coordinators"], {})
        self.assertEqual(self.hass.data[DOMAIN]["feeding_locks"], {})

    async def test_flow_heater_keeps_its_existing_entities(self):
        entry = SimpleNamespace(unique_id=ADDRESS, entry_id="heater")
        base = SimpleNamespace(device_type=0x04)
        for module, expected_count in [(number, 4), (switch, 2), (time_platform, 2)]:
            with (
                self.subTest(module=module.__name__),
                patch.object(
                    module, "async_get_gatt_coordinator", AsyncMock(return_value=base)
                ),
                patch.object(feeding, "AquaelFeedingCoordinator") as factory,
            ):
                callback = MagicMock()
                await module.async_setup_entry(self.hass, entry, callback)
                self.assertEqual(len(callback.call_args.args[0]), expected_count)
                factory.assert_not_called()


class FeedingParserTests(unittest.TestCase):
    def test_realistic_block(self):
        result = feeding.parse_ultramax_feeding(FeedingDevice().payload())
        self.assertFalse(result["feeding_enabled"])
        self.assertTrue(result["feeding_time_3_enabled"])
        self.assertEqual(result["feeding_time_2_seconds"], 39600)
        self.assertAlmostEqual(result["feeding_flow_percent"], 40, places=1)

    def test_malformed_blocks(self):
        device = FeedingDevice()
        invalid_time = bytearray(device.payload())
        invalid_time[5:9] = (86400).to_bytes(4, "little")
        invalid_flow = bytearray(device.payload())
        invalid_flow[21:25] = (4097).to_bytes(4, "little")
        for payload in [b"", device.payload()[:24], invalid_time, invalid_flow]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                feeding.parse_ultramax_feeding(payload)


if __name__ == "__main__":
    unittest.main()
