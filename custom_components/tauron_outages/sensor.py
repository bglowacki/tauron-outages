from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            TauronSensor(coordinator, config_entry, sensor_type, sensor_config)
            for sensor_type, sensor_config in SENSOR_TYPES.items()
        ],
        False,
    )


def _item(outage: Outage) -> dict[str, Any]:
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

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        sensor_config: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._local_only = sensor_type.startswith("local_")
        self._kind = sensor_type.removeprefix("local_")
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
        return data.local if self._local_only else data.schedule

    async def async_added_to_hass(self) -> None:
        self._evaluate()
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._evaluate()
        self.async_write_ha_state()

    def _evaluate(self) -> None:
        schedule = self._schedule
        if schedule is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        now = dt_util.utcnow()
        value: Any = None
        attributes: dict[str, Any] = {}

        if self._kind == "outage_status":
            is_active = schedule.is_active(now)
            next_outage = schedule.next(now)
            value = "Active" if is_active else "Inactive"
            attributes["is_active"] = is_active
            attributes["total_outages"] = schedule.count
            if next_outage:
                attributes["next_outage_start"] = next_outage.start_raw
                attributes["next_outage_end"] = next_outage.end_raw
                attributes["next_outage_reason"] = next_outage.message or UNKNOWN

        elif self._kind == "next_outage":
            next_outage = schedule.next(now)
            if next_outage:
                value = next_outage.start
                attributes["end_time"] = next_outage.end_raw
                attributes["reason"] = next_outage.message or UNKNOWN
                attributes["type"] = next_outage.type if next_outage.type is not None else UNKNOWN

        elif self._kind == "outage_count":
            value = schedule.count
            if schedule.count:
                active = schedule.active(now)
                attributes["active_outages"] = len(active)
                attributes["upcoming_outages"] = len(schedule.upcoming(now))
                attributes["is_active"] = bool(active)

        elif self._kind == "outage_items":
            value = schedule.count
            attributes["outages"] = [_item(o) for o in schedule.all()]
            attributes["total_outages"] = schedule.count
            attributes["has_active"] = schedule.is_active(now)
            attributes["has_upcoming"] = schedule.next(now) is not None

        self._attr_native_value = value
        self._attr_extra_state_attributes = attributes
