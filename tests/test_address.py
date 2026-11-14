from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tauron_outages.address import Address
from tauron_outages.address_search import CityMatch, StreetMatch

MODULE = Path(__file__).parents[1] / "custom_components" / "tauron_outages" / "address.py"

OGRODNICA = CityMatch(
    gaid="118484",
    name="Ogrodnica",
    commune="Środa Śląska",
    district="średzki",
    province="dolnośląskie",
)
OGRODNICA_STREET = StreetMatch(gaid="910691", name="Ogrodnica", label="Ogrodnica", unnamed=True)
WROCLAW = CityMatch(
    gaid="119431",
    name="Wrocław",
    commune="Wrocław",
    district="Wrocław",
    province="dolnośląskie",
)
LEGNICKA = StreetMatch(gaid="897490", name="Legnicka", label="ul. Legnicka", unnamed=False)

VILLAGE_DATA = {
    "city_gaid": "118484",
    "street_gaid": "910691",
    "house_no": "12",
    "city_name": "Ogrodnica",
    "city_label": "Ogrodnica (gm. Środa Śląska, pow. średzki, dolnośląskie)",
    "commune": "Środa Śląska",
    "street_label": "",
}
TOWN_DATA = {
    "city_gaid": "119431",
    "street_gaid": "897490",
    "house_no": "1",
    "city_name": "Wrocław",
    "city_label": "Wrocław (gm. Wrocław, pow. Wrocław, dolnośląskie)",
    "commune": "Wrocław",
    "street_label": "ul. Legnicka",
}


def village() -> Address:
    return Address.picked(OGRODNICA, OGRODNICA_STREET, " 12 ")


def town() -> Address:
    return Address.picked(WROCLAW, LEGNICKA, "1")


def test_picked_village_address_has_todays_entry_data():
    assert village().entry_data() == VILLAGE_DATA


def test_picked_town_address_has_todays_entry_data():
    assert town().entry_data() == TOWN_DATA


@pytest.mark.parametrize("address", [village(), town()])
def test_entry_data_round_trip(address):
    assert Address.from_entry_data(address.entry_data()) == address


def test_from_entry_data_ignores_entry_level_keys():
    data = {**TOWN_DATA, "name": "Dom"}

    assert Address.from_entry_data(data) == town()


def test_unique_id_is_gaids_and_house_number():
    assert village().unique_id == "118484_910691_12"
    assert town().unique_id == "119431_897490_1"


def test_unnamed_street():
    assert village().unnamed_street
    assert not town().unnamed_street


def test_label_of_a_village_names_the_commune():
    assert village().label == "Ogrodnica 12, gm. Środa Śląska"


def test_label_of_a_town_names_the_street():
    assert town().label == "Wrocław, ul. Legnicka 1"


def test_feed_request_fields():
    address = town()

    assert (address.city_gaid, address.street_gaid, address.house_no) == ("119431", "897490", "1")


def test_address_is_immutable():
    with pytest.raises(AttributeError):
        town().house_no = "2"


def test_imports_no_home_assistant():
    code = (
        "import sys, types;"
        "pkg = types.ModuleType('tauron_outages');"
        f"pkg.__path__ = [{str(MODULE.parent)!r}];"
        "sys.modules['tauron_outages'] = pkg;"
        "import tauron_outages.address;"
        "print(any(k.split('.')[0] == 'homeassistant' for k in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
