"""Decode Aquael BT Bluetooth advertisements."""

from dataclasses import dataclass

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    FLOW_HEATER_MIN_PAYLOAD_LENGTH,
    SERVICE_DATA_UUID,
)


@dataclass(frozen=True, slots=True)
class AquaelAdvertisement:
    """Decoded Aquael advertisement."""

    device_type: int
    temperature: float | None


def parse_advertisement(
    service_info: BluetoothServiceInfoBleak,
) -> AquaelAdvertisement | None:
    """Parse a supported Aquael service-data advertisement."""
    payload = service_info.service_data.get(SERVICE_DATA_UUID)
    if payload is None or len(payload) < FLOW_HEATER_MIN_PAYLOAD_LENGTH:
        return None

    # All packets observed so far start with ASCII "AQ".
    if payload[0:2] != b"AQ":
        return None

    device_type = payload[10]
    if device_type != DEVICE_TYPE_FLOW_HEATER:
        return None

    # Reverse-engineered working hypothesis:
    # bytes 16..17 are little-endian hundredths of a degree Celsius.
    raw_temperature = int.from_bytes(payload[16:18], "little")
    temperature = raw_temperature / 100.0

    # Reject implausible values while the protocol is still being validated.
    if not 0.0 <= temperature <= 50.0:
        temperature = None

    return AquaelAdvertisement(
        device_type=device_type,
        temperature=temperature,
    )
