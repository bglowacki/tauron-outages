from __future__ import annotations

import pytest

from tauron_outages.migration import migrate_v1_to_v2

ADDRESS = {"city_gaid": "1", "street_gaid": "2", "house_no": "3", "name": "Ogrodnica"}


def test_setup_filter_becomes_locality():
    data, options = migrate_v1_to_v2(
        {**ADDRESS, "filter_type": "", "filter_message": "Ogrodnica"},
        {"update_interval_hours": 4},
    )
    assert data == ADDRESS
    assert options == {"update_interval_hours": 4, "locality": "Ogrodnica"}


def test_non_empty_options_filter_wins():
    data, options = migrate_v1_to_v2(
        {**ADDRESS, "filter_message": "Ogrodnica"},
        {"filter_type": "1", "filter_message": "Chwalimierz"},
    )
    assert data == ADDRESS
    assert options == {"locality": "Chwalimierz"}


@pytest.mark.parametrize("cleared", ["", None])
def test_empty_options_filter_falls_back_to_setup_value(cleared):
    _, options = migrate_v1_to_v2(
        {**ADDRESS, "filter_message": "Ogrodnica"}, {"filter_message": cleared}
    )
    assert options == {"locality": "Ogrodnica"}


def test_no_filter_anywhere_gives_empty_locality():
    data, options = migrate_v1_to_v2(dict(ADDRESS), {})
    assert data == ADDRESS
    assert options == {"locality": ""}


def test_inputs_are_not_mutated():
    data = {**ADDRESS, "filter_message": "Ogrodnica"}
    options = {"filter_message": "Chwalimierz"}
    migrate_v1_to_v2(data, options)
    assert data == {**ADDRESS, "filter_message": "Ogrodnica"}
    assert options == {"filter_message": "Chwalimierz"}
