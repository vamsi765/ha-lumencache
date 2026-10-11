"""LumenCache ReNetA lighting."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from pylumencache import Change, LumenCache, NotConnectedError, SystemModel, UnsupportedError

from .const import (
    ATTR_COMMAND,
    ATTR_SYSTEM,
    CONF_PREFIX,
    CONF_VERIFY_TLS,
    CONNECT_TIMEOUT,
    DOMAIN,
    NO_DEVICES_DELAY,
    SAVE_DELAY,
    SERVICE_SEND_RAW,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.LIGHT]


@dataclass
class LumenCacheData:
    cache: LumenCache
    model: SystemModel
    signal: str   # dispatcher signal for model changes of this entry
    connection_signal: str


type LumenCacheConfigEntry = ConfigEntry[LumenCacheData]


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SEND_RAW_SCHEMA = vol.Schema({
    vol.Required(ATTR_COMMAND): vol.All(dict, vol.Schema({vol.Required("e"): vol.Coerce(int)}, extra=vol.ALLOW_EXTRA)),
    vol.Optional(ATTR_SYSTEM): cv.string,
})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def send_raw(call: ServiceCall) -> None:
        """Send any command to a system: the one given, or the only one set up."""
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if ATTR_SYSTEM in call.data:
            entries = [e for e in entries if e.entry_id == call.data[ATTR_SYSTEM]]
        if len(entries) != 1:
            raise ServiceValidationError(
                "Give the system (config entry id) to send to" if entries else "No LumenCache system is loaded"
            )
        try:
            await entries[0].runtime_data.cache.send_raw(call.data[ATTR_COMMAND])
        except NotConnectedError as err:
            raise HomeAssistantError("Not connected to the LumenCache system") from err
        except UnsupportedError as err:
            raise HomeAssistantError("This connection does not take raw commands") from err

    hass.services.async_register(DOMAIN, SERVICE_SEND_RAW, send_raw, schema=SEND_RAW_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> bool:
    store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    saved = await store.async_load()
    model = SystemModel.from_dict(saved) if saved else SystemModel()

    cache = LumenCache.mqtt(
        entry.data[CONF_HOST],
        entry.data[CONF_PREFIX],
        model=model,
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify_tls=entry.data[CONF_VERIFY_TLS],
    )
    data = LumenCacheData(cache, model, f"{DOMAIN}_{entry.entry_id}_model", f"{DOMAIN}_{entry.entry_id}_connection")

    @callback
    def model_changed(change: Change) -> None:
        if change.kind in ("device", "zone", "fixture"):
            store.async_delay_save(model.to_dict, SAVE_DELAY)
        async_dispatcher_send(hass, data.signal, change)

    @callback
    def connection_changed(connected: bool) -> None:
        async_dispatcher_send(hass, data.connection_signal, connected)

    entry.async_on_unload(model.add_listener(model_changed))
    entry.async_on_unload(cache.add_connection_listener(connection_changed))
    entry.runtime_data = data

    await cache.start()
    try:
        await cache.wait_connected(CONNECT_TIMEOUT)
    except TimeoutError as err:
        await cache.stop()
        raise ConfigEntryNotReady(f"Could not connect to {entry.data[CONF_HOST]}") from err

    _watch_for_no_devices(hass, entry, data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


def _watch_for_no_devices(hass: HomeAssistant, entry: LumenCacheConfigEntry, data: LumenCacheData) -> None:
    """Raise a repair issue when connected but no device has been announced for a while.

    The usual cause is a wrong Prefix Topic: the broker accepts the login but nothing arrives under it.
    """
    issue_id = f"no_devices_{entry.entry_id}"

    @callback
    def check(_now: Any = None) -> None:
        if data.model.devices:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
        elif data.cache.connected:
            ir.async_create_issue(
                hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                translation_key="no_devices",
            )

    @callback
    def model_changed(change: Change) -> None:
        if change.kind == "device":
            check()

    entry.async_on_unload(async_call_later(hass, NO_DEVICES_DELAY, check))
    entry.async_on_unload(data.model.add_listener(model_changed))
    entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, issue_id))


async def _options_updated(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.cache.stop()
        store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.{entry.entry_id}")
        await store.async_save(entry.runtime_data.model.to_dict())
    return unloaded
