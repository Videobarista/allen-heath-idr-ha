# Allen & Heath iDR for Home Assistant

[![Release](https://img.shields.io/github/v/release/Videobarista/allen-heath-idr-ha)](https://github.com/Videobarista/allen-heath-idr-ha/releases)
[![License](https://img.shields.io/github/license/Videobarista/allen-heath-idr-ha)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Works with Home Assistant 2025.1+](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5)](https://www.home-assistant.io)
[![Ruff](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/ruff.yml/badge.svg?branch=main)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/ruff.yml)
[![Hassfest](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hassfest.yml/badge.svg?branch=main)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hassfest.yml)
[![HACS Validate](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hacs.yml/badge.svg?branch=main)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hacs.yml)
[![CodeQL](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/codeql.yml)
[![Tests](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/tests.yml)
[![Aligned with the Home Assistant quality scale: Bronze](https://img.shields.io/badge/HA%20quality%20scale-Bronze%20(aligned)-cd7f32)](custom_components/allen_heath_idr/quality_scale.yaml)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Videobarista&repository=allen-heath-idr-ha&category=integration)

A local-polling Home Assistant integration for the Allen & Heath iDR-4 / iDR-8
audio mix processor, controlled over its Telnet protocol (TCP port 23). No
cloud, no app, no third-party server.

Not affiliated with or endorsed by Allen & Heath. "Allen & Heath" and "iDR"
are trademarks of their respective owner.

## Status

| Version | Notes |
|---|---|
| 1.2.0 | Setup no longer fails when the iDR is switched off at startup (it's assumed to simply be offline and polling keeps retrying); aligned the integration with the Home Assistant quality scale Bronze tier (tests, `quality_scale.yaml`). |
| 1.1.2 | Friendlier, specific error message when the iDR can't be reached. |
| 1.1.1 | Fixed `set_crosspoint` after a Home Assistant breaking change removed device filters from service targets; the service now targets entities (a device pick still works, HA expands it automatically). |
| 1.1.0 | Added the `set_crosspoint` service for scripting a single crosspoint without needing its entities enabled. |
| 1.0.0 | Added an "Integration version" diagnostic sensor; crosspoint matrix support (optional, off by default) with configurable channel counts, groups and poll interval. |
| 0.2.0 | Gain, mute and preset control. |
| 0.1.0 | Initial release: read-only sensors. |

## Requirements

- An iDR-4 or iDR-8 running firmware **V3.50 or later** (the Telnet control
  protocol was introduced in that version).
- The iDR's Telnet port (23) reachable from Home Assistant. There's no way to
  check the firmware version over Telnet itself — if nothing responds, try
  updating the unit's firmware first.

## Installation

### HACS (custom repository)

1. HACS → the **⋮** menu (top right) → **Custom repositories**.
2. Add `https://github.com/Videobarista/allen-heath-idr-ha`, category **Integration**.
3. Find "Allen & Heath iDR" in HACS and install it.
4. Restart Home Assistant.

Or use the badge above ("Open in HACS") to jump straight to adding the
repository.

### Manual

Copy `custom_components/allen_heath_idr` into your Home Assistant `config/custom_components/` folder and restart.

## Configuration

**Settings → Devices & Services → Add Integration → "Allen & Heath iDR"**, then enter:

- **Host** — the iDR's IP address or hostname.
- **Port** — 23, unless you've changed it on the unit.
- **Password** — only if a Telnet password is set on the unit.

### Options

After adding the integration, open its entry and click **Configure** to set:

| Option | Default | What it does |
|---|---|---|
| Number of input channels | 8 | How many of the 16 possible inputs to expose. |
| Number of output channels | 8 | How many of the 16 possible outputs to expose. |
| Expose groups | Off | Adds 16 entities (8 input + 8 output group gains). |
| Expose crosspoints | Off | Adds a gain **and** a mute entity for every input/output pair — see below before turning this on. |
| Poll interval | 10s | How often to poll. Lower reacts faster but puts more load on the iDR's single Telnet connection. |

Most Home Assistant users don't expect an integration to have an options
step at all — if **Configure** isn't greyed out on the integration's card,
that's where these live.

**Crosspoints adds a lot of entities, on purpose.** Every input/output pair
gets its own gain and mute entity (inputs × outputs × 2), because that's
what it takes to control a true mixing matrix (see below). Some examples:

| Inputs × outputs | Groups | Crosspoints | Entities |
|---|---|---|---|
| 8 × 8 | off | off | 35 (the default) |
| 8 × 8 | on | on | 179 |
| 16 × 16 | off | off | 67 |
| 16 × 16 | on | on | 595 |

If you only need to script one or two crosspoints, the `set_crosspoint`
service (below) does that without turning this option on at all.

## Entities

- **Number**: preset recall, one gain per input/output/group/crosspoint channel exposed.
- **Switch**: one mute per input/output/crosspoint channel exposed.
- **Sensor** (diagnostic): response time, integration version.

### Gain values

The iDR reports an "off" channel as `-Inf`, which isn't a normal dB value, so
each gain number's range includes one extra step below its real minimum,
reserved as the off position — move the slider all the way down (or set it
to that value) to turn the channel off, same as the unit's own front panel.
Each gain entity also exposes an `off` attribute if you'd rather check that
in a template or automation than compare numbers.

### Why a gain and mute per crosspoint, not one dropdown?

A routing matrix (like a video router) sends one input to an output at a
time, so a dropdown per output makes sense there. The iDR's matrix is a true
*mixer*: several inputs can be summed into one output simultaneously, each at
its own independent level. That needs a value per input/output pair, not a
single selection — which is why crosspoints are exposed as individual gain
and mute entities rather than one entity per output.

## Services

### `allen_heath_idr.set_crosspoint`

Sets the gain and/or mute state of a single crosspoint, even if crosspoint
entities aren't enabled in the integration's options. Useful for scripting a
handful of crosspoints without the full entity count above.

```yaml
action: allen_heath_idr.set_crosspoint
target:
  device_id: <your iDR device>
data:
  input: 1
  output: 3
  gain: -6.0
  mute: false
```

`gain` accepts a dB value or `"-Inf"` / `"off"`. At least one of `gain` or
`mute` is required.

## Offline behavior

The integration is built to assume the iDR can simply be switched off —
whether at the wall, or via a mains/NET IO control — and treats that as a
normal state, not a setup failure:

- Setting up the integration (including after a Home Assistant restart)
  **always succeeds**, even if the iDR doesn't respond at that moment.
- While unreachable, all of its entities show as **unavailable** rather than
  the integration failing to load.
- Polling keeps retrying in the background on the normal interval, and
  everything comes back automatically once the unit powers back on — no
  reload needed.

The one exception is the very first time you add the integration: the setup
wizard does need to reach the iDR once, to read its name and model.

## Good to know

- The iDR only ever has **one** Telnet command in flight — sending a second
  before the first reply arrives gets a "Buffer Overrun" error back. This
  integration serializes every read and write through a single connection,
  so it won't trip that itself, but a very short poll interval combined with
  a lot of manual changes at the same time could still be slow to catch up.
- Recalling a preset can change many gains and mutes at once, so the
  integration re-reads everything right after a recall rather than waiting
  for the next scheduled poll.
- The Telnet connection is unencrypted, and a configured password is sent in
  plain text — this is a limitation of the iDR's own protocol, not something
  this integration can change. Only use it on a network you trust.
- Password handling has not been verified against a real password-protected
  unit (the protocol document is slightly ambiguous about the exact bytes
  sent on a wrong password); if you hit trouble here, please open an issue
  with what you saw.
- The iDR's firmware version isn't available over Telnet, so there's no
  sensor for it — only this integration's own version (see the "Integration
  version" diagnostic sensor).

## Quality scale

This integration aims to stay aligned with the Home Assistant quality scale,
**Bronze** tier — see [`quality_scale.yaml`](custom_components/allen_heath_idr/quality_scale.yaml)
for the checklist and the one deliberate exception (setup doesn't fail when
the device is offline, by design — see "Offline behavior" above). This is a
self-assessment: Home Assistant only officially grades core integrations, so
nothing here is an official rating. Higher tiers aren't a current goal.

## Troubleshooting

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.allen_heath_idr: debug
```

## Removing the integration

**Settings → Devices & Services → Allen & Heath iDR → ⋮ → Delete.** This
only removes the integration and its entities from Home Assistant; it has no
effect on the iDR unit itself.

## Brand

`Brand/` contains a generic, self-drawn icon — not Allen & Heath's own logo,
for copyright reasons. See [`Brand/README.md`](Brand/README.md).

## License

MIT — see [LICENSE](LICENSE).
