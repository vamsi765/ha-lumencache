"""How a config entry becomes a connection to a system. The one place that knows which transport is used."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from pylumencache import LumenCache, SystemModel

from .const import CONF_PREFIX, CONF_VERIFY_TLS


def cache_from(data: Mapping[str, Any], model: SystemModel | None = None) -> LumenCache:
    """A connection (not yet started) to the system the entry data describes."""
    return LumenCache.mqtt(
        data[CONF_HOST],
        data[CONF_PREFIX],
        model=model,
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        verify_tls=data[CONF_VERIFY_TLS],
    )
