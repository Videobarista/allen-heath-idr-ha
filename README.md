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

Early development, but usable: the integration reads and controls the audio
matrix of the iDR.

| Version | Content |
| ------- | ------- |
| 0.1.0 | Connection, config flow, diagnostic sensors |
| 0.2.0 | Input and output gain and mute, preset recall, optional group gains and crosspoints, options |

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

Open the integration and choose **Configure** to decide what is created:

| Option | Default | Description |
| ------ | ------- | ----------- |
| Number of input channels | 8 | Input channels 1 up to this number get a gain and mute entity |
| Number of output channels | 8 | Output channels 1 up to this number get a gain and mute entity |
| Group gains | off | Gain entities for the 8 input groups, 8 output groups and 16 crosspoint groups |
| Crosspoint gain and mute | off | A gain and mute entity for every crosspoint (inputs x outputs) |
| Update interval | 10 s | How often the unit is read |

The iDR always has 16 input and 16 output channels in its matrix. Only channels
that you use need an entity. Crosspoints multiply quickly: 8 x 8 gives 128
entities, 16 x 16 gives 512.

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
