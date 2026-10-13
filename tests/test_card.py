"""The integration serves its Lovelace card and has the frontend load it."""
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.setup import async_setup_component

from custom_components.lumencache import CARD_FILE, CARD_URL
from custom_components.lumencache.const import DOMAIN


async def test_card_is_served_and_loaded_by_the_frontend(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    assert CARD_FILE.is_file()
    urls = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert any(url.startswith(f"{CARD_URL}?v=") for url in urls)   # versioned, so an update is fetched again
    routes = [resource.canonical for resource in hass.http.app.router.resources()]
    assert CARD_URL in routes


async def test_the_card_file_is_really_served(hass, hass_client):
    assert await async_setup_component(hass, "frontend", {})
    assert await async_setup_component(hass, DOMAIN, {})
    response = await (await hass_client()).get(CARD_URL)
    assert response.status == 200
    assert "customElements.define(\"lumencache-card\"" in await response.text()
