# Roroshetta Sense Custom Component

A custom Home Assistant integration for the Roroshetta Sense Bluetooth environmental sensor.

## Features

- **Automatic Bluetooth Discovery**: Discovers Roroshetta Sense devices via Bluetooth advertising
- **Environmental Monitoring**: Monitors temperature, humidity, CO2, TVOC, PM2.5, and more
- **Real-time Updates**: Holds a BLE connection open and receives pushed notifications (~1/second)
- **Comprehensive Debug Logging**: Extensive debug logging for troubleshooting

## Installation

1. Copy the `custom_components/roroshetta/` directory to your Home Assistant `custom_components` folder
2. Restart Home Assistant
3. The integration will automatically discover your Roroshetta Sense device

## Configuration

The integration is configured automatically through Bluetooth discovery. When your Roroshetta Sense device is detected, you'll see a notification in Home Assistant to set it up.

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
- **Alarm Level**: Stove-guard hazard integrator. Rises while the hob draws power, is knocked
  back down by activity, and triggers the cooktop cut-off if it passes a threshold with nobody
  present. The trip threshold is not known; the highest value ever observed is 35

## Controls

As well as the sensors above, the integration exposes:

- **Light** (`light.*`) — on/off and brightness, 0-255. The hood reports no brightness back, so the
  entity remembers what it last set; it also re-applies brightness after switching on, because the
  hood drops to a dim default across an off/on cycle.
- **Fan** (`fan.*`) — on/off and speed as a percentage of the raw 0-255 range. This one has real
  feedback: byte 57 reports the actual motor speed. Note the separate **Fan Speed** *sensor* reads a
  different byte, the hood's own level index, which stays at 0 while Home Assistant drives the fan.
- **Reset grease filter** (`button.*`) — resets the filter counter to 0 after cleaning the filter.

### `roroshetta.send_command`

A raw escape hatch for reverse-engineering: writes an arbitrary command code and parameter to the
hood's command characteristic. Known codes are in `const.py` and `captures/gatt.md`. Deliberately
raw, since the command set is still being mapped — the light, fan and filter commands were all
found this way.

    action: roroshetta.send_command
    data:
      code: "0x2005"
      param: 1

## Debug Logging

The integration includes comprehensive debug logging. To enable debug logging:

1. Go to **Settings** > **System** > **Logs**
2. Set log level to `debug` for the following loggers:
   - `custom_components.roroshetta`
   - `homeassistant.components.bluetooth`

Or add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.roroshetta: debug
    homeassistant.components.bluetooth: debug
```

## Troubleshooting

### Device Not Discovered

1. Ensure your Roroshetta Sense device is powered on and in Bluetooth range
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
   - Ensuring no other devices are connected to the Roroshetta Sense
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

The Roroshetta Sense may require Bluetooth pairing before it allows connections. The integration automatically attempts pairing during connection establishment. If you encounter persistent connection failures:

1. **Check device pairing status**: Ensure the Roroshetta Sense is not already paired with another device
2. **Reset device pairing**: Some devices may need to be reset to factory settings to clear existing pairings
3. **Device firmware**: Ensure your Roroshetta Sense has firmware that supports the expected Bluetooth characteristics
4. **Bluetooth range**: Keep the device within Bluetooth range of your ESPHome proxy

## Requirements

- Home Assistant 2024.1+
- Bluetooth adapter with BLE support
- Roroshetta Sense device firmware that supports the expected characteristics
- **Device must be pairable**: The device should allow Bluetooth pairing for connection establishment