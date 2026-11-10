"""Constants for SATEL ETHM-1 Legacy."""

DOMAIN = "satel_ethm1_legacy"

CONF_USER_CODE = "user_code"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INTEGRATION_KEY = "integration_key"
CONF_MOTION_HOLD_SECONDS = "motion_hold_seconds"
CONF_MOTION_HOLD_ZONES = "motion_hold_zones"

DEFAULT_PORT = 7094
DEFAULT_SCAN_INTERVAL = 1
DEFAULT_TIMEOUT = 5.0
DEFAULT_MOTION_HOLD_SECONDS = 30
DEFAULT_MOTION_HOLD_ZONES = "1-8"

PLATFORMS = ["binary_sensor", "alarm_control_panel"]
