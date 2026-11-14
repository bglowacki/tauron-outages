from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

import tauron_outages
from tauron_outages import TauronDataUpdateCoordinator

UTC = timezone.utc
FIXTURE = Path(__file__).parent / "fixtures" / "feed_ogrodnica_chwalimierz.json"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


class FakeAPI:
    def __init__(self, feed) -> None:
        self.feed = feed
        self.calls = 0

    async def async_get_outages(self):
        self.calls += 1
        return self.feed


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.timers: list[dict] = []

    def track(self, hass, action, when):
        timer = {"action": action, "when": when, "cancelled": False}
        self.timers.append(timer)

        def cancel() -> None:
            timer["cancelled"] = True

        return cancel

    @property
    def pending(self) -> list[dict]:
        return [t for t in self.timers if not t["cancelled"] and not t.get("fired")]

    def fire(self) -> None:
        (timer,) = self.pending
        self.now = timer["when"]
        timer["fired"] = True
        timer["action"](self.now)


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock(utc(2026, 11, 14))
    monkeypatch.setattr(tauron_outages, "async_track_point_in_utc_time", fake.track)
    monkeypatch.setattr(tauron_outages.dt_util, "utcnow", lambda: fake.now)
    previous_tz = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(ZoneInfo("Europe/Warsaw"))
    yield fake
    dt_util.set_default_time_zone(previous_tz)


def run(scenario, feed=None):
    async def main():
        hass = HomeAssistant(str(Path(__file__).parent))
        api = FakeAPI(json.loads(FIXTURE.read_text()) if feed is None else feed)
        coordinator = TauronDataUpdateCoordinator(hass, None, api, update_minutes=60 * 168)
        await coordinator.async_refresh()
        try:
            await scenario(coordinator, api)
        finally:
            await coordinator.async_shutdown()
            await hass.async_stop(force=True)

    asyncio.run(main())


def test_arms_one_timer_at_next_boundary(clock):
    async def scenario(coordinator, api):
        coordinator.async_start_transition_timer()
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 17, 6)]

    run(scenario)


def test_firing_notifies_listeners_rearms_and_does_not_fetch(clock):
    async def scenario(coordinator, api):
        coordinator.async_start_transition_timer()
        seen = []
        coordinator.async_add_listener(
            lambda: seen.append(coordinator.data.schedule.is_active(clock.now))
        )
        calls_before = api.calls

        clock.fire()
        assert seen == [True]
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 17, 14)]

        clock.fire()
        assert seen == [True, False]
        assert len(clock.pending) == 1
        assert api.calls == calls_before

    run(scenario)


def test_rearms_after_refresh_with_changed_schedule(clock):
    async def scenario(coordinator, api):
        coordinator.async_start_transition_timer()
        api.feed = {
            "OutageItems": [
                {
                    "startDate": "2026-11-15T10:00:00",
                    "endDate": "2026-11-15T12:00:00",
                    "Message": "Ogrodnica",
                }
            ]
        }
        await coordinator.async_refresh()
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 15, 9)]

    run(scenario)


def test_no_timer_without_upcoming_boundary(clock):
    async def scenario(coordinator, api):
        coordinator.async_start_transition_timer()
        assert clock.pending == []

    run(scenario, feed={"OutageItems": []})


def test_no_timer_after_last_boundary(clock):
    clock.now = utc(2026, 12, 1)

    async def scenario(coordinator, api):
        coordinator.async_start_transition_timer()
        assert clock.pending == []

    run(scenario)


def test_stop_cancels_pending_timer_and_stops_rearming(clock):
    async def scenario(coordinator, api):
        stop = coordinator.async_start_transition_timer()
        assert len(clock.pending) == 1
        stop()
        assert clock.pending == []
        await coordinator.async_refresh()
        assert clock.pending == []

    run(scenario)
