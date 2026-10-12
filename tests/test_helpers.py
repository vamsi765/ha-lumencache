"""The Home Assistant-free helpers, loaded by path so the integration package is not imported."""
import importlib.util
from pathlib import Path

import pytest
from pylumencache import Fixture, SetFixture, Zone

SPEC = importlib.util.spec_from_file_location(
    "lumencache_helpers", Path(__file__).parent.parent / "custom_components" / "lumencache" / "helpers.py"
)
helpers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helpers)


@pytest.mark.parametrize("ha,percent", [(0, 0), (255, 100), (128, 50.2), (1, 0.4)])
def test_brightness_to_percent(ha, percent):
    assert helpers.ha_to_percent(ha) == percent


@pytest.mark.parametrize("percent", [0, 1, 50, 99, 100])
def test_percent_survives_a_round_trip_within_one_step(percent):
    assert abs(helpers.ha_to_percent(helpers.percent_to_ha(percent)) - percent) < 0.5


def test_zones_are_parsed_with_and_without_names():
    assert helpers.parse_zones("250: Living room, 251:Kitchen\n252") == {
        250: "Living room", 251: "Kitchen", 252: "Zone 252"}
    assert helpers.parse_zones("") == {}


@pytest.mark.parametrize("bad", ["abc: x", "70000: x", "-1: x"])
def test_bad_zones_are_refused(bad):
    with pytest.raises(ValueError):
        helpers.parse_zones(bad)


def test_zones_format_and_parse_agree():
    zones = {250: "Living room", 251: "Kitchen"}
    assert helpers.parse_zones(helpers.format_zones(zones)) == zones


def kwargs(**over):
    base = dict(on=True, brightness_percent=None, kelvin=None, fade_ms=None, last_brightness=100.0, last_kelvin=None)
    return {**base, **over}


def test_turn_on_zone_with_everything_given():
    command = helpers.light_command(Zone(250), **kwargs(brightness_percent=50, kelvin=4000, fade_ms=800))
    assert command == SetFixture(Zone(250), 50, 4000, 800)


def test_turn_on_restores_the_last_values():
    command = helpers.light_command(Fixture(14), **kwargs(last_brightness=35.5, last_kelvin=3000))
    assert command == SetFixture(Fixture(14), 35.5, 3000)


def test_first_turn_on_uses_the_highest_brightness():
    assert helpers.light_command(Fixture(14), **kwargs()).brightness == 100.0


def test_turn_off_sets_zero_and_leaves_the_color_alone():
    command = helpers.light_command(Zone(250), **kwargs(on=False, kelvin=4000, fade_ms=1000, last_kelvin=3000))
    assert command == SetFixture(Zone(250), 0, None, 1000)
