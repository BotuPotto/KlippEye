"""Test stand-in for dbus-fast: the e2e world has no D-Bus, Moonraker falls back to systemctl."""
class Variant:
    def __init__(self, sig, value): self.signature, self.value = sig, value
class _Errors:
    class DBusError(Exception): pass
errors = _Errors
