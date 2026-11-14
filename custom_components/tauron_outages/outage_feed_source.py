from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Awaitable, Callable

from .outage_schedule import OutageSchedule

WINDOW = timedelta(days=7)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MILLISECOND = timedelta(milliseconds=1)


class OutageFeedError(Exception):
    pass


type Transport = Callable[[dict[str, str]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Address:
    city_gaid: str
    street_gaid: str
    house_no: str


class OutageFeedSource:

    def __init__(self, address: Address, transport: Transport, local_tz: tzinfo) -> None:
        self._address = address
        self._transport = transport
        self._local_tz = local_tz

    async def fetch(self, now: datetime) -> OutageSchedule:
        try:
            feed = await self._transport(self._request(now))
        except OutageFeedError:
            raise
        except (OSError, ValueError) as err:
            raise OutageFeedError(f"Failed to fetch outages: {err!r}") from err
        return OutageSchedule.from_feed(feed, self._local_tz)

    def _request(self, now: datetime) -> dict[str, str]:
        since_epoch = (now - EPOCH) // MILLISECOND
        start = EPOCH + since_epoch * MILLISECOND
        return {
            "cityGAID": self._address.city_gaid,
            "streetGAID": self._address.street_gaid,
            "houseNo": self._address.house_no,
            "getLightingSupport": "true",
            "getServicedSwitchingoff": "true",
            "fromDate": _timestamp(start),
            "toDate": _timestamp(start + WINDOW),
            "_": str(since_epoch),
        }


def _timestamp(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
