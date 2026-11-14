from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from . import address_label_of
from .const import CONF_NAME, DOMAIN


def device_info(config_entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=config_entry.data.get(CONF_NAME, "Tauron Outages"),
        manufacturer="Tauron Dystrybucja",
        model=address_label_of(config_entry.data),
        sw_version="1.0.0",
    )
