from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tauron_outages.const import DOMAIN
from custom_components.tauron_outages.http_transport import BASE_URL

FEED = json.loads(
    (Path(__file__).parent / "fixtures" / "feed_ogrodnica_chwalimierz.json").read_text()
)
DATA = {
    "city_gaid": "118484",
    "street_gaid": "910691",
    "house_no": "12",
    "name": "Ogrodnica",
    "city_name": "Ogrodnica",
    "city_label": "Ogrodnica (gm. Środa Śląska, pow. średzki, Dolnośląskie)",
    "commune": "Środa Śląska",
    "street_label": "",
}
START = datetime(2026, 11, 14, tzinfo=timezone.utc)

STATUS = "sensor.ogrodnica_outage_status"
NEXT = "sensor.ogrodnica_next_outage"
COUNT = "sensor.ogrodnica_outage_count"
ITEMS = "sensor.ogrodnica_outage_items"
CALENDAR = "calendar.ogrodnica_outages"
ENTITIES = (STATUS, NEXT, COUNT, ITEMS, CALENDAR)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
async def warsaw(hass: HomeAssistant, enable_custom_integrations, freezer: FrozenDateTimeFactory):
    freezer.move_to(START)
    await hass.config.async_set_time_zone("Europe/Warsaw")


@pytest.fixture
def feed(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    aioclient_mock.get(BASE_URL, json=FEED)
    return aioclient_mock


def entry_with(locality: str = "Ogrodnica", **options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Ogrodnica",
        unique_id="118484_910691_12",
        data=DATA,
        options={"locality": locality, **options},
    )


async def set_up(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def travel(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()


def respond_with(aioclient_mock: AiohttpClientMocker, **response) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(BASE_URL, **response)


async def test_setup_creates_one_set_of_entities_with_clean_ids(hass, feed):
    entry = await set_up(hass, entry_with())

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {e.entity_id: e.unique_id for e in entities} == {
        STATUS: f"{entry.entry_id}_outage_status",
        NEXT: f"{entry.entry_id}_next_outage",
        COUNT: f"{entry.entry_id}_outage_count",
        ITEMS: f"{entry.entry_id}_outage_items",
        CALENDAR: f"{entry.entry_id}_calendar",
    }
    assert not [e for e in entities if "filtered" in e.entity_id or "local" in e.entity_id]


async def test_entities_show_only_local_outages(hass, feed):
    await set_up(hass, entry_with("Ogrodnica"))

    assert hass.states.get(STATUS).state == "Inactive"
    assert hass.states.get(STATUS).attributes["total_outages"] == 2
    assert hass.states.get(COUNT).state == "2"
    assert hass.states.get(NEXT).state == "2026-11-19T07:00:00+00:00"
    items = hass.states.get(ITEMS).attributes["outages"]
    assert [i["startDate"] for i in items] == ["2026-11-19T07:00:00Z", "2026-11-20T08:00:00Z"]
    assert all(i["message"].startswith("Ogrodnica") for i in items)


async def test_empty_locality_shows_every_outage(hass, feed):
    await set_up(hass, entry_with(""))

    assert hass.states.get(COUNT).state == "6"
    assert hass.states.get(NEXT).state == "2026-11-17T06:00:00+00:00"


async def change_options(hass: HomeAssistant, entry: MockConfigEntry, **user_input):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    return result


async def test_changing_locality_updates_entities_without_reload_or_fetch(hass, feed):
    entry = await set_up(hass, entry_with("Ogrodnica"))
    fetches = feed.call_count

    await change_options(hass, entry, locality="Chwalimierz", update_interval_hours=4)

    assert entry.state is ConfigEntryState.LOADED
    assert feed.call_count == fetches
    assert hass.states.get(COUNT).state == "4"
    assert hass.states.get(NEXT).state == "2026-11-17T06:00:00+00:00"


async def test_clearing_locality_really_clears_it(hass, feed):
    entry = await set_up(hass, entry_with("Ogrodnica"))

    await change_options(hass, entry, update_interval_hours=4)

    assert entry.options["locality"] == ""
    assert hass.states.get(COUNT).state == "6"


async def test_changing_poll_interval_changes_how_often_the_feed_is_fetched(
    hass, feed, freezer
):
    entry = await set_up(hass, entry_with("Ogrodnica"))
    await change_options(hass, entry, locality="Ogrodnica", update_interval_hours=1)
    fetches = feed.call_count

    await travel(hass, freezer, START + timedelta(hours=1, seconds=1))

    assert feed.call_count == fetches + 1


async def test_status_flips_at_local_outage_start_and_end_without_polling(hass, feed, freezer):
    await set_up(hass, entry_with("Ogrodnica", update_interval_hours=168))
    fetches = feed.call_count

    await travel(hass, freezer, utc(2026, 11, 19, 7))
    assert hass.states.get(STATUS).state == "Active"
    assert hass.states.get(CALENDAR).state == "on"

    await travel(hass, freezer, utc(2026, 11, 19, 11))
    assert hass.states.get(STATUS).state == "Inactive"
    assert hass.states.get(CALENDAR).state == "off"
    assert feed.call_count == fetches


async def test_next_outage_moves_on_when_a_local_outage_starts(hass, feed, freezer):
    await set_up(hass, entry_with("Ogrodnica", update_interval_hours=168))

    await travel(hass, freezer, utc(2026, 11, 19, 7))
    assert hass.states.get(NEXT).state == "2026-11-20T08:00:00+00:00"

    await travel(hass, freezer, utc(2026, 11, 20, 8))
    assert hass.states.get(NEXT).state == "unknown"


async def test_get_events_returns_local_outages_overlapping_the_range(hass, feed):
    await set_up(hass, entry_with("Ogrodnica"))

    response = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {
            "entity_id": CALENDAR,
            "start_date_time": "2026-11-19T11:00:00+00:00",
            "end_date_time": "2026-11-21T00:00:00+00:00",
        },
        blocking=True,
        return_response=True,
    )

    events = response[CALENDAR]["events"]
    assert [(e["start"], e["end"]) for e in events] == [
        ("2026-11-20T09:00:00+01:00", "2026-11-20T13:00:00+01:00")
    ]
    assert events[0]["summary"] == "⚡ Ogrodnica,"


async def test_calendar_end_trigger_fires_when_a_local_outage_ends(hass, feed, freezer):
    await set_up(hass, entry_with("Ogrodnica", update_interval_hours=168))
    when = utc(2026, 11, 19, 10, 7, 13)
    await travel(hass, freezer, when)
    calls = async_mock_service(hass, "test", "outage_ended")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "trigger": {"platform": "calendar", "event": "end", "entity_id": CALENDAR},
                "action": {
                    "service": "test.outage_ended",
                    "data": {"end": "{{ trigger.calendar_event.end }}"},
                },
            }
        },
    )
    await hass.async_block_till_done()

    while when <= utc(2026, 11, 19, 11, 30):
        when += timedelta(minutes=1)
        await travel(hass, freezer, when)

    assert [c.data["end"] for c in calls] == ["2026-11-19T12:00:00+01:00"]
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )


async def test_unload_removes_entities_and_cancels_the_transition_timer(hass, feed, freezer):
    entry = await set_up(hass, entry_with("Ogrodnica", update_interval_hours=168))

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert all(hass.states.get(e).state == STATE_UNAVAILABLE for e in ENTITIES)
    fetches = feed.call_count
    await travel(hass, freezer, utc(2026, 11, 19, 7))
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert feed.call_count == fetches


async def test_feed_error_makes_entities_unavailable_until_next_good_poll(hass, feed, freezer):
    await set_up(hass, entry_with("Ogrodnica"))

    respond_with(feed, status=503)
    await travel(hass, freezer, START + timedelta(hours=4, seconds=1))
    assert all(hass.states.get(e).state == STATE_UNAVAILABLE for e in ENTITIES)

    respond_with(feed, json=FEED)
    await travel(hass, freezer, START + timedelta(hours=8, seconds=2))
    assert hass.states.get(STATUS).state == "Inactive"
    assert hass.states.get(COUNT).state == "2"


async def test_device_shows_the_village_address(hass, feed):
    entry = await set_up(hass, entry_with())

    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert device.name == "Ogrodnica"
    assert device.model == "Ogrodnica 12, gm. Środa Śląska"


async def test_device_shows_the_town_street_address(hass, feed):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title="Dom",
        unique_id="119431_897490_1",
        data={
            "city_gaid": "119431",
            "street_gaid": "897490",
            "house_no": "1",
            "name": "Dom",
            "city_name": "Wrocław",
            "city_label": "Wrocław (gm. Wrocław, pow. Wrocław, Dolnośląskie)",
            "commune": "Wrocław",
            "street_label": "ul. Legnicka",
        },
        options={"locality": ""},
    )
    await set_up(hass, entry)

    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert device.model == "Wrocław, ul. Legnicka 1"
    assert hass.states.get("calendar.dom_outages") is not None


async def test_options_dialog_says_which_address_it_watches(hass, feed):
    entry = await set_up(hass, entry_with())

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["description_placeholders"] == {"address": "Ogrodnica 12, gm. Środa Śląska"}


@pytest.mark.parametrize("version", [1, 2])
async def test_entries_from_before_address_search_fail_migration(hass, feed, version):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=version,
        title="Ogrodnica",
        unique_id="111_222_12A",
        data={"city_gaid": "111", "street_gaid": "222", "house_no": "12A", "name": "Ogrodnica"},
        options={"locality": "Ogrodnica"},
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert hass.states.get(STATUS) is None
