from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tauron_outages.outage_feed import OutageFeed, OutageFeedError

from conftest import ADDRESS, FIXTURE, FixtureTransport

UTC = timezone.utc
WARSAW = ZoneInfo("Europe/Warsaw")
MODULE = Path(__file__).parents[1] / "custom_components" / "tauron_outages" / "outage_feed.py"


def fetch(transport: FixtureTransport, now: datetime, tz=WARSAW):
    return asyncio.run(OutageFeed(ADDRESS, transport, tz).fetch(now))


def test_recorded_payload_becomes_the_outage_schedule():
    transport = FixtureTransport(payload=json.loads(FIXTURE.read_text()))

    schedule = fetch(transport, datetime(2026, 11, 14, tzinfo=UTC))

    assert schedule.count == 6
    assert schedule.local("Ogrodnica").count == 2


def test_requests_seven_days_from_now_for_the_address():
    transport = FixtureTransport(payload={"OutageItems": []})

    fetch(transport, datetime(2026, 11, 14, 10, 0, 0, 123456, tzinfo=WARSAW))

    assert transport.requests == [
        {
            "cityGAID": "111",
            "streetGAID": "222",
            "houseNo": "12A",
            "getLightingSupport": "true",
            "getServicedSwitchingoff": "true",
            "fromDate": "2026-11-14T09:00:00.123Z",
            "toDate": "2026-11-21T09:00:00.123Z",
            "_": "1794646800123",
        }
    ]


def test_request_parameters_keep_their_order():
    transport = FixtureTransport(payload=[])

    fetch(transport, datetime(2026, 11, 14, tzinfo=UTC))

    assert list(transport.requests[0]) == [
        "cityGAID",
        "streetGAID",
        "houseNo",
        "getLightingSupport",
        "getServicedSwitchingoff",
        "fromDate",
        "toDate",
        "_",
    ]


def test_naive_feed_timestamps_are_read_in_the_given_time_zone():
    transport = FixtureTransport(
        payload=[{"startDate": "2026-11-17T08:00:00", "endDate": "2026-11-17T14:00:00", "Message": "Ogrodnica"}]
    )

    (outage,) = fetch(transport, datetime(2026, 11, 14, tzinfo=UTC)).all()

    assert outage.start == datetime(2026, 11, 17, 7, tzinfo=UTC)


def test_transport_failure_surfaces_as_feed_error():
    transport = FixtureTransport(error=OutageFeedError("HTTP 503"))

    with pytest.raises(OutageFeedError, match="HTTP 503"):
        fetch(transport, datetime(2026, 11, 14, tzinfo=UTC))


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("timed out"),
        ConnectionResetError("reset by peer"),
        json.JSONDecodeError("Expecting value", "<html>", 0),
    ],
)
def test_any_transport_failure_surfaces_as_feed_error(failure):
    transport = FixtureTransport(error=failure)

    with pytest.raises(OutageFeedError) as raised:
        fetch(transport, datetime(2026, 11, 14, tzinfo=UTC))

    assert raised.value.__cause__ is failure


def test_module_imports_nothing_from_homeassistant():
    code = (
        "import sys, types;"
        "pkg = types.ModuleType('tauron_outages');"
        f"pkg.__path__ = [{str(MODULE.parent)!r}];"
        "sys.modules['tauron_outages'] = pkg;"
        "import tauron_outages.outage_feed;"
        "print(any(k.split('.')[0] == 'homeassistant' for k in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
