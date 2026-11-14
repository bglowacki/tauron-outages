from __future__ import annotations

from datetime import timedelta

from conftest import run, utc
from tauron_outages.outage_feed import OutageFeedError


def test_arms_one_timer_at_next_boundary(clock):
    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 17, 6)]

    run(scenario)


def test_firing_notifies_listeners_rearms_and_does_not_fetch(clock):
    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        seen = []
        coordinator.async_add_listener(
            lambda: seen.append(coordinator.data.is_active(clock.now))
        )
        requests_before = len(transport.requests)

        clock.fire()
        assert seen == [True]
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 17, 14)]

        clock.fire()
        assert seen == [True, False]
        assert len(clock.pending) == 1
        assert len(transport.requests) == requests_before

    run(scenario)


def test_rearms_after_refresh_with_changed_schedule(clock):
    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        transport.payload = {
            "OutageItems": [
                {
                    "startDate": "2026-11-15T10:00:00",
                    "endDate": "2026-11-15T12:00:00",
                    "Message": "Ogrodnica",
                }
            ]
        }
        await coordinator.async_refresh()
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 15, 9)]

    run(scenario)


def test_no_timer_without_upcoming_boundary(clock):
    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        assert clock.pending == []

    run(scenario, feed={"OutageItems": []})


def test_no_timer_after_last_boundary(clock):
    clock.now = utc(2026, 12, 1)

    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        assert clock.pending == []

    run(scenario)


def test_stop_cancels_pending_timer_and_stops_rearming(clock):
    async def scenario(coordinator, transport):
        stop = coordinator.async_start_transition_timer()
        assert len(clock.pending) == 1
        stop()
        assert clock.pending == []
        await coordinator.async_refresh()
        assert clock.pending == []

    run(scenario)


def messages(schedule) -> list[str]:
    return [o.message.split(",")[0] for o in schedule.all()]


def test_data_is_the_local_schedule(clock):
    async def scenario(coordinator, transport):
        assert messages(coordinator.data) == ["Ogrodnica", "Ogrodnica"]

    run(scenario, locality="Ogrodnica")


def test_empty_locality_makes_every_outage_local(clock):
    async def scenario(coordinator, transport):
        assert coordinator.data.count == 6

    run(scenario, locality="")


def test_timer_follows_local_outage_boundaries(clock):
    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 19, 7)]
        clock.fire()
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 19, 11)]

    run(scenario, locality="Ogrodnica")


def test_apply_options_rearms_timer_for_new_locality(clock):
    async def scenario(coordinator, transport):
        coordinator.async_start_transition_timer()
        coordinator.async_apply_options(locality="", update_minutes=60 * 168)
        assert [t["when"] for t in clock.pending] == [utc(2026, 11, 17, 6)]

    run(scenario, locality="Ogrodnica")


def test_apply_options_changes_locality_without_fetching(clock):
    async def scenario(coordinator, transport):
        seen = []
        coordinator.async_add_listener(
            lambda: seen.append(messages(coordinator.data))
        )
        requests_before = len(transport.requests)

        coordinator.async_apply_options(locality="chwalimierz", update_minutes=60 * 168)

        assert seen == [["Chwalimierz"] * 4]
        assert len(transport.requests) == requests_before

    run(scenario, locality="Ogrodnica")


def test_apply_options_clearing_locality_shows_every_outage(clock):
    async def scenario(coordinator, transport):
        coordinator.async_apply_options(locality="", update_minutes=60 * 168)
        assert coordinator.data.count == 6

    run(scenario, locality="Ogrodnica")


def test_apply_options_changes_poll_interval(clock):
    async def scenario(coordinator, transport):
        coordinator.async_apply_options(locality="Ogrodnica", update_minutes=60)
        assert coordinator.update_interval == timedelta(hours=1)
        assert coordinator.data.count == 2

    run(scenario, locality="Ogrodnica")


def test_apply_options_keeps_failed_poll_unavailable(clock):
    async def scenario(coordinator, transport):
        transport.error = OutageFeedError("down")
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False

        coordinator.async_apply_options(locality="", update_minutes=60 * 168)

        assert coordinator.last_update_success is False
        assert coordinator.data.count == 6

    run(scenario, locality="Ogrodnica")


def test_polls_the_outage_feed_for_seven_days_from_the_current_time(clock):
    async def scenario(coordinator, transport):
        clock.now = utc(2026, 11, 15, 12)
        await coordinator.async_refresh()

        request = transport.requests[-1]
        assert (request["fromDate"], request["toDate"]) == (
            "2026-11-15T12:00:00.000Z",
            "2026-11-22T12:00:00.000Z",
        )

    run(scenario)
