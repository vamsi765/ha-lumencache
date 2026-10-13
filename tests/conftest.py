import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

try:
    # pycares (behind aiohttp's resolver) starts one long-lived thread the first time it is used. Older versions of
    # the Home Assistant test plugin blame the first test that uses an HTTP client for it, so start it up front.
    import pycares

    pycares.Channel()
except Exception:   # not installed, or a version that does not need this
    pass


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield
