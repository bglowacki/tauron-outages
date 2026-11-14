import json
import logging
import urllib.parse
from typing import Any

import aiohttp
from yarl import URL

from .outage_feed_source import Transport

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.tauron-dystrybucja.pl/waapi/outages/address"
TIMEOUT = 30


def aiohttp_transport(
    session: aiohttp.ClientSession, base_url: str = BASE_URL, timeout: float = TIMEOUT
) -> Transport:

    async def fetch(params: dict[str, str]) -> Any:
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        _LOGGER.debug("Requesting URL: %s", url)
        try:
            async with session.get(
                URL(url, encoded=True), timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status >= 400:
                    raise OSError(f"HTTP {resp.status} from {base_url}")
                body = await resp.read()
        except aiohttp.ClientError as err:
            raise OSError(f"{err!r}") from err
        return json.loads(body.decode("utf-8"))

    return fetch
