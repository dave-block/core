"""Config flow for distech-hvac integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .async_hvac import eclypseCtrl
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host", default="10.14.5.54"): str,
        vol.Required("username", default="onlogic_admin"): str,
        vol.Required("password", default="P@ssword1234"): str,
        vol.Required("device_name", default="Demo FCU"): str,
    }
)


class PlaceholderHub:
    """Placeholder class to make tests pass.

    TODO Remove this placeholder class and replace with things from your PyPI package.
    """

    def __init__(self, host: str) -> None:
        """Initialize."""
        self.host = host

    async def authenticate(self, username: str, password: str) -> bool:
        """Test if we can authenticate with the host."""
        return True


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    api = eclypseCtrl(
        data["host"], {"user": data["username"], "password": data["password"]}, hass
    )
    result = await api.get("info/device")
    # hub = PlaceholderHub(data["host"])

    # if not await hub.authenticate(data["username"], data["password"]):
    #    raise InvalidAuth

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    return {
        "title": result["controllerName"],
        "device_info": result,
        "user_input": data,
        "api": api,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for distech-hvac."""

    VERSION = 1
    api: eclypseCtrl

    def __init__(self, *args, **kwargs) -> None:
        self.data = {}
        self.bacnet_objects = None
        self.bacnet_properties = {}
        self.api = None
        self.objname = None
        super().__init__(*args, **kwargs)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.api = info.pop("api")
                self.data = info
                # build a set of bacnet objects and properties. probably should be moved somewhere else,
                # but it does all need to be defined before handing off to create_entry
                self.api.bacnet_objects = await self.api.getObjectData()
                for obj in self.api.bacnet_objects.values():
                    for prop in (
                        ("presentValue", False),
                        ("reliability", False),
                        ("statusFlags", False),
                        ("units", True),
                        ("alarmValue", False),
                        ("alarmValues", False),
                    ):
                        if (
                            prop[0]
                            in obj.bacnet_properties["propertyList"].propertyValue
                        ):
                            _LOGGER.info(f"adding property {prop} to {obj.name}")
                            obj.addBacnetProperty(
                                {
                                    "property_type": obj.type,
                                    "instance": obj.index,
                                    "property_name": prop[0],
                                    "static": prop[1],
                                    "update_required": True,
                                }
                            )
                await self.api.close()
                self.data.update(self.api.export())
                return self.async_create_entry(title=self.data["title"], data=self.data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
