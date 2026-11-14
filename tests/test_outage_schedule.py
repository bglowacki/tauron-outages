"""Tests for the Outage schedule, exercised only through its public interface."""
from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from outage_schedule import OutageSchedule

UTC = timezone.utc
WARSAW = ZoneInfo("Europe/Warsaw")
FIXTURE = Path(__file__).parent / "fixtures" / "feed_ogrodnica_chwalimierz.json"
MODULE = Path(__file__).parents[1] / "custom_components" / "tauron_outages" / "outage_schedule.py"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def item(start: str, end: str, message: str = "Ogrodnica", **extra) -> dict:
    return {"startDate": start, "endDate": end, "Message": message, **extra}


def build(*items: dict, tz=WARSAW) -> OutageSchedule:
    return OutageSchedule.from_feed({"OutageItems": list(items)}, tz)


@pytest.fixture
def recorded() -> OutageSchedule:
    return OutageSchedule.from_feed(json.loads(FIXTURE.read_text()), WARSAW)




def test_module_imports_nothing_from_homeassistant():
    code = (
        f"import sys; sys.path.insert(0, {str(MODULE.parent)!r}); import outage_schedule as m;"
        "print(any(k.split('.')[0] == 'homeassistant' for k in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
    assert "homeassistant" not in MODULE.read_text()




def test_recorded_feed(recorded):
    assert recorded.count == 6
    starts = [o.start for o in recorded.all()]
    assert starts == sorted(starts)
    first = recorded.all()[0]
    assert first.start == utc(2026, 11, 17, 6)
    assert first.start_raw == "2026-11-17T06:00:00Z"
    assert first.end_raw == "2026-11-17T14:00:00Z"
    assert first.type == 1
    assert first.is_active_flag is False
    assert first.modified == "2026-11-12T09:41:27.153Z"


@pytest.mark.parametrize("key", ["OutageItems", "outageItems"])
def test_dict_feed_shape(key):
    feed = {key: [item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z")]}
    assert OutageSchedule.from_feed(feed, WARSAW).count == 1


def test_list_feed_shape():
    feed = [item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z")]
    assert OutageSchedule.from_feed(feed, WARSAW).count == 1


@pytest.mark.parametrize(
    "feed", [None, "oops", 42, {"Other": []}, {"OutageItems": "nope"}, {}, []]
)
def test_unexpected_feed_shape_gives_empty_schedule(feed):
    schedule = OutageSchedule.from_feed(feed, WARSAW)
    assert schedule.count == 0
    assert schedule.all() == ()


def test_non_dict_items_are_ignored():
    feed = ["x", None, item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z")]
    assert OutageSchedule.from_feed(feed, WARSAW).count == 1



CANONICAL = {
    "startDate": "2026-11-17T06:00:00Z",
    "endDate": "2026-11-17T14:00:00Z",
    "message": "Ogrodnica,",
    "type": 1,
    "isActive": True,
    "outageId": "abc",
    "modified": "2026-11-12T09:41:27.153Z",
}

SPELLINGS = {
    "startDate": ["startDate", "StartDate", "start_date"],
    "endDate": ["endDate", "EndDate", "end_date"],
    "message": ["message", "Message", "reason", "description", "Description"],
    "type": ["type", "TypeId", "typeId"],
    "isActive": ["isActive", "IsActive"],
    "outageId": ["outageId", "OutageId"],
    "modified": ["modified", "Modified"],
}


@pytest.mark.parametrize(
    "field,spelling",
    [(field, spelling) for field, spellings in SPELLINGS.items() for spelling in spellings],
)
def test_every_key_spelling_gives_the_same_outage(field, spelling):
    expected = build(CANONICAL).all()[0]
    variant = dict(CANONICAL)
    variant[spelling] = variant.pop(field)
    assert build(variant).all()[0] == expected


def test_message_precedence():
    outage = build(
        {**item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z", "from Message"),
         "reason": "from reason", "description": "from description"}
    ).all()[0]
    assert outage.message == "from Message"
    outage = build(
        {"startDate": "2026-11-17T06:00:00Z", "endDate": "2026-11-17T14:00:00Z",
         "reason": "from reason", "Description": "from Description"}
    ).all()[0]
    assert outage.message == "from reason"


def test_missing_message_is_none():
    outage = build({"startDate": "2026-11-17T06:00:00Z", "endDate": "2026-11-17T14:00:00Z"}).all()[0]
    assert outage.message is None




def test_z_timestamp_is_utc():
    outage = build(item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00.000Z")).all()[0]
    assert outage.start == utc(2026, 11, 17, 6)
    assert outage.end == utc(2026, 11, 17, 14)
    assert outage.start.utcoffset() == timedelta(0)


def test_naive_timestamp_uses_given_time_zone():
    outage = build(item("2026-11-17T07:00:00", "2026-11-17 15:00:00")).all()[0]
    assert outage.start == utc(2026, 11, 17, 6)
    assert outage.end == utc(2026, 11, 17, 14)
    assert outage.start.utcoffset() == timedelta(0)
    other = build(item("2026-11-17T07:00:00", "2026-11-17T15:00:00"), tz=UTC).all()[0]
    assert other.start == utc(2026, 11, 17, 7)


def test_explicit_offset_is_respected():
    outage = build(item("2026-11-17T07:00:00+01:00", "2026-11-17T15:00:00+01:00"), tz=UTC).all()[0]
    assert outage.start == utc(2026, 11, 17, 6)


def test_naive_timestamps_across_spring_dst_change():
    outage = build(item("2026-03-29T01:00:00", "2026-03-29T05:00:00")).all()[0]
    assert outage.start == utc(2026, 3, 29, 0)
    assert outage.end == utc(2026, 3, 29, 3)
    assert outage.end - outage.start == timedelta(hours=3)


def test_naive_timestamps_across_autumn_dst_change():
    outage = build(item("2026-10-25T01:00:00", "2026-10-25T05:00:00")).all()[0]
    assert outage.start == utc(2026, 10, 24, 23)
    assert outage.end == utc(2026, 10, 25, 4)
    assert outage.end - outage.start == timedelta(hours=5)


@pytest.mark.parametrize(
    "start,end",
    [
        ("not a date", "2026-11-17T14:00:00Z"),
        ("2026-11-17T06:00:00Z", "2026-13-45T99:00:00"),
        ("", "2026-11-17T14:00:00Z"),
        (None, "2026-11-17T14:00:00Z"),
        ("2026-11-17T06:00:00Z", None),
        (12345, "2026-11-17T14:00:00Z"),
    ],
)
def test_unparseable_item_is_dropped_with_warning(start, end, caplog):
    bad = {"startDate": start, "endDate": end, "Message": "bad"}
    good = item("2026-11-18T06:00:00Z", "2026-11-18T14:00:00Z", "good")
    with caplog.at_level("WARNING"):
        schedule = build(bad, good)
    assert [o.message for o in schedule.all()] == ["good"]
    assert any("Dropping outage" in r.message for r in caplog.records)



START = utc(2026, 11, 17, 6)
END = utc(2026, 11, 17, 14)


@pytest.fixture
def single() -> OutageSchedule:
    return build(item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z"))


@pytest.mark.parametrize(
    "now,active,upcoming",
    [
        (START - timedelta(seconds=1), False, True),
        (START, True, False),
        (START + timedelta(hours=3), True, False),
        (END, True, False),
        (END + timedelta(seconds=1), False, False),
    ],
    ids=["before", "at-start", "inside", "at-end", "after"],
)
def test_active_and_upcoming_around_an_outage(single, now, active, upcoming):
    assert single.is_active(now) is active
    assert len(single.active(now)) == int(active)
    assert len(single.upcoming(now)) == int(upcoming)
    assert (single.next(now) is not None) is upcoming


def test_tauron_active_flag_does_not_decide_activity():
    schedule = build(item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z", isActive=True))
    assert not schedule.is_active(START - timedelta(hours=1))
    schedule = build(item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z", isActive=False))
    assert schedule.is_active(START + timedelta(hours=1))


def test_overlapping_outages(recorded):
    now = utc(2026, 11, 19, 10)
    assert len(recorded.active(now)) == 2
    now = utc(2026, 11, 19, 12)
    assert [o.message for o in recorded.active(now)] == [
        "Chwalimierz, , Chwalimierz: Zabudowa w obrębie działek numer 98, 99."
    ]


def test_next_is_earliest_upcoming(recorded):
    assert recorded.next(utc(2026, 11, 14)).start == utc(2026, 11, 17, 6)
    assert recorded.next(utc(2026, 11, 17, 6)).start == utc(2026, 11, 18, 6)
    assert recorded.next(utc(2026, 11, 21)) is None


def test_upcoming_counts(recorded):
    assert len(recorded.upcoming(utc(2026, 11, 14))) == 6
    assert len(recorded.upcoming(utc(2026, 11, 19, 7))) == 2


def test_next_transition_picks_earliest_boundary(recorded):
    assert recorded.next_transition(utc(2026, 11, 14)) == utc(2026, 11, 17, 6)
    assert recorded.next_transition(utc(2026, 11, 17, 6)) == utc(2026, 11, 17, 14)
    assert recorded.next_transition(utc(2026, 11, 19, 7)) == utc(2026, 11, 19, 11)
    assert recorded.next_transition(utc(2026, 11, 19, 11)) == utc(2026, 11, 19, 15)


def test_next_transition_none_after_last(recorded):
    assert recorded.next_transition(utc(2026, 11, 20, 13)) is None
    assert OutageSchedule().next_transition(utc(2026, 11, 14)) is None


@pytest.mark.parametrize(
    "range_start,range_end,expected",
    [
        (END, END + timedelta(hours=1), 0),
        (START - timedelta(hours=1), START, 0),
        (END - timedelta(seconds=1), END + timedelta(hours=1), 1),
        (START - timedelta(hours=1), START + timedelta(seconds=1), 1),
        (END + timedelta(seconds=1), END + timedelta(hours=1), 0),
        (START - timedelta(hours=1), START - timedelta(seconds=1), 0),
        (START + timedelta(hours=1), START + timedelta(hours=2), 1),
        (START - timedelta(days=1), END + timedelta(days=1), 1),
    ],
    ids=["touches-end", "touches-start", "overlaps-end", "overlaps-start", "after", "before", "inside", "covers"],
)
def test_overlapping_range_edges(single, range_start, range_end, expected):
    assert len(single.overlapping(range_start, range_end)) == expected


def test_overlapping_with_local_time_range(single):
    local_start = datetime(2026, 11, 17, 0, 0, tzinfo=WARSAW)
    local_end = datetime(2026, 11, 18, 0, 0, tzinfo=WARSAW)
    assert len(single.overlapping(local_start, local_end)) == 1




@pytest.mark.parametrize("locality", ["Ogrodnica", "ogrodnica", "OGRODNICA", "  Ogrodnica  ", "Ogrodnica,"])
def test_locality_case_and_whitespace(recorded, locality):
    local = recorded.local(locality)
    assert local.count == 2
    assert all("Ogrodnica" in o.message for o in local.all())


def test_locality_matches_message_with_trailing_comma(recorded):
    messages = [o.message for o in recorded.local("Chwalimierz").all()]
    assert "Chwalimierz," in messages
    assert len(messages) == 4


def test_locality_matches_multi_locality_message():
    schedule = build(
        item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z", "Chwalimierz, Ogrodnica, Środa Śląska"),
        item("2026-11-18T06:00:00Z", "2026-11-18T14:00:00Z", "Chwalimierz"),
    )
    assert schedule.local("ogrodnica").count == 1
    assert schedule.local("środa śląska").count == 1


@pytest.mark.parametrize("locality", ["", "   ", None])
def test_empty_locality_is_the_same_schedule(recorded, locality):
    assert recorded.local(locality).all() == recorded.all()


def test_locality_without_message_never_matches():
    schedule = build({"startDate": "2026-11-17T06:00:00Z", "endDate": "2026-11-17T14:00:00Z"})
    assert schedule.local("Ogrodnica").count == 0


def test_local_schedule_answers_time_questions(recorded):
    local = recorded.local("Ogrodnica")
    assert local.next(utc(2026, 11, 14)).start == utc(2026, 11, 19, 7)
    assert local.next_transition(utc(2026, 11, 19, 11)) == utc(2026, 11, 20, 8)




def test_outages_are_immutable(recorded):
    outage = recorded.all()[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        outage.message = "changed"
    assert isinstance(recorded.all(), tuple)


def test_queries_do_not_change_outages(recorded):
    before = recorded.all()
    now = utc(2026, 11, 19, 10)
    recorded.next(now), recorded.active(now), recorded.local("x"), recorded.next_transition(now)
    assert recorded.all() == before


def test_uid_uses_outage_id_when_present(recorded):
    assert recorded.all()[0].uid == "a3c1f6e2-0b7d-4e8a-9c61-1d2f3e4a5b01"


def test_uid_without_outage_id_is_deterministic():
    raw = item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z", "Ogrodnica,")
    uid = build(raw).all()[0].uid
    assert uid == build(dict(raw)).all()[0].uid
    assert uid.startswith(f"{int(START.timestamp())}-{int(END.timestamp())}-")
    assert uid != build(item("2026-11-17T06:00:00Z", "2026-11-17T14:00:00Z", "Chwalimierz,")).all()[0].uid


def test_uid_without_outage_id_is_stable_across_processes():
    code = (
        f"import sys; sys.path.insert(0, {str(MODULE.parent)!r}); import outage_schedule as m;"
        "from datetime import timezone;"
        "s = m.OutageSchedule.from_feed([{'startDate': '2026-11-17T06:00:00Z',"
        " 'endDate': '2026-11-17T14:00:00Z', 'Message': 'Ogrodnica,'}], timezone.utc);"
        "print(s.all()[0].uid)"
    )
    uids = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, check=True,
            env={"PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("1", "2", "3")
    }
    assert len(uids) == 1
