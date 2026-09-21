# Security Policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private vulnerability reporting instead: open the **Security** tab
of this repository and choose **Report a vulnerability**. Include the version of
the integration, the iDR firmware version and steps to reproduce the problem.

You can expect a first response within a few days.

## Good to know

The iDR Telnet control protocol is not encrypted. The password, if you set one
on the unit, is sent as plain text. Keep the iDR on a trusted network or VLAN
and do not expose its Telnet port to the internet.
