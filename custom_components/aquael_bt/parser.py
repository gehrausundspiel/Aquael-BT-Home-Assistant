"""Decode Aquael BT Bluetooth advertisements."""

from dataclasses import dataclass

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    DEVICE_TYPE_FLOW_HEATER,
    DEVICE_TYPE_ULTRAMAX,
    MIN_PAYLOAD_LENGTH,
    MODEL_FLOW_HEATER,
    MODEL_ULTRAMAX,
    SERVICE_DATA_UUID,
)


@dataclass(frozen=True, slots=True)
class AquaelAdvertisement:
    """Decoded Aquael advertisement."""

    address: str
    device_type: int
    model: str
    temperature: float | None = None
    rssi: int | None = None


def parse_advertisement(
    service_info: BluetoothServiceInfoBleak,
) -> AquaelAdvertisement | None:
    """Parse a supported Aquael service-data advertisement."""
    payload = service_info.service_data.get(SERVICE_DATA_UUID)
    if payload is None or len(payload) < MIN_PAYLOAD_LENGTH:
        return None
    if payload[0:2] != b"AQ":
        return None

    device_type = payload[10]
    if device_type == DEVICE_TYPE_FLOW_HEATER:
        model = MODEL_FLOW_HEATER
        raw_temperature = int.from_bytes(payload[16:18], "little")
        temperature = raw_temperature / 100.0
        if not 0.0 <= temperature <= 50.0:
            temperature = None
    elif device_type == DEVICE_TYPE_ULTRAMAX:
        model = MODEL_ULTRAMAX
        temperature = None
    else:
        return None

    return AquaelAdvertisement(
        address=service_info.address,
        device_type=device_type,
        model=model,
        temperature=temperature,
        rssi=service_info.rssi,
    )
