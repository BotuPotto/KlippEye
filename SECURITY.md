# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository. Describe what an attacker can do, the steps to reproduce it and the
KlippEye release (`klippeye versione`, or *Settings → Updates* in the dashboard). You will get an answer as soon as possible;
fixes are released as a new version and mentioned in `CHANGELOG.md`.

## Supported versions

Only the latest release receives security fixes. Update from Mainsail/Fluidd (*Update manager → klippeye*) or with `klippeye aggiorna`.

## How KlippEye is meant to be used

* KlippEye runs on your home network. **Never expose port 8085 to the internet.** For remote access use a VPN such as ZeroTier or Tailscale.
* Turn on the optional password (*Settings → Access*, or `klippeye password`) when other people or devices share your network.
* The AI monitor sends pictures of the print to the AI provider you configure (Groq or OpenAI) only when it suspects a failure.
