from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Awaitable, Callable

from .outage_schedule import OutageSchedule

WINDOW = timedelta(days=7)


class OutageFeedError(Exception):
    pass


Transport = Callable[[dict[str, str]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Address:
    city_gaid: str
    street_gaid: str
    house_no: str


class OutageFeed:

    def __init__(self, address: Address, transport: Transport, local_tz: tzinfo) -> None:
        self._address = address
        self._transport = transport
        self._local_tz = local_tz

    async def fetch(self, now: datetime) -> OutageSchedule:
        feed = await self._transport(self._request(now))
        return OutageSchedule.from_feed(feed, self._local_tz)

    def _request(self, now: datetime) -> dict[str, str]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc).replace(microsecond=now.microsecond // 1000 * 1000)
        return {
            "cityGAID": self._address.city_gaid,
            "streetGAID": self._address.street_gaid,
            "houseNo": self._address.house_no,
            "getLightingSupport": "true",
            "getServicedSwitchingoff": "true",
            "fromDate": _timestamp(now),
            "toDate": _timestamp(now + WINDOW),
            "_": str(int(now.timestamp() * 1000)),
        }


def _timestamp(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
