from datetime import timedelta
import logging
from typing import Any, final

# from homeassistant.components.sensor import (
#    ClimateEntity,
#    ClimateEntityFeature,
#    HVACMode,
# )
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
)
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
    api: eclypseCtrl = hass.data[DOMAIN]["api"]

    coordinator = hass.data[DOMAIN]["coordinator"]

    device = hass.data[DOMAIN]["device"]

    bacnet_sensors = []
    for obj in api.bacnet_objects.values():
        bacnet_sensors.append(
            DistechSensorEntity(
                coordinator, api, entry.data["device_info"], obj, device
            )
        )
    async_add_entities(bacnet_sensors)


class DistechSensorEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    # _attr_name = "Distech CO2 Sensor"
    # _attr_device_class = SensorDeviceClass.
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator, api, device_info, obj: bacnetObject, device: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._object = obj
        self._name = self._object.bacnet_properties["objectName"].propertyValue
        self._attr_name = f"{self._name}"
        if "humidity" in self._name.lower():
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif "temperature" in self._name.lower():
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
        elif "co2" in self._name.lower():
            self._attr_device_class = SensorDeviceClass.CO2
            self._attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
        elif "speed" in self._name.lower():
            # self._attr_device_class = SensorDeviceClass.SPEED
            self._attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE
        elif "power" in self._name.lower():
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_device_info = device

        self._present_value = self._object.bacnet_properties["presentValue"]
        self._attr_unique_id = f"{device_info['hostName']}_sensor_{self._name}"
        # self.entity_id = self._attr_unique_id

    @property
    def native_value(self) -> float:
        if self._present_value:
            return self._present_value.propertyValue
        else:
            return None
