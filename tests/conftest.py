from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from homeassistant.components import logger
from homeassistant.components.logger import helpers
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

import tauron_outages
from tauron_outages import TauronDataUpdateCoordinator
from tauron_outages.address import Address
from tauron_outages.outage_feed_source import OutageFeedSource

logger._clear_logger_overwrites = helpers._clear_logger_overwrites

pytest_plugins = ["pytest_homeassistant_custom_component.plugins"]

UTC = timezone.utc
ADDRESS = Address(
    city_gaid="111",
    street_gaid="222",
    house_no="12A",
    city_name="Ogrodnica",
    city_label="Ogrodnica (gm. Środa Śląska, pow. średzki, dolnośląskie)",
    commune="Środa Śląska",
    street_label="",
)
FIXTURE = Path(__file__).parent / "fixtures" / "feed_ogrodnica_chwalimierz.json"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


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
        transport = FixtureTransport(json.loads(FIXTURE.read_text()) if feed is None else feed)
        source = OutageFeedSource(ADDRESS, transport, dt_util.get_default_time_zone())
        coordinator = TauronDataUpdateCoordinator(
            hass, None, source, update_minutes=60 * 168, locality=locality
        )
        await coordinator.async_refresh()
        try:
            await scenario(coordinator, transport)
        finally:
            await coordinator.async_shutdown()
            await hass.async_stop(force=True)

    asyncio.run(main())



class FixtureTransport:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.requests: list[dict[str, str]] = []

    async def __call__(self, params: dict[str, str]):
        self.requests.append(dict(params))
        if self.error is not None:
            raise self.error
        return self.payload
