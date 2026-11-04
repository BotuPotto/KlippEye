"""More printers (1.61): which addresses a KlippEye may look at for another printer's state.

Each printer has its own KlippEye. The dashboard of one shows the others (the switcher in the top bar, the overview)
by asking its own KlippEye service, which asks the other one (/api/printers/self): no browser rule stands in the way
(a page may not read another address), and only addresses of the home network are reached, never the internet.
"""
import ipaddress
import re
import socket

KLIPPEYE_PORT = 8085
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$")
_SHARED = ipaddress.ip_network("100.64.0.0/10")  # ZeroTier / Tailscale ranges (carrier-grade NAT)


def clean_host(value):
    """'192.168.1.50' or 'voron.local:8085' (no scheme, no path), or None."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"^https?://", "", value.strip(), flags=re.I).split("/")[0]
    if not _HOST.match(text):
        return None
    port = re.search(r":(\d+)$", text)
    if port and not 0 < int(port.group(1)) <= 65535:
        return None
    return text


def home_address(address):
    """True for an address of the home network (private, the Raspberry itself, link-local, ZeroTier / Tailscale)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or (ip.version == 4 and ip in _SHARED)


def reachable(host, resolve=socket.getaddrinfo):
    """True when every address the host name gives is of the home network (a name pointing outside is refused)."""
    name = re.sub(r":\d+$", "", host)
    try:
        addresses = {info[4][0] for info in resolve(name, None)}
    except (OSError, UnicodeError):
        return False
    return bool(addresses) and all(home_address(a) for a in addresses)


def base_url(host):
    """http://host:8085 (the port KlippEye always uses, unless the host gives its own)."""
    return "http://" + host + ("" if re.search(r":\d+$", host) else ":%d" % KLIPPEYE_PORT)


def summary(status, settings, release):
    """What another dashboard shows of this printer: name, logo, state, progress, file, temperatures."""
    stats = status.get("print_stats") or {}
    shown = status.get("display_status") or {}
    sd = status.get("virtual_sdcard") or {}
    printer = (settings or {}).get("printer") or {}

    def temps(name):
        heater = status.get(name) or {}
        if "temperature" not in heater:
            return None
        return [round(float(heater.get("temperature") or 0), 1), round(float(heater.get("target") or 0), 1)]

    progress = shown.get("progress")
    if progress is None:
        progress = sd.get("progress")
    return {
        "ok": True,
        "name": str(printer.get("name") or ""),
        "brand": str(printer.get("brand") or "klippeye"),
        "release": release,
        "state": str(stats.get("state") or "standby"),
        "filename": str(stats.get("filename") or ""),
        "progress": max(0.0, min(1.0, float(progress or 0))),
        "duration": float(stats.get("print_duration") or 0),
        "extruder": temps("extruder"),
        "bed": temps("heater_bed"),
    }
