"""The integration serves its Lovelace card and has the frontend load it."""
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.setup import async_setup_component

from custom_components.lumencache import CARD_FILE, CARD_URL
from custom_components.lumencache.const import DOMAIN


async def test_card_is_served_and_loaded_by_the_frontend(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    assert CARD_FILE.is_file()
    assert CARD_URL in hass.data[DATA_EXTRA_MODULE_URL].urls
    routes = [resource.canonical for resource in hass.http.app.router.resources()]
    assert CARD_URL in routes
