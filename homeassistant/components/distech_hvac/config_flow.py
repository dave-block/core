"""Config flow for distech-hvac integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .async_hvac import eclypseCtrl
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# TODO adjust the data schema to the data that you need
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host", default="10.14.5.54"): str,
        vol.Required("username", default="onlogic_admin"): str,
        vol.Required("password", default="P@ssword1234"): str,
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
    # TODO validate the data can be used to set up a connection.

    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    # result = await hass.async_add_executor_job(
    #     eclypseCtrl(
    #         data["host"],
    #         {"user": data["username"], "password": data["password"]},
    #         hass,
    #     ).get,
    #     "info/device",
    # )
    api = eclypseCtrl(
        data["host"], {"user": data["username"], "password": data["password"]}, hass
    )
    result = await api.get("info/device")
    # await api._session.close()

    # hub = PlaceholderHub(data["host"])

    # if not await hub.authenticate(data["username"], data["password"]):
    #    raise InvalidAuth

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
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
                return await self.async_step_points()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_points(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        "Allow the user to select which endpoints to monitor."
        if user_input is not None:
            self.data["object_names"] = [x.split(":")[0] for x in user_input["objects"]]
            _LOGGER.info(f"cfg flow {self.data['object_names']}")

            for bacnet_obj in self.bacnet_objects:
                if (
                    self.bacnet_objects[bacnet_obj]
                    .bacnet_properties["objectName"]
                    .propertyValue
                    in self.data["object_names"]
                ):
                    self.api.bacnet_objects[bacnet_obj] = self.bacnet_objects[
                        bacnet_obj
                    ]
            self.bacnet_objects = None
            self.data["object_names"] = list(self.api.bacnet_objects.keys())
            return await self.async_step_bacnet_properties()

        objs = await self.api.getObjectData()
        self.bacnet_objects = objs

        menu_sort = [
            f"{bacnetObj.bacnet_properties['objectName'].propertyValue}: {bacnetObj.bacnet_properties['description'].propertyValue}"
            for bacnetObj in objs.values()
        ]
        menu_sort.sort()

        obj_menu = {
            vol.Optional(
                "objects", default=None, description="multiselect for bacnet endpoints"
            ): cv.multi_select({x: False for x in menu_sort})
        }

        return self.async_show_form(
            step_id="points",
            data_schema=vol.Schema(obj_menu),
        )

    async def async_step_bacnet_properties(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        "Ask the user to select which properties of an endpoint to monitor."
        _LOGGER.info(self.data.get("object_names"))
        if user_input is not None:
            _LOGGER.info(f"cfg flow selected props {user_input}")
            for prop in user_input["properties"]:
                _LOGGER.info(f"adding property {prop} to {self.objname}")
                self.api.bacnet_objects[self.objname].addBacnetProperty(
                    {
                        "property_type": self.objname.split("_")[0],
                        "instance": self.objname.split("_")[1],
                        "property_name": prop,
                        "static": False,
                        "update_required": True,
                    }
                )
        if user_input is not None and not self.data.get("object_names"):
            _LOGGER.info(f"cfg flow props {user_input}")
            await self.api.close()
            self.data.update(self.api.export())
            return self.async_create_entry(title=self.data["title"], data=self.data)

        self.objname = self.data["object_names"].pop(0)
        prop_list_sorted = [
            f"{x}"
            for x in self.api.bacnet_objects[self.objname]
            .bacnet_properties["propertyList"]
            .propertyValue
        ]
        prop_list_sorted.sort()
        prop_menu = {
            vol.Optional(
                "pointname",
                default=self.api.bacnet_objects[self.objname]
                .bacnet_properties["objectName"]
                .propertyValue,
            ): str,
            vol.Optional(
                "properties",
                default=None,
                description="multiselect for bacnet properties",
            ): cv.multi_select({x: False for x in prop_list_sorted}),
        }

        return self.async_show_form(
            step_id="bacnet_properties",
            data_schema=vol.Schema(prop_menu),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
