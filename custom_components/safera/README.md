# Safera Sense Custom Component

A custom Home Assistant integration for the Safera Sense Bluetooth environmental sensor.

## Features

- **Automatic Bluetooth Discovery**: Discovers Safera Sense devices via Bluetooth advertising
- **Environmental Monitoring**: Monitors temperature, humidity, CO2, TVOC, PM2.5, and more
- **Real-time Updates**: Holds a BLE connection open and receives pushed notifications (~1/second)
- **Comprehensive Debug Logging**: Extensive debug logging for troubleshooting

## Installation

1. Copy the `custom_components/safera/` directory to your Home Assistant `custom_components` folder
2. Restart Home Assistant
3. The integration will automatically discover your Safera Sense device

## Configuration

The integration is configured automatically through Bluetooth discovery. When your Safera Sense device is detected, you'll see a notification in Home Assistant to set it up.

Setup asks you to put the device into pairing mode. Note there is roughly a 10 second gap between
submitting that step and the actual pairing attempt, so stay at the hood until it completes. Once
paired the flag is stored in the config entry and never asked again.

## Sensors

The integration provides the following sensors:

- **Temperature**: Ambient temperature in °C
- **Heat Index**: Misnamed — this is the hob's **surface temperature**, not a computed heat index.
  It tracked 23.4 → 28.0 °C across a cooking session while ambient moved 0.3 °C, and an independent
  reverse-engineering of the protocol labels the same field Surface Temperature
- **Humidity**: Relative humidity in %
- **CO2**: Carbon dioxide concentration in ppm
- **TVOC**: Total Volatile Organic Compounds (reported as µg/m³; unit not yet confirmed against the app)
- **PM2.5**: Particulate matter 2.5 in µg/m³
- **AQI**: Air Quality Index
- **Power**: Power drawn by the cooktop, in W (0 when the hob is off; observed up to 2660 W)
- **Uptime**: Device uptime in seconds
- **Light Level**: The hood's own lamp, not ambient light. Raw byte / 30; only 0 and 3.0 have
  ever been observed, so intermediate brightness steps are unconfirmed
- **Fan Speed**: Raw byte / 30. Observed 0 through 4.0
- **Grease Filter**: Filter saturation in percent — a slow counter, climbs about 1 per 15 h
- **Activity Level**: Presence at the hob — spikes when someone is there, then decays steadily to 0
- **Alarm Level**: Stove-guard hazard integrator, in percent. Rises while the hob draws power, is
  knocked back down by activity, and **trips at 100**, cutting power to the cooktop. It is not
  capped at 100 — it was seen to reach 107 after a cut
- **Device state**: `normal`, `pre_alarm` (buzzer, 15 seconds) or `alarm` (cooktop cut)
- **Last OK pressed**: when the hood's OK button was last pressed. The hood keeps no such timer —
  it timestamps the press in its own uptime, and this derives the wall-clock moment from that

### Diagnostic sensors

Filed under the device page's Diagnostic section rather than with the environment sensors, and kept
off the auto-generated dashboard — visible and usable, just shelved as information about the device.

- **Pitch** and **Roll** — auto-detected mounting angles in degrees, signed. These are live
  accelerometer readings and drift by a degree frame to frame. Pitch moved 10° between 2026-08-28
  and 08-31 without anyone noticing, so they are worth a glance if alignment ever matters

### Binary sensors

- **Stove alarm** — on during both the pre-alarm buzzer and the cooktop cut, so it fires when the
  warning starts rather than only once power has gone
- **Cooktop power cut** — on only while the hood is actually holding the cooktop off

## Controls

As well as the sensors above, the integration exposes:

- **Light** (`light.*`) — on/off, brightness and colour temperature. The hood reports all three
  back, so the state is real rather than assumed. Brightness and colour both read 0 while the lamp
  is off and the hood returns at a dim default, so the entity remembers the last values and
  re-applies them when switching on. Note the Kelvin range is a mapping for the UI, not a
  measurement: the hood's colour control is a plain 0-255 warm-to-cool slider.
- **Fan** (`fan.*`) — on/off and speed as a percentage of the raw 0-255 range. This one has real
  feedback: byte 57 reports the actual motor speed. Note the separate **Fan Speed** *sensor* reads a
  different byte, the hood's own level index, which stays at 0 while Home Assistant drives the fan.
- **Reset grease filter** (`button.*`) — resets the filter counter to 0 after cleaning the filter.
- **Fan auto mode** and **Light auto mode** (`switch.*`) — whether the hood starts the fan and light
  by itself when it detects cooking. **Any manual light or fan command disarms the matching auto
  mode**, whether it comes from Home Assistant, the Safera app or the hood's own controls, so
  switching the light on here stops it auto-starting next time until you turn the switch back on.

- **Sensor height** and **Cooker width** (cm) — the hood's mounting geometry. Editable, since they
  are configuration rather than measurements; the height is mirrored live in the payload too
- **Ventilation sensitivity**, **Fan presets 1-4 and Boost**, **Light preset 1-3 brightness** and
  **Light preset 1-3 colour** (`number.*`) — the same presets the Safera app edits under Cooker Hood Settings. Values come from
  the hood's own settings block, re-read once per connection and after every write, so they are not
  guesses. Colour is in Kelvin, 2700-4995 K in 9 K steps.

### `safera.send_command`

A raw escape hatch for reverse-engineering: writes an arbitrary command code and parameter to the
hood's command characteristic. Known codes are in `const.py` and `captures/gatt.md`. Deliberately
raw, since the command set is still being mapped — the light, fan and filter commands were all
found this way.

    action: safera.send_command
    data:
      code: "0x2005"
      param: 1

### `safera.write_setting`

Writes one byte of the hood's 200-byte configuration block and reads it back to confirm. The preset
offsets are mapped (see `captures/gatt.md`) but most of the block is not, and it also holds
stove-guard configuration — so this is deliberately low level.

    action: safera.write_setting
    data:
      offset: 87
      value: 22

## Debug Logging

The integration includes comprehensive debug logging. To enable debug logging:

1. Go to **Settings** > **System** > **Logs**
2. Set log level to `debug` for the following loggers:
   - `custom_components.safera`
   - `homeassistant.components.bluetooth`

Or add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.safera: debug
    homeassistant.components.bluetooth: debug
```

## Troubleshooting

### Device Not Discovered

1. Ensure your Safera Sense device is powered on and in Bluetooth range
2. Check Bluetooth proxy logs for device advertising data
3. Verify the device is advertising with the expected service UUID: `0000f00d-1212-efde-1523-785fef13d123`

### Connection Issues

1. Check debug logs for connection attempts
2. Ensure the device is not connected to another application
3. Verify Bluetooth permissions and range
4. **ESP_GATT_CONN_FAIL_ESTABLISH errors**: This indicates the ESPHome Bluetooth proxy cannot establish a GATT connection. The integration retries indefinitely with exponential backoff. Try:
   - Restarting the ESPHome device
   - Moving the device closer to the Bluetooth proxy
   - Checking ESPHome device logs for Bluetooth issues
   - Ensuring no other devices are connected to the Safera Sense
   - **Pairing issues**: If the device requires pairing, ensure it's not already paired with another device. The integration attempts automatic pairing on connection.

### Data Not Updating

1. Check if the device is sending notifications
2. Verify the characteristic UUID is correct: `0000beef-1212-efde-1523-785fef13d123`
3. Look for timeout messages in debug logs
4. Check the proxy's signal to the hood — below about -80 dBm, GATT connections become unreliable
   even though advertisements still arrive

## Technical Details

- **Bluetooth Service UUID**: `0000f00d-1212-efde-1523-785fef13d123`
- **Characteristic UUID**: `0000beef-1212-efde-1523-785fef13d123`
- **Manufacturer ID**: `1837`
- **Payload**: 69 bytes, little-endian, pushed roughly once per second
- **Connection Type**: Persistent connection with GATT notifications (push, not polling)
- **Connection Handling**: Reconnect loop with exponential backoff capped at 30s, retried indefinitely
- **Pairing**: Attempted once on first setup, then recorded so later restarts skip it

## Device Compatibility

The Safera Sense may require Bluetooth pairing before it allows connections. The integration automatically attempts pairing during connection establishment. If you encounter persistent connection failures:

1. **Check device pairing status**: Ensure the Safera Sense is not already paired with another device
2. **Reset device pairing**: Some devices may need to be reset to factory settings to clear existing pairings
3. **Device firmware**: Ensure your Safera Sense has firmware that supports the expected Bluetooth characteristics
4. **Bluetooth range**: Keep the device within Bluetooth range of your ESPHome proxy

## Requirements

- Home Assistant 2024.1+
- Bluetooth adapter with BLE support
- Safera Sense device firmware that supports the expected characteristics
- **Device must be pairable**: The device should allow Bluetooth pairing for connection establishment