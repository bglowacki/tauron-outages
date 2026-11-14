from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TauronDataUpdateCoordinator
from .const import CONF_NAME, DOMAIN
from .entity import device_info
from .outage_schedule import OutageSchedule

UNKNOWN = "Unknown"

type Reading = tuple[Any, dict[str, Any]]


@dataclass(frozen=True, kw_only=True)
class TauronSensorDescription(SensorEntityDescription):
    reading: Callable[[OutageSchedule, datetime], Reading]


def _outage_status(schedule: OutageSchedule, now: datetime) -> Reading:
    is_active = schedule.is_active(now)
    attributes: dict[str, Any] = {"is_active": is_active, "total_outages": schedule.count}
    if next_outage := schedule.next(now):
        attributes["next_outage_start"] = next_outage.start_raw
        attributes["next_outage_end"] = next_outage.end_raw
        attributes["next_outage_reason"] = next_outage.message or UNKNOWN
    return ("Active" if is_active else "Inactive"), attributes


def _next_outage(schedule: OutageSchedule, now: datetime) -> Reading:
    next_outage = schedule.next(now)
    if next_outage is None:
        return None, {}
    return next_outage.start, {
        "end_time": next_outage.end_raw,
        "reason": next_outage.message or UNKNOWN,
        "type": next_outage.type if next_outage.type is not None else UNKNOWN,
    }


def _outage_count(schedule: OutageSchedule, now: datetime) -> Reading:
    if not schedule.count:
        return 0, {}
    active = schedule.active(now)
    return schedule.count, {
        "active_outages": len(active),
        "upcoming_outages": len(schedule.upcoming(now)),
        "is_active": bool(active),
    }


def _outage_items(schedule: OutageSchedule, now: datetime) -> Reading:
    return schedule.count, {
        "outages": [o.as_feed_item() for o in schedule.all()],
        "total_outages": schedule.count,
        "has_active": schedule.is_active(now),
        "has_upcoming": schedule.next(now) is not None,
    }


SENSORS: tuple[TauronSensorDescription, ...] = (
    TauronSensorDescription(
        key="outage_status",
        name="Outage Status",
        icon="mdi:power-plug-off",
        reading=_outage_status,
    ),
    TauronSensorDescription(
        key="next_outage",
        name="Next Outage",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        reading=_next_outage,
    ),
    TauronSensorDescription(
        key="outage_count",
        name="Outage Count",
        icon="mdi:counter",
        reading=_outage_count,
    ),
    TauronSensorDescription(
        key="outage_items",
        name="Outage Items",
        icon="mdi:format-list-bulleted",
        reading=_outage_items,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [TauronSensor(coordinator, config_entry, description) for description in SENSORS],
        False,
    )


class TauronSensor(CoordinatorEntity[TauronDataUpdateCoordinator], SensorEntity):

    entity_description: TauronSensorDescription

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        description: TauronSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = f"{config_entry.data.get(CONF_NAME, 'Tauron')} {description.name}"
        self._attr_unique_id = f"{config_entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(config_entry)

    async def async_added_to_hass(self) -> None:
        self._evaluate()
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._evaluate()
        self.async_write_ha_state()

    def _evaluate(self) -> None:
        schedule = self.coordinator.data
        if schedule is None:
            value, attributes = None, {}
        else:
            value, attributes = self.entity_description.reading(schedule, dt_util.utcnow())
        self._attr_native_value = value
        self._attr_extra_state_attributes = attributes
