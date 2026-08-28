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
- **`sensor.py` is table-driven.** Each sensor is a `RoroshettaSensorEntityDescription` with a
  `value_fn(coordinator)`; adding a sensor means adding a field to the `RoroshettaData` dataclass,
  a decode line in `_parse_data`, and one entry in the `SENSORS` tuple.

## The BLE payload

**Real frames are 69 bytes, arriving about once per second.** `test.py`'s docstring claims "≈ 54
bytes" and `_parse_data` guards on `len(data) < 60` — both were written before anyone measured, and
both are wrong. Highest mapped offset is 59, so **bytes 60-68 are entirely unexplored**.

`_parse_data` decodes the frame little-endian by hardcoded offsets, mirroring `decode_env1` in
`test.py`. The offsets were reverse-engineered from dumps against app screenshots and several are
still marked unsure (`alarm_level` @44, `activity` @45, `grease_filter` @59). **Keep `test.py` and
`coordinator._parse_data` in sync** — if you change a scaling factor or offset in one, change it in
the other, and validate against a live device before trusting a new mapping.

To capture frames, switch on the dedicated frame logger
(`custom_components.roroshetta.coordinator.frames` → `debug` via the `logger.set_level` service)
and grep the core log for `coordinator.frames`. See `captures/` for tooling, a stored idle baseline,
and a per-byte analyser that labels each offset with the field currently read from it.

What the idle baseline (51 frames, 2026-08-27) established:

- **Bytes 60-68 are static** at `03 00 00 00 00 00 00 00 ff` with the hood idle — likely a trailer
  or status block rather than live sensor data. Not yet observed under load.
- **Bytes 6-7 are a live 16-bit LE value the parser ignores entirely.** It drifts smoothly
  (~24000-33000) and is unambiguously little-endian: big-endian reads as noise. It correlates with
  `tvoc` at +0.66 and `temperature` at -0.50, which is the signature of a raw MOX gas reading, but
  tVOC barely moved during the capture so that is a lead, not a conclusion.
- Bytes 24-35 (`15 01 64 ff 01 ae ff 1e 00 02 00 00`) are constant and look like configuration or
  thresholds. Bytes 9 and 52 vary slightly. `uptime` is confirmed as a 3-byte LE counter.
- `fan`, `light`, `power`, `activity` and `alarm_level` all read zero at idle, so **the unsure
  offsets cannot be confirmed without someone operating the hood** while frames are captured.

Values confirmed plausible on a real device: temp 23.4 °C, humidity 49 %, CO₂ 657 ppm, PM2.5
6.1 µg/m³, AQI 22, uptime 3287464 s (~38 days). Note `uptime` is read as a 3-byte LE value via
`get_u16_le(36, 3)` despite the helper's name.

## Traps that already bit this code

Two bugs here cost real debugging time and are easy to reintroduce:

- **`asyncio.wait()` requires tasks.** Passing bare coroutines raises `TypeError: Passing coroutines
  is forbidden` on Python 3.11+. It fired every connection right after `start_notify`, got swallowed
  by the loop's broad `except Exception`, and disconnected — so exactly one frame arrived and the
  integration looked like it "fetched once then stopped".
- **`BleakClient.set_disconnected_callback` no longer exists** (removed in bleak 0.19). The old code
  guarded it with `hasattr`, so it silently did nothing and dropped links were never noticed. The
  callback must be passed to `establish_connection(...)` / `BleakClient(...)` at construction.

The broad `except Exception` in `_run_notify_loop` is what turned both into silent misbehaviour
rather than a traceback. Be suspicious of it when a symptom looks like "works once, then nothing".

## Verifying a change without hardware

`homeassistant` and `bleak` are not installed locally, so `coordinator.py` cannot simply be imported.
The workable pattern is to stub both module trees in `sys.modules` (each stub needs `__path__ = []`
to act as a package, and the `DataUpdateCoordinator` stub needs `__class_getitem__` to be
subscriptable), then load `coordinator.py` by file path under a synthetic package whose `__path__`
points at the component directory — that satisfies `from .const import ...` without executing
`__init__.py`. A fake client that streams N notifications then fires its `disconnected_callback` is
enough to exercise connect, stream, disconnect, reconnect and shutdown timing.

This proves control flow only. It says nothing about byte offsets, which need a real device.
