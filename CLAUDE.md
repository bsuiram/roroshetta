# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single custom Home Assistant integration (`custom_components/roroshetta/`) that reads environmental
sensors from a Safera / Røroshetta Sense kitchen hood over BLE. There is no build system, no test
suite, no linter config, and no `requirements` in the manifest — it is plain Python deployed by
copying `custom_components/roroshetta/` into a Home Assistant config directory and restarting HA.

Status per the top-level README: it installs and fetches sensor data but historically did not keep
updating. That reconnect/notification loop is the live area of work.

## Running / debugging

There is no unit test harness. The two ways to exercise the code:

- `python test.py` — standalone bleak script, run from a machine with a BLE adapter near the hood.
  It scans for `Roroshetta Sense`, subscribes to the `0000BEEF-…` characteristic and prints decoded
  frames. This is the reference implementation of the byte decoding and the fastest way to check a
  protocol change or probe unmapped bytes (flip `print_bit` / `print_all` in `decode_env1`).
- Deploy into Home Assistant and watch logs with `custom_components.roroshetta` and
  `homeassistant.components.bluetooth` at `debug` (see `custom_components/roroshetta/README.md`).

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
- **`sensor.py` is table-driven.** Each sensor is a `RoroshettaSensorEntityDescription` with a
  `value_fn(coordinator)`; adding a sensor means adding a field to the `RoroshettaData` dataclass,
  a decode line in `_parse_data`, and one entry in the `SENSORS` tuple.

## The BLE payload

`_parse_data` decodes a ~60-byte little-endian frame by hardcoded offsets, mirroring `decode_env1`
in `test.py`. The offsets were reverse-engineered from dumps against app screenshots and several are
marked unsure (`alarm_level` @44, `activity` @45, `grease_filter` @59). **Keep `test.py` and
`coordinator._parse_data` in sync** — if you change a scaling factor or offset in one, change it in
the other, and prefer validating against a live device before trusting a new mapping. Frames shorter
than 60 bytes are dropped with a warning.
