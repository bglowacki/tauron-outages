"""Calendar platform for Tauron Power Outages."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TauronDataUpdateCoordinator
from .const import DOMAIN, CONF_NAME

_LOGGER = logging.getLogger(__name__)


def _prepend_thunderbolt(summary: str | None) -> str:
    """Prepend a thunderbolt emoji to the summary, avoiding duplicates.
    If summary is empty, return a sensible default with icon.
    """
    base = summary or "Planned outage"
    s = str(base).strip()
    return s if s.startswith("⚡") else f"⚡ {s}"


class _BaseTauronOutagesCalendar(CoordinatorEntity, CalendarEntity):
    """Shared implementation for Tauron outages calendars.

    Subclasses provide:
      - name_suffix: e.g. "Outages" or "Filtered Outages"
      - unique_id_suffix: e.g. "calendar" or "filtered_calendar"
      - next_key: data key for the next event (e.g. "next_outage", "filtered_next_outage")
      - list_key: data key for the list of events (e.g. "outages", "filtered_outages")
    """

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        *,
        name_suffix: str,
        unique_id_suffix: str,
        next_key: str,
        list_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._next_key = next_key
        self._list_key = list_key
        base_name = config_entry.data.get(CONF_NAME, "Tauron")
        self._attr_name = f"{base_name} {name_suffix}".strip()
        self._attr_unique_id = f"{config_entry.entry_id}_{unique_id_suffix}"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._config_entry.data.get(CONF_NAME, "Tauron Outages"),
            "manufacturer": "Tauron Dystrybucja",
            "model": "Power Outages",
            "sw_version": "1.0.0",
        }

    @property
    def event(self) -> Optional[CalendarEvent]:
        """Return the next upcoming outage as current calendar event."""
        data = self.coordinator.data or {}
        next_outage = data.get(self._next_key)
        if not next_outage:
            return None

        return self._build_event_from_outage(next_outage)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:
        """Return list of outages overlapping the [start_date, end_date] range."""
        data = self.coordinator.data or {}
        outages = data.get(self._list_key, []) or []
        events: List[CalendarEvent] = []

        for outage in outages:
            evt = self._build_event_from_outage(outage)
            if not evt:
                continue
            # Overlap check
            if evt.end < start_date or evt.start > end_date:
                continue
            events.append(evt)

        return events

    def _build_event_from_outage(self, outage: dict[str, Any]) -> Optional[CalendarEvent]:
        start_dt = self._parse_dt(outage.get("startDate") or outage.get("start_date"))
        end_dt = self._parse_dt(outage.get("endDate") or outage.get("end_date"))
        if not start_dt or not end_dt:
            return None

        summary = (
            outage.get("reason")
            or outage.get("description")
            or outage.get("message")
            or outage.get("Message")
            or "Planned outage"
        )
        uid = str(outage.get("outageId") or outage.get("OutageId") or "")
        if not uid:
            uid = f"{int(start_dt.timestamp())}-{int(end_dt.timestamp())}-{hash(summary)}"
        description = (
            outage.get("message")
            or outage.get("Message")
            or outage.get("description")
            or outage.get("reason")
            or "Planned outage"
        )
        return CalendarEvent(
            start=start_dt,
            end=end_dt,
            summary=_prepend_thunderbolt(summary),
            description=description,
            uid=uid,
        )

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        """Parse datetime string using API helper and ensure timezone-aware in local tz."""
        if not value:
            return None
        try:
            dt_obj = self.coordinator.api._parse_datetime(value)
            if dt_obj is None:
                return None
            # Ensure timezone-aware and convert to Home Assistant's local time
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            return dt_util.as_local(dt_obj)
        except Exception:
            return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tauron calendar platform."""
    coordinator: TauronDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug("Setting up TauronOutagesCalendar for entry_id=%s", config_entry.entry_id)
    entities: list[CalendarEntity] = [
        TauronOutagesCalendar(coordinator, config_entry),
        TauronOutagesFilteredCalendar(coordinator, config_entry),
    ]
    async_add_entities(entities, False)


class TauronOutagesCalendar(_BaseTauronOutagesCalendar):
    """Calendar entity representing Tauron outages."""

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            name_suffix="Outages",
            unique_id_suffix="calendar",
            next_key="next_outage",
            list_key="outages",
        )


class TauronOutagesFilteredCalendar(_BaseTauronOutagesCalendar):
    """Calendar entity representing filtered Tauron outages."""

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            name_suffix="Filtered Outages",
            unique_id_suffix="filtered_calendar",
            next_key="filtered_next_outage",
            list_key="filtered_outages",
        )
