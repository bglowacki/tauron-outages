from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pytest
from freezegun.api import FrozenDateTimeFactory

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tauron_outages.const import DOMAIN
from custom_components.tauron_outages.http_transport import (
    BASE_URL,
    CITIES_URL,
    HOUSE_NUMBERS_URL,
    ONLY_STREET_URL,
    STREETS_URL,
)

FIXTURES = Path(__file__).parent / "fixtures"
FEED = json.loads((FIXTURES / "feed_ogrodnica_chwalimierz.json").read_text())
OGRODNICA = "118484"
WROCLAW = "119431"
OGRODNICA_STREET = "910691"
LEGNICKA = "897490"


def recorded(name: str):
    return json.loads((FIXTURES / "register" / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
async def setup(hass: HomeAssistant, enable_custom_integrations, freezer: FrozenDateTimeFactory):
    freezer.move_to(datetime(2026, 11, 14, tzinfo=timezone.utc))
    await hass.config.async_set_time_zone("Europe/Warsaw")


def mock_register(aioclient_mock: AiohttpClientMocker, only_street: bool = True) -> AiohttpClientMocker:
    for text, name in {
        "Ogrodn": "cities_ogrodn",
        "Ogrodnica": "cities_ogrodnica",
        "Wrocł": "cities_wrocl",
        "Wro": "cities_wro",
        "Wroclaw": "cities_wroclaw",
    }.items():
        aioclient_mock.get(CITIES_URL, params={"partName": text}, json=recorded(name))
    for city, text, name in [
        (OGRODNICA, "Ogrodnica", "streets_ogrodnica"),
        (WROCLAW, "Legn", "streets_wroclaw_legn"),
        (WROCLAW, "ska", "streets_wroclaw_ska"),
        (WROCLAW, "Wrocław", "streets_wroclaw_wroclaw"),
    ]:
        aioclient_mock.get(
            STREETS_URL, params={"partName": text, "ownerGAID": city}, json=recorded(name)
        )
    aioclient_mock.get(STREETS_URL, params={"partName": "Qqqzz"}, json=[])
    if only_street:
        aioclient_mock.get(
            ONLY_STREET_URL, params={"ownerGAID": OGRODNICA}, json=recorded("onlyonestreet_ogrodnica")
        )
    else:
        aioclient_mock.get(ONLY_STREET_URL, params={"ownerGAID": OGRODNICA}, status=500)
    aioclient_mock.get(
        ONLY_STREET_URL, params={"ownerGAID": WROCLAW}, json=recorded("onlyonestreet_wroclaw")
    )
    for city, street, text, name in [
        (OGRODNICA, OGRODNICA_STREET, "12", "housenumbers_ogrodnica_12"),
        (OGRODNICA, OGRODNICA_STREET, "22", "housenumbers_ogrodnica_22"),
        (OGRODNICA, OGRODNICA_STREET, "22A", "housenumbers_ogrodnica_22a"),
        (OGRODNICA, OGRODNICA_STREET, "999", None),
        (WROCLAW, LEGNICKA, "1", "housenumbers_wroclaw_legnicka_1"),
        (WROCLAW, LEGNICKA, "17", "housenumbers_wroclaw_legnicka_17"),
    ]:
        aioclient_mock.get(
            HOUSE_NUMBERS_URL,
            params={"partName": text, "cityGAID": city, "streetGAID": street},
            json=recorded(name) if name else [],
        )
    aioclient_mock.get(BASE_URL, json=FEED)
    return aioclient_mock


@pytest.fixture
def register(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    return mock_register(aioclient_mock)


@pytest.fixture
def register_without_only_street(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    return mock_register(aioclient_mock, only_street=False)


def field(result, name: str):
    for key, value in result["data_schema"].schema.items():
        if key == name:
            return key, value
    raise AssertionError(f"no field {name} in step {result['step_id']}")


def suggested(result, name: str):
    key, _ = field(result, name)
    return (key.description or {}).get("suggested_value")


def options(result, name: str) -> list[tuple[str, str]]:
    _, selector = field(result, name)
    return [(o["value"], o["label"]) for o in selector.config["options"]]


async def start(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def submit(hass: HomeAssistant, result, **user_input):
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def at_street_search(hass: HomeAssistant, city: str):
    result = await start(hass)
    if city == OGRODNICA:
        return await submit(hass, result, city="Ogrodnica")
    result = await submit(hass, result, city="Wrocł")
    return await submit(hass, result, city=WROCLAW)


async def at_details(hass: HomeAssistant):
    return await submit(hass, await start(hass), city="Ogrodnica")


async def at_legnicka(hass: HomeAssistant):
    result = await at_street_search(hass, WROCLAW)
    result = await submit(hass, result, street="Legn")
    return await submit(hass, result, street=LEGNICKA)


async def test_village_with_one_street_goes_straight_to_the_house_number(hass, register):
    result = await submit(hass, await start(hass), city="Ogrodnica")

    assert result["step_id"] == "details"
    assert result["errors"] in (None, {})
    assert result["description_placeholders"]["street"] == "Ogrodnica (no street)"


async def test_town_goes_to_the_street_search_prefilled_with_its_name(hass, register):
    result = await at_street_search(hass, WROCLAW)

    assert result["step_id"] == "street"
    assert suggested(result, "street") == "Wrocław"


async def test_village_falls_back_to_the_street_search_when_tauron_cannot_say(
    hass, register_without_only_street
):
    result = await at_street_search(hass, OGRODNICA)

    assert result["step_id"] == "street"
    assert suggested(result, "street") == "Ogrodnica"


async def test_several_city_matches_are_picked_by_their_labels(hass, register):
    result = await submit(hass, await start(hass), city="Ogrodn")

    assert result["step_id"] == "pick_city"
    choices = options(result, "city")
    assert len(choices) == 17
    assert choices[0] == (OGRODNICA, "Ogrodnica (gm. Środa Śląska, pow. średzki, Dolnośląskie)")
    assert choices[1] == ("130920", "Ogrodniczki (gm. Supraśl, pow. białostocki, Podlaskie)")

    result = await submit(hass, result, city=OGRODNICA)

    assert result["step_id"] == "details"


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (" Og ", "too_short"),
        ("Wroclaw", "no_matches"),
        ("Wro", "too_many"),
    ],
)
async def test_city_search_errors_keep_what_was_typed(hass, register, text, error):
    result = await submit(hass, await start(hass), city=text)

    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}
    assert result["description_placeholders"]["query"] == text.strip()
    assert suggested(result, "city") == text


async def test_too_short_city_search_does_not_ask_tauron(hass, register):
    calls = register.call_count

    await submit(hass, await start(hass), city="Og")

    assert register.call_count == calls


@pytest.mark.parametrize("response", [{"status": 500}, {"exc": aiohttp.ClientError()}, {"text": "<html>"}])
async def test_tauron_error_during_city_search_shows_cannot_connect_and_allows_retry(
    hass, aioclient_mock, response
):
    aioclient_mock.get(CITIES_URL, **response)
    result = await submit(hass, await start(hass), city="Ogrodnica")

    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}
    assert suggested(result, "city") == "Ogrodnica"

    aioclient_mock.clear_requests()
    mock_register(aioclient_mock)
    result = await submit(hass, result, city="Ogrodnica")

    assert result["step_id"] == "details"


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("Le", "too_short"),
        ("Qqqzz", "no_matches"),
        ("ska", "too_many"),
    ],
)
async def test_street_search_errors_keep_what_was_typed(hass, register, text, error):
    result = await at_street_search(hass, WROCLAW)
    assert suggested(result, "street") == "Wrocław"

    result = await submit(hass, result, street=text)

    assert result["step_id"] == "street"
    assert result["errors"] == {"base": error}
    assert result["description_placeholders"]["query"] == text
    assert suggested(result, "street") == text


@pytest.mark.parametrize("text", ["22a", " 22 ", "7/3", "15 B", "12a/4"])
async def test_house_number_in_street_search_points_back_to_the_city_name(
    hass, register, text
):
    result = await at_street_search(hass, WROCLAW)
    calls = register.call_count

    result = await submit(hass, result, street=text)

    assert register.call_count == calls
    assert result["step_id"] == "street"
    assert result["errors"] == {"base": "house_number"}
    assert result["description_placeholders"]["query"] == text.strip()
    assert result["description_placeholders"]["city_name"] == "Wrocław"
    assert suggested(result, "street") == "Wrocław"

    result = await submit(hass, result, street="Wrocław")

    assert result["step_id"] == "pick_street"


@pytest.mark.parametrize("text", ["3 Maja", "11 Listopada"])
async def test_street_named_after_a_date_is_searched(hass, register, text):
    register.get(STREETS_URL, params={"partName": text, "ownerGAID": WROCLAW}, json=[])
    result = await at_street_search(hass, WROCLAW)
    calls = register.call_count

    result = await submit(hass, result, street=text)

    assert register.call_count == calls + 1
    assert result["errors"] == {"base": "no_matches"}


async def test_tauron_error_during_street_search_shows_cannot_connect(hass, register):
    result = await at_street_search(hass, WROCLAW)
    register.clear_requests()
    register.get(STREETS_URL, status=500)

    result = await submit(hass, result, street="Legn")

    assert result["step_id"] == "street"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_village_unnamed_street_is_offered_even_as_the_only_match(
    hass, register_without_only_street
):
    result = await at_street_search(hass, OGRODNICA)

    result = await submit(hass, result, street="Ogrodnica")

    assert result["step_id"] == "pick_street"
    assert options(result, "street") == [(OGRODNICA_STREET, "Ogrodnica (no street)")]


async def test_town_streets_are_shown_by_their_full_names(hass, register):
    result = await at_street_search(hass, WROCLAW)

    result = await submit(hass, result, street="Legn")

    assert result["step_id"] == "pick_street"
    assert options(result, "street") == [(LEGNICKA, "ul. Legnicka")]


async def test_town_street_without_prefix_is_not_taken_for_an_unnamed_street(hass, register):
    result = await at_street_search(hass, WROCLAW)

    result = await submit(hass, result, street="Wrocław")

    labels = [label for _, label in options(result, "street")]
    assert labels[:2] == ["A8", "ul. Inowrocławska"]
    assert not [label for label in labels if "no street" in label]


async def test_details_prefill_name_and_locality_with_the_city_name(hass, register):
    result = await at_details(hass)

    assert result["step_id"] == "details"
    assert suggested(result, "name") == "Ogrodnica"
    assert suggested(result, "locality") == "Ogrodnica"
    assert result["description_placeholders"]["street"] == "Ogrodnica (no street)"


async def test_finishing_creates_entry_with_gaids_and_names(hass, register):
    result = await submit(
        hass, await at_details(hass), house_no="12", name="Dom", locality="Chwalimierz"
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dom"
    entry = result["result"]
    assert entry.version == 3
    assert entry.unique_id == f"{OGRODNICA}_{OGRODNICA_STREET}_12"
    assert dict(entry.data) == {
        "city_gaid": OGRODNICA,
        "street_gaid": OGRODNICA_STREET,
        "house_no": "12",
        "name": "Dom",
        "city_name": "Ogrodnica",
        "city_label": "Ogrodnica (gm. Środa Śląska, pow. średzki, Dolnośląskie)",
        "commune": "Środa Śląska",
        "street_label": "",
    }
    assert dict(entry.options) == {"locality": "Chwalimierz"}
    feed_request = next(url for _, url, _, _ in register.mock_calls if url.path.endswith("address"))
    assert feed_request.query["cityGAID"] == OGRODNICA
    assert feed_request.query["streetGAID"] == OGRODNICA_STREET
    assert feed_request.query["houseNo"] == "12"


async def test_town_entry_stores_the_street_label(hass, register):
    result = await submit(hass, await at_legnicka(hass), house_no="17", name="Wrocław", locality="")
    await hass.async_block_till_done()

    entry = result["result"]
    assert entry.data["street_label"] == "ul. Legnicka"
    assert entry.data["city_name"] == "Wrocław"
    assert dict(entry.options) == {"locality": ""}


@pytest.mark.parametrize("response", [{"status": 500}, {"exc": aiohttp.ClientError()}, {"text": "<html>"}])
async def test_feed_error_on_the_last_step_shows_cannot_connect(
    hass, register, caplog, response
):
    result = await at_details(hass)
    register.clear_requests()
    register.get(BASE_URL, **response)
    mock_register(register)

    result = await submit(hass, result, house_no="12", name="Dom", locality="Ogrodnica")

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "details"
    assert result["errors"] == {"base": "cannot_connect"}
    assert "Unexpected exception" not in caplog.text


async def test_duplicate_address_aborts(hass, register):
    MockConfigEntry(
        domain=DOMAIN, version=3, unique_id=f"{OGRODNICA}_{OGRODNICA_STREET}_12"
    ).add_to_hass(hass)

    result = await submit(
        hass, await at_details(hass), house_no="12", name="Second", locality="Ogrodnica"
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_unnamed_street_label_follows_the_ha_language(hass, register):
    hass.config.language = "pl"

    result = await at_details(hass)

    assert result["description_placeholders"]["street"] == "Ogrodnica (bez ulicy)"


async def test_house_number_is_stored_as_tauron_spells_it(hass, register):
    result = await submit(hass, await at_details(hass), house_no=" 22A ", name="Dom")
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].data["house_no"] == "22a"
    assert result["result"].unique_id == f"{OGRODNICA}_{OGRODNICA_STREET}_22a"


async def test_unknown_house_number_lists_tauron_numbers_containing_it(hass, register):
    result = await submit(hass, await at_legnicka(hass), house_no="1", name="Wrocław")

    assert result["step_id"] == "details"
    assert result["errors"] == {"base": "unknown_house_number"}
    assert result["description_placeholders"]["house_no"] == "1"
    assert result["description_placeholders"]["suggestions"] == ", ".join(
        recorded("housenumbers_wroclaw_legnicka_1")[:10]
    )
    assert suggested(result, "house_no") == "1"

    result = await submit(hass, result, house_no="17", name="Wrocław")

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_house_number_tauron_has_nothing_like_is_refused(hass, register):
    result = await submit(hass, await at_details(hass), house_no="999", name="Dom")

    assert result["step_id"] == "details"
    assert result["errors"] == {"base": "house_number_not_found"}
    assert result["description_placeholders"]["house_no"] == "999"


@pytest.mark.parametrize("response", [{"status": 500}, {"exc": aiohttp.ClientError()}, {"text": "<html>"}, {"json": {"a": 1}}])
async def test_tauron_error_while_checking_the_house_number_shows_cannot_connect(
    hass, aioclient_mock, response
):
    aioclient_mock.get(HOUSE_NUMBERS_URL, **response)
    mock_register(aioclient_mock)

    result = await submit(hass, await at_details(hass), house_no="12", name="Dom")

    assert result["step_id"] == "details"
    assert result["errors"] == {"base": "cannot_connect"}
