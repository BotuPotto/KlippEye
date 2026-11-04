"""Release 1.61: backend/printers_peek.py (more printers): which addresses the KlippEye service may ask about another
printer, the address it asks, and what it tells another dashboard about this printer. No network."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "backend"))
import printers_peek as pp  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:300]) if (extra != "" and not cond) else ""), flush=True)


check("a plain address is kept", pp.clean_host("192.168.1.50") == "192.168.1.50")
check("http:// and the path are dropped, the port kept", pp.clean_host(" http://voron.local:8086/x ") == "voron.local:8086")
check("not an address: refused", pp.clean_host("a b") is None and pp.clean_host("x:99999") is None and pp.clean_host("") is None and pp.clean_host(None) is None)
check("the port 8085 is added when none is given", pp.base_url("192.168.1.50") == "http://192.168.1.50:8085" and pp.base_url("h:9000") == "http://h:9000")

for address in ("192.168.1.5", "10.0.0.2", "172.20.1.1", "127.0.0.1", "169.254.3.3", "100.64.1.1", "100.127.255.1", "fd00::1"):
    check("home network: %s" % address, pp.home_address(address))
for address in ("8.8.8.8", "1.1.1.1", "100.128.0.1", "2001:4860::8888", "nonsense"):
    check("not the home network: %s" % address, not pp.home_address(address))


def resolver(*addresses):
    return lambda name, port: [(2, 1, 6, "", (a, 0)) for a in addresses]


def broken(name, port):
    raise OSError("no such name")


check("a name of the home network is reached", pp.reachable("voron.local:8085", resolver("192.168.1.9")))
check("a name pointing outside is refused", not pp.reachable("evil.example", resolver("93.184.216.34")))
check("a name with one address outside is refused", not pp.reachable("both", resolver("192.168.1.9", "93.184.216.34")))
check("a name that does not resolve is refused", not pp.reachable("nowhere.local", broken))

s = pp.summary({"print_stats": {"state": "printing", "filename": "Benchy.gcode", "print_duration": 120.5}, "display_status": {"progress": 0.42},
                "extruder": {"temperature": 215.27, "target": 220}, "heater_bed": {"temperature": 60.04, "target": 60}},
               {"printer": {"name": "Voron", "brand": "voron"}}, "1.61.0")
check("summary: name, logo, state, file, progress, temperatures", s == {"ok": True, "name": "Voron", "brand": "voron", "release": "1.61.0", "state": "printing", "filename": "Benchy.gcode",
                                                                       "progress": 0.42, "duration": 120.5, "extruder": [215.3, 220.0], "bed": [60.0, 60.0]}, s)
s = pp.summary({"virtual_sdcard": {"progress": 1.7}}, None, "1.61.0")
check("summary with little known: standby, the logo of KlippEye, progress from the SD card, at most 1, no temperatures", s["state"] == "standby" and s["brand"] == "klippeye" and s["progress"] == 1.0 and s["extruder"] is None and s["name"] == "", s)

print("\n%d failure(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)
