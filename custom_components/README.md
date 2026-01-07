# Roroshetta Sense Custom Component

A custom Home Assistant integration for the Roroshetta Sense Bluetooth environmental sensor.

## Features

- **Automatic Bluetooth Discovery**: Discovers Roroshetta Sense devices via Bluetooth advertising
- **Environmental Monitoring**: Monitors temperature, humidity, CO2, TVOC, PM2.5, and more
- **Real-time Updates**: Active polling with notification-based data updates
- **Comprehensive Debug Logging**: Extensive debug logging for troubleshooting

## Installation

1. Copy the `custom_components/roroshetta/` directory to your Home Assistant `custom_components` folder
2. Restart Home Assistant
3. The integration will automatically discover your Roroshetta Sense device

## Configuration

The integration is configured automatically through Bluetooth discovery. When your Roroshetta Sense device is detected, you'll see a notification in Home Assistant to set it up.

## Sensors

The integration provides the following sensors:

- **Temperature**: Ambient temperature in °C
- **Heat Index**: Heat index temperature in °C
- **Humidity**: Relative humidity in %
- **CO2**: Carbon dioxide concentration in ppm
- **TVOC**: Total Volatile Organic Compounds in ppb
- **PM2.5**: Particulate matter 2.5 in µg/m³
- **AQI**: Air Quality Index
- **Power**: Current power consumption in W
- **Uptime**: Device uptime in seconds
- **Light Level**: Ambient light level (0-30 scale)
- **Fan Speed**: Fan speed (0-30 scale)
- **Grease Filter Status**: Filter status indicator
- **Activity Level**: Device activity indicator
- **Alarm Level**: Alarm status

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
4. **ESP_GATT_CONN_FAIL_ESTABLISH errors**: This indicates the ESPHome Bluetooth proxy cannot establish a GATT connection. The integration will automatically retry up to 3 times and attempt pairing. Try:
   - Restarting the ESPHome device
   - Moving the device closer to the Bluetooth proxy
   - Checking ESPHome device logs for Bluetooth issues
   - Ensuring no other devices are connected to the Roroshetta Sense
   - **Pairing issues**: If the device requires pairing, ensure it's not already paired with another device. The integration attempts automatic pairing on connection.

### Data Not Updating

1. Check if the device is sending notifications
2. Verify the characteristic UUID is correct: `0000beef-1212-efde-1523-785fef13d123`
3. Look for timeout messages in debug logs
4. The integration will retry failed connections up to 3 times with exponential backoff

## Technical Details

- **Bluetooth Service UUID**: `0000f00d-1212-efde-1523-785fef13d123`
- **Characteristic UUID**: `0000beef-1212-efde-1523-785fef13d123`
- **Manufacturer ID**: `1837`
- **Update Interval**: 60 seconds
- **Connection Handling**: Automatic retry with exponential backoff (up to 3 attempts) and Bluetooth pairing
- **Error Recovery**: Graceful handling of Bluetooth connection failures
- **Connection Type**: Active polling with notifications

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