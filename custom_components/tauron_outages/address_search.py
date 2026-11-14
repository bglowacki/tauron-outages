import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .outage_feed_source import Transport

MIN_LENGTH = 3
MAX_SUGGESTIONS = 10
HOUSE_NUMBER = re.compile(r"\d+\s*[^\W\d_]?(\s*/\s*\d+\s*[^\W\d_]?)?")


class AddressSearchError(Exception):
    pass


class Refusal(StrEnum):
    TOO_SHORT = "too_short"
    NO_MATCHES = "no_matches"
    HOUSE_NUMBER = "house_number"
    UNKNOWN_HOUSE_NUMBER = "unknown_house_number"


class SearchRefused(Exception):
    def __init__(self, refusal: Refusal, suggestions: tuple[str, ...] = ()) -> None:
        super().__init__(refusal.value)
        self.refusal = refusal
        self.suggestions = suggestions


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

    def __init__(
        self,
        cities: Transport,
        streets: Transport,
        only_street: Transport,
        house_numbers: Transport,
    ) -> None:
        self._cities = cities
        self._streets = streets
        self._only_street = only_street
        self._house_numbers = house_numbers

    async def cities(self, text: str) -> list[CityMatch]:
        return await self._search(self._cities, {"partName": _query(text)}, _city)

    async def streets(self, city: CityMatch, text: str) -> list[StreetMatch]:
        if HOUSE_NUMBER.fullmatch(text.strip()):
            raise SearchRefused(Refusal.HOUSE_NUMBER)
        params = {"partName": _query(text), "ownerGAID": city.gaid}
        return await self._search(self._streets, params, lambda item: _street(city, item))

    async def only_street(self, city: CityMatch) -> StreetMatch | None:
        items = await self._ask(self._only_street, {"ownerGAID": city.gaid})
        streets = _parsed(items, lambda item: _street(city, item))
        return streets[0] if len(streets) == 1 else None

    async def house_number(self, city: CityMatch, street: StreetMatch, text: str) -> str:
        wanted = _house_key(text)
        if not wanted:
            raise SearchRefused(Refusal.UNKNOWN_HOUSE_NUMBER)
        params = {"partName": text.strip(), "cityGAID": city.gaid, "streetGAID": street.gaid}
        known = [str(number) for number in await self._ask(self._house_numbers, params)]
        for number in known:
            if _house_key(number) == wanted:
                return number
        raise SearchRefused(Refusal.UNKNOWN_HOUSE_NUMBER, tuple(known[:MAX_SUGGESTIONS]))

    async def _ask(self, transport: Transport, params: dict[str, str]) -> list:
        try:
            items = await transport(params)
        except (OSError, ValueError) as err:
            raise AddressSearchError(f"Failed to search Tauron's register: {err!r}") from err
        if not isinstance(items, list):
            raise AddressSearchError(f"Unexpected answer from Tauron's register: {items!r}")
        return items

    async def _search(self, transport: Transport, params: dict[str, str], parse) -> list:
        matches = _parsed(await self._ask(transport, params), parse)
        if not matches:
            raise SearchRefused(Refusal.NO_MATCHES)
        return matches


def _query(text: str) -> str:
    query = text.strip()
    if len(query) < MIN_LENGTH:
        raise SearchRefused(Refusal.TOO_SHORT)
    return query


def _parsed(items: list, parse) -> list:
    try:
        return [parse(item) for item in items]
    except (KeyError, TypeError, AttributeError) as err:
        raise AddressSearchError(f"Unexpected answer from Tauron's register: {err!r}") from err


def _house_key(text: str) -> str:
    return "".join(text.split()).casefold()


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
