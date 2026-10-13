"""Presets: saved brightness and color temperature, per user and shared, over the websocket the card uses."""
import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.lumencache.const import DOMAIN
from custom_components.lumencache.presets import EVENT_UPDATED, MAX_PER_LIST, PresetStore, async_register

CLIENT_ID = "https://example.com/app"
LIGHT = "light.kitchen"


@pytest.fixture
async def setup(hass):
    store = PresetStore(hass)
    await store.async_load()
    async_register(hass, store)
    er.async_get(hass).async_get_or_create("light", DOMAIN, "kitchen-uid", suggested_object_id="kitchen")
    er.async_get(hass).async_get_or_create("light", "other_platform", "x", suggested_object_id="other")


@pytest.fixture
def ws(hass, hass_ws_client):
    """A websocket client for a user (created with the given admin flag)."""
    async def make(name, admin):
        user = await hass.auth.async_create_user(name, group_ids=[GROUP_ID_ADMIN if admin else GROUP_ID_USER])
        refresh = await hass.auth.async_create_refresh_token(user, CLIENT_ID)
        client = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
        client.user = user
        return client
    return make


async def call(client, command, **fields):
    await client.send_json({"id": 1 + getattr(client, "_n", 0), "type": f"{DOMAIN}/presets/{command}", **fields})
    client._n = getattr(client, "_n", 0) + 1
    return await client.receive_json()


def values(name="Relax", kelvin=2700, brightness=30):
    return {"name": name, "kelvin": kelvin, "brightness": brightness}


async def test_a_user_saves_presets_that_only_they_see(hass, setup, ws):
    ann, ben = await ws("Ann", False), await ws("Ben", False)
    reply = await call(ann, "save", entity_id=LIGHT, **values())
    assert reply["success"] and reply["result"]["name"] == "Relax"
    assert (await call(ann, "get", entity_id=LIGHT))["result"]["personal"][0]["brightness"] == 30
    assert (await call(ben, "get", entity_id=LIGHT))["result"]["personal"] == []


async def test_it_only_works_for_this_integrations_lights(hass, setup, ws):
    ann = await ws("Ann", False)
    for entity in ("light.other", "light.nothing", "switch.kitchen"):
        reply = await call(ann, "get", entity_id=entity)
        assert not reply["success"] and reply["error"]["code"] == "not_found"


@pytest.mark.parametrize("bad", [
    {"name": "", "kelvin": 2700, "brightness": 30},
    {"name": "x", "kelvin": 500, "brightness": 30},
    {"name": "x", "kelvin": 2700, "brightness": 0},
    {"name": "x", "kelvin": 2700, "brightness": 101},
])
async def test_bad_values_are_refused(hass, setup, ws, bad):
    reply = await call(await ws("Ann", False), "save", entity_id=LIGHT, **bad)
    assert not reply["success"]


async def test_a_light_without_color_temperature_has_a_preset_with_none(hass, setup, ws):
    ann = await ws("Ann", False)
    assert (await call(ann, "save", entity_id=LIGHT, name="Dim", kelvin=None, brightness=10))["success"]


async def test_names_are_trimmed_and_shortened(hass, setup, ws):
    ann = await ws("Ann", False)
    reply = await call(ann, "save", entity_id=LIGHT, **values("  A   very very very very long name  "))
    assert reply["result"]["name"] == "A very very very very lo"


async def test_a_preset_can_be_changed_deleted_and_hidden(hass, setup, ws):
    ann = await ws("Ann", False)
    first = (await call(ann, "save", entity_id=LIGHT, **values()))["result"]
    await call(ann, "save", entity_id=LIGHT, preset_id=first["id"], **values("Calm", 2700, 20))
    mine = (await call(ann, "get", entity_id=LIGHT))["result"]["personal"]
    assert [(p["name"], p["brightness"]) for p in mine] == [("Calm", 20)]
    await call(ann, "hide", entity_id=LIGHT, preset_id=first["id"], hidden=True)
    assert (await call(ann, "get", entity_id=LIGHT))["result"]["hidden"] == [first["id"]]
    await call(ann, "hide", entity_id=LIGHT, preset_id=first["id"], hidden=False)
    assert (await call(ann, "get", entity_id=LIGHT))["result"]["hidden"] == []
    assert (await call(ann, "delete", entity_id=LIGHT, preset_id=first["id"]))["success"]
    assert not (await call(ann, "delete", entity_id=LIGHT, preset_id=first["id"]))["success"]


async def test_there_is_a_limit(hass, setup, ws):
    ann = await ws("Ann", False)
    for i in range(MAX_PER_LIST):
        assert (await call(ann, "save", entity_id=LIGHT, **values(f"P{i}")))["success"]
    reply = await call(ann, "save", entity_id=LIGHT, **values("One too many"))
    assert not reply["success"] and reply["error"]["code"] == "too_many"


async def test_only_admins_review_and_share(hass, setup, ws):
    ann = await ws("Ann", False)
    ours = {"user_id": "u", "preset_id": "i"}
    commands = {
        "review": {}, "share": ours, "dismiss": ours, "add_shared": values(),
        "update_shared": {"preset_id": "i", "name": "x"}, "unshare": {"preset_id": "i"},
    }
    for command, fields in commands.items():
        reply = await call(ann, command, entity_id=LIGHT, **fields)
        assert not reply["success"] and reply["error"]["code"] == "unauthorized", command


async def test_an_admin_reviews_and_shares_a_members_preset(hass, setup, ws):
    admin, ann, ben = await ws("Root", True), await ws("Ann", False), await ws("Ben", False)
    movie = (await call(ann, "save", entity_id=LIGHT, **values("Movie", 2700, 15)))["result"]

    review = (await call(admin, "review", entity_id=LIGHT))["result"]
    assert [(g["user_name"], [p["name"] for p in g["presets"]]) for g in review] == [("Ann", ["Movie"])]

    shared = (await call(admin, "share", entity_id=LIGHT, user_id=ann.user.id, preset_id=movie["id"]))["result"]
    assert (await call(ben, "get", entity_id=LIGHT))["result"]["shared"] == [shared]
    assert (await call(admin, "review", entity_id=LIGHT))["result"][0]["presets"][0]["shared"] is True

    await call(admin, "dismiss", entity_id=LIGHT, user_id=ann.user.id, preset_id=movie["id"])
    assert (await call(admin, "review", entity_id=LIGHT))["result"] == []


async def test_an_admin_does_not_review_their_own(hass, setup, ws):
    admin = await ws("Root", True)
    await call(admin, "save", entity_id=LIGHT, **values())
    assert (await call(admin, "review", entity_id=LIGHT))["result"] == []


async def test_a_personal_preset_can_stand_in_for_a_shared_one(hass, setup, ws):
    admin, ann = await ws("Root", True), await ws("Ann", False)
    bright = (await call(admin, "add_shared", entity_id=LIGHT, **values("Bright", 5000, 100)))["result"]
    await call(ann, "save", entity_id=LIGHT, of=bright["id"], **values("Bright", 4000, 90))
    await call(ann, "save", entity_id=LIGHT, of=bright["id"], **values("Bright", 4000, 85))   # the same stand-in
    view = (await call(ann, "get", entity_id=LIGHT))["result"]
    assert [(p["of"], p["brightness"]) for p in view["personal"]] == [(bright["id"], 85)]
    assert view["shared"][0]["brightness"] == 100   # the shared one is untouched

    await call(admin, "unshare", entity_id=LIGHT, preset_id=bright["id"])
    assert (await call(ann, "get", entity_id=LIGHT))["result"]["personal"][0]["of"] is None


async def test_sharing_a_stand_in_updates_the_shared_preset(hass, setup, ws):
    admin, ann = await ws("Root", True), await ws("Ann", False)
    bright = (await call(admin, "add_shared", entity_id=LIGHT, **values("Bright", 5000, 100)))["result"]
    mine = (await call(ann, "save", entity_id=LIGHT, of=bright["id"], **values("Bright", 4000, 90)))["result"]
    await call(admin, "share", entity_id=LIGHT, user_id=ann.user.id, preset_id=mine["id"])
    shared = (await call(ann, "get", entity_id=LIGHT))["result"]["shared"]
    assert [(s["id"], s["kelvin"], s["brightness"]) for s in shared] == [(bright["id"], 4000, 90)]


async def test_an_admin_edits_shared_presets(hass, setup, ws):
    admin = await ws("Root", True)
    preset = (await call(admin, "add_shared", entity_id=LIGHT, **values("Bright", 5000, 100)))["result"]
    await call(admin, "update_shared", entity_id=LIGHT, preset_id=preset["id"], name="Cooking", brightness=90)
    shared = (await call(admin, "get", entity_id=LIGHT))["result"]["shared"]
    assert [(s["name"], s["kelvin"], s["brightness"]) for s in shared] == [("Cooking", 5000, 90)]


async def test_a_change_is_announced_so_other_cards_update(hass, setup, ws):
    events = async_capture_events(hass, EVENT_UPDATED)
    ann = await ws("Ann", False)
    await call(ann, "get", entity_id=LIGHT)
    assert events == []
    await call(ann, "save", entity_id=LIGHT, **values())
    await hass.async_block_till_done()
    assert [e.data for e in events] == [{"entity_id": LIGHT}]


async def test_presets_follow_a_renamed_entity(hass, setup, ws):
    ann = await ws("Ann", False)
    await call(ann, "save", entity_id=LIGHT, **values())
    er.async_get(hass).async_update_entity(LIGHT, new_entity_id="light.kitchen_main")
    assert len((await call(ann, "get", entity_id="light.kitchen_main"))["result"]["personal"]) == 1


async def test_presets_are_kept_between_restarts(hass, hass_storage):
    store = PresetStore(hass)
    store.save("light-key", "user-1", "Relax", 2700, 30)
    store.add_shared("light-key", "Bright", 5000, 100)
    await store._store.async_save(store._data)

    again = PresetStore(hass)
    await again.async_load()
    view = again.view("light-key", "user-1")
    assert [p["name"] for p in view["personal"]] == ["Relax"] and [p["name"] for p in view["shared"]] == ["Bright"]
