from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TauronDataUpdateCoordinator
from .const import CONF_NAME, DOMAIN
from .entity import device_info
from .outage_schedule import Outage, OutageSchedule

_LOGGER = logging.getLogger(__name__)

FALLBACK_TEXT = "Planned outage"


def _prepend_thunderbolt(summary: str) -> str:
    s = summary.strip()
    return s if s.startswith("⚡") else f"⚡ {s}"


def _event(outage: Outage) -> CalendarEvent:
    text = outage.message or FALLBACK_TEXT
    return CalendarEvent(
        start=dt_util.as_local(outage.start),
        end=dt_util.as_local(outage.end),
        summary=_prepend_thunderbolt(text),
        description=text,
        uid=outage.uid,
    )


class _BaseTauronOutagesCalendar(CoordinatorEntity[TauronDataUpdateCoordinator], CalendarEntity):

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        *,
        name_suffix: str,
        unique_id_suffix: str,
        local_only: bool,
    ) -> None:
        super().__init__(coordinator)
        self._local_only = local_only
        base_name = config_entry.data.get(CONF_NAME, "Tauron")
        self._attr_name = f"{base_name} {name_suffix}".strip()
        self._attr_unique_id = f"{config_entry.entry_id}_{unique_id_suffix}"
        self._attr_device_info = device_info(config_entry)

    @property
    def _schedule(self) -> OutageSchedule:
        data = self.coordinator.data
        if not data:
            return OutageSchedule()
        return data.local if self._local_only else data.schedule

    @property
    def event(self) -> CalendarEvent | None:
        schedule = self._schedule
        now = dt_util.utcnow()
        outage = next(iter(schedule.active(now)), None) or schedule.next(now)
        return _event(outage) if outage else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [_event(o) for o in self._schedule.overlapping(start_date, end_date)]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TauronDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            TauronOutagesCalendar(coordinator, config_entry),
            TauronOutagesFilteredCalendar(coordinator, config_entry),
        ],
        False,
    )


class TauronOutagesCalendar(_BaseTauronOutagesCalendar):

    def __init__(self, coordinator: TauronDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            config_entry,
            name_suffix="Outages",
            unique_id_suffix="calendar",
            local_only=False,
        )


class TauronOutagesFilteredCalendar(_BaseTauronOutagesCalendar):

    def __init__(self, coordinator: TauronDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            config_entry,
            name_suffix="Filtered Outages",
            unique_id_suffix="filtered_calendar",
            local_only=True,
        )
