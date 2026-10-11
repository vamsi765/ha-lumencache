"""LumenCache ReNetA lighting."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from pylumencache.client import LumenCacheClient
from pylumencache.inventory import Change, SystemModel

from .const import CONF_PREFIX, CONF_VERIFY_TLS, CONNECT_TIMEOUT, DOMAIN, SAVE_DELAY

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.LIGHT]


@dataclass
class LumenCacheData:
    client: LumenCacheClient
    model: SystemModel
    signal: str   # dispatcher signal for model changes of this entry
    connection_signal: str


type LumenCacheConfigEntry = ConfigEntry[LumenCacheData]


async def async_setup_entry(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> bool:
    store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    saved = await store.async_load()
    model = SystemModel.from_dict(saved) if saved else SystemModel()

    client = LumenCacheClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PREFIX],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify_tls=entry.data[CONF_VERIFY_TLS],
    )
    data = LumenCacheData(client, model, f"{DOMAIN}_{entry.entry_id}_model", f"{DOMAIN}_{entry.entry_id}_connection")

    @callback
    def model_changed(change: Change) -> None:
        if change.kind in ("device", "zone", "fixture"):
            store.async_delay_save(model.to_dict, SAVE_DELAY)
        async_dispatcher_send(hass, data.signal, change)

    @callback
    def connection_changed(connected: bool) -> None:
        async_dispatcher_send(hass, data.connection_signal, connected)

    entry.async_on_unload(model.add_listener(model_changed))
    entry.async_on_unload(model.attach(client))
    entry.async_on_unload(client.add_connection_listener(connection_changed))
    entry.runtime_data = data

    await client.start()
    try:
        await client.wait_connected(CONNECT_TIMEOUT)
    except TimeoutError as err:
        await client.stop()
        raise ConfigEntryNotReady(f"Could not connect to {entry.data[CONF_HOST]}") from err

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.stop()
        await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_save(entry.runtime_data.model.to_dict())
    return unloaded
