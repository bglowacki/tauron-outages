from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .outage_feed_source import Transport

MIN_LENGTH = 3
MAX_MATCHES = 20


class AddressSearchError(Exception):
    pass


class Refusal(StrEnum):
    TOO_SHORT = "too_short"
    NO_MATCHES = "no_matches"
    TOO_MANY = "too_many"


class SearchRefused(Exception):
    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.value)
        self.refusal = refusal


@dataclass(frozen=True, slots=True)
class CityMatch:
    gaid: str
    name: str
    commune: str
    district: str
    province: str

    @property
    def label(self) -> str:
        return f"{self.name} (gm. {self.commune}, pow. {self.district}, {self.province})"


@dataclass(frozen=True, slots=True)
class StreetMatch:
    gaid: str
    name: str
    label: str
    unnamed: bool


class AddressSearch:

    def __init__(self, cities: Transport, streets: Transport) -> None:
        self._cities = cities
        self._streets = streets

    async def cities(self, text: str) -> list[CityMatch]:
        return await self._search(self._cities, {"partName": _query(text)}, _city)

    async def streets(self, city: CityMatch, text: str) -> list[StreetMatch]:
        params = {"partName": _query(text), "ownerGAID": city.gaid}
        return await self._search(self._streets, params, lambda item: _street(city, item))

    async def _search(self, transport: Transport, params: dict[str, str], parse) -> list:
        try:
            items = await transport(params)
            matches = [parse(item) for item in items]
        except (OSError, ValueError, KeyError, TypeError) as err:
            raise AddressSearchError(f"Failed to search Tauron's register: {err!r}") from err
        if not matches:
            raise SearchRefused(Refusal.NO_MATCHES)
        if len(matches) > MAX_MATCHES:
            raise SearchRefused(Refusal.TOO_MANY)
        return matches


def address_label(
    city_name: str, commune: str, street_label: str, house_no: str
) -> str:
    if street_label:
        return f"{city_name}, {street_label} {house_no}"
    return f"{city_name} {house_no}, gm. {commune}"


def _query(text: str) -> str:
    query = text.strip()
    if len(query) < MIN_LENGTH:
        raise SearchRefused(Refusal.TOO_SHORT)
    return query


def _city(item: Mapping[str, Any]) -> CityMatch:
    return CityMatch(
        gaid=str(item["GAID"]),
        name=item["Name"],
        commune=item["CommuneName"],
        district=item["DistrictName"],
        province=item["ProvinceName"],
    )


def _street(city: CityMatch, item: Mapping[str, Any]) -> StreetMatch:
    name = item["Name"]
    return StreetMatch(
        gaid=str(item["GAID"]),
        name=name,
        label=(item.get("FullName") or name).strip(),
        unnamed=not (item.get("Prefix") or "").strip()
        and name.strip().casefold() == city.name.strip().casefold(),
    )
