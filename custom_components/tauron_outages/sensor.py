"""Sensor platform for Tauron Power Outages."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TauronDataUpdateCoordinator
from .const import CONF_NAME, DOMAIN, SENSOR_TYPES
from .entity import device_info
from .outage_schedule import Outage, OutageSchedule

_LOGGER = logging.getLogger(__name__)

UNKNOWN = "Unknown"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tauron sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            TauronSensor(coordinator, config_entry, sensor_type, sensor_config)
            for sensor_type, sensor_config in SENSOR_TYPES.items()
        ],
        False,
    )


def _item(outage: Outage) -> dict[str, Any]:
    """Outage as exposed in the `outages` attribute (keys and raw strings unchanged)."""
    return {
        "outageId": outage.outage_id,
        "startDate": outage.start_raw,
        "endDate": outage.end_raw,
        "message": outage.message,
        "type": outage.type,
        "isActive": outage.is_active_flag,
        "modified": outage.modified,
    }


class TauronSensor(CoordinatorEntity[TauronDataUpdateCoordinator], SensorEntity):
    """Representation of a Tauron power outage sensor.

    Values are evaluated against the schedule at the moment HA reads them.
    """

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        sensor_config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._filtered = sensor_type.startswith("filtered_")
        self._kind = sensor_type.removeprefix("filtered_")
        self._attr_name = f"{config_entry.data.get(CONF_NAME, 'Tauron')} {sensor_config['name']}"
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        self._attr_icon = sensor_config["icon"]
        self._attr_device_info = device_info(config_entry)
        if sensor_config.get("device_class"):
            self._attr_device_class = sensor_config["device_class"]

    @property
    def _schedule(self) -> OutageSchedule | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.filtered if self._filtered else data.schedule

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        schedule = self._schedule
        if schedule is None:
            return None
        now = dt_util.utcnow()

        if self._kind == "outage_status":
            return "Active" if schedule.is_active(now) else "Inactive"
        if self._kind == "next_outage":
            next_outage = schedule.next(now)
            return next_outage.start if next_outage else None
        if self._kind in ("outage_count", "outage_items"):
            return schedule.count
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        schedule = self._schedule
        if schedule is None:
            return {}
        now = dt_util.utcnow()
        attributes: dict[str, Any] = {}

        if self._kind == "outage_status":
            attributes["is_active"] = schedule.is_active(now)
            attributes["total_outages"] = schedule.count
            next_outage = schedule.next(now)
            if next_outage:
                attributes["next_outage_start"] = next_outage.start_raw
                attributes["next_outage_end"] = next_outage.end_raw
                attributes["next_outage_reason"] = next_outage.message or UNKNOWN

        elif self._kind == "next_outage":
            next_outage = schedule.next(now)
            if next_outage:
                attributes["end_time"] = next_outage.end_raw
                attributes["reason"] = next_outage.message or UNKNOWN
                attributes["type"] = next_outage.type if next_outage.type is not None else UNKNOWN

        elif self._kind == "outage_count":
            if schedule.count:
                attributes["active_outages"] = len(schedule.active(now))
                attributes["upcoming_outages"] = len(schedule.upcoming(now))
                attributes["is_active"] = schedule.is_active(now)

        elif self._kind == "outage_items":
            attributes["outages"] = [_item(o) for o in schedule.all()]
            attributes["total_outages"] = schedule.count
            attributes["has_active"] = schedule.is_active(now)
            attributes["has_upcoming"] = bool(schedule.upcoming(now))

        return attributes
