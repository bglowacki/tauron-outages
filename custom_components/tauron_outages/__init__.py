"""The Tauron Power Outages integration."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL, CONF_UPDATE_INTERVAL_HOURS
from .tauron_api import TauronAPI, TauronAPIError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tauron Power Outages from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    api = TauronAPI(
        city_gaid=entry.data["city_gaid"],
        street_gaid=entry.data["street_gaid"],
        house_no=entry.data["house_no"],
    )

    # Determine update interval from options (hours) or default (minutes)
    hours_opt = None
    try:
        hours_opt = entry.options.get(CONF_UPDATE_INTERVAL_HOURS) if entry.options else None
    except Exception:
        hours_opt = None
    update_minutes = (int(hours_opt) * 60) if hours_opt else UPDATE_INTERVAL

    # Create data update coordinator
    coordinator = TauronDataUpdateCoordinator(
        hass,
        api,
        update_minutes=update_minutes,
        filters={
            "filter_type": (entry.options.get("filter_type") if entry.options else None) or entry.data.get("filter_type"),
            "filter_message": (entry.options.get("filter_message") if entry.options else None) or entry.data.get("filter_message"),
        },
    )
    _LOGGER.debug("Starting first refresh for entry_id=%s", entry.entry_id)
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("First refresh completed for entry_id=%s", entry.entry_id)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Listen for options updates to apply filters without full reload
    async def _update_listener(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        coord: TauronDataUpdateCoordinator = hass.data[DOMAIN][updated_entry.entry_id]
        new_filters = {
            "filter_type": (updated_entry.options.get("filter_type") if updated_entry.options else None) or updated_entry.data.get("filter_type"),
            "filter_message": (updated_entry.options.get("filter_message") if updated_entry.options else None) or updated_entry.data.get("filter_message"),
        }
        # Apply filters if changed
        if getattr(coord, "_filters", None) != new_filters:
            _LOGGER.debug("Applying updated filters for entry_id=%s: %s", updated_entry.entry_id, new_filters)
            coord._filters = new_filters  # internal, acceptable within integration scope
            await coord.async_request_refresh()
        # Apply update interval change if provided
        try:
            hours_opt = updated_entry.options.get(CONF_UPDATE_INTERVAL_HOURS) if updated_entry.options else None
        except Exception:
            hours_opt = None
        new_minutes = (int(hours_opt) * 60) if hours_opt else UPDATE_INTERVAL
        if getattr(coord, "update_interval", None) is not None:
            if coord.update_interval != timedelta(minutes=new_minutes):
                _LOGGER.debug(
                    "Updating polling interval for entry_id=%s from %s to %s minutes",
                    updated_entry.entry_id,
                    int(coord.update_interval.total_seconds() / 60) if coord.update_interval else None,
                    new_minutes,
                )
                coord.update_interval = timedelta(minutes=new_minutes)

    entry.async_on_unload(entry.add_update_listener(_update_listener))

    # Set up platforms
    _LOGGER.debug("Forwarding platforms %s for entry_id=%s", PLATFORMS, entry.entry_id)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except AttributeError:
        # Backward compatibility
        for platform in PLATFORMS:
            _LOGGER.debug("Forwarding platform %s for entry_id=%s", platform, entry.entry_id)
            await hass.config_entries.async_forward_entry_setup(entry, platform)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class TauronDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Tauron API."""

    def __init__(self, hass: HomeAssistant, api: TauronAPI, *, update_minutes: int, filters: dict = None) -> None:
        """Initialize."""
        self.api = api
        self._filters = filters or {}
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_minutes),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            outages = await self.api.async_get_outages()
            next_outage = self.api.get_next_outage(outages)
            is_active = self.api.is_outage_active(outages)

            data = {
                "outages": outages,
                "next_outage": next_outage,
                "is_active": is_active,
                "outage_count": len(outages),
            }

            # Apply filters if provided in config
            f_type = (self._filters.get("filter_type") or "").strip()
            f_msg = (self._filters.get("filter_message") or "").strip()
            if f_type or f_msg:
                f_type_cf = f_type.casefold()
                f_msg_cf = f_msg.casefold()

                def _match(o: dict) -> bool:
                    ok = True
                    if f_type:
                        # compare as string for robustness; normalize whitespace and case
                        o_type_str = str(o.get("type") or o.get("TypeId") or o.get("typeId") or "").strip()
                        ok = ok and (o_type_str.casefold() == f_type_cf)
                    if f_msg:
                        msg = (
                            o.get("message")
                            or o.get("Message")
                            or o.get("reason")
                            or o.get("description")
                            or o.get("Description")
                            or ""
                        )
                        ok = ok and (f_msg_cf in str(msg).casefold())
                    return ok
                filtered = [o for o in outages if _match(o)]
                data.update({
                    "filtered_outages": filtered,
                    "filtered_outage_count": len(filtered),
                    "filtered_next_outage": self.api.get_next_outage(filtered),
                })

            return data
        except TauronAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
