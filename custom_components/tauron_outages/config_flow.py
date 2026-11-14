import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from typing import Optional, Any, Dict

from .const import DOMAIN
from .tauron_api import TauronAPI, TauronAPIError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("city_gaid"): str,
        vol.Required("street_gaid"): str,
        vol.Required("house_no"): str,
        vol.Required("name"): str,
        vol.Optional("filter_type"): str,
        vol.Optional("filter_message"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    api = TauronAPI(
        city_gaid=data["city_gaid"],
        street_gaid=data["street_gaid"],
        house_no=data["house_no"]
    )

    try:
        await api.async_get_outages()
    except TauronAPIError as err:
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise CannotConnect from err

    return {
        "title": data["name"],
        "city_gaid": data["city_gaid"],
        "street_gaid": data["street_gaid"],
        "house_no": data["house_no"],
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

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
                unique_id = f"{user_input['city_gaid']}_{user_input['street_gaid']}_{user_input['house_no']}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)

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
            return self.async_create_entry(title="Options", data=user_input)

        cur_opts = self._entry.options or {}
        data = self._entry.data or {}
        schema = vol.Schema(
            {
                vol.Optional("filter_type", default=cur_opts.get("filter_type", data.get("filter_type", ""))): str,
                vol.Optional("filter_message", default=cur_opts.get("filter_message", data.get("filter_message", ""))): str,
                vol.Optional("update_interval_hours", default=cur_opts.get("update_interval_hours", 4)): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


class CannotConnect(HomeAssistantError):
    pass


class InvalidAuth(HomeAssistantError):
    pass
