"""Tauron API client for power outages."""
import logging
import urllib.parse
import urllib.request
import urllib.error
import time
import asyncio
import json
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.tauron-dystrybucja.pl/waapi/outages/address"
TIMEOUT = 30


class TauronAPIError(Exception):
    """Exception for Tauron API errors."""
    pass


class TauronAPI:
    """Client for Tauron power outages API."""
    
    def __init__(self, city_gaid: str, street_gaid: str, house_no: str):
        """Initialize the API client."""
        self.city_gaid = city_gaid
        self.street_gaid = street_gaid
        self.house_no = house_no
        
    async def async_get_outages(self) -> Any:
        """Fetch the raw Outage feed (parsed JSON) for the configured address."""
        try:
            now = datetime.now(timezone.utc)
            from_date = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            to_date = (now + timedelta(days=7)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            
            params = {
                "cityGAID": self.city_gaid,
                "streetGAID": self.street_gaid,
                "houseNo": self.house_no,
                "getLightingSupport": "true",
                "getServicedSwitchingoff": "true",
                "fromDate": from_date,
                "toDate": to_date,
                "_": str(int(time.time() * 1000))
            }
            
            url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
            _LOGGER.debug("Requesting URL: %s", url)
            
            def _fetch() -> Any:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    status = getattr(resp, "status", 200)
                    if status and int(status) >= 400:
                        raise urllib.error.HTTPError(url, status, "HTTP error", hdrs=None, fp=None)
                    raw = resp.read()
                    return json.loads(raw.decode("utf-8"))
            
            data = await asyncio.to_thread(_fetch)
            _LOGGER.debug("API response: %s", data)
            return data

        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as err:
            _LOGGER.error("Error fetching outages from Tauron API: %s", err)
            raise TauronAPIError(f"Failed to fetch outages: {err}") from err
        except (ValueError, KeyError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Tauron API response: %s", err)
            raise TauronAPIError(f"Invalid response format: {err}") from err
