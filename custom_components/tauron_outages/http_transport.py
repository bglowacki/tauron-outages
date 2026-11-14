import asyncio
import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from .outage_feed_source import Transport

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.tauron-dystrybucja.pl/waapi/outages/address"
TIMEOUT = 30


def urllib_transport(base_url: str = BASE_URL, timeout: float = TIMEOUT) -> Transport:

    async def fetch(params: dict[str, str]) -> Any:
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        _LOGGER.debug("Requesting URL: %s", url)

        def _fetch() -> Any:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))

        return await asyncio.to_thread(_fetch)

    return fetch
