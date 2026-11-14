"""Outage schedule: typed, immutable Outages built from Tauron's Outage feed.

Pure Python, no Home Assistant imports. Every time-based question takes an
explicit ``now`` so that answers are always evaluated at the moment they are asked.

All knowledge of Tauron's key spellings, feed shapes and date formats lives here.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import Any, Iterable, Mapping

_LOGGER = logging.getLogger(__name__)

# Key spellings Tauron (or older payloads) have used, in order of preference.
_START_KEYS = ("startDate", "StartDate", "start_date")
_END_KEYS = ("endDate", "EndDate", "end_date")
_MESSAGE_KEYS = ("message", "Message", "reason", "description", "Description")
_TYPE_KEYS = ("type", "TypeId", "typeId")
_ACTIVE_KEYS = ("isActive", "IsActive")
_ID_KEYS = ("outageId", "OutageId")
_MODIFIED_KEYS = ("modified", "Modified")
_FEED_ITEM_KEYS = ("OutageItems", "outageItems")


@dataclass(frozen=True, slots=True)
class Outage:
    """A single interruption of power supply published by Tauron."""

    start: datetime  # timezone-aware, UTC
    end: datetime  # timezone-aware, UTC
    start_raw: str
    end_raw: str
    message: str | None
    type: Any = None
    is_active_flag: Any = None  # Tauron's own flag; informational only
    outage_id: Any = None
    modified: Any = None

    def is_active(self, now: datetime) -> bool:
        """Whether ``now`` lies within the outage window (inclusive)."""
        return self.start <= now <= self.end

    @property
    def uid(self) -> str:
        """Stable identifier: Tauron's ID, or a digest of start, end and message."""
        if self.outage_id not in (None, ""):
            return str(self.outage_id)
        digest = hashlib.sha256(
            f"{self.start.isoformat()}|{self.end.isoformat()}|{self.message or ''}".encode()
        ).hexdigest()[:16]
        return f"{int(self.start.timestamp())}-{int(self.end.timestamp())}-{digest}"


class OutageSchedule:
    """An immutable, start-ordered collection of Outages."""

    __slots__ = ("_outages",)

    def __init__(self, outages: Iterable[Outage] = ()) -> None:
        self._outages: tuple[Outage, ...] = tuple(
            sorted(outages, key=lambda o: (o.start, o.end))
        )

    @classmethod
    def from_feed(cls, feed: Any, local_tz: tzinfo) -> OutageSchedule:
        """Build a schedule from the raw Outage feed.

        Naive timestamps are interpreted in ``local_tz``; ``Z``/offset timestamps
        keep their own zone. Items with an unreadable start or end are dropped.
        """
        if isinstance(feed, Mapping):
            items = _first(feed, _FEED_ITEM_KEYS) or []
        elif isinstance(feed, list):
            items = feed
        else:
            _LOGGER.warning("Unexpected Outage feed type: %s", type(feed).__name__)
            items = []
        if not isinstance(items, list):
            _LOGGER.warning("Unexpected Outage feed items type: %s", type(items).__name__)
            items = []
        outages = (_build_outage(item, local_tz) for item in items if isinstance(item, Mapping))
        return cls(o for o in outages if o is not None)

    def all(self) -> tuple[Outage, ...]:
        return self._outages

    @property
    def count(self) -> int:
        return len(self._outages)

    def __len__(self) -> int:
        return len(self._outages)

    def __iter__(self):
        return iter(self._outages)

    def active(self, now: datetime) -> tuple[Outage, ...]:
        return tuple(o for o in self._outages if o.is_active(now))

    def is_active(self, now: datetime) -> bool:
        return any(o.is_active(now) for o in self._outages)

    def upcoming(self, now: datetime) -> tuple[Outage, ...]:
        return tuple(o for o in self._outages if o.start > now)

    def next(self, now: datetime) -> Outage | None:
        upcoming = self.upcoming(now)
        return upcoming[0] if upcoming else None

    def overlapping(self, range_start: datetime, range_end: datetime) -> tuple[Outage, ...]:
        """Outages sharing at least one instant with [range_start, range_end]."""
        return tuple(
            o for o in self._outages if not (o.end < range_start or o.start > range_end)
        )

    def next_transition(self, now: datetime) -> datetime | None:
        """Earliest start or end strictly after ``now``, or None."""
        boundaries = [t for o in self._outages for t in (o.start, o.end) if t > now]
        return min(boundaries, default=None)

    def local(self, locality: str | None) -> OutageSchedule:
        """Local outages: those whose message names ``locality``.

        Matching is a casefolded substring test. An empty Locality returns this schedule.
        """
        needle = (locality or "").strip().strip(",").strip().casefold()
        if not needle:
            return self
        return OutageSchedule(
            o for o in self._outages if needle in (o.message or "").casefold()
        )

    def of_type(self, outage_type: str | None) -> OutageSchedule:
        """Outages whose type equals ``outage_type`` (string compare, casefolded).

        Transitional: kept only until the type filter is removed. Empty means no filter.
        """
        wanted = str(outage_type or "").strip().casefold()
        if not wanted:
            return self
        return OutageSchedule(
            o
            for o in self._outages
            if str(o.type if o.type is not None else "").strip().casefold() == wanted
        )


def _first(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    """First value present (not None, not empty string) under any of ``keys``."""
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def _parse(value: Any, local_tz: tzinfo) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(timezone.utc)


def _build_outage(item: Mapping[str, Any], local_tz: tzinfo) -> Outage | None:
    start_raw = _first(item, _START_KEYS)
    end_raw = _first(item, _END_KEYS)
    start = _parse(start_raw, local_tz)
    end = _parse(end_raw, local_tz)
    if start is None or end is None:
        _LOGGER.warning(
            "Dropping outage with unreadable dates (start=%r, end=%r)", start_raw, end_raw
        )
        return None
    message = _first(item, _MESSAGE_KEYS)
    return Outage(
        start=start,
        end=end,
        start_raw=start_raw,
        end_raw=end_raw,
        message=str(message) if message is not None else None,
        type=_first(item, _TYPE_KEYS),
        is_active_flag=_first_present(item, _ACTIVE_KEYS),
        outage_id=_first(item, _ID_KEYS),
        modified=_first(item, _MODIFIED_KEYS),
    )


def _first_present(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    """Like ``_first`` but keeps falsy values such as ``False``."""
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None
