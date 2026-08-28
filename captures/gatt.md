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

**Writable characteristics exist**, so controlling the hood over BLE is plausible. Four of them:
`abba`, `babe`, `abd3` and `abd2`.

Best guesses, all unverified:

- **`abba` (2 bytes) and `babe` (8 bytes)** are the plausible control surface for light and fan.
  They are small, writable and readable, and `babe`'s `02 10 00 00 | 3c 00 00 00` reads naturally as
  two little-endian u32s — 4098 and 60 — which looks like settings rather than a live command.
- **`abd1` / `abd2` / `abd3` are almost certainly WiFi provisioning**, not hood control: `abd1`
  holds the SSID, `abd3` is a 32-byte writable field the size of a WPA passphrase, and `abd2` is a
  512-byte buffer the right shape for a network scan list. **Writing to `abd3` could overwrite the
  hood's WiFi credentials.**
- `dcba` / `dcbb` are read-only and overlap by a 2-byte shift, so they are probably the same config
  block exposed two ways. Worth decoding — thresholds for the stove guard may live here.

**Do not guess writes.** This device switches mains power to a cooktop, one writable characteristic
is the firmware bootloader and another probably holds WiFi credentials. The safe path is an Android
HCI snoop capture of the Safera app driving the controls, which yields the exact handle and payload
per action. See the debugging notes in `CLAUDE.md`.
