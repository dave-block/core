# from homeassistant.components.sensor import (
#    ClimateEntity,
#    ClimateEntityFeature,
#    HVACMode,
# )
from typing import Any, final

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
        if obj.type in ("binaryInput", "binaryOutput", "binaryValue"):
            bacnet_sensors.append(
                DistechBinarySensorEntity(
                    coordinator, api, entry.data["device_info"], obj, device
                )
            )
    async_add_entities(bacnet_sensors)


class DistechBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator, api, device_info, obj: bacnetObject, device: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._object = obj
        self._name = self._object.bacnet_properties["objectName"].propertyValue
        self._attr_name = f"{self._name}"
        self._attr_device_info = device

        self._present_value = self._object.bacnet_properties["presentValue"]
        self._attr_unique_id = f"{device_info['hostName']}_binarysensor_{self._name}"

    @property
    def is_on(self) -> bool | None:
        if self._present_value:
            if self._present_value.propertyValue.lower() == "inactive":
                return False
            elif self._present_value.propertyValue.lower() == "active":
                return True
        else:
            return None

    def _get_bacnet_property(self, property_name: str) -> Any:
        """Retrieve a BACNet property from the object associated with this sensor."""
        prop = self._object.bacnet_properties.get(property_name)
        if prop is not None:
            return prop.propertyValue
        return None

    @final
    @property
    def state_attributes(self) -> dict[str, Any] | None:
        """Return state attributes."""
        if not (data := super().state_attributes):
            data = {}
        data["raw_state"] = self._present_value.propertyValue
        data["endpoint_type"] = self._present_value.objectType
        for prop in ("reliability", "statusFlags", "notificationClass", "propertyList"):
            data[prop] = self._get_bacnet_property(prop)
        for prop in self._object.bacnet_properties:
            data[prop] = self._object.bacnet_properties[prop].propertyValue
        data["known_properties"] = list(self._object.bacnet_properties.keys())
        return data
