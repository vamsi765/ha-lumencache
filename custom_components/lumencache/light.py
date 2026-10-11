"""Lights: one per socket card (a fixture) and one per zone listed in the options."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pylumencache.client import NotConnectedError
from pylumencache.inventory import Category, Change, Device, LightState

from . import LumenCacheConfigEntry
from .binary_sensor import hub_device_info
from .const import (
    ATTR_BRIGHTNESS_PCT,
    CONF_MAX_KELVIN,
    CONF_MIN_KELVIN,
    CONF_ZONES,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    DOMAIN,
    SERVICE_SET_LIGHT,
)
from .helpers import ha_to_percent, light_command, parse_zones, percent_to_ha, supports_color_temperature


async def async_setup_entry(
    hass: HomeAssistant, entry: LumenCacheConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_SET_LIGHT,
        {
            vol.Required(ATTR_BRIGHTNESS_PCT): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(ATTR_COLOR_TEMP_KELVIN): vol.All(vol.Coerce(int), vol.Range(min=1000, max=20000)),
            vol.Optional(ATTR_TRANSITION): vol.All(vol.Coerce(float), vol.Range(min=0, max=6553)),
        },
        "async_set_light",
    )
    min_k = entry.options.get(CONF_MIN_KELVIN, DEFAULT_MIN_KELVIN)
    max_k = entry.options.get(CONF_MAX_KELVIN, DEFAULT_MAX_KELVIN)

    # Zones cannot be listed by the system, so they come from the options.
    zones = parse_zones(entry.options.get(CONF_ZONES, ""))
    async_add_entities(
        LumenLight(entry, "zone", zone_id, name, hub_device_info(entry), True, min_k, max_k)
        for zone_id, name in zones.items()
    )

    known: set[int] = set()

    @callback
    def add_fixtures(_change: Change | None = None) -> None:
        new = [d for d in data.model.devices.values() if d.category == Category.SOCKET_CARD and d.gid not in known]
        known.update(d.gid for d in new)
        async_add_entities(_fixture_light(entry, d, min_k, max_k) for d in new)

    add_fixtures()
    # The inventory arrives some seconds after connecting, and again after the system restarts.
    entry.async_on_unload(async_dispatcher_connect(hass, data.signal, add_fixtures))


def _fixture_light(entry: LumenCacheConfigEntry, device: Device, min_k: int, max_k: int) -> LumenLight:
    info = DeviceInfo(
        identifiers={(DOMAIN, device.hsn or f"{entry.entry_id}-{device.gid}")},
        name=device.name or f"Fixture {device.gid}",
        manufacturer="LumenCache",
        model=device.name,
        via_device=(DOMAIN, entry.entry_id),
    )
    return LumenLight(
        entry, "fixture", device.gid, None, info, supports_color_temperature(device.name), min_k, max_k,
        unique=device.hsn,
    )


class LumenLight(LightEntity):
    """A zone or a fixture. The system does not report light state, so the state is assumed."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(
        self,
        entry: LumenCacheConfigEntry,
        kind: str,
        target: int,
        name: str | None,
        device_info: DeviceInfo,
        color_temperature: bool,
        min_kelvin: int,
        max_kelvin: int,
        unique: str | None = None,
    ) -> None:
        self._data = entry.runtime_data
        self._kind, self._target = kind, target
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_unique_id = unique or f"{entry.entry_id}_{kind}_{target}"
        self._attr_min_color_temp_kelvin = min_kelvin
        self._attr_max_color_temp_kelvin = max_kelvin
        if color_temperature:
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
        else:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        self._last_brightness = 100.0   # the first turn-on uses the highest brightness
        self._last_kelvin: int | None = max_kelvin if color_temperature else None

    @property
    def _state(self) -> LightState:
        table = self._data.model.zones if self._kind == "zone" else self._data.model.fixtures
        state = table.get(self._target, LightState())
        if state.brightness:
            self._last_brightness = state.brightness
        if state.color_temperature:
            self._last_kelvin = state.color_temperature
        return state

    @property
    def available(self) -> bool:
        return self._data.client.connected

    @property
    def is_on(self) -> bool | None:
        return self._state.on

    @property
    def brightness(self) -> int | None:
        state = self._state
        if state.brightness is not None:
            return percent_to_ha(state.brightness)
        return 255 if state.on else None

    @property
    def color_temp_kelvin(self) -> int | None:
        if self._attr_color_mode == ColorMode.COLOR_TEMP:
            return self._state.color_temperature
        return None

    async def async_added_to_hass(self) -> None:
        @callback
        def model_changed(change: Change) -> None:
            if change.kind == self._kind and change.key == self._target:
                self.async_write_ha_state()

        @callback
        def connection_changed(_connected: bool) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, self._data.signal, model_changed))
        self.async_on_remove(async_dispatcher_connect(self.hass, self._data.connection_signal, connection_changed))

    async def async_turn_on(self, **kwargs: Any) -> None:
        _ = self._state   # refreshes the remembered last values
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        transition = kwargs.get(ATTR_TRANSITION)
        await self._send(light_command(
            zone=self._target if self._kind == "zone" else None,
            gid=self._target if self._kind == "fixture" else None,
            on=True,
            brightness_percent=None if brightness is None else ha_to_percent(brightness),
            kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            fade_ms=None if transition is None else int(transition * 1000),
            last_brightness=self._last_brightness,
            last_kelvin=self._last_kelvin,
        ))

    async def async_turn_off(self, **kwargs: Any) -> None:
        transition = kwargs.get(ATTR_TRANSITION)
        await self._send(light_command(
            zone=self._target if self._kind == "zone" else None,
            gid=self._target if self._kind == "fixture" else None,
            on=False,
            brightness_percent=None,
            kelvin=None,
            fade_ms=None if transition is None else int(transition * 1000),
            last_brightness=self._last_brightness,
            last_kelvin=self._last_kelvin,
        ))

    async def async_set_light(self, **kwargs: Any) -> None:
        """The `lumencache.set_light` service: brightness in percent, down to 0.1%. Zero turns the light off."""
        percent = round(kwargs[ATTR_BRIGHTNESS_PCT], 1)
        transition = kwargs.get(ATTR_TRANSITION)
        _ = self._state   # refreshes the remembered last values
        await self._send(light_command(
            zone=self._target if self._kind == "zone" else None,
            gid=self._target if self._kind == "fixture" else None,
            on=percent > 0,
            brightness_percent=percent,
            kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            fade_ms=None if transition is None else int(transition * 1000),
            last_brightness=self._last_brightness,
            last_kelvin=self._last_kelvin,
        ))

    async def _send(self, command: dict[str, Any]) -> None:
        try:
            await self._data.client.send(command)
        except NotConnectedError as err:
            raise HomeAssistantError("Not connected to the LumenCache system") from err
