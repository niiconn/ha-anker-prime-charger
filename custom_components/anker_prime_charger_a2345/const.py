"""Constants for the Anker Prime Charger integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "anker_prime_charger_a2345"
NAME = "Anker Prime Charger (A2345)"
MANUFACTURER = "Anker"

MODEL_A2345 = "A2345"
SUPPORTED_MODELS = {MODEL_A2345}

PLATFORMS = ["sensor", "binary_sensor", "switch"]

CONF_COUNTRY = "country"
CONF_DEVICE_SN = "device_sn"
CONF_DEVICE_NAME = "device_name"
CONF_MANUAL_DEVICE = "manual_device"
CONF_REALTIME_REFRESH_INTERVAL = "realtime_refresh_interval"
CONF_OFFLINE_TIMEOUT = "offline_timeout"
CONF_MQTT_KEEPALIVE = "mqtt_keepalive"
CONF_POLLING_FALLBACK = "polling_fallback"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_DEBUG_LOGGING = "debug_logging"
CONF_SHOW_UNKNOWN_FIELDS = "show_unknown_fields"

DEFAULT_COUNTRY = "US"
DEFAULT_REALTIME_REFRESH_INTERVAL = 300
DEFAULT_OFFLINE_TIMEOUT = 180
DEFAULT_MQTT_KEEPALIVE = 60
DEFAULT_POLLING_FALLBACK = True
DEFAULT_POLLING_INTERVAL = 300
DEFAULT_DEBUG_LOGGING = False
DEFAULT_SHOW_UNKNOWN_FIELDS = False

MIN_REALTIME_REFRESH_INTERVAL = 60
MAX_REALTIME_REFRESH_INTERVAL = 600
MIN_OFFLINE_TIMEOUT = 60
MAX_OFFLINE_TIMEOUT = 900

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

SERVICE_DUMP_LAST_PAYLOAD = "dump_last_payload"
SERVICE_DUMP_PAYLOAD_HISTORY = "dump_payload_history"

ATTR_DEVICE_SN = "device_sn"
ATTR_INCLUDE_RAW = "include_raw"
