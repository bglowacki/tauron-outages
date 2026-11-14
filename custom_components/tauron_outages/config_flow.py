import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from typing import Optional, Any, Dict

from .const import (
    CONF_CITY_GAID,
    CONF_HOUSE_NO,
    CONF_LOCALITY,
    CONF_NAME,
    CONF_STREET_GAID,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)
from homeassistant.util import dt as dt_util

from . import address_of
from .http_transport import urllib_transport
from .outage_feed import OutageFeed, OutageFeedError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CITY_GAID): str,
        vol.Required(CONF_STREET_GAID): str,
        vol.Required(CONF_HOUSE_NO): str,
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_LOCALITY, default=""): str,
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


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    feed = OutageFeed(address_of(data), urllib_transport(), dt_util.get_default_time_zone())

    try:
        await feed.fetch(dt_util.utcnow())
    except OutageFeedError as err:
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect from err

    return {
        "title": data[CONF_NAME],
        CONF_CITY_GAID: data[CONF_CITY_GAID],
        CONF_STREET_GAID: data[CONF_STREET_GAID],
        CONF_HOUSE_NO: data[CONF_HOUSE_NO],
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 2

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                unique_id = f"{user_input[CONF_CITY_GAID]}_{user_input[CONF_STREET_GAID]}_{user_input[CONF_HOUSE_NO]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                data = {k: v for k, v in user_input.items() if k != CONF_LOCALITY}
                return self.async_create_entry(
                    title=info["title"],
                    data=data,
                    options={CONF_LOCALITY: user_input.get(CONF_LOCALITY, "")},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input.setdefault(CONF_LOCALITY, "")
            return self.async_create_entry(title="Options", data=user_input)

        options = self._entry.options
        schema = _options_schema(
            options.get(CONF_LOCALITY, ""),
            options.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS),
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


class CannotConnect(HomeAssistantError):
    pass


class InvalidAuth(HomeAssistantError):
    pass
