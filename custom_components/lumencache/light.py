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
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pylumencache import Category, Change, Device, FixtureState, Target, Zone, fixture_for

from . import LumenCacheConfigEntry
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
from .entity import LumenFixtureEntity, hub_device_info
from .helpers import ha_to_percent, light_command, parse_zones, percent_to_ha


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
        LumenLight(entry, Zone(zone_id), name, hub_device_info(entry), True, min_k, max_k)
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
    fixture = fixture_for(device)
    info = DeviceInfo(
        identifiers={(DOMAIN, device.hsn or f"{entry.entry_id}-{device.gid}")},
        name=device.name or f"Fixture {device.gid}",
        manufacturer="LumenCache",
        model=device.name,
        via_device=(DOMAIN, entry.entry_id),
    )
    return LumenLight(entry, fixture, None, info, fixture.color_temperature, min_k, max_k, unique=device.hsn)


class LumenLight(LumenFixtureEntity, LightEntity):
    """A zone or a fixture shown as a light."""

    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(
        self,
        entry: LumenCacheConfigEntry,
        target: Target,
        name: str | None,
        device_info: DeviceInfo,
        color_temperature: bool,
        min_kelvin: int,
        max_kelvin: int,
        unique: str | None = None,
    ) -> None:
        super().__init__(entry, target, name, device_info, unique)
        self._attr_min_color_temp_kelvin = min_kelvin
        self._attr_max_color_temp_kelvin = max_kelvin
        mode = ColorMode.COLOR_TEMP if color_temperature else ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {mode}
        self._attr_color_mode = mode
        self._last_brightness = 100.0   # the first turn-on uses the highest brightness
        self._last_kelvin: int | None = max_kelvin if color_temperature else None

    @property
    def _state(self) -> FixtureState:
        """The state, remembering the last brightness and color temperature to restore on the next turn-on."""
        state = super()._state
        if state.brightness:
            self._last_brightness = state.brightness
        if state.color_temperature:
            self._last_kelvin = state.color_temperature
        return state

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        await self._set(
            on=True,
            brightness_percent=None if brightness is None else ha_to_percent(brightness),
            kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            transition=kwargs.get(ATTR_TRANSITION),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(on=False, brightness_percent=None, kelvin=None, transition=kwargs.get(ATTR_TRANSITION))

    async def async_set_light(self, **kwargs: Any) -> None:
        """The `lumencache.set_light` service: brightness in percent, down to 0.1%. Zero turns the light off."""
        percent = round(kwargs[ATTR_BRIGHTNESS_PCT], 1)
        await self._set(
            on=percent > 0,
            brightness_percent=percent,
            kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            transition=kwargs.get(ATTR_TRANSITION),
        )

    async def _set(
        self, *, on: bool, brightness_percent: float | None, kelvin: int | None, transition: float | None
    ) -> None:
        _ = self._state   # refreshes the remembered last values
        await self._send(light_command(
            self._target,
            on=on,
            brightness_percent=brightness_percent,
            kelvin=kelvin,
            fade_ms=None if transition is None else int(transition * 1000),
            last_brightness=self._last_brightness,
            last_kelvin=self._last_kelvin,
        ))
