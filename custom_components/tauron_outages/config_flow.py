import logging
from typing import Any

import probatio as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from . import address_search_for, outage_feed_source_for
from .address import Address
from .address_search import AddressSearchError, CityMatch, SearchRefused, StreetMatch
from .const import (
    CONF_LOCALITY,
    CONF_NAME,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)
from .outage_feed_source import OutageFeedError

_LOGGER = logging.getLogger(__name__)

CITY = "city"
STREET = "street"
HOUSE_NO = "house_no"
NO_STREET_KEY = f"component.{DOMAIN}.selector.street.options.no_street"


def _search_schema(key: str, text: str) -> vol.Schema:
    return vol.Schema({vol.Required(key, description={"suggested_value": text}): str})


def _pick_schema(key: str, choices: list[SelectOptionDict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(key): SelectSelector(
                SelectSelectorConfig(options=choices, mode=SelectSelectorMode.DROPDOWN)
            )
        }
    )


def _details_schema(city_name: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(HOUSE_NO): str,
            vol.Required(CONF_NAME, description={"suggested_value": city_name}): str,
            vol.Optional(CONF_LOCALITY, description={"suggested_value": city_name}): str,
        }
    )


def _options_schema(locality: str, hours: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_LOCALITY, description={"suggested_value": locality}
            ): str,
            vol.Optional(CONF_UPDATE_INTERVAL_HOURS, default=hours): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=168)
            ),
        }
    )


def _search_error(err: Exception) -> str:
    if isinstance(err, SearchRefused):
        return err.refusal.value
    return "cannot_connect"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 3

    def __init__(self) -> None:
        self._cities: list[CityMatch] = []
        self._city: CityMatch | None = None
        self._streets: list[StreetMatch] = []
        self._street: StreetMatch | None = None
        self._street_labels: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        text = ""
        errors: dict[str, str] = {}
        if user_input is not None:
            text = user_input[CITY]
            try:
                self._cities = await address_search_for(self.hass).cities(text)
            except (SearchRefused, AddressSearchError) as err:
                errors["base"] = _search_error(err)
            else:
                if len(self._cities) == 1:
                    self._city = self._cities[0]
                    return await self.async_step_street()
                return await self.async_step_pick_city()

        return self.async_show_form(
            step_id="user",
            data_schema=_search_schema(CITY, text),
            errors=errors,
            description_placeholders={"query": text.strip()},
        )

    async def async_step_pick_city(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._city = next(c for c in self._cities if c.gaid == user_input[CITY])
            return await self.async_step_street()

        choices = [SelectOptionDict(value=c.gaid, label=c.label) for c in self._cities]
        return self.async_show_form(step_id="pick_city", data_schema=_pick_schema(CITY, choices))

    async def async_step_street(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._city is not None
        text = self._city.name
        errors: dict[str, str] = {}
        if user_input is not None:
            text = user_input[STREET]
            try:
                self._streets = await address_search_for(self.hass).streets(self._city, text)
            except (SearchRefused, AddressSearchError) as err:
                errors["base"] = _search_error(err)
            else:
                return await self.async_step_pick_street()

        return self.async_show_form(
            step_id="street",
            data_schema=_search_schema(STREET, text),
            errors=errors,
            description_placeholders={"query": text.strip(), "city": self._city.label},
        )

    async def async_step_pick_street(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._street = next(s for s in self._streets if s.gaid == user_input[STREET])
            return await self.async_step_details()

        no_street = await self._no_street_template()
        self._street_labels = {
            s.gaid: no_street.format(city=s.name) if s.unnamed else s.label
            for s in self._streets
        }
        choices = [
            SelectOptionDict(value=gaid, label=label)
            for gaid, label in self._street_labels.items()
        ]
        return self.async_show_form(
            step_id="pick_street", data_schema=_pick_schema(STREET, choices)
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._city is not None and self._street is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            address = Address.picked(self._city, self._street, user_input[HOUSE_NO])
            await self.async_set_unique_id(address.unique_id)
            self._abort_if_unique_id_configured()
            try:
                await outage_feed_source_for(self.hass, address).fetch(dt_util.utcnow())
            except OutageFeedError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={**address.entry_data(), CONF_NAME: user_input[CONF_NAME]},
                    options={CONF_LOCALITY: user_input.get(CONF_LOCALITY, "")},
                )

        return self.async_show_form(
            step_id="details",
            data_schema=self.add_suggested_values_to_schema(
                _details_schema(self._city.name), user_input or {}
            ),
            errors=errors,
            description_placeholders={
                "city": self._city.label,
                "street": self._street_labels[self._street.gaid],
            },
        )

    async def _no_street_template(self) -> str:
        translations = await async_get_translations(
            self.hass, self.hass.config.language, "selector", {DOMAIN}
        )
        return translations.get(NO_STREET_KEY, "{city} (no street)")

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input.setdefault(CONF_LOCALITY, "")
            return self.async_create_entry(title="Options", data=user_input)

        options = self._entry.options
        schema = _options_schema(
            options.get(CONF_LOCALITY, ""),
            options.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"address": Address.from_entry_data(self._entry.data).label},
        )
