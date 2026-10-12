"""What every entity of the integration shares, whatever platform it belongs to."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from pylumencache import Change, Command, FixtureState, NotConnectedError, Target

from . import LumenCacheConfigEntry
from .const import DOMAIN


def hub_device_info(entry: LumenCacheConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="LumenCache", manufacturer="LumenCache")


class LumenFixtureEntity(Entity):
    """An entity for a zone or a fixture. A platform's entity extends this with that platform's features.

    The system does not report the state of a fixture, so the state is assumed.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(
        self,
        entry: LumenCacheConfigEntry,
        target: Target,
        name: str | None,
        device_info: DeviceInfo,
        unique: str | None = None,
    ) -> None:
        self._data = entry.runtime_data
        self._target = target
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_unique_id = unique or f"{entry.entry_id}_{target.kind}_{target.key}"

    @property
    def _state(self) -> FixtureState:
        return self._data.model.state(self._target)

    @property
    def available(self) -> bool:
        return self._data.cache.connected

    async def async_added_to_hass(self) -> None:
        @callback
        def model_changed(change: Change) -> None:
            if change.kind == self._target.kind and change.key == self._target.key:
                self.async_write_ha_state()

        @callback
        def connection_changed(_connected: bool) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, self._data.signal, model_changed))
        self.async_on_remove(async_dispatcher_connect(self.hass, self._data.connection_signal, connection_changed))

    async def _send(self, command: Command) -> None:
        try:
            await self._data.cache.send(command)
        except NotConnectedError as err:
            raise HomeAssistantError("Not connected to the LumenCache system") from err
