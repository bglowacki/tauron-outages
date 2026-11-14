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
from typing import Dict, List, Optional, Any

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.tauron-dystrybucja.pl/waapi/outages/address"
TIMEOUT = 30


class TauronAPIError(Exception):
    """Exception for Tauron API errors."""
    pass


from homeassistant.util import dt as dt_util

class TauronAPI:
    """Client for Tauron power outages API."""
    
    def __init__(self, city_gaid: str, street_gaid: str, house_no: str):
        """Initialize the API client."""
        self.city_gaid = city_gaid
        self.street_gaid = street_gaid
        self.house_no = house_no
        
    async def async_get_outages(self) -> List[Dict[str, Any]]:
        """Get power outages for the configured address."""
        try:
            # Generate dates for the next 7 days
            now = dt_util.utcnow()
            # Ensure Z suffix
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
            
            # Run blocking HTTP call in a thread to avoid blocking the event loop
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
            
            # Normalize response: API may return a dict with 'OutageItems' or a list
            normalized: List[Dict[str, Any]] = []
            if isinstance(data, dict):
                items = data.get("OutageItems") or data.get("outageItems") or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            normalized.append(self._normalize_outage_item(item))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        normalized.append(self._normalize_outage_item(item))
            else:
                _LOGGER.warning("Unexpected API response type: %s", type(data))
            
            return normalized
            
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as err:
            _LOGGER.error("Error fetching outages from Tauron API: %s", err)
            raise TauronAPIError(f"Failed to fetch outages: {err}") from err
        except (ValueError, KeyError, json.JSONDecodeError) as err:
            _LOGGER.error("Error parsing Tauron API response: %s", err)
            raise TauronAPIError(f"Invalid response format: {err}") from err
    
    def _normalize_outage_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize various outage item key formats to a consistent schema.
        Expected keys after normalization:
          - startDate, endDate, message, type, isActive, outageId, modified
        All other original keys are preserved as well.
        """
        normalized: Dict[str, Any] = dict(item)  # keep originals as attributes
        # Dates
        start = item.get("startDate") or item.get("StartDate") or item.get("start_date")
        end = item.get("endDate") or item.get("EndDate") or item.get("end_date")
        if start is not None:
            normalized["startDate"] = start
        if end is not None:
            normalized["endDate"] = end
        # Message / description / reason
        msg = (
            item.get("message")
            or item.get("Message")
            or item.get("reason")
            or item.get("description")
            or item.get("Description")
        )
        if msg is not None:
            normalized["message"] = msg
        # Type
        typ = item.get("type") or item.get("TypeId") or item.get("typeId")
        if typ is not None:
            normalized["type"] = typ
        # Active flag
        is_active = item.get("isActive") or item.get("IsActive")
        if is_active is not None:
            normalized["isActive"] = is_active
        # IDs
        oid = item.get("outageId") or item.get("OutageId")
        if oid is not None:
            normalized["outageId"] = oid
        mod = item.get("modified") or item.get("Modified")
        if mod is not None:
            normalized["modified"] = mod
        return normalized
    
    def get_next_outage(self, outages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Get the next upcoming outage."""
        if not outages:
            return None
            
        now = dt_util.utcnow()
        upcoming_outages = []
        
        for outage in outages:
            try:
                # Parse start time (assuming ISO format)
                start_time_str = outage.get('startDate') or outage.get('start_date')
                if not start_time_str:
                    continue
                    
                # Handle different possible datetime formats
                start_time = self._parse_datetime(start_time_str)
                if start_time and start_time > now:
                    outage['parsed_start_time'] = start_time
                    upcoming_outages.append(outage)
                    
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Error parsing outage date: %s", err)
                continue
        
        if not upcoming_outages:
            return None
            
        # Sort by start time and return the earliest
        upcoming_outages.sort(key=lambda x: x['parsed_start_time'])
        return upcoming_outages[0]
    
    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        """Parse a datetime string and return a timezone-aware UTC datetime.
        Assumptions:
        - Strings ending with 'Z' are in UTC.
        - Naive strings (no tzinfo) are assumed to be in the system's local timezone (Home Assistant's configured tz) and converted to UTC.
        """
        # Try common formats quickly using strptime
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                dt_obj = datetime.strptime(date_str, fmt)
                if date_str.endswith("Z"):
                    return dt_obj.replace(tzinfo=timezone.utc)
                # Treat as local time and convert to UTC
                local_tz = dt_util.DEFAULT_TIME_ZONE
                dt_local = dt_obj.replace(tzinfo=local_tz)
                return dt_util.as_utc(dt_local)
            except ValueError:
                continue

        # As a fallback, try Home Assistant's parser which supports more formats
        try:
            parsed = dt_util.parse_datetime(date_str)
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                return dt_util.as_utc(parsed)
        except Exception:  # noqa: BLE001 - be defensive
            pass

        _LOGGER.warning("Unable to parse datetime: %s", date_str)
        return None
    
    def is_outage_active(self, outages: List[Dict[str, Any]]) -> bool:
        """Check if any outage is currently active."""
        now = dt_util.utcnow()
        
        for outage in outages:
            try:
                start_time_str = outage.get('startDate') or outage.get('start_date')
                end_time_str = outage.get('endDate') or outage.get('end_date')
                
                if not start_time_str or not end_time_str:
                    continue
                
                start_time = self._parse_datetime(start_time_str)
                end_time = self._parse_datetime(end_time_str)
                
                if start_time and end_time and start_time <= now <= end_time:
                    return True
                    
            except (ValueError, TypeError):
                continue
        
        return False
