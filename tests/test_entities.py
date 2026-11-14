from __future__ import annotations

from types import SimpleNamespace

from conftest import run, utc
from tauron_outages import calendar, sensor
from tauron_outages.const import DOMAIN

ENTRY = SimpleNamespace(entry_id="abc", data={"name": "Ogrodnica"})


async def setup_entities(coordinator):
    coordinator.hass.data[DOMAIN] = {ENTRY.entry_id: coordinator}
    entities = []
    for platform in (sensor, calendar):
        await platform.async_setup_entry(
            coordinator.hass, ENTRY, lambda new, _update: entities.extend(new)
        )
    for entity in entities:
        if isinstance(entity, sensor.TauronSensor):
            entity._evaluate()
    return {entity.unique_id: entity for entity in entities}


def test_one_set_of_entities_with_clean_ids_and_names(clock):
    async def scenario(coordinator, api):
        entities = await setup_entities(coordinator)
        assert {uid: e.name for uid, e in entities.items()} == {
            "abc_outage_status": "Ogrodnica Outage Status",
            "abc_next_outage": "Ogrodnica Next Outage",
            "abc_outage_count": "Ogrodnica Outage Count",
            "abc_outage_items": "Ogrodnica Outage Items",
            "abc_calendar": "Ogrodnica Outages",
        }

    run(scenario, locality="Ogrodnica")


def test_entities_show_only_local_outages(clock):
    async def scenario(coordinator, api):
        entities = await setup_entities(coordinator)
        assert entities["abc_outage_status"].extra_state_attributes["total_outages"] == 2
        assert entities["abc_next_outage"].native_value == utc(2026, 11, 19, 7)
        assert entities["abc_outage_count"].native_value == 2
        items = entities["abc_outage_items"].extra_state_attributes["outages"]
        assert all(i["message"].startswith("Ogrodnica") for i in items)
        events = await entities["abc_calendar"].async_get_events(
            coordinator.hass, utc(2026, 11, 14), utc(2026, 11, 21)
        )
        assert [e.start for e in events] == [utc(2026, 11, 19, 7), utc(2026, 11, 20, 8)]

    run(scenario, locality="Ogrodnica")


def test_empty_locality_shows_every_outage(clock):
    async def scenario(coordinator, api):
        entities = await setup_entities(coordinator)
        assert entities["abc_outage_count"].native_value == 6
        assert entities["abc_next_outage"].native_value == utc(2026, 11, 17, 6)

    run(scenario, locality="")


def test_calendar_event_is_active_local_outage_then_next(clock):
    async def scenario(coordinator, api):
        entities = await setup_entities(coordinator)
        cal = entities["abc_calendar"]
        assert cal.event.start == utc(2026, 11, 19, 7)
        clock.now = utc(2026, 11, 19, 9)
        assert cal.event.end == utc(2026, 11, 19, 11)
        clock.now = utc(2026, 11, 19, 12)
        assert cal.event.start == utc(2026, 11, 20, 8)

    run(scenario, locality="Ogrodnica")
