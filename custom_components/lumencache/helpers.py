"""Pure helpers with no Home Assistant imports, so they can be tested on their own."""
from __future__ import annotations

from pylumencache import Command, SetFixture, Target


def ha_to_percent(brightness: int) -> float:
    """Home Assistant brightness (0 to 255) to the system's percent (0 to 100)."""
    return round(brightness * 100 / 255, 1)


def percent_to_ha(percent: float) -> int:
    return round(percent * 255 / 100)


def parse_zones(text: str) -> dict[int, str]:
    """Parse "250: Living room, 251: Kitchen" (a bare "250" is also fine) into {250: "Living room", ...}."""
    zones: dict[int, str] = {}
    for part in text.replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        number, _, name = part.partition(":")
        try:
            zone_id = int(number.strip())
        except ValueError as err:
            raise ValueError(f"not a zone number: {number.strip()!r}") from err
        if not 0 <= zone_id <= 65535:
            raise ValueError(f"zone number out of range: {zone_id}")
        zones[zone_id] = name.strip() or f"Zone {zone_id}"
    return zones


def format_zones(zones: dict[int, str]) -> str:
    return ", ".join(f"{zone_id}: {name}" for zone_id, name in zones.items())


def light_command(
    target: Target,
    *,
    on: bool,
    brightness_percent: float | None,
    kelvin: int | None,
    fade_ms: int | None,
    last_brightness: float,
    last_kelvin: int | None,
) -> Command:
    """The command for turning a zone or a fixture on or off.

    Turning on without a brightness restores the last one (the highest, 100, the first time).
    """
    if not on:
        return SetFixture(target, 0, None, fade_ms)
    brightness = brightness_percent if brightness_percent is not None else last_brightness
    return SetFixture(target, brightness, kelvin if kelvin is not None else last_kelvin, fade_ms)
