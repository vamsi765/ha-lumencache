"""Diagnostics download, with credentials, the Prefix Topic and device serial numbers removed."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import LumenCacheConfigEntry
from .const import CONF_PREFIX

TO_REDACT = {CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_PREFIX, "hsn", "path"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: LumenCacheConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "connected": data.client.connected,
        "model": async_redact_data(data.model.to_dict(), TO_REDACT),
    }
