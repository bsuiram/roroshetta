# Frame captures

Raw 69-byte payloads from the `0000beef-…` characteristic, one per line:

    <timestamp>\t<length>\t<hex>

## Capturing

The coordinator logs every frame on a dedicated logger, so frames can be collected
without turning on debug for everything else. Call the `logger.set_level` service with:

    {"custom_components.roroshetta.coordinator.frames": "debug"}

then pull `/api/hassio/core/logs?lines=N` and grep for `coordinator.frames`.
Frames arrive at ~1/second. The level resets on restart.

## Analysing

    python3 analyze.py 2026-08-27-idle.tsv

Prints per-byte distinct/min/max with each offset labelled by the field
`coordinator._parse_data` currently reads from it, so unmapped and constant
bytes stand out.

## Where the captures live

**Not in this repo.** It is public, and frame data reveals the temperature, humidity, CO₂
and usage pattern of someone's kitchen. `.tsv` files are gitignored; keep captures in a
local directory outside the working tree (currently `~/priv/roroshetta-captures/`).

Captures taken so far, for reference:

- `2026-08-27-idle.tsv` — hood idle: fan, light, power, activity and alarm all zero.
  Establishes which bytes move on their own.
- `2026-08-27-light-fan.tsv` — light toggled and fan run on low. Broken up by several BLE
  disconnects, so it has gaps; cross-check against HA's own recorder history
  (`/api/history/period`), which is more complete than sampling the debug log.
- `2026-08-28-egg.tsv` — **the useful one.** 2871 frames over 53 min covering a full cooking
  session: hob on 11:31:41, off 11:39:57 (peak 2660 W), fan and light auto-on 1 s after the hob
  and off together at 11:44:25. Gap-free. This is what confirmed offsets 44, 45, 46 and 59.

## Confirmed from these captures

| offset | field | evidence |
|---|---|---|
| 2-3 | *(mislabelled `heat_index`)* | Ambient temp @0 moved 21.5→21.8 °C all session while this went 23.4→28.0, corr +0.39 with hob power. Not a heat index — a second heat measurement, probably the stove guard's IR sensor. Also jumps when a person is in front of the hood. |
| 43 | `Activity Type` | Cooking-session latch. 0→2 on the exact frame power went nonzero; cleared to 0 at 11:54:42, ~15 min after the hob went off. |
| 44 | `alarm_level` | Interlock integrator, gated on hob power: mean 1.58 with the hob on vs 0.00 with it off (only 3 of 854 hob-off frames nonzero). Climbed 1→17 over ~65 s unattended, driven to 0 in 19 s by a presence spike. 83% of increments happen at `activity` ≤ 1. Steps of 1 about every 3 s. Peak ever seen 35; `magicus/safera-ble` calls it a percentage and our data neither confirms nor contradicts that. |
| 45 | `activity` | Presence detector. Impulses up, then **every decrement is exactly −2** — 70/70 in the egg session, 594/594 on 08-27. Peak seen 100. |
| 46-47 | `power` | Real mains watts, u16 LE. 0→2660 W, all values multiples of 20 W, nonzero for exactly the hob-on span. Read a constant 0 in every earlier capture only because the hob was never on during one. |
| 6-7 | ambient light | `value / 32` lux per `magicus/safera-ble`. Reads 25-157 lux (mean 108) on our frames. Dips when someone is at the hob — 114 lux with nobody there vs 100 with someone present — i.e. shadowing. Neither parser decodes it. |
| 53 | `light` | 0 with light off, 90 with light on → `/30` = 3.0. Intermediate steps never observed. |
| 56 | `fan` | 30 with fan on low → `/30` = 1.0. |
| 57 | *(unmapped)* | 0 with the fan off, 23 with it on low, in every capture. Fan-related. |
| 59 | `grease_filter` | Constant within a capture, but the recorder shows 20 → 21 (08-27 14:43 UTC) → 22 (08-28 05:44 UTC): ~1 per 15 h, ~62 days for 0→100. Filter saturation in percent. |

## External reference

[magicus/safera-ble](https://github.com/magicus/safera-ble/discussions/1) is an independent
reverse-engineering of the same protocol, and is where the command codes in `gatt.md`, the ambient
light scaling and the `Activity Type` name come from. It agrees with the measurements here on
`@0-1`, `@2-3` (which it calls Surface Temperature, confirming that `heat_index` is misnamed),
`@4-5`, `@10-11`, `@15-16`, `@17-18`, `@43`, `@44`, `@45` and `@46-47`. It disagrees on `@12-13`
and `@24`, where our frames say it is wrong, and its table stops at offset 47 — it describes a
"54+ byte" payload where ours are 69 bytes. Probably an older firmware.

## How the safety interlock works

Safera Sense is a stove guard first: it cuts power to the cooktop if something stays too hot for
too long. `alarm_level` accumulates while the hob draws power, `activity` knocks it back down, and
the alarm fires when `alarm_level` passes a threshold with no `activity`. The capture data matches
this on every count except the trip itself.

## Still unresolved

- **No alarm trip has ever been captured**, so `alarm_level`'s threshold and units are unknown and
  nothing is known about how a power cut is reported. The hood's self-test should exercise this.
- **Byte 60 is not a light/fan state.** On 08-27 it read 3 idle / 1 light / 0 fan across 1067
  frames, which looked airtight; it then sat constant at 3 through the whole 08-28 session with
  light and fan on. Bytes 61-68 stay static at `00 …  00 ff`.
- ~~Bytes 6-7~~ **resolved**: ambient light, `value / 32` lux — see the table above.
- Whether the light has intermediate brightness steps — only 0 and 90 have ever been seen at @53,
  and only 0 and 30 at @56, so the `/30` scaling rests on two points.
- Whether the auto-on of light and fan when the hob starts is really automatic. It is consistent
  with the data but the frames cannot distinguish it from a button press at the same moment.
