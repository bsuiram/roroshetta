"""Constants for the Roroshetta Sense integration."""

DOMAIN = "roroshetta"

# Bluetooth characteristic UUID
BEEF_CHARACTERISTIC = "0000beef-1212-efde-1523-785fef13d123"

# Update interval in seconds
UPDATE_INTERVAL = 60

# Config entry data keys
DATA_PAIRED_ONCE = "paired_once"

# Pairing window delay on first setup
PAIRING_WINDOW_SECONDS = 5

# Connection loop timings
DEVICE_WAIT_SECONDS = 5
MAX_BACKOFF_SECONDS = 30
STOP_TIMEOUT_SECONDS = 5

# Mark entities unavailable if no notification arrives within this window
STALE_AFTER_SECONDS = 300
