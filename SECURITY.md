# Security Policy

## Supported Versions

Only the latest released version of this integration is supported with
security updates.

## Reporting a Vulnerability

If you discover a security vulnerability, please open a private report via
[GitHub Security Advisories](https://github.com/Videobarista/allen-heath-idr-ha/security/advisories/new)
rather than a public issue.

Note that this integration only talks to a device on your local network
over plain, unencrypted Telnet — the Allen & Heath iDR control protocol
itself provides no encryption and sends any configured password in plain
text. This integration does not expose any inbound network service itself.
