# ha-lumencache

Control a [LumenCache](https://www.lumencache.com) ReNetA lighting system entirely from Home Assistant, with no need to talk to MQTT yourself.

> **Unofficial.** This is an independent, community project. It is not made, endorsed or supported by LumenCache. "LumenCache" and "ReNetA" are names of their respective owners.

> **Status: pre-alpha.** Nothing is released yet. A first version of the integration exists (see [What works now](#what-works-now)); items marked *(planned)* do not exist yet. Follow the [roadmap](#roadmap) for progress.

## What works now

- Setup from the UI (host, port, username, password, Prefix Topic, TLS verification).
- A **connection** `binary_sensor`.
- A `light` for each socket card the system announces (color temperature for SC-CC models, brightness only otherwise) and for each zone you list in the integration's options (the system cannot list its zones). Brightness, color temperature and transition (fade) work; turning on without parameters restores the last values.
- A **brightness × color-temperature card** (`custom:lumencache-card`): color temperature across, brightness up, a fade time, and a card editor for every setting. See [The brightness × color card](#the-brightness--color-card).
- Optionally, the color temperatures your lights can be set to, in the integration's options (for example `2700, 3000, 3500, 4000, 5000`). They set the lights' range and are shown by the card.
- The inventory is saved between restarts, because the system does not keep it on the broker.
- Services: `lumencache.set_light` (brightness in 0.1% steps, with color temperature and transition) and `lumencache.send_raw` (any command).
- A diagnostics download with the host, credentials, Prefix Topic and serial numbers removed.
- A repair issue when the integration is connected but no device is announced for 10 minutes, which usually means a wrong Prefix Topic.
- **Reconfigure** from the integration's menu, to change the host, credentials or Prefix Topic without removing the system.
- **State is assumed.** The system does not report the state of a light. A light shows the state of the last command sent through the system (by this integration, a wall switch or any other client). Fixtures that belong to a zone do not follow zone commands, because zone membership cannot be read.

Not yet: wall-switch events, zone membership services, commissioning, reboot and reset, and the other services listed below. The color temperature range (default 2700 to 6500 K) is a setting because the fixtures' real range is not known yet.

The protocol library is in its own repository, [pylumencache](https://github.com/vamsi765/pylumencache), together with the protocol description.

## What it does

ha-lumencache sits between Home Assistant and your ReNetA system's MQTT broker. It translates Home Assistant actions into ReNetA commands, listens to the system's `status`, `meta` and `events` topics, and keeps an accurate live picture of every light, zone and switch.

Goals:

- **Complete wrapper.** Every ReNetA function is reachable from Home Assistant, including commissioning and configuration, so you rarely need the PowerPlane display or raw MQTT.
- **Built to last.** Typed protocol layer, tested against recorded real traffic, documented, and versioned.
- **Native feel.** Standard Home Assistant `light` entities that work with automations, scenes, groups, voice assistants and Adaptive Lighting.

## Features *(planned)*

- Fixtures and zones as `light` entities, with brightness, color temperature and fade.
- Brightness down to the system's 0.1% minimum through a precise service and the card.
- **Turn-on restores the last settings.** Each fixture keeps its current and last brightness, color temperature and fade. Turning a light on with no parameters restores the last values instead of jumping to 100%. The first-ever turn-on uses the highest brightness and highest color temperature.
- Zone control and zone membership management.
- Wall-switch (SW-D) events as Home Assistant `event` entities for use in automations.
- Diagnostics: connection status, faults, socket card / SIB mismatch reports, a diagnostics download with credentials removed, and Home Assistant repair issues.
- Commissioning tools as services: find uncommissioned devices, assign group IDs, set drive current, set socket card mode.
- A guarded **factory reset** in a "Danger zone" (see [Safety](#safety)).
- Several ReNetA systems at once. Each system is independent and is added separately; with only one system, no selector is shown anywhere.

## How it works

```
Home Assistant (e.g. in Docker)
 ├─ lumencache-card            Lovelace card (2D brightness × color pad), served by the integration
 ├─ custom_components/lumencache   thin integration: config flow, entities, services
 └─ pylumencache               protocol library (separate repository, from PyPI)
      │  MQTT over TLS (port 8883)
      ▼
ReNetA system → PDMs → SIBs / socket cards → fixtures
```

Design points:

- The integration uses its **own MQTT client** to the ReNetA broker. It does not use, and does not interfere with, Home Assistant's built-in MQTT integration.
- Entities are **created dynamically** from the system's `meta` data and keyed by hardware identity, so reassigning group IDs does not break entities.
- Each ReNetA system gets its own client and state; one system going offline does not affect another.
- The system's own memory of each light's previous settings is mirrored where it can be read. The integration keeps its own copy only as a fallback.

## Requirements

- Home Assistant (container, OS or supervised installs all work; the integration is a custom component and needs no add-on).
- A ReNetA system reachable from Home Assistant, with MQTT enabled.
- MQTT credentials for the system. LumenCache issues them on request.

## Installation

You need a recent Home Assistant: the library uses `paho-mqtt` 2.1 or later through `aiomqtt`, and older Home Assistant releases pin version 1.6. The `pylumencache` library comes from [PyPI](https://pypi.org/project/pylumencache/); Home Assistant installs it by itself when the integration loads, in Docker too.

### Through HACS

[HACS](https://hacs.xyz) as a custom repository at first:

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/vamsi765/ha-lumencache` with category **Integration**.
3. Install **LumenCache**, then restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → LumenCache**.

To update later: open **LumenCache** in HACS, choose **⋮ → Update information**, then **Update** (or **Redownload**), and restart Home Assistant.

The card is served by the integration itself, so there is no separate card install.

### By hand, for debugging

Use this to try a change quickly, or a build of the library that is not on PyPI, without waiting for a release.

1. Build the library wheel from a checkout of [pylumencache](https://github.com/vamsi765/pylumencache): `pip wheel . --no-deps -w dist`.
2. Copy the integration folder `custom_components/lumencache` into your Home Assistant configuration directory (the one mounted at `/config`), so you have `<config>/custom_components/lumencache`. Copy the wheel to `<config>/wheels/`.
3. Install the wheel inside the container, using your container's name: `docker exec homeassistant pip install /config/wheels/pylumencache-*.whl`
4. Restart the container, then go to **Settings → Devices & services → Add integration → LumenCache**.

The library is installed inside the container, so recreating the container (for example after pulling a new Home Assistant image) removes it. Run step 3 again afterwards. A wheel with a version at or above what `manifest.json` asks for is kept, and Home Assistant does not replace it from PyPI.

## Configuration

Setup is done in the UI:

1. Enter the system's host, port (default `8883`), username, password and **Prefix Topic** (the value LumenCache gives you, a topic path such as `platform:na/.../<id>`), and choose the TLS option (certificate verification is on by default).
2. The integration connects, reads the system's device list and creates the entities.
3. Optionally, use the integration's options to rename fixtures, assign areas, set color temperature ranges, and set the default fade time.

To add another ReNetA system, repeat step 1. Each system keeps its own options.

## Entities *(planned)*

| What | Home Assistant entity |
|---|---|
| Fixture or socket card | `light` (brightness, and color temperature for CCT fixtures) |
| Zone | `light` (derived group state) |
| Wall switch (SW-D) | `event` (click, multi-click, long press) |
| System connection | `binary_sensor` (connectivity) |
| Port, SIB and fault status | diagnostic `sensor` / `binary_sensor` |
| Reboot | `button` |

## Services

`lumencache.set_light` and `lumencache.send_raw` exist now; the others are *(planned)*.

| Service | Purpose |
|---|---|
| `lumencache.set_light` | Precise brightness (0.1% steps), color temperature and fade, for lights or zones. Available now |
| `lumencache.add_to_zone`, `remove_from_zone`, `list_device_zones` | Zone membership: add (with optional zone defaults), remove, and list a device's zones |
| `lumencache.hail` | Look up what is at a GID (the default, GID 0, lists devices not yet commissioned) |
| `lumencache.query_device` | Ask a device to ping, send its heartbeat, report its status, or dump its configuration |
| `lumencache.assign_gid` | Commission a device (optionally persist) |
| `lumencache.set_drive_current` | Set drive current and defaults (optionally persist) |
| `lumencache.set_socket_mode` | Change a socket card's operating mode |
| `lumencache.reboot` | Reboot a device (by GID) |
| `lumencache.factory_reset` | Factory reset a device (by GID), behind safeguards |
| `lumencache.send_raw` | Send any ReNetA command, as a fallback. Available now |

System-level services take an optional `system` field. With one system it is filled in automatically; with several it is required.

The standard `light.turn_on` / `light.turn_off` services also work, so voice assistants and existing automations behave normally.

## The brightness × color card

The integration serves the card and loads it in the dashboard by itself, so there is nothing else to install. Add it from the card picker (**LumenCache brightness × colour**), or in YAML:

```yaml
type: custom:lumencache-card
entity: light.kitchen
```

The card has two layouts, chosen with `layout`. **Pad** (the default) is described below. **Sliders** is the plain version: two upright sliders side by side, one for brightness and one for color temperature (warm at the bottom), which suits a phone held upright, with the same bands, off zone, snapping, fade time and editor. Both send the same commands, so brightness can be set in 0.1% steps either way.

- **Pad, X axis: color temperature.** If the lights have a list of temperatures (the integration's options, or the card's own list), each one is a band of the same width, with its own background color, however far apart they are in kelvin. Without a list the pad is a smooth range.
- **Pad, Y axis: brightness**, on a gamma curve by default so that equal steps look equal. There is a hatched "off" zone under a line at the minimum brightness: dragging down through the line gives off, dragging up from off gives the minimum.
- **Dragging** moves the handle exactly with your finger. The value changes where the background changes, and the handle settles on it when you let go, over the fade time (at most 3 s; 0.25 s when the fade is 0).
- **Fade time** sits below the pad, in one of four looks.
- **Off** puts the handle at the bottom, in the last color band.
- Keyboard: the arrow keys move between bands and brightness steps.

Everything can be set in the card editor, with no YAML: the light and its name; each temperature, its value and background color (or the integration's list); snapping; the minimum and maximum brightness; the brightness scale; the color of the off/on line; whether the fade shows, its look and its choices; and whether to send while dragging or on release. The editor shows what is wrong with a value and keeps the card at its last good settings until it is fixed. **Copy the settings of another light's card** takes over another card's settings, including its layout (but not its light or name), so a second light is one step.

In YAML, with the defaults:

```yaml
type: custom:lumencache-card
entity: light.kitchen
name: ""                         # defaults to the entity's name
layout: pad                      # pad, or sliders for one slider each
color_steps:                     # defaults to the integration's list; a number, or {kelvin, color}
  - 2700
  - {kelvin: 3000, color: "#ffb36b"}
  - 3500
snap_to_steps: true              # false allows values between neighbouring bands
min_brightness_pct: 5            # under it the pad means off; 0 for no off zone
max_brightness_pct: 100
brightness_curve: gamma          # gamma, perceptual (logarithmic) or linear
marker_color: "#ffffff"          # the off/on line
show_fade: true
fade_style: segments             # segments, slider, stepper or classic (a box with buttons)
fade_presets: [0, 0.5, 1, 3, 10] # seconds
show_presets: true
preset_hold_ms: 550              # milliseconds to hold a preset to change it
preset_ring: accent              # accent (the theme's), preset (its own colour), or any CSS colour
send_mode: live                  # live (throttled while dragging) or on_release
```

### Presets

Right under the title the card shows presets: saved brightness and color temperature, as named dots with a ring for the brightness, in a row you swipe sideways. The active one is kept in view, and **…** stays at the right, under the power button, outside the scrolling part. Tap one to apply it (with the fade time chosen on the card). **Hold** one for about half a second (`preset_hold_ms`, 550 by default, 300 to 3000) to change it, with a ring filling as you hold; moving your finger or the mouse more than a few pixels, or scrolling the strip, cancels the hold: a sheet offers *Save these values* (the light's current values), *Rename*, *Reset to shared* and *Hide*. The **…** button opens **Presets**, where you switch presets on and off for yourself, delete your own, and add one from the light's current values (or a few typical ones to start).

- **Per light and per person.** Presets belong to a light, so every card for that light shows the same ones, and each Home Assistant user has their own list. Nobody sees another person's presets.
- **Shared presets.** An admin can share presets with everyone. In **Presets** an admin also sees every member's presets for the light, and can *Add to shared* or *Dismiss* them, and can update, rename or remove a shared preset. A member who changes a shared preset gets their own copy of it, and *Reset to shared* puts the shared one back. Each person can hide any preset from their own card.
- **Stored by the integration**, in Home Assistant's storage and not in the dashboard, so they follow you across devices and survive card edits. They are kept under the light's registry id, so renaming the entity keeps them.
- The ring round each dot shows its brightness. Its colour is the theme's accent by default (`preset_ring: accent`), can be each preset's own colour (`preset`), or any colour you choose; the editor has a picker. A very light colour can be hard to see on a light theme.
- All switched-on presets show, however many; the strip scrolls. `show_presets: false` turns them off. There is a limit of 30 presets per list, only as a guard.

A config with a problem (a minimum above the maximum, a temperature listed twice, an unknown value) is refused with a message that says what to change.

The lights are ordinary Home Assistant lights, so the built-in light controls, tile cards and other cards work as well, and Home Assistant's own dialog is a third way to set them.

## Multiple systems

Each fixture and zone belongs to exactly one ReNetA system, and systems are fully independent. To control lights from two systems together, combine their entities in Home Assistant with light groups, scenes, automations, or the card with several entities. The integration does not span systems.

## Safety

- Commands that persist to the system (`store`) are **off by default** and must be requested explicitly.
- **Factory reset** is available but deliberately hard to reach: the service is admin-only and needs a confirm flag plus the exact device (its GID and name), because the command acts on one device; its button entity is in the configuration category and disabled by default; and the card's device panel shows it in a collapsed "Danger zone" with a red button and a typed-name confirmation.
- Credentials are stored only in the Home Assistant config entry, never in logs or diagnostics.
- TLS verification is on by default.

## Development

### Repository layout *(planned)*

```
ha-lumencache/
├─ custom_components/lumencache/   Home Assistant integration
│  └─ frontend/                    the Lovelace card and its editor (plain JavaScript, no build step)
├─ .devcontainer/                  development container
└─ .github/workflows/
```

### Principles

- Every command and incoming message is a typed model; unknown fields and messages are preserved, never fatal.
- Protocol quirks live in one folder, so a firmware change touches one place.
- `mypy --strict`, `ruff`, `pytest`, `hassfest` and HACS validation run in CI.
- Tests use recorded real traffic and a fake controller, so most development never touches live lights. Live tests on real hardware follow a safety checklist (one known-good fixture; no factory reset).
- The card is checked in a headless browser against a mocked `hass` object; the integration tests check that the card is registered and served.

### Protocol and capture tool

The protocol library, the protocol spec (`asyncapi.yaml`, `protocol.md`) and the capture tool live in the separate [pylumencache](https://github.com/vamsi765/pylumencache) repository. This integration depends on it through `manifest.json` (`requirements`).

## Roadmap

1. **Discovery**: protocol captured and written up.
2. **Library core**: typed models, async client, CLI with capture and diff, tests.
3. **Dev environment**: fake controller and devcontainer.
4. **Integration MVP**: config flow, lights with brightness, color temperature and fade, last-value restore.
5. **Card v1**: the 2D pad, fade input and card editor (done).
6. **Zones and events**: zone lights, membership services, switch events.
7. **Commissioning and configuration services**, including guarded factory reset.
8. **Diagnostics and repairs.**
9. **Hardening and first release** (HACS).

## Contributing

Issues and pull requests are welcome. The project is pre-alpha, so for larger changes please open an issue first. Please keep changes typed and tested, and do not include credentials, MAC addresses or other identifying data in fixtures or issue reports.

## License

Apache License 2.0. See [LICENSE](LICENSE).
