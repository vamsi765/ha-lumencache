"""Presets: saved brightness and color temperature for a light, shown as buttons on the card.

Each light has a list shared by everyone (set by an admin) and a list for each user. A user can hide any
preset from their own card, and a personal preset can stand in for a shared one (`of`). Admins can see every
user's presets and add them to the shared list. Presets are keyed by the entity registry id, so renaming an
entity keeps them.
"""
from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN

MAX_PER_LIST = 30   # only a guard against a runaway list; the card scrolls
NAME_LENGTH = 24
SAVE_DELAY = 2   # seconds
EVENT_UPDATED = f"{DOMAIN}_presets_updated"
DATA_KEY = f"{DOMAIN}_presets"

Preset = dict[str, Any]


class PresetError(Exception):
    """A request that cannot be done, with a code and message for the card."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise PresetError("invalid_name", "Give the preset a name")
    return name[:NAME_LENGTH]


class PresetStore:
    """All presets, saved in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.presets")
        self._data: dict[str, Any] = {"shared": {}, "personal": {}, "hidden": {}, "dismissed": {}}

    async def async_load(self) -> None:
        saved = await self._store.async_load()
        if saved:
            for key in self._data:
                self._data[key] = saved.get(key, {})

    def _changed(self) -> None:
        self._store.async_delay_save(lambda: self._data, SAVE_DELAY)

    def _shared(self, light: str) -> list[Preset]:
        return self._data["shared"].setdefault(light, [])

    def _personal(self, user: str, light: str) -> list[Preset]:
        return self._data["personal"].setdefault(user, {}).setdefault(light, [])

    def _hidden(self, user: str, light: str) -> list[str]:
        return self._data["hidden"].setdefault(user, {}).setdefault(light, [])

    # --- what a user sees ----------------------------------------------------------

    def view(self, light: str, user: str) -> dict[str, Any]:
        shared = self._shared(light)
        shared_ids = {p["id"] for p in shared}
        mine = self._personal(user, light)
        personal = [{**p, "of": p.get("of") if p.get("of") in shared_ids else None} for p in mine]
        return {"shared": [dict(p) for p in shared], "personal": personal, "hidden": list(self._hidden(user, light))}

    # --- a user's own presets --------------------------------------------------------

    def save(self, light: str, user: str, name: str, kelvin: int | None, brightness: float,
             preset_id: str | None = None, of: str | None = None) -> Preset:
        """Add or change one of the user's presets. With `of`, it stands in for that shared preset."""
        name = _clean_name(name)
        mine = self._personal(user, light)
        shared_ids = {p["id"] for p in self._shared(light)}
        if of is not None and of not in shared_ids:
            raise PresetError("not_found", "That shared preset no longer exists")
        existing = None
        if preset_id is not None:
            existing = next((p for p in mine if p["id"] == preset_id), None)
            if existing is None:
                raise PresetError("not_found", "That preset no longer exists")
        elif of is not None:
            existing = next((p for p in mine if p.get("of") == of), None)
        if existing is None:
            if len(mine) >= MAX_PER_LIST:
                raise PresetError("too_many", f"At most {MAX_PER_LIST} presets of your own")
            existing = {"id": secrets.token_hex(4), "of": of}
            mine.append(existing)
        existing.update(name=name, kelvin=kelvin, brightness=brightness)
        self._changed()
        return dict(existing)

    def delete(self, light: str, user: str, preset_id: str) -> None:
        mine = self._personal(user, light)
        kept = [p for p in mine if p["id"] != preset_id]
        if len(kept) == len(mine):
            raise PresetError("not_found", "That preset no longer exists")
        mine[:] = kept
        self._changed()

    def set_hidden(self, light: str, user: str, preset_id: str, hidden: bool) -> None:
        ids = self._hidden(user, light)
        if hidden and preset_id not in ids:
            ids.append(preset_id)
        elif not hidden and preset_id in ids:
            ids.remove(preset_id)
        self._changed()

    # --- admin ------------------------------------------------------------------------

    def review(self, light: str, admin: str) -> list[dict[str, Any]]:
        """Every other user's presets that are not shared yet and have not been dismissed."""
        shared = self._shared(light)
        dismissed = set(self._data["dismissed"].get(light, []))
        out = []
        for user, lights in self._data["personal"].items():
            if user == admin:
                continue
            items = []
            for p in lights.get(light, []):
                if f"{user}:{p['id']}" in dismissed:
                    continue
                same = any(s["name"] == p["name"] and s["kelvin"] == p["kelvin"] and s["brightness"] == p["brightness"]
                           for s in shared)
                items.append({**p, "shared": same})
            if items:
                out.append({"user_id": user, "presets": items})
        return out

    def share(self, light: str, user: str, preset_id: str) -> Preset:
        """Make a user's preset shared. One that stands in for a shared preset replaces its values."""
        source = next((p for p in self._personal(user, light) if p["id"] == preset_id), None)
        if source is None:
            raise PresetError("not_found", "That preset no longer exists")
        shared = self._shared(light)
        target = next((s for s in shared if s["id"] == source.get("of")), None)
        if target is None:
            if len(shared) >= MAX_PER_LIST:
                raise PresetError("too_many", f"At most {MAX_PER_LIST} shared presets")
            target = {"id": secrets.token_hex(4)}
            shared.append(target)
        target.update(name=source["name"], kelvin=source["kelvin"], brightness=source["brightness"])
        self._changed()
        return dict(target)

    def dismiss(self, light: str, user: str, preset_id: str) -> None:
        self._data["dismissed"].setdefault(light, []).append(f"{user}:{preset_id}")
        self._changed()

    def update_shared(self, light: str, preset_id: str, **changes: Any) -> Preset:
        target = next((s for s in self._shared(light) if s["id"] == preset_id), None)
        if target is None:
            raise PresetError("not_found", "That shared preset no longer exists")
        if "name" in changes:
            changes["name"] = _clean_name(changes["name"])
        target.update(changes)
        self._changed()
        return dict(target)

    def add_shared(self, light: str, name: str, kelvin: int | None, brightness: float) -> Preset:
        shared = self._shared(light)
        if len(shared) >= MAX_PER_LIST:
            raise PresetError("too_many", f"At most {MAX_PER_LIST} shared presets")
        preset = {"id": secrets.token_hex(4), "name": _clean_name(name), "kelvin": kelvin, "brightness": brightness}
        shared.append(preset)
        self._changed()
        return dict(preset)

    def unshare(self, light: str, preset_id: str) -> None:
        shared = self._shared(light)
        kept = [s for s in shared if s["id"] != preset_id]
        if len(kept) == len(shared):
            raise PresetError("not_found", "That shared preset no longer exists")
        shared[:] = kept
        self._changed()


# --- the card's connection to it ----------------------------------------------------------

NAME = vol.All(str, vol.Length(min=1, max=200))
KELVIN = vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=1000, max=20000)))
BRIGHTNESS = vol.All(vol.Coerce(float), vol.Range(min=0.1, max=100))
VALUES: dict[Any, Any] = {
    vol.Required("name"): NAME, vol.Required("kelvin"): KELVIN, vol.Required("brightness"): BRIGHTNESS,
}
ID: dict[Any, Any] = {vol.Required("preset_id"): str}
FOR_USER: dict[Any, Any] = {vol.Required("user_id"): str, vol.Required("preset_id"): str}


@dataclass
class Request:
    """What a command works on: the store, the light's key, who asked, and the message."""

    hass: HomeAssistant
    store: PresetStore
    light: str
    user: Any
    msg: dict[str, Any]


Handler = Callable[[Request], Awaitable[Any]]
_COMMANDS: list[Any] = []


def _light(hass: HomeAssistant, entity_id: str) -> str:
    """The registry id that presets are kept under, for one of this integration's lights."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != DOMAIN or entry.domain != "light":
        raise PresetError("not_found", f"{entity_id} is not a LumenCache light")
    return entry.id


def _command(
    schema: dict[Any, Any] | None = None, *, admin: bool = False, reads: bool = False
) -> Callable[[Handler], Handler]:
    """Make a function a websocket command on the store. A change is announced so that other cards update."""
    def decorator(func: Handler) -> Handler:
        message = {
            vol.Required("type"): f"{DOMAIN}/presets/{func.__name__}",
            vol.Required("entity_id"): str,
            **(schema or {}),
        }

        @websocket_api.websocket_command(message)
        @websocket_api.async_response
        async def handler(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
            try:
                request = Request(hass, hass.data[DATA_KEY], _light(hass, msg["entity_id"]), connection.user, msg)
                result = await func(request)
            except PresetError as err:
                connection.send_error(msg["id"], err.code, str(err))
                return
            if not reads:
                hass.bus.async_fire(EVENT_UPDATED, {"entity_id": msg["entity_id"]})
            connection.send_result(msg["id"], result)

        _COMMANDS.append(websocket_api.require_admin(handler) if admin else handler)
        return func

    return decorator


@_command(reads=True)
async def get(r: Request) -> Any:
    return {**r.store.view(r.light, r.user.id), "is_admin": r.user.is_admin}


@_command({**VALUES, vol.Optional("preset_id"): str, vol.Optional("of"): str})
async def save(r: Request) -> Any:
    m = r.msg
    return r.store.save(r.light, r.user.id, m["name"], m["kelvin"], m["brightness"], m.get("preset_id"), m.get("of"))


@_command(ID)
async def delete(r: Request) -> None:
    r.store.delete(r.light, r.user.id, r.msg["preset_id"])


@_command({**ID, vol.Required("hidden"): bool})
async def hide(r: Request) -> None:
    r.store.set_hidden(r.light, r.user.id, r.msg["preset_id"], r.msg["hidden"])


@_command(admin=True, reads=True)
async def review(r: Request) -> Any:
    out = []
    for group in r.store.review(r.light, r.user.id):
        user = await r.hass.auth.async_get_user(group["user_id"])
        out.append({**group, "user_name": user.name if user else "Unknown user"})
    return out


@_command(FOR_USER, admin=True)
async def share(r: Request) -> Any:
    return r.store.share(r.light, r.msg["user_id"], r.msg["preset_id"])


@_command(FOR_USER, admin=True)
async def dismiss(r: Request) -> None:
    r.store.dismiss(r.light, r.msg["user_id"], r.msg["preset_id"])


@_command(VALUES, admin=True)
async def add_shared(r: Request) -> Any:
    m = r.msg
    return r.store.add_shared(r.light, m["name"], m["kelvin"], m["brightness"])


@_command({**ID, vol.Optional("name"): NAME, vol.Optional("kelvin"): KELVIN, vol.Optional("brightness"): BRIGHTNESS},
          admin=True)
async def update_shared(r: Request) -> Any:
    changes = {k: v for k, v in r.msg.items() if k in ("name", "kelvin", "brightness")}
    return r.store.update_shared(r.light, r.msg["preset_id"], **changes)


@_command(ID, admin=True)
async def unshare(r: Request) -> None:
    r.store.unshare(r.light, r.msg["preset_id"])


@callback
def async_register(hass: HomeAssistant, store: PresetStore) -> None:
    hass.data[DATA_KEY] = store
    for command in _COMMANDS:
        websocket_api.async_register_command(hass, command)
