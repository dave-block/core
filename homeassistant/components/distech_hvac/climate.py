import logging
from typing import Any, final

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    ATTR_AUX_HEAT,
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_HUMIDITY,
    ATTR_HVAC_ACTION,
    ATTR_PRESET_MODE,
    ATTR_SWING_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_HOME,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, STATE_ON, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.temperature import display_temp as show_temp
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .async_hvac import eclypseCtrl
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    pass


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    # logging.getLogger("distech").info(entry.data)
    api = hass.data[DOMAIN]["api"]
    coordinator = hass.data[DOMAIN]["coordinator"]
    device = hass.data[DOMAIN]["device"]

    async_add_entities(
        [
            DistechEntity(coordinator, api, entry.data["device_info"], device),
        ]
    )


class DistechEntity(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit: str
    _attr_current_c02: float

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: eclypseCtrl,
        device_info: dict[str],
        device: DeviceInfo,
    ) -> None:
        # self.name = name
        self._attr_name = "Thermostat"
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._api = api

        self._authed = False
        self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.HEAT_COOL,
        ]
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_unique_id = f"{device_info['hostName']}_Thermostat"
        self._attr_device_info = device
        self._attr_supported_features |= (
            ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_target_temperature_high = 70
        self._attr_target_temperature_low = 50
        self._attr_current_c02 = 0
        # self._attr_preset_mode = PRESET_HOME
        self._attr_preset_modes = [PRESET_HOME, PRESET_AWAY, PRESET_ECO]
        self._attr_occupancy_status = None
        self._update_required = False

        self._objmap = {
            "roomtemperature": None,
            "roomhumidity": None,
            "occupancystatus": None,
        }
        for objectName in self._objmap:
            for bacnetObject in self._api.bacnet_objects.values():
                if (
                    bacnetObject.bacnet_properties["objectName"].propertyValue.lower()
                    == objectName
                ):
                    self._objmap[objectName] = bacnetObject

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return self._attr_temperature_unit

    @property
    def current_humidity(self) -> float:
        self._attr_current_humidity = round(
            float(
                self._objmap["roomhumidity"]
                .bacnet_properties["presentValue"]
                .propertyValue
            ),
            2,
        )
        return self._attr_current_humidity

    @property
    def current_temperature(self):
        """Return the current temperature."""
        self._attr_current_temperature = float(
            self._objmap["roomtemperature"]
            .bacnet_properties["presentValue"]
            .propertyValue
        )
        return self._attr_current_temperature

    @property
    def preset_mode(self) -> float:
        if self.occupancy_status == 1:
            return PRESET_HOME
        if self.occupancy_status == 2:
            return PRESET_AWAY
        if self.occupancy_status == 4:
            return PRESET_ECO

    @property
    def occupancy_status(self):
        if not self._objmap.get("occupancystatus"):
            return None
        self._attr_occupancy_status = int(
            self._objmap["occupancystatus"]
            .bacnet_properties["presentValue"]
            .propertyValue
        )
        return self._attr_occupancy_status

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        # self._attr_preset_mode = preset_mode
        self._update_required = True
        if preset_mode == PRESET_HOME:
            self._attr_occupancy_status = 1
        elif preset_mode == PRESET_AWAY:
            self._attr_occupancy_status = 2
        elif preset_mode == PRESET_ECO:
            self._attr_occupancy_status = 4
        else:
            self._update_required = False
        await self._coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        await self._coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        # if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
        #    return
        if (high := kwargs.get(ATTR_TARGET_TEMP_HIGH)) is not None:
            self._attr_target_temperature_high = high

        if (low := kwargs.get(ATTR_TARGET_TEMP_LOW)) is not None:
            self._attr_target_temperature_low = low
        await self._coordinator.async_request_refresh()

    @final
    @property
    def state_attributes(self) -> dict[str, Any]:
        """Return the optional state attributes."""
        supported_features = self.supported_features
        temperature_unit = self.temperature_unit
        precision = self.precision
        hass = self.hass

        data: dict[str, str | float | None] = {
            ATTR_CURRENT_TEMPERATURE: show_temp(
                hass, self.current_temperature, temperature_unit, precision
            ),
        }

        if supported_features & ClimateEntityFeature.TARGET_TEMPERATURE:
            data[ATTR_TEMPERATURE] = show_temp(
                hass,
                self.target_temperature,
                temperature_unit,
                precision,
            )

        if supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE:
            data[ATTR_TARGET_TEMP_HIGH] = show_temp(
                hass, self.target_temperature_high, temperature_unit, precision
            )
            data[ATTR_TARGET_TEMP_LOW] = show_temp(
                hass, self.target_temperature_low, temperature_unit, precision
            )

        data["occupancy"] = self.occupancy_status

        for x in self._api.bacnet_objects:
            res = self._api.bacnet_objects[x].bacnet_properties.get("presentValue")
            logging.getLogger("distech").debug(f"{x}: {res.propertyValue}")
            if res:
                data[
                    f"{self._api.bacnet_objects[x].bacnet_properties.get('objectName').propertyValue}::{x}"
                ] = res.propertyValue

        if (current_humidity := self.current_humidity) is not None:
            data[ATTR_CURRENT_HUMIDITY] = current_humidity

        if supported_features & ClimateEntityFeature.TARGET_HUMIDITY:
            data[ATTR_HUMIDITY] = self.target_humidity

        if supported_features & ClimateEntityFeature.FAN_MODE:
            data[ATTR_FAN_MODE] = self.fan_mode

        if hvac_action := self.hvac_action:
            data[ATTR_HVAC_ACTION] = hvac_action

        if supported_features & ClimateEntityFeature.PRESET_MODE:
            data[ATTR_PRESET_MODE] = self.preset_mode

        if supported_features & ClimateEntityFeature.SWING_MODE:
            data[ATTR_SWING_MODE] = self.swing_mode

        if supported_features & ClimateEntityFeature.AUX_HEAT:
            data[ATTR_AUX_HEAT] = STATE_ON if self.is_aux_heat else STATE_OFF

        return data
