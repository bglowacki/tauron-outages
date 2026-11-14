import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, UPDATE_INTERVAL, CONF_UPDATE_INTERVAL_HOURS
from .outage_schedule import OutageSchedule
from .tauron_api import TauronAPI, TauronAPIError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    api = TauronAPI(
        city_gaid=entry.data["city_gaid"],
        street_gaid=entry.data["street_gaid"],
        house_no=entry.data["house_no"],
    )

    hours_opt = None
    try:
        hours_opt = entry.options.get(CONF_UPDATE_INTERVAL_HOURS) if entry.options else None
    except Exception:
        hours_opt = None
    update_minutes = (int(hours_opt) * 60) if hours_opt else UPDATE_INTERVAL

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

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(coordinator.async_start_transition_timer())

    async def _update_listener(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
        coord: TauronDataUpdateCoordinator = hass.data[DOMAIN][updated_entry.entry_id]
        new_filters = {
            "filter_type": (updated_entry.options.get("filter_type") if updated_entry.options else None) or updated_entry.data.get("filter_type"),
            "filter_message": (updated_entry.options.get("filter_message") if updated_entry.options else None) or updated_entry.data.get("filter_message"),
        }
        if getattr(coord, "_filters", None) != new_filters:
            _LOGGER.debug("Applying updated filters for entry_id=%s: %s", updated_entry.entry_id, new_filters)
            coord._filters = new_filters
            await coord.async_request_refresh()
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

    _LOGGER.debug("Forwarding platforms %s for entry_id=%s", PLATFORMS, entry.entry_id)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except AttributeError:
        for platform in PLATFORMS:
            _LOGGER.debug("Forwarding platform %s for entry_id=%s", platform, entry.entry_id)
            await hass.config_entries.async_forward_entry_setup(entry, platform)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class TauronDataUpdateCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, api: TauronAPI, *, update_minutes: int, filters: dict = None) -> None:
        self.api = api
        self._filters = filters or {}
        self._unsub_transition: CALLBACK_TYPE | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_minutes),
        )

    @callback
    def async_start_transition_timer(self) -> CALLBACK_TYPE:
        remove_listener = self.async_add_listener(self._arm_transition)
        self._arm_transition()

        @callback
        def stop() -> None:
            remove_listener()
            self._cancel_transition()

        return stop

    @callback
    def _arm_transition(self) -> None:
        self._cancel_transition()
        if not self.data:
            return
        when = self.data.schedule.next_transition(dt_util.utcnow())
        if when is not None:
            self._unsub_transition = async_track_point_in_utc_time(
                self.hass, self._on_transition, when
            )

    @callback
    def _cancel_transition(self) -> None:
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None

    @callback
    def _on_transition(self, _now) -> None:
        self._unsub_transition = None
        self.async_update_listeners()

    async def _async_update_data(self) -> "TauronData":
        try:
            feed = await self.api.async_get_outages()
        except TauronAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        schedule = OutageSchedule.from_feed(feed, dt_util.get_default_time_zone())
        filtered = schedule.local(self._filters.get("filter_message")).of_type(
            self._filters.get("filter_type")
        )
        return TauronData(schedule=schedule, filtered=filtered)


@dataclass(frozen=True, slots=True)
class TauronData:

    schedule: OutageSchedule
    filtered: OutageSchedule
