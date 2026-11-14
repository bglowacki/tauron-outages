import asyncio
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .outage_feed import OutageFeedError, Transport

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.tauron-dystrybucja.pl/waapi/outages/address"
TIMEOUT = 30


def urllib_transport(base_url: str = BASE_URL, timeout: float = TIMEOUT) -> Transport:

    async def fetch(params: dict[str, str]) -> Any:
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        _LOGGER.debug("Requesting URL: %s", url)

        def _fetch() -> Any:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                if status and int(status) >= 400:
                    raise urllib.error.HTTPError(url, status, "HTTP error", hdrs=None, fp=None)
                raw = resp.read()
                return json.loads(raw.decode("utf-8"))

        try:
            data = await asyncio.to_thread(_fetch)
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as err:
            _LOGGER.error("Error fetching outages from Tauron API: %s", err)
            raise OutageFeedError(f"Failed to fetch outages: {err}") from err
        except ValueError as err:
            _LOGGER.error("Error parsing Tauron API response: %s", err)
            raise OutageFeedError(f"Invalid response format: {err}") from err
        _LOGGER.debug("API response: %s", data)
        return data

    return fetch
