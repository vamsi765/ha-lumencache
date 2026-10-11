"""The integration running in Home Assistant on a fake ReNetA system (needs pytest-homeassistant-custom-component)."""
import json
from unittest.mock import patch

import aiomqtt
import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pylumencache.client import LumenCacheClient
from pylumencache.fake import FakeController
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lumencache.const import (
    CONF_PREFIX,
    CONF_VERIFY_TLS,
    CONF_ZONES,
    DOMAIN,
)

PREFIX = "platform:na/test"
DATA = {
    CONF_HOST: "broker.test", CONF_PORT: 8883, CONF_USERNAME: "u", CONF_PASSWORD: "p",
    CONF_PREFIX: PREFIX, CONF_VERIFY_TLS: True,
}
RECORDS = [
    {"topic": "dev/pp:1", "payload": {"gid": 1, "name": "Reneta PP", "cat": 32, "parent": 65535}},
    {"topic": "dev/pp:1/pdm:2", "payload": {"gid": 2, "hsn": "HSN2", "name": "PDM_RJ", "cat": 35, "parent": 1}},
    {"topic": "dev/pp:1/pdm:2/skt:4/scard:14",
     "payload": {"gid": 14, "hsn": "HSN14", "name": "SC-CC2-50W", "cat": 37, "parent": 4}},
    {"topic": "dev/pp:1/pdm:2/skt:6/scard:15",
     "payload": {"gid": 15, "hsn": "HSN15", "name": "SC-PV2-50W", "cat": 37, "parent": 6}},
]


@pytest.fixture
def controller():
    """The fake system; every connection the integration makes is one of its replays."""
    fake = FakeController(RECORDS, PREFIX)
    connections = []

    def factory():
        connection = fake.factory()
        connections.append(connection)
        return connection

    def client(*args, **kwargs):
        return LumenCacheClient(*args, **{**kwargs, "client_factory": factory})

    with patch("custom_components.lumencache.LumenCacheClient", client), \
            patch("custom_components.lumencache.config_flow.LumenCacheClient", client):
        fake.connections = connections
        yield fake


async def setup(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=options or {CONF_ZONES: "250: Living room"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def wait_for(hass, predicate):
    for _ in range(100):
        await hass.async_block_till_done()
        if predicate():
            return
        await hass.async_add_executor_job(lambda: None)
        import asyncio
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


async def test_config_flow_creates_an_entry(hass, controller):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PREFIX] == PREFIX


async def test_config_flow_reports_a_failed_connection(hass):
    class Refusing:
        async def __aenter__(self):
            raise aiomqtt.MqttError("refused")

        async def __aexit__(self, *exc):
            return False

    def client(*args, **kwargs):
        return LumenCacheClient(*args, **{**kwargs, "client_factory": Refusing, "reconnect_delays": (0.01,)})

    with patch("custom_components.lumencache.config_flow.LumenCacheClient", client), \
            patch("custom_components.lumencache.config_flow.CONNECT_TIMEOUT", 0.2):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}


async def test_entities_are_created_from_the_inventory_and_the_options(hass, controller):
    await setup(hass)
    await wait_for(hass, lambda: hass.states.get("light.sc_cc2_50w") is not None)
    assert hass.states.get("binary_sensor.lumencache_connection").state == "on"
    assert hass.states.get("light.lumencache_living_room") is not None            # a zone, from the options
    assert hass.states.get("light.sc_cc2_50w").attributes["supported_color_modes"] == ["color_temp"]
    assert hass.states.get("light.sc_pv2_50w").attributes["supported_color_modes"] == ["brightness"]


async def test_turning_a_fixture_on_sends_a_command_and_follows_the_echo(hass, controller):
    await setup(hass)
    await wait_for(hass, lambda: hass.states.get("light.sc_cc2_50w") is not None)
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.sc_cc2_50w", "brightness": 128, "color_temp_kelvin": 4000,
                             "transition": 0.8}, blocking=True)
    await wait_for(hass, lambda: hass.states.get("light.sc_cc2_50w").state == "on")
    sent = [json.loads(p) for c in controller.connections for t, p in c.published if t.endswith("/cmd")]
    assert sent == [{"e": 57, "g": 14, "bri": 50.2, "cct": 4000, "fade": 800}]
    assert hass.states.get("light.sc_cc2_50w").attributes["brightness"] == 128


async def test_first_turn_on_uses_highest_brightness_and_off_sets_zero_for_a_zone(hass, controller):
    await setup(hass)
    await wait_for(hass, lambda: hass.states.get("light.lumencache_living_room") is not None)
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.lumencache_living_room"}, blocking=True)
    await hass.services.async_call("light", "turn_off", {"entity_id": "light.lumencache_living_room"}, blocking=True)
    await wait_for(hass, lambda: hass.states.get("light.lumencache_living_room").state == "off")
    sent = [json.loads(p) for c in controller.connections for t, p in c.published if t.endswith("/cmd")]
    assert sent == [{"e": 56, "z": 250, "bri": 100.0, "cct": 6500}, {"e": 56, "z": 250, "bri": 0}]


async def test_entry_unloads(hass, controller):
    entry = await setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)


def _sent(controller):
    return [json.loads(p) for c in controller.connections for t, p in c.published if t.endswith("/cmd")]


async def test_set_light_service_sends_a_precise_brightness(hass, controller):
    await setup(hass)
    await wait_for(hass, lambda: hass.states.get("light.sc_cc2_50w") is not None)
    await hass.services.async_call(
        DOMAIN, "set_light", {"entity_id": "light.sc_cc2_50w", "brightness_pct": 0.3, "transition": 2}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "set_light", {"entity_id": "light.lumencache_living_room", "brightness_pct": 0}, blocking=True)
    assert _sent(controller) == [
        {"e": 57, "g": 14, "bri": 0.3, "cct": 6500, "fade": 2000},
        {"e": 56, "z": 250, "bri": 0},
    ]


async def test_send_raw_service_sends_the_command(hass, controller):
    await setup(hass)
    await hass.services.async_call(DOMAIN, "send_raw", {"command": {"e": 10, "g": 12}}, blocking=True)
    assert _sent(controller) == [{"e": 10, "g": 12}]


async def test_send_raw_needs_a_loaded_system(hass):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.lumencache import async_setup
    await async_setup(hass, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send_raw", {"command": {"e": 10}}, blocking=True)


async def test_diagnostics_hide_secrets(hass, controller):
    from custom_components.lumencache.diagnostics import async_get_config_entry_diagnostics

    entry = await setup(hass)
    await wait_for(hass, lambda: hass.states.get("light.sc_cc2_50w") is not None)
    result = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(result)
    for secret in ("broker.test", PREFIX, "HSN14", '"p"'):
        assert secret not in text
    assert result["connected"] is True
    assert {d["gid"] for d in result["model"]["devices"]} == {1, 2, 14, 15}


async def test_repair_issue_when_no_device_arrives(hass, controller):
    from homeassistant.helpers import issue_registry as ir

    from custom_components.lumencache.const import NO_DEVICES_DELAY

    controller._records = []   # a wrong Prefix Topic: connected, nothing announced
    entry = await setup(hass)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"no_devices_{entry.entry_id}") is None
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=NO_DEVICES_DELAY + 1))
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, f"no_devices_{entry.entry_id}") is not None


async def test_reconfigure_changes_the_prefix_and_reloads(hass, controller):
    entry = await setup(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DATA, CONF_PREFIX: "platform:na/other/"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PREFIX] == "platform:na/other"
