"""The distech-hvac integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .async_hvac import bacnetObject, eclypseCtrl
from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up distech-hvac from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    api = eclypseCtrl(
        entry.data["ip"],
        entry.data["creds"],
        hass,
    )

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
    for obj in entry.data["objects"]:
        api.bacnet_objects[obj] = bacnetObject(**entry.data["objects"][obj])

    await coordinator.async_refresh()

    hass.data[DOMAIN] = {
        "api": api,
        "coordinator": coordinator,
        "device": DeviceInfo(
            identifiers={(DOMAIN, "controller")},
            name=entry.data["device_info"]["hostName"],
            manufacturer="Distech",
            model=entry.data["device_info"]["modelName"],
            sw_version=entry.data["device_info"]["softwareVersion"],
        ),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # hass.data[DOMAIN].pop(entry.entry_id)
        pass

    return unload_ok
