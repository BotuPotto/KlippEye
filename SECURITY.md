# Security policy

## Reporting a problem

Please don't open a public issue for a security problem. Use GitHub's private reporting instead: **Security → Report a
vulnerability** on this repository. Describe what an attacker could do, the steps to reproduce it and the KlippEye release
(`klippeye version` on the Raspberry, or *Settings → Updates* in the dashboard). You will get an answer as soon as possible;
the fix comes in a new release and is mentioned in [CHANGELOG.md](CHANGELOG.md).

## Supported versions

Only the latest release receives security fixes. Update from the dashboard (*Settings → Updates → Update KlippEye*) or with
`klippeye update` on the Raspberry.

## How KlippEye is meant to be used

- KlippEye runs on your home network. Never open its ports (80, 443 and 8085) to the internet on your router. To reach the
  printer from outside, use a VPN such as ZeroTier, Tailscale or WireGuard ([guide, chapter 8](docs/GUIDE.md#8-using-it-away-from-home)).
- Turn on the optional password (*Settings → Access*, or `klippeye password`) when other people or devices share your network.
  The password protects KlippEye only: Moonraker (port 7125) has its own `[authorization]` settings.
- With the online AI on, the AI monitor sends the pictures of an alarm to the service you configured, and only those. With
  *Local model only*, no picture leaves the Raspberry.
- Keys and passwords are kept in `~/printer_data/klippeye`, readable only by the user that runs the service. The password is
  stored only as a hash.
