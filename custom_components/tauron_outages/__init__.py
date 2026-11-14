import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CITY_GAID,
    CONF_HOUSE_NO,
    CONF_LOCALITY,
    CONF_STREET_GAID,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)
from .migration import migrate_v1_to_v2
from .outage_schedule import OutageSchedule
from .tauron_api import TauronAPI, TauronAPIError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    api = TauronAPI(
        city_gaid=entry.data[CONF_CITY_GAID],
        street_gaid=entry.data[CONF_STREET_GAID],
        house_no=entry.data[CONF_HOUSE_NO],
    )

    locality, update_minutes = _options_of(entry)
    coordinator = TauronDataUpdateCoordinator(
        hass, entry, api, update_minutes=update_minutes, locality=locality
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(coordinator.async_start_transition_timer())
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    locality, update_minutes = _options_of(entry)
    coordinator: TauronDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_apply_options(locality=locality, update_minutes=update_minutes)


def _options_of(entry: ConfigEntry) -> tuple[str, int]:
    locality = entry.options.get(CONF_LOCALITY) or ""
    hours = entry.options.get(CONF_UPDATE_INTERVAL_HOURS) or DEFAULT_UPDATE_INTERVAL_HOURS
    return locality, int(hours) * 60


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 2:
        return False
    if entry.version == 1:
        data, options = migrate_v1_to_v2(entry.data, entry.options)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=2
        )
        _LOGGER.debug("Migrated entry_id=%s to version 2", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class TauronDataUpdateCoordinator(DataUpdateCoordinator):

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        api: TauronAPI,
        *,
        update_minutes: int,
        locality: str = "",
    ) -> None:
        self.api = api
        self._locality = locality
        self._unsub_transition: CALLBACK_TYPE | None = None

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=update_minutes),
        )

    @callback
    def async_apply_options(self, *, locality: str, update_minutes: int) -> None:
        self._locality = locality
        interval = timedelta(minutes=update_minutes)
        if interval != self.update_interval:
            self.update_interval = interval
            if self._listeners:
                self._schedule_refresh()
        if self.data is not None:
            self.data = self._with_local_outages(self.data.schedule)
            self.async_update_listeners()

    def _with_local_outages(self, schedule: OutageSchedule) -> "TauronData":
        return TauronData(schedule=schedule, local=schedule.local(self._locality))

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

        return self._with_local_outages(
            OutageSchedule.from_feed(feed, dt_util.get_default_time_zone())
        )


@dataclass(frozen=True, slots=True)
class TauronData:

    schedule: OutageSchedule
    local: OutageSchedule
