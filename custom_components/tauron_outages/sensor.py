"""Sensor platform for Tauron Power Outages."""
from datetime import datetime
import logging
from homeassistant.util import dt as dt_util
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TauronDataUpdateCoordinator
from .const import DOMAIN, SENSOR_TYPES, CONF_NAME, CONF_FILTER_TYPE, CONF_FILTER_MESSAGE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tauron sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
    for sensor_type, sensor_config in SENSOR_TYPES.items():
        # Always add filtered sensors; they will reflect current options (may yield 0/empty when no filters configured)
        entities.append(
            TauronSensor(
                coordinator,
                config_entry,
                sensor_type,
                sensor_config,
            )
        )

    async_add_entities(entities, False)


class TauronSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Tauron power outage sensor."""

    def __init__(
        self,
        coordinator: TauronDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        sensor_config: Dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._sensor_type = sensor_type
        self._config_entry = config_entry
        self._attr_name = f"{config_entry.data.get(CONF_NAME, 'Tauron')} {sensor_config['name']}"
        self._attr_unique_id = f"{config_entry.entry_id}_{sensor_type}"
        self._attr_icon = sensor_config["icon"]
        
        if sensor_config.get("device_class"):
            self._attr_device_class = sensor_config["device_class"]

    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._config_entry.data.get(CONF_NAME, "Tauron Outages"),
            "manufacturer": "Tauron Dystrybucja",
            "model": "Power Outages",
            "sw_version": "1.0.0",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        data = self.coordinator.data
        
        if self._sensor_type == "outage_status":
            return "Active" if data.get("is_active", False) else "Inactive"
        
        elif self._sensor_type == "next_outage":
            next_outage = data.get("next_outage")
            if next_outage and "parsed_start_time" in next_outage:
                return next_outage["parsed_start_time"]
            return None
        
        elif self._sensor_type == "outage_count":
            return data.get("outage_count", 0)
        
        elif self._sensor_type == "outage_items":
            # State = number of outages; details go into attributes
            return data.get("outage_count", 0)
        
        elif self._sensor_type == "filtered_next_outage":
            next_outage = data.get("filtered_next_outage")
            if next_outage and "parsed_start_time" in next_outage:
                return next_outage["parsed_start_time"]
            return None
        
        elif self._sensor_type == "filtered_outage_count":
            return data.get("filtered_outage_count", 0)
        
        elif self._sensor_type == "filtered_outage_items":
            return data.get("filtered_outage_count", 0)
        
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        attributes = {}
        data = self.coordinator.data
        
        if self._sensor_type == "outage_status":
            attributes["is_active"] = data.get("is_active", False)
            attributes["total_outages"] = data.get("outage_count", 0)
            
            # Add info about next outage
            next_outage = data.get("next_outage")
            if next_outage:
                attributes["next_outage_start"] = next_outage.get("startDate") or next_outage.get("start_date")
                attributes["next_outage_end"] = next_outage.get("endDate") or next_outage.get("end_date")
                attributes["next_outage_reason"] = (
                    next_outage.get("reason")
                    or next_outage.get("description")
                    or next_outage.get("message")
                    or next_outage.get("Message")
                    or "Unknown"
                )
        
        elif self._sensor_type == "next_outage":
            next_outage = data.get("next_outage")
            if next_outage:
                attributes["end_time"] = next_outage.get("endDate") or next_outage.get("end_date")
                attributes["reason"] = (
                    next_outage.get("reason")
                    or next_outage.get("description")
                    or next_outage.get("message")
                    or next_outage.get("Message")
                    or "Unknown"
                )
                attributes["type"] = next_outage.get("type") or next_outage.get("TypeId") or "Unknown"
        
        elif self._sensor_type == "outage_count":
            outages = data.get("outages", [])
            if outages:
                # Group outages by type or status
                active_count = sum(1 for o in outages if self._is_outage_active_now(o))
                upcoming_count = sum(1 for o in outages if self._is_outage_upcoming(o))
                
                attributes["active_outages"] = active_count
                attributes["upcoming_outages"] = upcoming_count
                attributes["is_active"] = data.get("is_active", False)
        
        elif self._sensor_type == "outage_items":
            outages = data.get("outages", [])
            # Provide a normalized list so UI templates can iterate reliably
            def _norm(o: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "outageId": o.get("outageId") or o.get("OutageId"),
                    "startDate": o.get("startDate") or o.get("start_date"),
                    "endDate": o.get("endDate") or o.get("end_date"),
                    "message": (
                        o.get("message")
                        or o.get("Message")
                        or o.get("reason")
                        or o.get("description")
                        or o.get("Description")
                    ),
                    "type": o.get("type") or o.get("TypeId") or o.get("typeId"),
                    "isActive": o.get("isActive") or o.get("IsActive"),
                    "modified": o.get("modified") or o.get("Modified"),
                }

            attributes["outages"] = [_norm(o) for o in outages]
            attributes["total_outages"] = data.get("outage_count", 0)
            # Optional quick flags for convenience
            attributes["has_active"] = any(self._is_outage_active_now(o) for o in outages)
            attributes["has_upcoming"] = any(self._is_outage_upcoming(o) for o in outages)
        
        elif self._sensor_type == "filtered_outage_count":
            outages = data.get("filtered_outages", [])
            if outages:
                active_count = sum(1 for o in outages if self._is_outage_active_now(o))
                upcoming_count = sum(1 for o in outages if self._is_outage_upcoming(o))
                attributes["active_outages"] = active_count
                attributes["upcoming_outages"] = upcoming_count
                attributes["is_active"] = any(self._is_outage_active_now(o) for o in outages)
        
        elif self._sensor_type == "filtered_next_outage":
            next_outage = data.get("filtered_next_outage")
            if next_outage:
                attributes["end_time"] = next_outage.get("endDate") or next_outage.get("end_date")
                attributes["reason"] = (
                    next_outage.get("reason")
                    or next_outage.get("description")
                    or next_outage.get("message")
                    or next_outage.get("Message")
                    or "Unknown"
                )
                attributes["type"] = next_outage.get("type") or next_outage.get("TypeId") or "Unknown"
        
        elif self._sensor_type == "filtered_outage_items":
            outages = data.get("filtered_outages", [])
            def _norm(o: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "outageId": o.get("outageId") or o.get("OutageId"),
                    "startDate": o.get("startDate") or o.get("start_date"),
                    "endDate": o.get("endDate") or o.get("end_date"),
                    "message": (
                        o.get("message")
                        or o.get("Message")
                        or o.get("reason")
                        or o.get("description")
                        or o.get("Description")
                    ),
                    "type": o.get("type") or o.get("TypeId") or o.get("typeId"),
                    "isActive": o.get("isActive") or o.get("IsActive"),
                    "modified": o.get("modified") or o.get("Modified"),
                }
            attributes["outages"] = [_norm(o) for o in outages]
            attributes["total_outages"] = data.get("filtered_outage_count", 0)
            attributes["has_active"] = any(self._is_outage_active_now(o) for o in outages)
            attributes["has_upcoming"] = any(self._is_outage_upcoming(o) for o in outages)

        return attributes

    def _is_outage_active_now(self, outage: Dict[str, Any]) -> bool:
        """Check if an outage is currently active."""
        try:
            now = dt_util.utcnow()
            start_time_str = outage.get('startDate') or outage.get('start_date')
            end_time_str = outage.get('endDate') or outage.get('end_date')
            
            if not start_time_str or not end_time_str:
                return False
            
            start_time = self.coordinator.api._parse_datetime(start_time_str)
            end_time = self.coordinator.api._parse_datetime(end_time_str)
            
            if start_time and end_time:
                return start_time <= now <= end_time
        except (ValueError, TypeError):
            pass
        
        return False

    def _is_outage_upcoming(self, outage: Dict[str, Any]) -> bool:
        """Check if an outage is upcoming."""
        try:
            now = dt_util.utcnow()
            start_time_str = outage.get('startDate') or outage.get('start_date')
            
            if not start_time_str:
                return False
            
            start_time = self.coordinator.api._parse_datetime(start_time_str)
            
            if start_time:
                return start_time > now
        except (ValueError, TypeError):
            pass
        
        return False
