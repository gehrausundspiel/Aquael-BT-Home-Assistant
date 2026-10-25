# ULTRAMAX BT – GATT protocol notes

Observed on an **ULTRAMAX 2000** (firmware 1.7.0, hardware 1.2.0, software 2.18.0)
and verified by changing settings in the official Aquael app and re-reading the
characteristics. All integers are little-endian. Flow values use a raw scale where
`4096 = 100 %`. Times are seconds after midnight.

## Device Information (0x180A)

| Characteristic | Example |
|---|---|
| 0x2A23 / 0x2A00 | `ULTRAMAX BT` |
| 0x2A24 Model number | `2000` |
| 0x2A26 Firmware revision | `1.7.0` |
| 0x2A27 Hardware revision | `1.2.0` |
| 0x2A28 Software revision | `2.18.0` |
| 0x2A29 Manufacturer | `AQUAEL Sp. z o.o.` |

## Fish feeding – service `19b30000-98b5-11ed-a8fc-0242ac120002` (new)

| UUID | Type | Meaning |
|---|---|---|
| `19b30001` | uint8 | Fish feeding enabled (0/1) |
| `19b30002` | 4 × uint8 | One byte per feeding time, `01` = enabled (e.g. `01 01 00 00` = times 1 and 2) |
| `19b30003`–`19b30006` | uint32 | Feeding time 1–4 (seconds after midnight) |
| `19b30007` | uint32 | Water flow during feeding (raw, 4096 = 100 %) |
| `19b300ee` | 25 bytes | Combined read: enabled(1) + 4×time enabled(1) + 4×time(4) + flow(4) |

Verification (app → read-back):

| Change in app | Before | After |
|---|---|---|
| Fish feeding enabled | `19b30001 = 00` | `01` |
| Time 1 on | `19b30002 = 00 00 00 00` | `01 00 00 00` |
| Time 1 = 08:00 | `19b30003 = 43200` | `28800` |
| Feeding flow 40 % | `19b30007 = 2048` | `1638` |
| Time 2 on at 11:00 | `19b30002 = 01 00 00 00`, `19b30004 = 43200` | `01 01 00 00`, `39600` |
| Feeding flow 45 % (written from HA) | `1638` | `1843` (shown as 45 % in the app) |

Writing a single feeding-time byte from Home Assistant must send all four bytes;
writing the value as a uint32 bitmask (`03 00 00 00`) is accepted but only enables time 1.
The app does not expose a feeding duration, so it is presumably fixed in firmware.

## Unknown / not used – service `19b00000-98b5-11ed-a8fc-0242ac120002`

| UUID | Props | Observed | Notes |
|---|---|---|---|
| `19b00001` | read/write | 61293 → 61294 within one read | counts up once per second (timer) |
| `19b00003` | read/write/notify | 160 | live value? |
| `19b00004` | read/write | 174 | |
| `19b00005` | read/write | 0 | |
| `19b000ee` | read | combined | |

Not exposed by the app; left untouched (no writes).

## Other services (not used)

- `d6f1d96d-594c-4c53-b1c6-144a1dfde6d8` with `7ad671aa…` (read/write/notify) and
  `23408888…` (write) – likely firmware update; do not write.
- `4c8765b0-1207-481f-8c37-246097cdd961` / `4c8765b1…` – second seconds counter.

## Advertisement (service data UUID `0xA0B7`)

`41 51 | xx xx | <MAC 6 bytes> | 07 | 00 E0 A1 xx xx 9C 09 00 …`
Byte 10 `0x07` = ULTRAMAX. Bytes 16–17 match the current day flow raw value
(`9C 09` = 2460 ≈ 60 %).
