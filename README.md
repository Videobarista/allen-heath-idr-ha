# Allen & Heath iDR for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration for the
Allen & Heath **iDR** audio mix processors (iDR-4 and iDR-8). It talks to the
unit over the network with the Telnet control protocol, fully local and without
any cloud.

> This project is not affiliated with or endorsed by Allen & Heath.

## Status

Early development. Version 0.1.0 provides the connection and a few diagnostic
sensors. Control of the audio matrix follows in the next versions.

| Version | Content |
| ------- | ------- |
| 0.1.0 | Connection, config flow, preset, unit name and response time sensors |
| planned | Input and output channel mute and gain |
| planned | Group gains, preset recall, crosspoint gain and mute |

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

## Entities

| Entity | Description |
| ------ | ----------- |
| Preset | Number of the preset that is currently active |
| Unit name (diagnostic) | Name of the unit as set on the iDR |
| Response time (diagnostic) | Time the iDR needed to answer a request, in milliseconds |

## Good to know

- The iDR accepts one command at a time and has a very small input buffer. The
  integration therefore keeps a single connection open and sends commands one
  after another. The unit allows up to 10 simultaneous Telnet connections.
- Changes made on the unit or in iDR System Manager are picked up when Home
  Assistant polls the unit, every 10 seconds.
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
