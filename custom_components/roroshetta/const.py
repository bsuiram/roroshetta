"""Constants for the Roroshetta Sense integration."""

DOMAIN = "roroshetta"

# Services
SERVICE_SEND_COMMAND = "send_command"

# Bluetooth characteristic UUIDs
BEEF_CHARACTERISTIC = "0000beef-1212-efde-1523-785fef13d123"

# Command channel. Writes are 8 bytes: a 4-byte LE code then a 4-byte LE
# parameter. Confirmed working on this hood — see captures/gatt.md.
BABE_CHARACTERISTIC = "0000babe-1212-efde-1523-785fef13d123"

# Fallback for BABE_CHARACTERISTIC. Resolving it by UUID string has been seen to
# fail against a partial cached GATT table while notifications on the same
# service were streaming fine, so the handle is used if the lookup comes up
# empty. Verified against firmware 13; re-check if the hood is ever updated.
BABE_HANDLE = 42

# Advertised identifiers, kept in sync with the matchers in manifest.json
SERVICE_UUID = "0000f00d-1212-efde-1523-785fef13d123"
MANUFACTURER_ID = 1837

# Update interval in seconds
UPDATE_INTERVAL = 60

# Device Information Service (0x180A) characteristics. Read once per hood and
# cached in the config entry so Home Assistant's device page shows the real
# manufacturer, model and revisions instead of hardcoded guesses.
DIS_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"
DIS_MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
DIS_SERIAL = "00002a25-0000-1000-8000-00805f9b34fb"
DIS_HARDWARE_REV = "00002a27-0000-1000-8000-00805f9b34fb"
DIS_FIRMWARE_REV = "00002a26-0000-1000-8000-00805f9b34fb"
DIS_SOFTWARE_REV = "00002a28-0000-1000-8000-00805f9b34fb"

# Config entry data keys
DATA_PAIRED_ONCE = "paired_once"
DATA_DEVICE_INFO = "device_info"

# Pairing window delay on first setup
PAIRING_WINDOW_SECONDS = 5

# Connection loop timings
DEVICE_WAIT_SECONDS = 5
MAX_BACKOFF_SECONDS = 30
STOP_TIMEOUT_SECONDS = 5

# Command codes, from magicus/safera-ble and verified against this hood on
# 2026-08-28 except where noted. Payload is a 4-byte LE code then a 4-byte LE
# parameter, written to BABE_CHARACTERISTIC.
CMD_MOTOR_RAW_SPEED = 0x2002  # parameter 0-255, 0 stops the motor
CMD_MOTOR_AUTO_MODE = 0x2004  # no observable effect on this firmware
CMD_LIGHT_PRESET = 0x2005  # 0 off, 1 on
CMD_LIGHT_BRIGHTNESS = 0x2006  # parameter 0-255; 0 is a dim floor, not off
CMD_LIGHT_AUTO_MODE = 0x2008  # no observable effect on this firmware
CMD_FILTER_CHANGED = 0x2009  # parameter 0 resets the grease filter counter

LIGHT_PRESET_OFF = 0
LIGHT_PRESET_ON = 1

# The motor takes 0-255. Anything above roughly 180 was not audibly different,
# though byte 57 does report the higher values back.
FAN_SPEED_RANGE = (1, 255)

# Commands are rate limited. The hood is a stove guard on a single BLE
# connection and a burst of writes has dropped the link before.
COMMAND_MIN_INTERVAL_SECONDS = 1.0
COMMAND_TIMEOUT_SECONDS = 10

# Mark entities unavailable if no notification arrives within this window.
# The device pushes roughly once per second, so this is ~30 missed frames.
STALE_AFTER_SECONDS = 30
