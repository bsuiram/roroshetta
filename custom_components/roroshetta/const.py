"""Constants for the Roroshetta Sense integration."""

DOMAIN = "roroshetta"

# Bluetooth characteristic UUID
BEEF_CHARACTERISTIC = "0000beef-1212-efde-1523-785fef13d123"

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

# Mark entities unavailable if no notification arrives within this window.
# The device pushes roughly once per second, so this is ~30 missed frames.
STALE_AFTER_SECONDS = 30
