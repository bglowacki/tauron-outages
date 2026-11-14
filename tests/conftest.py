from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
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


def run(scenario, feed=None, locality=None):
    async def main():
        hass = HomeAssistant(str(Path(__file__).parent))
        api = FakeAPI(json.loads(FIXTURE.read_text()) if feed is None else feed)
        coordinator = TauronDataUpdateCoordinator(
            hass, None, api, update_minutes=60 * 168, locality=locality
        )
        await coordinator.async_refresh()
        try:
            await scenario(coordinator, api)
        finally:
            await coordinator.async_shutdown()
            await hass.async_stop(force=True)

    asyncio.run(main())

