"""Review 1.116: backend/macro_catalog.py (what /api/macros/list answers): the parameters of a macro and their defaults,
the three sources (Klipper's configuration, its object list, the files) and which one wins. No network: a fake http."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "backend"))
import macro_catalog as mc  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:400]) if (extra != "" and not cond) else ""), flush=True)


class Answer:
    def __init__(self, body, ok=True):
        self.ok, self._body = ok, body

    def json(self):
        return self._body


class Http:
    def __init__(self, config=None, objects=None, files=None, down=False):
        self.config, self.objects, self.files, self.down = config or {}, objects or [], files or [], down

    def get(self, url, timeout=None):
        if self.down:
            raise OSError("connection refused")
        if "objects/query?configfile" in url:
            return Answer({"result": {"status": {"configfile": {"config": self.config}}}})
        if url.endswith("/printer/objects/list"):
            return Answer({"result": {"objects": self.objects}})
        if "files/list?root=config" in url:
            return Answer({"result": [{"path": path} for path in self.files]})
        raise AssertionError(url)


params = mc.params_of("{% set s = params.SPEED|default(50)|int %}\nG1 X{params.X} F{params.speed} ; {params.T|default(\"a b\")} {params.F|float|default(1.5)}")
check("the parameters in order, once each, upper case", [p["name"] for p in params] == ["SPEED", "X", "T", "F"], params)
check("... their defaults and types", [(p["default"], p["type"]) for p in params] == [("50", "int"), ("", "text"), ("a b", "text"), ("1.5", "float")], params)
check("... a default belongs to its own parameter, not to one before it on the same line", params[1]["default"] == "")
check("no parameters: none", mc.params_of("G28\nG1 Z10") == [])

root = tempfile.mkdtemp()
config = os.path.join(root, "config")
os.makedirs(os.path.join(config, "macros"))
os.makedirs(os.path.join(config, ".git"))
with open(os.path.join(config, "printer.cfg"), "w") as handle:
    handle.write("[include macros/*.cfg]\n[gcode_macro PARK]\ndescription: Park the head\ngcode:\n  G1 X{params.X|default(10)} Y{params.Y}\n\n[printer]\nkinematics: corexy\n")
with open(os.path.join(config, "macros", "extra.cfg"), "w") as handle:
    handle.write("[gcode_macro _HELPER]\ngcode:\n  M400\n[gcode_macro NOT_LOADED]\ngcode:\n  M117 {params.MSG}\n[gcode_macro PARK]\ngcode:\n  G28\n")
with open(os.path.join(config, ".git", "old.cfg"), "w") as handle:
    handle.write("[gcode_macro FROM_GIT]\ngcode:\n  G28\n")
with open(os.path.join(config, "printer-20240101_120000.cfg"), "w") as handle:
    handle.write("[gcode_macro FROM_BACKUP]\ngcode:\n  G28\n")

found = mc.macros_in_text(open(os.path.join(config, "printer.cfg")).read(), os.path.join(config, "printer.cfg"))
check("a file's macro: its name, file, description, parameters; the section after it is not read into it",
      len(found) == 1 and found[0]["name"] == "PARK" and found[0]["file"] == "printer.cfg" and found[0]["description"] == "Park the head"
      and [p["name"] for p in found[0]["params"]] == ["X", "Y"] and found[0]["has_params"] is True, found)

http = Http(config={"gcode_macro PARK": {"gcode": "G1 X{params.X|default(5)}", "description": "From Klipper"}, "gcode_macro _HIDDEN": {"gcode": ""}, "printer": {}},
            objects=["gcode_macro PARK", "gcode_macro FROM_EXTENSION", "gcode_macro _HIDDEN", "toolhead"],
            files=["printer.cfg", "macros/extra.cfg", "printer-20240101_120000.cfg", "missing.cfg", "notes.txt"])
macros = mc.catalog("http://moonraker", http, config, [os.path.join(config, "shaketune")])
by_name = {macro["name"]: macro for macro in macros}
check("the three sources together, sorted by name; helpers (_) and dated copies left out", [m["name"] for m in macros] == ["FROM_EXTENSION", "NOT_LOADED", "PARK"], [m["name"] for m in macros])
check("... Klipper's own configuration wins over the files", by_name["PARK"]["source"] == "configfile" and by_name["PARK"]["description"] == "From Klipper" and by_name["PARK"]["params"][0]["default"] == "5", by_name["PARK"])
check("... a macro registered by an extension: from the object list", by_name["FROM_EXTENSION"]["source"] == "objects/list" and by_name["FROM_EXTENSION"]["params"] == [])
check("... a macro of a file Klipper has not loaded: from the file", by_name["NOT_LOADED"]["source"] == "filesystem" and by_name["NOT_LOADED"]["file"] == "extra.cfg")
check("... no G-code in the answer (the dashboard does not use it)", all("gcode" not in macro for macro in macros))

few = mc.catalog("http://moonraker", Http(), config, [])
check("Moonraker lists no files: the configuration folder is walked (not .git, not the dated copies)", [m["name"] for m in few] == ["NOT_LOADED", "PARK"], [m["name"] for m in few])
down = mc.catalog("http://moonraker", Http(down=True), config, [])
check("Moonraker down: the files are still read", "PARK" in [m["name"] for m in down])

shaketune = os.path.join(root, "klippain_shaketune")
os.makedirs(shaketune)
with open(os.path.join(shaketune, "commands.py"), "w") as handle:
    handle.write("def axes_shaper_calibration(gcmd):\n    pass\n")
with_st = {m["name"]: m for m in mc.catalog("http://moonraker", http, config, [shaketune, os.path.join(root, "nowhere")])}
check("Shake&Tune's folder is there: its commands are listed by name", all(name in with_st for name in mc.SHAKETUNE_COMMANDS) and with_st["BELT_TUNING"]["source"] == "shaketune_scan")
check("... without it they are not", "BELT_TUNING" not in by_name)

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
