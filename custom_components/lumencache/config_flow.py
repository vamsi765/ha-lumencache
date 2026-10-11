"""Config flow: connect to a ReNetA system, then choose zones and the color temperature range."""
from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from pylumencache.client import LumenCacheClient

from .const import (
    CONF_MAX_KELVIN,
    CONF_MIN_KELVIN,
    CONF_PREFIX,
    CONF_VERIFY_TLS,
    CONF_ZONES,
    CONNECT_TIMEOUT,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    DEFAULT_PORT,
    DOMAIN,
)
from .helpers import format_zones, parse_zones


async def _can_connect(data: dict[str, Any]) -> bool:
    client = LumenCacheClient(
        data[CONF_HOST],
        data[CONF_PREFIX],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        verify_tls=data[CONF_VERIFY_TLS],
    )
    await client.start()
    try:
        await client.wait_connected(CONNECT_TIMEOUT)
    except TimeoutError:
        return False
    finally:
        await client.stop()
    return True


class LumenCacheConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_PREFIX] = user_input[CONF_PREFIX].strip().rstrip("/")
            # The Prefix Topic identifies the system; keep it out of the unique id as plain text.
            digest = hashlib.sha256(f"{user_input[CONF_HOST]}/{user_input[CONF_PREFIX]}".encode()).hexdigest()
            await self.async_set_unique_id(digest[:16])
            self._abort_if_unique_id_configured()
            if await _can_connect(user_input):
                return self.async_create_entry(title=f"LumenCache ({user_input[CONF_HOST]})", data=user_input)
            errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_PREFIX): str,
            vol.Required(CONF_VERIFY_TLS, default=True): bool,
        })
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> LumenCacheOptionsFlow:
        return LumenCacheOptionsFlow()


class LumenCacheOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        options = self.config_entry.options
        if user_input is not None:
            try:
                zones = parse_zones(user_input[CONF_ZONES])
            except ValueError:
                errors[CONF_ZONES] = "invalid_zones"
            else:
                if user_input[CONF_MIN_KELVIN] >= user_input[CONF_MAX_KELVIN]:
                    errors[CONF_MAX_KELVIN] = "invalid_range"
                else:
                    return self.async_create_entry(data={**user_input, CONF_ZONES: format_zones(zones)})

        schema = vol.Schema({
            vol.Optional(CONF_ZONES, default=options.get(CONF_ZONES, "")): str,
            vol.Required(CONF_MIN_KELVIN, default=options.get(CONF_MIN_KELVIN, DEFAULT_MIN_KELVIN)): int,
            vol.Required(CONF_MAX_KELVIN, default=options.get(CONF_MAX_KELVIN, DEFAULT_MAX_KELVIN)): int,
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
