"""Calendar platform for Tauron Power Outages."""
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
    """Prepend a thunderbolt emoji to the summary, avoiding duplicates."""
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
    """Shared implementation for Tauron outages calendars."""

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        *,
        name_suffix: str,
        unique_id_suffix: str,
        filtered: bool,
    ) -> None:
        super().__init__(coordinator)
        self._filtered = filtered
        base_name = config_entry.data.get(CONF_NAME, "Tauron")
        self._attr_name = f"{base_name} {name_suffix}".strip()
        self._attr_unique_id = f"{config_entry.entry_id}_{unique_id_suffix}"
        self._attr_device_info = device_info(config_entry)

    @property
    def _schedule(self) -> OutageSchedule:
        data = self.coordinator.data
        if not data:
            return OutageSchedule()
        return data.filtered if self._filtered else data.schedule

    @property
    def event(self) -> CalendarEvent | None:
        """Return the active outage, otherwise the next upcoming one."""
        schedule = self._schedule
        now = dt_util.utcnow()
        outage = next(iter(schedule.active(now)), None) or schedule.next(now)
        return _event(outage) if outage else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return outages overlapping the [start_date, end_date) range."""
        return [_event(o) for o in self._schedule.overlapping(start_date, end_date)]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tauron calendar platform."""
    coordinator: TauronDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            TauronOutagesCalendar(coordinator, config_entry),
            TauronOutagesFilteredCalendar(coordinator, config_entry),
        ],
        False,
    )


class TauronOutagesCalendar(_BaseTauronOutagesCalendar):
    """Calendar entity representing Tauron outages."""

    def __init__(self, coordinator: TauronDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            config_entry,
            name_suffix="Outages",
            unique_id_suffix="calendar",
            filtered=False,
        )


class TauronOutagesFilteredCalendar(_BaseTauronOutagesCalendar):
    """Calendar entity representing filtered Tauron outages."""

    def __init__(self, coordinator: TauronDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            config_entry,
            name_suffix="Filtered Outages",
            unique_id_suffix="filtered_calendar",
            filtered=True,
        )
