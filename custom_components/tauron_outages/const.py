DOMAIN = "tauron_outages"

DEFAULT_UPDATE_INTERVAL_HOURS = 4

CONF_CITY_GAID = "city_gaid"
CONF_STREET_GAID = "street_gaid"
CONF_HOUSE_NO = "house_no"
CONF_NAME = "name"
CONF_LOCALITY = "locality"
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"

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
