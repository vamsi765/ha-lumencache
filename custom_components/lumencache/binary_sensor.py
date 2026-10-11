"""Connection status of the ReNetA system."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LumenCacheConfigEntry
from .const import DOMAIN


def hub_device_info(entry: LumenCacheConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="LumenCache", manufacturer="LumenCache")


async def async_setup_entry(
    hass: HomeAssistant, entry: LumenCacheConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ConnectionSensor(entry)])


class ConnectionSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "connection"

    def __init__(self, entry: LumenCacheConfigEntry) -> None:
        self._data = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_connection"
        self._attr_device_info = hub_device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._data.client.connected

    async def async_added_to_hass(self) -> None:
        @callback
        def update(_connected: bool) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, self._data.connection_signal, update))
