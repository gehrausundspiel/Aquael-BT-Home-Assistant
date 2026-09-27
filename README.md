# Aquael BT for Home Assistant

Experimental local Bluetooth integration for Aquael BT aquarium devices.

## Current status — v0.1.0

Initial development version for **Flow Heater BT**.

- Local/passive Bluetooth advertisements only
- Automatic discovery via Aquael service-data UUID `0xA0B7`
- Flow Heater identification
- Water temperature sensor
- No cloud
- No writes or device control yet
- ULTRAMAX BT support is planned

## Reverse-engineered advertisement

Observed Flow Heater BT service-data payloads indicate:

- bytes 0–1: `41 51` (`AQ`)
- bytes 4–9: device MAC
- byte 10: device type (`0x04` observed for Flow Heater BT)
- bytes 16–17: little-endian temperature in 1/100 °C (working hypothesis)

Example: `24 0A` → `0x0A24` → 2596 → **25.96 °C**.

The decoder applies sanity checks and ignores packets that do not match the expected Aquael Flow Heater format.

## Installation (development)

Copy `custom_components/aquael_bt` into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

The integration should then be discovered automatically when the Flow Heater BT is advertising. You can also add **Aquael BT** from Settings → Devices & services.

## Important

This project is reverse-engineered and is not affiliated with or endorsed by Aquael.

Device control will only be added after the protocol has been sufficiently understood and tested.
