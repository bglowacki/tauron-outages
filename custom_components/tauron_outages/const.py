"""Constants for the Tauron Power Outages integration."""

DOMAIN = "tauron_outages"

# Update interval default in minutes (4 hours)
UPDATE_INTERVAL = 240

# Configuration keys
CONF_CITY_GAID = "city_gaid"
CONF_STREET_GAID = "street_gaid"
CONF_HOUSE_NO = "house_no"
CONF_NAME = "name"
# Optional filtering keys
CONF_FILTER_TYPE = "filter_type"
CONF_FILTER_MESSAGE = "filter_message"
# Options keys
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"

# Sensor types
SENSOR_TYPES = {
    "outage_status": {
        "name": "Outage Status",
        "icon": "mdi:power-plug-off",
        "device_class": None,
    },
    "next_outage": {
        "name": "Next Outage",
        "icon": "mdi:calendar-clock",
        "device_class": "timestamp",
    },
    "outage_count": {
        "name": "Outage Count",
        "icon": "mdi:counter",
        "device_class": None,
    },
    "outage_items": {
        "name": "Outage Items",
        "icon": "mdi:format-list-bulleted",
        "device_class": None,
    },
    # Filtered group (added only if filters configured)
    "filtered_next_outage": {
        "name": "Filtered Next Outage",
        "icon": "mdi:calendar-clock",
        "device_class": "timestamp",
    },
    "filtered_outage_count": {
        "name": "Filtered Outage Count",
        "icon": "mdi:counter",
        "device_class": None,
    },
    "filtered_outage_items": {
        "name": "Filtered Outage Items",
        "icon": "mdi:format-list-bulleted",
        "device_class": None,
    },
}
