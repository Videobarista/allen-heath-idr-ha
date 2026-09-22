# Allen & Heath iDR for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/Videobarista/allen-heath-idr-ha)](https://github.com/Videobarista/allen-heath-idr-ha/releases)
[![License: MIT](https://img.shields.io/github/license/Videobarista/allen-heath-idr-ha)](LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1%2B-41BDF5.svg)](https://www.home-assistant.io/)

[![Hassfest](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hassfest.yml/badge.svg)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hacs.yml/badge.svg)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/hacs.yml)
[![CodeQL](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/codeql.yml/badge.svg)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/codeql.yml)
[![Ruff](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/ruff.yml/badge.svg)](https://github.com/Videobarista/allen-heath-idr-ha/actions/workflows/ruff.yml)

A custom [Home Assistant](https://www.home-assistant.io/) integration for the
Allen & Heath **iDR** audio mix processors (iDR-4 and iDR-8). It talks to the
unit over the network with the Telnet control protocol, fully local and without
any cloud.

> This project is not affiliated with or endorsed by Allen & Heath.

## Status

Feature-complete for what the iDR Telnet protocol offers: reads and controls
gains, mutes, presets and the full crosspoint matrix.

| Version | Content |
| ------- | ------- |
| 0.1.0 | Connection, config flow, diagnostic sensors |
| 0.2.0 | Input and output gain and mute, preset recall, optional group gains and crosspoints, options |
| 0.2.1 | Retries a dropped connection a few times before marking the iDR unavailable |
| 0.2.2 | Documentation only: clarified the options screen and entity counts |
| 1.0.0 | First stable release. Adds an Integration version diagnostic entity |
| 1.1.0 | New `allen_heath_idr.set_crosspoint` service |
| 1.1.1 | Fixed the service's target: Home Assistant removed device filters from service targets |
| 1.1.2 | Clearer message when the iDR cannot be reached (no more raw network error text) |

## Requirements

- An iDR-4 or iDR-8 with firmware **V3.50 or later** (the Telnet control
  protocol was introduced in that version). To read the firmware version, remove
  the face plate and hold the ESC key.
- The network port of the iDR connected to a network that Home Assistant can
  reach. The Telnet server listens on TCP port 23.
- Home Assistant 2025.1 or newer.

## Installation

### HACS (custom repository)

1. In HACS, open the menu (three dots) and choose **Custom repositories**.
2. Add `https://github.com/Videobarista/allen-heath-idr-ha` with category
   **Integration**.
3. Download **Allen & Heath iDR** and restart Home Assistant.

### Manual

Copy the folder `custom_components/allen_heath_idr` to the `custom_components`
folder of your Home Assistant configuration and restart Home Assistant.

## Configuration

Go to **Settings > Devices & services > Add integration** and search for
**Allen & Heath iDR**. Enter the IP address of the iDR. The port is 23 unless you
changed it. Fill in the password only when one has been set on the unit.

The address, port and password can be changed later with **Reconfigure**.

### Options

The number of channels and whether the routing matrix is exposed are **not**
asked during setup — they live in a separate options screen that is easy to
miss:

1. Go to **Settings > Devices & services**.
2. Find the **Allen & Heath iDR** card and click it (or its three-dot menu).
3. Choose **Configure**.

| Option | Default | Description |
| ------ | ------- | ----------- |
| Number of input channels | 8 | Input channels 1 up to this number get a gain and mute entity |
| Number of output channels | 8 | Output channels 1 up to this number get a gain and mute entity |
| Group gains | off | Gain entities for the 8 input groups, 8 output groups and 16 crosspoint groups |
| Crosspoint gain and mute | off | A gain and mute entity for every crosspoint (inputs x outputs) |
| Update interval | 10 s | How often the unit is read |

The iDR always has 16 input and 16 output channels in its matrix. Only channels
that you use need an entity. Submitting the form applies the change immediately
and reloads the integration.

#### How many entities does this create?

Every channel gets a gain **and** a mute entity, and so does every crosspoint,
so the numbers add up faster than they might look. A few examples (plus 1
preset and 2 diagnostic entities in every case):

| Setup | Entities |
| ----- | -------- |
| Default (8 in / 8 out, no groups, no crosspoints) | 35 |
| 8 in / 8 out, with crosspoints | 163 |
| 16 in / 16 out, with crosspoints | 579 |

Crosspoints are the big multiplier: inputs &times; outputs &times; 2. Leave
that option off until you are ready to use it, for example to build a
dashboard for the routing matrix — the per-channel gain and mute entities
already cover simple level and mute control on their own.

## Entities

| Entity | Description |
| ------ | ----------- |
| Preset (number) | The active preset. Setting a value **recalls that preset immediately** |
| Input / Output gain (number) | Gain in dB in steps of 0.5 |
| Input / Output mute (switch) | On means muted |
| Group gain (number, optional) | Master gain of an input, output or crosspoint group |
| Crosspoint gain (number, optional) | Level of an input on an output |
| Crosspoint mute (switch, optional) | Mute of an input on an output |
| Unit name (diagnostic) | Name of the unit as set on the iDR |
| Response time (diagnostic) | Time the iDR needed to answer a request, in milliseconds |
| Integration version (diagnostic) | Installed version of this integration, for bug reports |

### Gain values

The gain of a channel, group or crosspoint can be switched off completely
(-infinity). A number entity shows this as its lowest value: -60 dB for channels,
-41 dB for crosspoints and -65 dB for groups. The attribute `off` is `true` in
that case. Setting the lowest value, or anything below the lowest real gain,
switches the gain off.

After every change the integration reads the value back from the iDR. What you
see is what the unit reports, so a value that the unit rounds to its own step is
shown as rounded. When the unit does not apply a value, Home Assistant shows an
error.

### Why a gain and mute per crosspoint, not a single "source" dropdown?

A routing matrix that only ever sends one source to an output would be fully
described by a dropdown per output. The iDR matrix is a real
**mixer**: several inputs can feed the same output at the same time, each at
its own level, and the levels sum together. Collapsing that into one dropdown
per output would only work for exclusive routing and would hide the mixing use
that this hardware is built for (paging over background music, combining
microphones into one zone, and so on).

The raw entities stay the source of truth for that reason. A dashboard card
that lays the crosspoints out as a compact grid, instead of a long flat entity
list, is the planned way to make them practical to use day to day.

## Services

### `allen_heath_idr.set_crosspoint`

Set the gain and/or mute of one crosspoint by input and output number.
Target the iDR device; Home Assistant no longer supports targeting a service
by device directly, so under the hood this targets any entity of that
device, which is the same thing from the picker in the UI:

```yaml
action: allen_heath_idr.set_crosspoint
target:
  device_id: <the iDR device>
data:
  input: 2
  output: 5
  gain: -6.5   # a number in dB, or "off" for -infinity
  mute: false  # optional; give gain, mute, or both
```

This is meant for automations, scripts, and the future dashboard card: `input`
and `output` are always plain channel numbers, so callers do not need to know
how Home Assistant slugged the entity for that specific crosspoint. Setting
gain and mute together also happens as one action instead of two separate
calls. The service writes directly to the iDR and works even when the
crosspoint entities are not enabled for this device, so it can be used purely
by automations without adding any entities.

## Good to know

- The iDR accepts one command at a time and has a very small input buffer. The
  integration therefore keeps a single connection open and sends commands one
  after another. The unit allows up to 10 simultaneous Telnet connections.
- Changes made on the unit or in iDR System Manager are picked up when Home
  Assistant polls the unit (every 10 seconds by default). Changes made from
  Home Assistant show immediately.
- Recalling a preset changes levels and routing on the unit, and all values are
  read again afterwards.
- The Telnet protocol is not encrypted, and a password (if set) is sent as
  plain text. Keep the iDR on a trusted network or VLAN.
- The password handling follows the protocol description of Allen & Heath and has
  not yet been verified on a unit that has a password set.
- The device page does not show a firmware version, because the iDR does not
  expose its own firmware version over the Telnet protocol. The Integration
  version diagnostic entity shows the version of this integration instead,
  which is what matters for bug reports.
- If the iDR is unreachable when Home Assistant starts (or when the
  integration is added or reloaded), Home Assistant shows **"Failed setup,
  will retry"** for the entry and keeps retrying on its own schedule. That
  status text is standard Home Assistant behaviour for any device that is
  offline at startup and cannot be changed by this integration, but the
  message below it is: it names the host and port and does not show raw
  network error details. If the iDR only goes offline *after* a successful
  start, entities turn "unavailable" instead, without this message.

## Troubleshooting

Enable debug logging to see every command and reply:

```yaml
logger:
  logs:
    custom_components.allen_heath_idr: debug
```

- **Cannot connect**: check the IP address and that the iDR and Home Assistant
  can reach each other (VLANs and firewalls).
- **Did not answer like an iDR**: check that the firmware is V3.50 or later.

## Brand

The `Brand` folder is meant for logo files. Logos of Allen & Heath are not
included.

## License

[MIT](LICENSE)
