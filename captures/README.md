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

## Confirmed from these captures

| offset | field | evidence |
|---|---|---|
| 53 | `light` | 0 with light off, 90 with light on → `/30` = 3.0. Intermediate steps never observed. |
| 56 | `fan` | 30 with fan on low → `/30` = 1.0. |
| 57 | *(unmapped)* | constant 0 across the whole idle baseline, 23 with fan on low. Almost certainly fan-related. |

Still unresolved: whether the light has intermediate brightness steps (30/60) — only 0 and
90 were ever seen. `alarm_level` @44 and `activity` @45 both move, but neither behaves like
the quantity its name claims: @44 looks like a running/status flag, @45 cycles 0-8 within
seconds.
