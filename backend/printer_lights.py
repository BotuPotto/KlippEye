"""The printer's lights as the dashboard sees them (1.100), for the services that switch them without a page open (the
Home Assistant / MQTT bridge). The same rules as frontend/src/app/13-capabilities.js (deriveParts) and
frontend/src/app/16a-printer-functions.js (detectLights, resolveLightItem, lightCommands, lightIsOn):

- the outputs that may drive a light: [output_pin], [led], [neopixel], [dotstar], [pca9533], [pca9632], each with the
  klipper-led_effect effects drawn on it;
- until the person changes the list in Settings › Printer functions, the lights are what KlippEye finds: every pair of
  light macros (LIGHT_ON / LIGHT_OFF, LUCI_ON / LUCI_OFF...) and every LED output (pins only when their name says light);
- each light is switched by its output (SET_PIN / SET_LED), by two macros or by G-code, and its state is read on an output.

Only Python's standard library: tests/backend/test_backend.py checks it against the same cases as the dashboard.
"""

import re

LIGHT_KINDS = ("output_pin", "led", "neopixel", "dotstar", "pca9533", "pca9632")
LIGHT_WORDS = re.compile(r"light|luci|luce|lamp|case|chamber|led", re.IGNORECASE)
ID_RE = re.compile(r"^[a-z0-9-]{1,40}$")
MACRO_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def slug(text):
    out = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:36]
    return out or "light"


def label(text):
    """"LUCI" -> "Luci", "case_light" -> "Case light", "KLIPPEYE_LIGHT" -> "Light"."""
    words = re.sub(r"[_-]+", " ", re.sub(r"^KLIPPEYE_", "", str(text), flags=re.IGNORECASE)).strip().lower()
    return words[:1].upper() + words[1:] if words else "Light"


def outputs_from(objects, configfile):
    """The outputs that may drive a light: [{object, kind, name, effects}]. `objects`: /printer/objects/list;
    `configfile`: Klipper's configfile object ({settings, config})."""
    raw = (configfile or {}).get("config") or {}
    lower = {key.lower(): value for key, value in raw.items()}
    out = []
    for obj in objects or []:
        kind, _, name = str(obj).partition(" ")
        if kind not in LIGHT_KINDS or not name:
            continue
        target = (kind + ":" + name).lower()
        effects = []
        for other in objects:
            if not str(other).startswith("led_effect "):
                continue
            leds = str((lower.get(str(other).lower()) or {}).get("leds") or "").lower()
            if any(re.sub(r"\(.*$", "", led) == target for led in re.split(r"[\s,]+", leds) if led):
                effects.append(other)
        out.append({"object": obj, "kind": kind, "name": name, "effects": effects})
    return out


def macros_from(configfile):
    settings = (configfile or {}).get("settings") or {}
    names = [key[12:].upper() for key in settings if key.startswith("gcode_macro ")]
    return sorted(name for name in names if not name.startswith("_"))


def find_light_object(outputs):
    for out in outputs:
        if LIGHT_WORDS.search(out["name"]) and out["kind"] != "output_pin":
            return out
    for out in outputs:
        if LIGHT_WORDS.search(out["name"]):
            return out
    return outputs[0] if len(outputs) == 1 else None


def light_macro_pairs(macros):
    have = set(macros)
    pairs = []
    for name in ["KLIPPEYE_LIGHT_ON"] + list(macros):
        match = re.match(r"^(.*?)(_?)ON$", name)
        if not match or not LIGHT_WORDS.search(match.group(1)) or name not in have or any(p["on"] == name for p in pairs):
            continue
        off = match.group(1) + match.group(2) + "OFF"
        if off in have:
            pairs.append({"on": name, "off": off, "stem": match.group(1)})
    return pairs


def output_named(outputs, stem):
    key = slug(stem)
    for out in outputs:
        if slug(out["name"]) == key:
            return out
    for out in outputs:
        name = slug(out["name"])
        if key and (key in name or name in key):
            return out
    return None


def by_object(outputs, name):
    return next((out for out in outputs if out["object"] == name), None)


def detect(outputs, macros):
    """The lights KlippEye finds by itself, as settings items."""
    pairs = light_macro_pairs(macros)
    used = set()
    items = []
    for pair in pairs:
        reads = output_named(outputs, pair["stem"])
        if not reads and len(pairs) == 1:
            reads = find_light_object([out for out in outputs if out["object"] not in used])
        if reads:
            used.add(reads["object"])
        items.append({"id": "m-" + slug(pair["on"]), "name": label(pair["stem"]), "mode": "macro", "onMacro": pair["on"], "offMacro": pair["off"],
                      "stateFrom": reads["object"] if reads else "", "main": True})
    for out in outputs:
        if out["object"] in used or (out["kind"] == "output_pin" and not LIGHT_WORDS.search(out["name"])):
            continue
        items.append({"id": "o-" + slug(out["object"]), "name": label(out["name"]), "mode": "object", "object": out["object"], "main": True})
    return items


def switch_commands(output, commands):
    if output["kind"] == "output_pin":
        return "SET_PIN PIN=%s VALUE=1" % output["name"], "SET_PIN PIN=%s VALUE=0" % output["name"]

    def led(value):
        return "SET_LED LED=%s RED=%s GREEN=%s BLUE=%s WHITE=%s" % (output["name"], value, value, value, value)
    stop = 'STOP_LED_EFFECTS LEDS="%s:%s"\n' % (output["kind"], output["name"]) if output["effects"] and "STOP_LED_EFFECTS" in (commands or {}) else ""
    return led(1), stop + led(0)


def _text(value, limit=4000):
    return value.strip()[:limit] if isinstance(value, str) else ""


def resolve(lights_setting, outputs, macros, commands):
    """The lights in use: [{id, name, on, off, object (the output read for the state, or None)}], those that can be
    switched. `lights_setting`: settings.functions.lights of the dashboard ({configured, items})."""
    setting = lights_setting if isinstance(lights_setting, dict) else {}
    items = setting.get("items") if setting.get("configured") and isinstance(setting.get("items"), list) else detect(outputs, macros)
    out, seen = [], set()
    for index, item in enumerate(items[:12]):
        if not isinstance(item, dict):
            continue
        ident = item.get("id") if isinstance(item.get("id"), str) and ID_RE.match(item["id"]) else "l%d" % index
        if ident in seen:
            continue
        seen.add(ident)
        mode = item.get("mode") if item.get("mode") in ("object", "macro", "gcode") else "object"
        obj, on, off = None, "", ""
        if mode == "object":
            obj = by_object(outputs, item.get("object"))
            if obj:
                on, off = switch_commands(obj, commands)
        else:
            if mode == "macro":
                on = item.get("onMacro") if isinstance(item.get("onMacro"), str) and MACRO_RE.match(item["onMacro"]) else ""
                off = item.get("offMacro") if isinstance(item.get("offMacro"), str) and MACRO_RE.match(item["offMacro"]) else ""
            else:
                on, off = _text(item.get("onGcode")), _text(item.get("offGcode"))
            state_from = item.get("stateFrom", "auto")
            if state_from == "auto":
                obj = (mode == "macro" and output_named(outputs, re.sub(r"_?ON$", "", on))) or find_light_object(outputs)
            elif state_from:
                obj = by_object(outputs, state_from)
        if not on or not off:
            continue
        name = _text(item.get("name"), 30) or (label(obj["name"]) if obj else "Light")
        out.append({"id": ident, "name": name, "on": on, "off": off, "object": obj})
    return out


def query_objects(lights):
    names = set()
    for light in lights:
        if light["object"]:
            names.add(light["object"]["object"])
            names.update(light["object"]["effects"])
    return sorted(names)


def is_on(status, light):
    """True / False from the output (a pin above 0, a LED with some colour, an effect running on it); None: unknown."""
    obj = light.get("object")
    own = obj and (status or {}).get(obj["object"])
    if not obj or not isinstance(own, dict):
        return None
    if any(isinstance(status.get(effect), dict) and status[effect].get("enabled") for effect in obj["effects"]):
        return True
    if obj["kind"] == "output_pin":
        try:
            return float(own.get("value") or 0) > 0
        except (TypeError, ValueError):
            return None
    colours = own.get("color_data") if isinstance(own.get("color_data"), list) else []
    for led in colours:
        if isinstance(led, list) and any(isinstance(c, (int, float)) and c > 0.001 for c in led):
            return True
    return False
