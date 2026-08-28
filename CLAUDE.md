# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single custom Home Assistant integration (`custom_components/roroshetta/`) that reads environmental
sensors from a Safera / Røroshetta Sense kitchen hood over BLE. There is no build system, no test
suite, no linter config, and no `requirements` in the manifest — it is plain Python deployed by
copying `custom_components/roroshetta/` into a Home Assistant config directory and restarting HA.

Status: working. The integration streams all 14 sensors at ~1 Hz against a real hood. The top-level
README still says "does not work" — it predates the fix. Note the component README also describes a
polling design with a 60s interval and 3 retries; that is stale too, see Architecture below.

## Running / debugging

There is no unit test harness and no CI. Four ways to exercise the code, cheapest first:

- **Stub-import the coordinator** — no hardware, no Home Assistant. See "Verifying a change without
  hardware" below. Catches control-flow regressions in seconds; proves nothing about byte offsets.
- **`python test.py`** — standalone bleak script, run from a machine with a BLE adapter near the
  hood. Scans for `Roroshetta Sense`, subscribes to `0000BEEF-…` and prints decoded frames. Reference
  implementation of the decoding (flip `print_bit` / `print_all` in `decode_env1` to probe bytes).
  Note it will fight the integration for the hood's single connection slot — stop one or the other.
- **Deploy to Home Assistant and read the log.** The details below are what make this bearable.
- **Read entity history** via `/api/history/period`. For questions about *values* (did `fan` change
  when I turned the fan on?) this beats sampling the log: it survives BLE disconnects and is already
  deduplicated. Reach for it first when correlating a physical action with a sensor.

### Deploying

Copy `custom_components/roroshetta/` into the HA config directory and **restart Home Assistant**.
Reloading the config entry is *not* enough — Python does not re-import a changed module, so a reload
silently runs the old code. Every code change needs a full restart; only config-entry state changes
can be tested with a reload.

### Reading the log

- `/api/error_log` was **removed** in recent HA versions (returns 404). Use the Supervisor proxy:
  `GET /api/hassio/core/logs?lines=N`, which returns the raw core log including DEBUG lines.
- Turn on debug at runtime with the **`logger.set_level`** service — no YAML edit, no restart:
  `{"custom_components.roroshetta": "debug"}`. It resets on every restart, so re-apply it after one.
- Keep `custom_components.roroshetta.sensor` at `info`. HA reads entity properties constantly and
  debug there is pure noise.
- Raw frames have their own logger, `custom_components.roroshetta.coordinator.frames`, so payloads
  can be captured without enabling debug for everything else. See `captures/`.

### Is it the code or the transport?

Most "it stopped updating" symptoms in this integration have turned out to be BLE transport
problems, not bugs. Before debugging the code, rule that out:

- **A clean `disconnected` with no GATT error means the remote end closed the link deliberately** —
  another client took the hood's single connection slot, or the bluetooth proxy's tunnel collapsed.
  RF failure looks different: GATT errors, timeouts, `error=133`.
- **If an ESPHome bluetooth proxy is in the path, its self-reported WiFi signal is misleading.** It
  reports what it *hears from* the access point, which is flattered by the AP's stronger transmitter.
  Check what the AP hears *from it* — that is the direction that fails. A gap of 25+ dB between the
  two is normal and the lower number is the real one.
- Proxy WiFi drops take every BLE connection tunnelled through them down too, so a hood disconnect
  can have nothing to do with the hood.

## Architecture

Flow: BLE advertisement → config flow → coordinator holds a persistent connection → notifications
push data → sensor entities read from `coordinator.data`.

- **Discovery is passive, data collection is not.** `manifest.json` declares several bluetooth
  matchers (service UUID `0000f00d-…`, local name, manufacturer id 1837). HA only uses these to
  trigger the config flow; the actual values come from a *connected* GATT notify subscription on
  `BEEF_CHARACTERISTIC` (`0000beef-…`), not from advertisement data.
- **`coordinator.py` is deliberately not a polling coordinator.** It subclasses
  `DataUpdateCoordinator` with `update_interval=None` and never implements `_async_update_data`.
  Instead `async_start_notify()` spawns `_run_notify_loop()`, a long-lived task that: resolves the
  `BLEDevice` from HA's bluetooth cache each iteration, connects via `bleak_retry_connector`'s
  `establish_connection` (falling back to raw `BleakClient` if the helper is missing), subscribes,
  then blocks on `stop_event | disconnect_event` and reconnects with exponential backoff capped at
  30s. Every notification calls `_parse_data()` then `async_set_updated_data()` to push entities.
  The manifest is `local_push` and `appropriate-polling` is marked exempt to match.
- **Pairing is a one-time dance.** The device must be put into pairing mode by a physical button.
  The config flow has a dedicated `pair` step that waits ~5s after the user confirms; the coordinator
  additionally sleeps `PAIRING_WINDOW_SECONDS` before the first connect and calls `client.pair()` once;
  only after `start_notify` succeeds does it persist `DATA_PAIRED_ONCE` into the config entry data, so
  later restarts skip both the delay and the pair call. Preserve this flag when writing entry data.
- **`entry.runtime_data` is the coordinator** (typed via `type RoroshettaConfigEntry =
  ConfigEntry[RoroshettaDataUpdateCoordinator]` in `coordinator.py`) — no `hass.data[DOMAIN]`.
- **The BLE link is held open permanently, by design.** The hood almost certainly accepts one
  central at a time, so while HA is running the Safera phone app cannot connect. This was considered
  and accepted (2026-08-27): the app was only ever a debugging tool, and log/data access through HA
  replaces it. Do not add connection-sharing or idle-release logic on the assumption that app access
  matters — it does not.
- **Availability is connection state, not `last_update_success`.** On a push coordinator with no
  `_async_update_data`, `last_update_success` is `True` forever, so entities would show stale values
  as live. `coordinator.device_available` instead requires an active connection plus a notification
  newer than `STALE_AFTER_SECONDS`, and `_set_connected()` calls `async_update_listeners()` on
  transition so entities re-render the instant a link drops. Caveat: staleness alone does not
  self-trigger a re-render — only connect/disconnect pushes do.
- **Four platforms: `button`, `fan`, `light`, `sensor`.** The three control platforms share
  `entity.py`'s `RoroshettaEntity` for device wiring and availability. `sensor.py` deliberately does
  **not** use it — its entities predate the base and switching them over risks changing unique ids
  or names, which would orphan history. New platforms should use it.
- **`sensor.py` is table-driven.** Each sensor is a `RoroshettaSensorEntityDescription` with a
  `value_fn(coordinator)`; adding a sensor means adding a field to the `RoroshettaData` dataclass,
  a decode line in `_parse_data`, and one entry in the `SENSORS` tuple.

## The BLE payload

**Real frames are 69 bytes, arriving about once per second.** `test.py`'s docstring claims "≈ 54
bytes" and `_parse_data` guards on `len(data) < 60` — both were written before anyone measured, and
both are wrong. Highest mapped offset is 59; bytes 60-68 are still largely unexplained.

`_parse_data` decodes the frame little-endian by hardcoded offsets, mirroring `decode_env1` in
`test.py`. **Keep `test.py` and `coordinator._parse_data` in sync** — if you change a scaling factor
or offset in one, change it in the other, and validate against a live device before trusting a new
mapping.

To capture frames, switch on the dedicated frame logger
(`custom_components.roroshetta.coordinator.frames` → `debug` via the `logger.set_level` service)
and grep the core log for `coordinator.frames`. See `captures/` for tooling, stored captures, and a
per-byte analyser that labels each offset with the field currently read from it.

`captures/gatt.md` holds the hood's full GATT table, dumped 2026-08-28, together with the command
protocol from [magicus/safera-ble](https://github.com/magicus/safera-ble/discussions/1) — an
independent reverse-engineering of the same device. Two things there matter
beyond reference value: **the hood stops advertising entirely while a central is connected**, so
nothing else can scan it while the integration runs (disable the config entry first); and
**writable characteristics do exist**, and BLE control is no longer theoretical — a command has
audibly run the fan.
Commands go to `babe` as a 4-byte LE code plus a 4-byte LE parameter, and **this has been tested on
the real hood** — see "Controlling the hood" below. Do not touch the Nordic DFU service at
`0000fe59-…`; it is the firmware bootloader.

### What the hood actually is

Safera Sense is a **stove guard first** and an air-quality sensor second. Its safety function cuts
power to the cooktop when something on the plate stays too hot for too long. That subsystem is what
most of the unexplained bytes belong to, and knowing it is what made them decodable — read the
frame as "hazard interlock plus environment", not "hood telemetry".

The mechanism, confirmed against a live cooking session: **`alarm_level` accumulates while the hob
draws power, `activity` (presence at the hob) knocks it back down, and an alarm fires if
`alarm_level` passes a threshold with no `activity`.**

### Confirmed by the 2026-08-28 cooking session

A full session (frying an egg, 2871 frames, 53 min, hob 11:31:41–11:39:57) settled the three
offsets that were previously marked unsure, and corrected one that was wrongly assumed dead:

- **`power` @46-47 is genuinely mains power in watts, u16 LE.** 0 → 2660 W, every observed value a
  multiple of 20 W, nonzero for exactly the span the hob was on and zero on both sides. It had read
  a constant 0 in every earlier capture **only because nobody had ever turned the hob on while
  capturing** — do not conclude a field is dead from idle data alone.
- **`alarm_level` @44 is the interlock integrator, gated on hob power.** Mean 1.58 while the hob
  drew power vs 0.00 while it did not; of 854 hob-off frames only 3 were nonzero, all value 1 and
  all the tail of a decay. It climbed 1 → 17 over ~65 s of unattended cooking, then a presence
  spike drove it to 0 within 19 s. 83% of its increments occur while `activity` ≤ 1. It ramps and
  decays in steps of 1 at roughly 3 s intervals. **Peak ever observed is 35, so the trip threshold
  is unknown.** `magicus/safera-ble` documents it as a percentage, which our data neither confirms
  nor contradicts — never seeing it above 35 says nothing about the top of the scale.
- **`activity` @45 is a presence detector with strict linear decay.** Impulse up on presence, then
  **every single decrement is exactly −2** (70 of 70 in this session, 594 of 594 on 2026-08-27).
  Peak observed 100.
- **`grease_filter` @59 is a slow monotonic counter.** Constant within any one capture, but the HA
  recorder shows 20 → 21 (08-27 14:43 UTC) → 22 (08-28 05:44 UTC): about 1 per 15 h, extrapolating
  to ~62 days for 0 → 100. Consistent with filter saturation in percent.
- **Byte 43 is a cooking-session latch**, `Activity Type` in `magicus/safera-ble`'s table. It
  flipped 0 → 2 on the exact frame `power` first went nonzero, held at 2 through the whole session,
  and cleared back to 0 at 11:54:42 — ~15 min after the hob went off and ~10 min after the fan
  stopped. Not decoded by either parser.
- **`heat_index` @2-3 is misnamed** — it is Surface Temperature, which `magicus/safera-ble`
  confirms independently. Ambient `temperature` @0-1 moved only 21.5 → 21.8 °C across the
  session while @2-3 went 23.4 → 28.0 and correlates with hob power at +0.39. A true heat index at
  21.7 °C / 52% RH is ~21.7, not 28. @2-3 is a second heat measurement, most plausibly the stove
  guard's IR sensor aimed at the hob — which also explains why it jumps when a person stands in
  front of it. The name is inherited from `test.py` and should not be trusted.
- Light and fan came on **one second after** the hob drew power and switched off together 4.5 min
  after it stopped, which looks like auto-start and run-on rather than button presses. Data cannot
  distinguish the two; do not assume a control change was user-initiated.

### Where the external table disagrees

[magicus/safera-ble](https://github.com/magicus/safera-ble/discussions/1) documents a "54+ byte"
payload and stops at offset 47. Our frames are consistently 69 bytes and carry `light@53`,
`fan@56` and `grease_filter@59`, which its table does not mention at all — most likely a different
firmware generation (this hood reports hardware 3.2.255.0, firmware 13, software 75). Two of its
offsets do not survive contact with our frames, so **prefer the measured values here**:

- its particle index at `@12-13 / 5` reads **0.00** on our frames, while our `pm25` at `@13 / 1000`
  gives 5.12 alongside an AQI of 19;
- its heat index at `@24 × 2` gives 48 °C, which is not credible.

Everything else it lists agrees, including several of our constant bytes: `@26` battery (100),
`@28` alarm status (1), `@33` device state (2), `@34-35` sensor error bitmask (0).

### Still open

- **Byte 60 is not an operating-state enum.** On the 2026-08-27 capture it read 3 idle / 1 light on
  / 0 fan on, which looked deterministic across 1067 frames. It then sat constant at 3 through the
  entire 08-28 session *including* light and fan on. Whatever drives it, it is not light or fan
  state. Bytes 61-68 remain static at `00 00 00 00 00 00 00 ff`.
- **No alarm trip has ever been observed**, so `alarm_level`'s threshold and units are unknown, and
  it is unclear whether any field reports the power actually being cut. The hood's self-test is the
  cheap way to exercise this without a genuinely dangerous pan.
- **Bytes 6-7 are ambient light**, `value / 32` lux per `magicus/safera-ble`, and both parsers
  ignore them. That reads as 25-157 lux (mean 108) on our frames, right for a kitchen, and explains
  the dips when someone is at the hob as shadowing: mean 114 lux with nobody present versus 100 lux
  with someone there. It also kills the earlier raw-MOX-gas lead, which rested on a `tvoc`
  correlation of +0.66 on the idle baseline that flipped to **−0.44** during cooking.
- Bytes 24-35 are near-constant and look like configuration or thresholds. Byte 9 and byte 52 vary
  slightly.
- **Intermediate light and fan steps have never been observed from the hood's own controls.** Set
  that way, @53 has only ever read 0 or 90 and @56 only 0 or 30, so the `/30` scaling is an
  inference from two points, not a measurement. BLE presets put 1 and 2 in @53, which does not fit
  that scaling at all — see "Controlling the hood". @57 is now mapped: it is the raw motor speed.
- **Auto mode has no known feedback.** Nothing in the payload or the settings blocks reports it,
  so `0x2004`/`0x2008` cannot be verified and no switch entity was built.

Values confirmed plausible on a real device: temp 23.4 °C, humidity 49 %, CO₂ 657 ppm, PM2.5
6.1 µg/m³, AQI 22, uptime 3287464 s (~38 days). Note `uptime` is read as a 3-byte LE value via
`get_u16_le(36, 3)` despite the helper's name.

## Controlling the hood

**Light, fan and the grease filter reset all work over BLE**, confirmed against the real hood on
2026-08-28 with someone standing at it. Commands go to `babe` as a 4-byte LE code plus a 4-byte LE
parameter; the codes live in `const.py`.

| what | command | parameter | feedback |
|---|---|---|---|
| light on/off | `0x2005` CMD_LIGHT_PRESET | 1 on, 0 off | `@53` |
| light brightness | `0x2006` CMD_LIGHT_BRIGHTNESS | 0-255 | `@54`, exact |
| light colour | `0x2007` CMD_LIGHT_COLOR | 0-255, warm to cool | `@55`, exact |
| fan speed | `0x2002` CMD_MOTOR_RAW_SPEED | 0-255, 0 stops | `@57`, the real speed |
| filter reset | `0x2009` CMD_FILTER_CHANGED | 0 | `@59` drops to 0 |

`0x2004` and `0x2008` (the auto modes) had no observable effect on this firmware.

**`0x2007` is not in `magicus/safera-ble`'s table.** It was found by letting the Safera app change
the colour while the integration was disabled, then reading `babe` back — it holds the last command
written, so the app's own writes can be read straight out of it. That trick is worth remembering
for anything else the app can do and we cannot.

Things that shaped the implementation, all learned the hard way:

- **The light has full feedback on all three channels**, each confirmed 1:1 against commanded
  values. `@54` and `@55` both read **0 while the lamp is off**, so brightness and colour have to be
  remembered across an off/on cycle — the hood also comes back at a dim default. `light.py` keeps
  the last non-zero values and re-applies them on turn-on.
- **Brightness 0 is a dim floor, not off.** Turning the lamp off has to go through the preset
  command. Confirmed by eye.
- **`@56` and `@57` are different things.** `@56` is a level index the hood's own controller
  maintains — it reads 30 with the fan on low from the panel and stays **0** while a BLE speed
  command drives the motor. `@57` is the actual motor speed in the same 0-255 units the command
  takes, and it tracked a commanded sweep (0 → 50 → 100 → 180 → 255 → 0) exactly, ramping between
  steps. The fan entity uses `@57`, so it has real feedback; the `fan_level` *sensor* still reads
  `@56` and will sit at 0 whenever HA is driving the fan. That is not a bug.
- **Above roughly 180 the motor is not audibly different**, though `@57` still reports the value.
- **The Kelvin range on the light is invented.** The hood has no notion of colour temperature —
  `@55` is a warm-to-cool slider — so `LIGHT_MIN_KELVIN`/`LIGHT_MAX_KELVIN` exist to drive the HA UI
  and are not a measurement.

Auto mode is the one thing still unresolved. `dcba` and `dcbb` were byte-identical either side of
enabling auto for both light and fan in the app, so **the auto state is not in the settings blocks**
and there is no known feedback for it. A switch entity would be optimistic and would silently drift
whenever the app changed it, so none was built.

### Writing commands

`coordinator.async_send_command(code, param)` is the only write path. It resolves the characteristic
object once per connection (`_resolve_command_char`), serialises writes behind a lock, spaces them
by `COMMAND_MIN_INTERVAL_SECONDS`, and raises `HomeAssistantError` rather than failing quietly. The
`roroshetta.send_command` service exposes it raw for experimentation — that is deliberate while the
command set is still being mapped, and it is how everything above was discovered without a redeploy
per attempt.

**Do not write from a boot-time experiment.** Writing seconds after `start_notify` returned
`[Errno 104] Connection reset by peer`, dropped the link and left every entity unavailable until a
restart; repeated restarts compound it, because the hood accepts one central at a time and each
restart re-takes the slot. Let the link settle, then drive writes on demand.

## Traps that already bit this code

Three bugs here cost real debugging time and are easy to reintroduce:

- **`asyncio.wait()` requires tasks.** Passing bare coroutines raises `TypeError: Passing coroutines
  is forbidden` on Python 3.11+. It fired every connection right after `start_notify`, got swallowed
  by the loop's broad `except Exception`, and disconnected — so exactly one frame arrived and the
  integration looked like it "fetched once then stopped".
- **`BleakClient.set_disconnected_callback` no longer exists** (removed in bleak 0.19). The old code
  guarded it with `hasattr`, so it silently did nothing and dropped links were never noticed. The
  callback must be passed to `establish_connection(...)` / `BleakClient(...)` at construction.
- **`write_gatt_char` by UUID string can fail while notifications on the same service work.**
  Writing to `"0000babe-…"` raised `BleakCharacteristicNotFoundError` on connections where
  `start_notify` on `beef` — same service — was streaming fine, which is the signature of a partial
  cached GATT table. Resolve the characteristic object by walking `client.services`, or write to its
  handle (`babe` is 42).

The broad `except Exception` in `_run_notify_loop` is what turned the first two into silent
misbehaviour rather than a traceback. Be suspicious of it when a symptom looks like "works once,
then nothing".

## Verifying a change without hardware

`homeassistant` and `bleak` are not installed locally, so `coordinator.py` cannot simply be imported.
The workable pattern is to stub both module trees in `sys.modules` (each stub needs `__path__ = []`
to act as a package, and the `DataUpdateCoordinator` stub needs `__class_getitem__` to be
subscriptable), then load `coordinator.py` by file path under a synthetic package whose `__path__`
points at the component directory — that satisfies `from .const import ...` without executing
`__init__.py`. A fake client that streams N notifications then fires its `disconnected_callback` is
enough to exercise connect, stream, disconnect, reconnect and shutdown timing.

This proves control flow only. It says nothing about byte offsets, which need a real device.
