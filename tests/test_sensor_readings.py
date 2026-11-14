from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from homeassistant.util import dt as dt_util

from tauron_outages import sensor
from tauron_outages.const import DOMAIN
from tauron_outages.outage_schedule import OutageSchedule

UTC = timezone.utc
MESSAGE = "Ogrodnica, Ogrodnica: numery domów 1-25."
A_START, A_END = "2026-11-19T07:00:00Z", "2026-11-19T11:00:00Z"
B_START, B_END = "2026-11-20T08:00:00Z", "2026-11-20T12:00:00Z"

SCHEDULE = OutageSchedule.from_feed(
    {
        "OutageItems": [
            {
                "outageId": "a",
                "startDate": A_START,
                "endDate": A_END,
                "Message": MESSAGE,
                "type": 1,
                "isActive": False,
                "modified": "2026-11-12T10:05:11.402Z",
            },
            {"startDate": B_START, "endDate": B_END},
        ]
    },
    ZoneInfo("Europe/Warsaw"),
)
EMPTY = OutageSchedule()

ITEMS = [
    {
        "outageId": "a",
        "startDate": A_START,
        "endDate": A_END,
        "message": MESSAGE,
        "type": 1,
        "isActive": False,
        "modified": "2026-11-12T10:05:11.402Z",
    },
    {
        "outageId": None,
        "startDate": B_START,
        "endDate": B_END,
        "message": None,
        "type": None,
        "isActive": None,
        "modified": None,
    },
]


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


BEFORE = utc(2026, 11, 18)
DURING = utc(2026, 11, 19, 9)
AFTER = utc(2026, 11, 21)

CASES = {
    "before": (
        SCHEDULE,
        BEFORE,
        {
            "outage_status": (
                "Inactive",
                {
                    "is_active": False,
                    "total_outages": 2,
                    "next_outage_start": A_START,
                    "next_outage_end": A_END,
                    "next_outage_reason": MESSAGE,
                },
            ),
            "next_outage": (
                utc(2026, 11, 19, 7),
                {"end_time": A_END, "reason": MESSAGE, "type": 1},
            ),
            "outage_count": (
                2,
                {"active_outages": 0, "upcoming_outages": 2, "is_active": False},
            ),
            "outage_items": (
                2,
                {
                    "outages": ITEMS,
                    "total_outages": 2,
                    "has_active": False,
                    "has_upcoming": True,
                },
            ),
        },
    ),
    "during": (
        SCHEDULE,
        DURING,
        {
            "outage_status": (
                "Active",
                {
                    "is_active": True,
                    "total_outages": 2,
                    "next_outage_start": B_START,
                    "next_outage_end": B_END,
                    "next_outage_reason": "Unknown",
                },
            ),
            "next_outage": (
                utc(2026, 11, 20, 8),
                {"end_time": B_END, "reason": "Unknown", "type": "Unknown"},
            ),
            "outage_count": (
                2,
                {"active_outages": 1, "upcoming_outages": 1, "is_active": True},
            ),
            "outage_items": (
                2,
                {
                    "outages": ITEMS,
                    "total_outages": 2,
                    "has_active": True,
                    "has_upcoming": True,
                },
            ),
        },
    ),
    "after": (
        SCHEDULE,
        AFTER,
        {
            "outage_status": ("Inactive", {"is_active": False, "total_outages": 2}),
            "next_outage": (None, {}),
            "outage_count": (
                2,
                {"active_outages": 0, "upcoming_outages": 0, "is_active": False},
            ),
            "outage_items": (
                2,
                {
                    "outages": ITEMS,
                    "total_outages": 2,
                    "has_active": False,
                    "has_upcoming": False,
                },
            ),
        },
    ),
    "empty": (
        EMPTY,
        BEFORE,
        {
            "outage_status": ("Inactive", {"is_active": False, "total_outages": 0}),
            "next_outage": (None, {}),
            "outage_count": (0, {}),
            "outage_items": (
                0,
                {
                    "outages": [],
                    "total_outages": 0,
                    "has_active": False,
                    "has_upcoming": False,
                },
            ),
        },
    ),
}


async def entity_readings(schedule, now, monkeypatch):
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    entry = SimpleNamespace(entry_id="abc", data={"name": "Ogrodnica"})
    coordinator = SimpleNamespace(data=schedule)
    hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: coordinator}})
    monkeypatch.setattr(sensor, "device_info", lambda _entry: None)
    entities = []
    await sensor.async_setup_entry(hass, entry, lambda new, _update: entities.extend(new))
    readings = {}
    for entity in entities:
        entity._evaluate()
        key = entity.unique_id.removeprefix("abc_")
        readings[key] = (entity.native_value, entity.extra_state_attributes)
    return readings


@pytest.mark.parametrize("case", CASES)
async def test_entities_report_each_reading(case, monkeypatch):
    schedule, now, expected = CASES[case]
    assert await entity_readings(schedule, now, monkeypatch) == expected


async def test_entities_report_nothing_without_a_schedule(monkeypatch):
    readings = await entity_readings(None, BEFORE, monkeypatch)
    assert readings == {key: (None, {}) for key in CASES["before"][2]}



@pytest.mark.parametrize("case", CASES)
def test_each_sensor_reads_the_schedule_at_now(case):
    schedule, now, expected = CASES[case]
    assert {d.key: d.reading(schedule, now) for d in sensor.SENSORS} == expected


def test_feed_items_keep_the_feed_key_order():
    assert [list(o.as_feed_item()) for o in SCHEDULE.all()] == [
        ["outageId", "startDate", "endDate", "message", "type", "isActive", "modified"]
    ] * 2
