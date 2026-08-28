# GATT table

Dumped from a live hood on 2026-08-28 (firmware rev 13, software rev 75) by temporarily logging
`client.services` from the coordinator after connect. The Mac could see the hood advertising at
-84 dBm but could never complete a connection, so this went out through the ESPHome proxy, which
sees it 30 dB stronger.

**The hood stops advertising entirely while a central is connected.** It accepts one connection at
a time, so nothing else can even scan it while the integration is running. Disable the config entry
before trying to connect from anywhere else.

Two values are redacted below: the serial number, and the contents of `abd1`, which carries the
household WiFi SSID and the device's own `Sense_xxxxxx` id. This repo is public.

## Standard services

| handle | UUID | props | value |
|---|---|---|---|
| 3 | `2a00` Device Name | read | `Roroshetta Sense` |
| 5 | `2a01` Appearance | read | `0000` |
| 7 | `2a04` Preferred Conn Params | read | `0600 2800 0000 5802` |
| 9 | `2aa6` Central Addr Resolution | read | `01` |
| 12 | `2a05` Service Changed | indicate | — |
| 16 | `2a29` Manufacturer | read | `Safera Oy` |
| 18 | `2a24` Model Number | read | `IFU10CR-PRO` |
| 20 | `2a25` Serial Number | read | *(redacted)* |
| 22 | `2a27` Hardware Revision | read | `3.2.255.0` |
| 24 | `2a26` Firmware Revision | read | `13` |
| 26 | `2a28` Software Revision | read | `75` |

## Nordic DFU — `0000fe59-…`

| handle | UUID | props |
|---|---|---|
| 29 | `8ec90003-f315-4f60-9fb8-838830daea50` | write, indicate |

This is **Nordic Secure DFU**, the firmware update service. It confirms the nRF chip family implied
by the vendor base UUID. **Never write here experimentally** — this is the characteristic that puts
the device into bootloader mode.

## Vendor service — `0000f00d-1212-efde-1523-785fef13d123`

| handle | UUID | props | size | value at idle |
|---|---|---|---|---|
| 33 | `beef` | read, notify | 69 | the sensor stream this integration decodes |
| 36 | `abba` | read, **write**, write-no-rsp | 2 | `2bff` |
| 38 | `dcba` | read | 200 | `a3000000...` config blob |
| 40 | `dcbb` | read | 202 | `0000a3000000...` — same blob shifted 2 bytes |
| 42 | `babe` | read, **write**, write-no-rsp | 8 | `02100000 3c000000` |
| 44 | `abcd` | read, notify | 178 | all zero |
| 47 | `abce` | read, notify | 183 | all zero |
| 50 | `abcf` | read, notify | 2 | `0000` |
| 53 | `abdf` | read, notify | 16 | `1d005b1ca00f0400a901000000000000` |
| 56 | `abd1` | read, notify | 95 | *(redacted — WiFi SSID + device id)* |
| 59 | `abd3` | read, **write**, write-no-rsp | 32 | all zero |
| 61 | `abd2` | read, **write**, write-no-rsp, notify | 512 | all zero |

## What this means for control

**Writable characteristics exist and the command protocol is known.** The
[magicus/safera-ble](https://github.com/magicus/safera-ble/discussions/1) project reverse-engineered
it independently; the naming below is theirs, cross-checked against this hood where possible.

| UUID | their name | purpose |
|---|---|---|
| `beef` | SENSOR_REPORT | the sensor stream this integration decodes |
| `babe` | DEVICE_COMMAND | **commands go here** |
| `dcba` | READ_SETTINGS | 200-byte configuration block |
| `abba` | WRITE_SETTINGS | configuration writes |
| `abd1` | CLOUD_WIFI_STATUS | WiFi/cloud state — this is where the SSID appears |
| `abdf` | DAY_STATISTICS | daily statistics |
| `abcf` | EVENT_LOG | device event history |
| `abd2` | GDT_DATA | hood-specific data |
| `abd3` | GDT_COMMAND | hood commands |

Commands written to `babe` are 8 bytes: **a 4-byte little-endian code followed by a 4-byte
little-endian parameter.** That matches the shape read back from this hood at idle,
`02100000 3c000000` — code `0x1002`, parameter 60. Note `0x1002` is not one of the command codes
below, so the read-back is not simply the last command sent.

| code | command | parameter |
|---|---|---|
| `0x2002` | CMD_MOTOR_RAW_SPEED | fan speed, 0-255, 0 = off |
| `0x2004` | CMD_MOTOR_AUTO_MODE | auto fan on/off |
| `0x2005` | CMD_LIGHT_PRESET | light preset |
| `0x2006` | CMD_LIGHT_BRIGHTNESS | light brightness |
| `0x2008` | CMD_LIGHT_AUTO_MODE | auto light on/off |
| `0x2009` | CMD_FILTER_CHANGED | filter timer reset, parameter 0 |

## What has actually been tried (2026-08-28)

`babe` is a working command channel on this firmware and the 8-byte code+parameter format is right.
Everything below was confirmed with someone standing at the hood.

| command | result |
|---|---|
| `0x2005` CMD_LIGHT_PRESET | **Works.** Parameter 1 lights the lamp, 0 switches it off. `light@53` follows the parameter, so it holds a preset index rather than a brightness when written this way — note the hood's own controls put 90 in the same byte. |
| `0x2006` CMD_LIGHT_BRIGHTNESS | **Works, 0-255 and monotonic.** 1 is very dim, and 200 and 255 are each visibly brighter than the last. **0 is a dim floor, not off**, so off has to go through the preset command. Nothing in the payload reports brightness back, and it resets to a dim default across an off/on cycle. |
| `0x2002` CMD_MOTOR_RAW_SPEED | **Works, 0-255.** A commanded sweep of 0 → 50 → 100 → 180 → 255 → 0 was tracked exactly by **byte 57**, ramping between steps. Above roughly 180 the motor is not audibly different, though 57 still reports the value. |
| `0x2009` CMD_FILTER_CHANGED | **Works.** Parameter 0 took `grease_filter@59` from 22 to 0 within four seconds — which also proves 59 really is the filter counter. |
| `0x2004` / `0x2008` auto modes | No observable effect on this firmware. |

**Byte 57 is the fan feedback, byte 56 is not.** `@56` is a level index the hood's own controller
maintains: it reads 30 with the fan on low from the panel, and stays 0 the whole time a BLE speed
command has the motor running. `@57` is the actual motor speed in the same 0-255 units the command
takes.

Colour is the one app feature with no known command code. It needs discovery — diff the 200-byte
`dcba` settings block before and after changing colour in the app, or capture an Android HCI snoop.

`babe` reads back the last command written, but reverts to `021000003c000000` after a reconnect, so
it is a volatile command buffer rather than a settings register. A before/after diff of `dcba`,
`dcbb`, `abba`, `babe` and `abd3` confirmed that none of this testing changed stored configuration.

## How not to test writes

Both of these cost a session and one of them took the integration down:

- **Do not resolve `babe` by UUID string.** `write_gatt_char("0000babe-…")` raised
  `BleakCharacteristicNotFoundError` on connections where `start_notify` on `beef` — the same
  service — worked fine, i.e. a partial cached GATT table. Walk `client.services` and keep the
  characteristic object, or write to its handle (42) directly.
- **Do not write seconds after connecting.** A write fired shortly after `start_notify` returned
  `[Errno 104] Connection reset by peer`, dropped the link, and left every entity unavailable in
  Home Assistant until a restart. Repeated HA restarts make this worse, because the hood accepts one
  central at a time and each restart re-takes the slot. Drive writes on demand from an established,
  known-healthy connection — a service or button entity — not from a boot-time experiment.

Every write can be verified from the notify stream a second later: this integration decodes
`light@53`, `fan@56` and `grease_filter@59`, so a command's effect is directly observable.

**The one thing not to touch is the Nordic DFU service** at `0000fe59-…`, which puts the device
into bootloader mode. Beyond that, prefer the documented command codes above to guessing: this
device switches mains power to a cooktop, and `abba` (WRITE_SETTINGS) reaches the configuration
block where the stove guard's thresholds plausibly live.
