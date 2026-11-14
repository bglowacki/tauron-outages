from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_CITY_GAID,
    CONF_CITY_LABEL,
    CONF_CITY_NAME,
    CONF_COMMUNE,
    CONF_HOUSE_NO,
    CONF_STREET_GAID,
    CONF_STREET_LABEL,
)

if TYPE_CHECKING:
    from .address_search import CityMatch, StreetMatch


@dataclass(frozen=True, slots=True)
class Address:
    city_gaid: str
    street_gaid: str
    house_no: str
    city_name: str
    city_label: str
    commune: str
    street_label: str

    @classmethod
    def picked(cls, city: CityMatch, street: StreetMatch, house_no: str) -> Address:
        return cls(
            city_gaid=city.gaid,
            street_gaid=street.gaid,
            house_no=house_no.strip(),
            city_name=city.name,
            city_label=city.label,
            commune=city.commune,
            street_label="" if street.unnamed else street.label,
        )

    @classmethod
    def from_entry_data(cls, data: Mapping[str, Any]) -> Address:
        return cls(
            city_gaid=data[CONF_CITY_GAID],
            street_gaid=data[CONF_STREET_GAID],
            house_no=data[CONF_HOUSE_NO],
            city_name=data[CONF_CITY_NAME],
            city_label=data[CONF_CITY_LABEL],
            commune=data[CONF_COMMUNE],
            street_label=data[CONF_STREET_LABEL],
        )

    def entry_data(self) -> dict[str, str]:
        return {
            CONF_CITY_GAID: self.city_gaid,
            CONF_STREET_GAID: self.street_gaid,
            CONF_HOUSE_NO: self.house_no,
            CONF_CITY_NAME: self.city_name,
            CONF_CITY_LABEL: self.city_label,
            CONF_COMMUNE: self.commune,
            CONF_STREET_LABEL: self.street_label,
        }

    @property
    def unique_id(self) -> str:
        return f"{self.city_gaid}_{self.street_gaid}_{self.house_no}"

    @property
    def unnamed_street(self) -> bool:
        return not self.street_label

    @property
    def label(self) -> str:
        if self.unnamed_street:
            return f"{self.city_name} {self.house_no}, gm. {self.commune}"
        return f"{self.city_name}, {self.street_label} {self.house_no}"
