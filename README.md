# Aquael BT for Home Assistant

Experimental local Bluetooth integration for Aquael BT aquarium devices.

## Current status — v0.1.1

Initial development version for **Flow Heater BT**.

- Local/passive Bluetooth advertisements only
- Automatic discovery via Aquael service-data UUID `0xA0B7`
- Manual setup with a dropdown of currently visible supported Aquael BT devices
- No hard-coded device MAC address
- Flow Heater identification from the advertisement protocol
- Water temperature sensor
- No cloud
- No writes or device control yet
- ULTRAMAX BT support is planned

## Device setup

Home Assistant can add a supported device in two ways:

1. Automatic Bluetooth discovery.
2. Settings → Devices & services → Add integration → **Aquael BT**, then select a currently visible supported device from the dropdown.

The Bluetooth address is used only as the unique ID for the selected physical device. It is not hard-coded into the integration.

## Reverse-engineered advertisement

Observed Flow Heater BT service-data payloads indicate:

- bytes 0–1: `41 51` (`AQ`)
- bytes 4–9: device MAC
- byte 10: device type (`0x04` observed for Flow Heater BT)
- bytes 16–17: little-endian temperature in 1/100 °C (working hypothesis)

Example: `24 0A` → `0x0A24` → 2596 → **25.96 °C**.

The decoder applies sanity checks and ignores packets that do not match the expected Aquael Flow Heater format.

## Installation (development)

Install the repository as a custom HACS integration and restart Home Assistant.

## Important

This project is reverse-engineered and is not affiliated with or endorsed by Aquael.

Device control will only be added after the protocol has been sufficiently understood and tested.
