from datetime import timedelta
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
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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

from .async_hvac import bacnetObject, eclypseCtrl
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    pass


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    # logging.getLogger("distech").info(entry.data)
    api = eclypseCtrl(
        entry.data["ip"],
        entry.data["creds"],
        hass,
    )

    for obj in entry.data["objects"]:
        api.bacnet_objects[obj] = bacnetObject(**entry.data["objects"][obj])

    async def async_update_data():
        data = await api.postRequestObjectProperties()
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger("distech"),
        name="distech",
        update_method=async_update_data,
        update_interval=timedelta(seconds=30),
    )

    # api.bacnet_objects = await api.getObjectData()

    await coordinator.async_refresh()

    async_add_entities(
        [
            DistechEntity(
                coordinator,
                api,
                entry.data["device_info"],
                "Thermostat",
            ),
            DistechCO2SensorEntity(
                entry.data["device_info"], coordinator, api, "RoomCO2"
            ),
        ]
    )


class DistechCO2SensorEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Distech CO2 Sensor"
    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, device_info, coordinator, api, sensorname: str):
        super().__init__(coordinator)
        self._api = api
        self._coordinator = coordinator
        self.sensorname = sensorname
        self._prop = None
        self._attr_native_unit_of_measurement = "ppm"
        for x in self._api.bacnet_objects.values():
            logging.getLogger("co2sensor").info(
                x.bacnet_properties.get("objectName").propertyValue
            )
            if x.bacnet_properties.get("objectName").propertyValue == self.sensorname:
                self._prop = x.bacnet_properties.get("presentValue")

        self._attr_unique_id = f"{device_info['hostName']}_co2_sensor"
        """self._attr_device_info = DeviceInfo(  # TODO: add the rest of the device info to this structure (hw/sw versions etc)
            identifiers={(DOMAIN, "co2_sensor")},
            name=device_info["hostName"],
            manufacturer="Distech",
            model=device_info["modelName"],
            sw_version=device_info["softwareVersion"],
        )"""

    @property
    def native_value(self) -> float:
        if self._prop:
            return self._prop.propertyValue
        else:
            return None


class DistechEntity(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit: str
    _attr_current_c02: float

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: eclypseCtrl,
        device_info: str,
        sensor: str,
    ) -> None:
        # self.name = name
        self._attr_name = sensor
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
        self._attr_unique_id = f"{device_info['hostName']}_{sensor}"
        self._attr_device_info = DeviceInfo(  # TODO: add the rest of the device info to this structure (hw/sw versions etc)
            identifiers={(DOMAIN, sensor)},
            name=device_info["hostName"],
            manufacturer="Distech",
            model=device_info["modelName"],
            sw_version=device_info["softwareVersion"],
        )
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

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return self._attr_temperature_unit

    @property
    def current_c02(self) -> float:
        for x in self.coordinator.data:
            if x["instance"] == 1003 and x["property"] == "presentValue":
                self._attr_current_c02 = float(x["value"])
        return self._attr_current_c02

    @property
    def current_humidity(self) -> float:
        for x in self.coordinator.data:
            if x["instance"] == 1002 and x["property"] == "presentValue":
                self._attr_current_humidity = round(float(x["value"]))
        return self._attr_current_humidity

    @property
    def current_temperature(self):
        """Return the current temperature."""
        for x in self.coordinator.data:
            if x["instance"] == 1001 and x["property"] == "presentValue":
                self._attr_current_temperature = float(x["value"])
        return self._attr_current_temperature

    @property
    def preset_mode(self) -> float:
        for x in self.coordinator.data:
            if (
                x["instance"] == 15
                and x["type"] == "multiStateValue"
                and x["property"] == "presentValue"
            ):
                self._attr_occupancy_status = int(x["value"])
        if self._attr_occupancy_status == 1:
            return PRESET_HOME
        if self._attr_occupancy_status == 2:
            return PRESET_AWAY
        if self._attr_occupancy_status == 4:
            return PRESET_ECO

    @property
    def occupancy_status(self):
        self.preset_mode
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

    """async def async_update(self) -> None:
        if not self._authed:
            await self.hass.async_add_executor_job(
                self._control_object.get, "info/device"
            )
            self._authed = True

        if self._update_required:
            await self.hass.async_add_executor_job(
                self._control_object.postSetObjectProperties,
                "multiStateValue_15",
                {"presentValue": self._attr_occupancy_status},
            )
            self._update_required = False
        res = await self.hass.async_add_executor_job(
            self._control_object.postRequestObjectProperties
        )
        for x in res:
            if x["instance"] == 1001:
                self._attr_current_temperature = float(x["value"])
            elif x["instance"] == 1002:
                self._attr_current_humidity = round(float(x["value"]))
            elif x["instance"] == 1003:
                self._attr_current_c02 = float(x["value"])
            elif x["instance"] == 15 and x["type"] == "multiStateValue":
                self._attr_occupancy_status = int(x["value"])
        logging.getLogger("distech").info(res)
    """

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

        data["current_c02"] = self.current_c02
        data["occupancy"] = self.occupancy_status

        for x in self._api.bacnet_objects:
            # logging.getLogger('distech').
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
