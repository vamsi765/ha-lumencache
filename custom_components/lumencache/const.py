"""Constants for the LumenCache integration."""
DOMAIN = "lumencache"

CONF_PREFIX = "prefix"
CONF_VERIFY_TLS = "verify_tls"
DEFAULT_PORT = 8883

# Options
CONF_ZONES = "zones"
CONF_MIN_KELVIN = "min_kelvin"
CONF_MAX_KELVIN = "max_kelvin"
DEFAULT_MIN_KELVIN = 2700
DEFAULT_MAX_KELVIN = 6500

CONNECT_TIMEOUT = 15   # seconds to wait for the first connection
SAVE_DELAY = 10   # seconds to wait before writing the inventory to disk
