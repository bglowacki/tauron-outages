import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_LOCALITY,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)
from .address import Address
from .address_search import AddressSearch
from .http_transport import CITIES_URL, STREETS_URL, aiohttp_transport
from .outage_feed_source import OutageFeedSource, OutageFeedError
from .outage_schedule import OutageSchedule

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    locality, update_minutes = _options_of(entry)
    coordinator = TauronDataUpdateCoordinator(
        hass, entry, outage_feed_source_for(hass, Address.from_entry_data(entry.data)), update_minutes=update_minutes, locality=locality
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


def outage_feed_source_for(hass: HomeAssistant, address: Address) -> OutageFeedSource:
    return OutageFeedSource(
        address, aiohttp_transport(async_get_clientsession(hass)), dt_util.get_default_time_zone()
    )


def address_search_for(hass: HomeAssistant) -> AddressSearch:
    session = async_get_clientsession(hass)
    return AddressSearch(
        aiohttp_transport(session, CITIES_URL), aiohttp_transport(session, STREETS_URL)
    )


def _options_of(entry: ConfigEntry) -> tuple[str, int]:
    locality = entry.options.get(CONF_LOCALITY) or ""
    hours = entry.options.get(CONF_UPDATE_INTERVAL_HOURS) or DEFAULT_UPDATE_INTERVAL_HOURS
    return locality, int(hours) * 60


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.error(
        "Entry %s was created by an older version; remove it and add it again", entry.title
    )
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class TauronDataUpdateCoordinator(DataUpdateCoordinator[OutageSchedule]):

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry | None,
        source: OutageFeedSource,
        *,
        update_minutes: int,
        locality: str = "",
    ) -> None:
        self.source = source
        self._locality = locality
        self._feed_schedule: OutageSchedule | None = None
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
        if self._feed_schedule is not None:
            self.data = self._feed_schedule.local(self._locality)
            self.async_update_listeners()

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
        if self.data is None:
            return
        when = self.data.next_transition(dt_util.utcnow())
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

    async def _async_update_data(self) -> OutageSchedule:
        try:
            self._feed_schedule = await self.source.fetch(dt_util.utcnow())
        except OutageFeedError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        return self._feed_schedule.local(self._locality)
