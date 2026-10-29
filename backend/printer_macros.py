"""
The macros KlippEye writes into the printer's configuration (roadmap phase 5b, "Printer functions"), in ONE file of its own,
klippeye_macros.cfg, next to printer.cfg, included at the end of printer.cfg. Nothing else of the configuration is changed.

Two things go in it:
  * the macros the person CREATED from the dashboard (a template proposed by KlippEye, e.g. KLIPPEYE_PARK, edited in the
    dashboard's editor before saving): their text is kept as written;
  * the ANNOUNCERS of the filament change: for each macro chosen (M600, a runout macro...) a wrapper with the same name that
    first writes "KlippEye: filament change" in the console (the notification service sees it) and then runs the original,
    which Klipper keeps under another name (rename_existing). The macro itself is not touched.

The state is kept in the data folder (printer_macros.json) and the file is written again from it each time: the file says on
top that it is KlippEye's and is changed from the dashboard (Settings -> Printer functions).
Klipper reads the file at its next restart (FIRMWARE_RESTART), which the dashboard proposes (never during a print).
"""
import json
import os
import re
import shutil
import time

FILE_NAME = "klippeye_macros.cfg"
INCLUDE_LINE = "[include %s]" % FILE_NAME
TAG = "KlippEye: filament change"
ORIGINAL_PREFIX = "KLIPPEYE_ORIGINAL_"
SAVE_CONFIG_MARK = "#*# <---------------------- SAVE_CONFIG ---------------------->"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
SECTION = re.compile(r"^\s*\[\s*gcode_macro\s+([^\]\s]+)\s*\]\s*$", re.MULTILINE)
ANY_SECTION = re.compile(r"^\s*\[([^\]]+)\]", re.MULTILINE)
MAX_TEXT = 20000
MAX_MACROS = 20
MAX_WRAPS = 10


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


class MacroError(ValueError):
    def __init__(self, text, **values):
        ValueError.__init__(self, text)
        self.values = values


def clean_macro(text):
    """A macro written in the dashboard: one or more [gcode_macro NAME] sections (and comments) and nothing else.
    -> (names, text). Raises MacroError with a message for people."""
    if not isinstance(text, str) or not text.strip():
        raise MacroError("the macro is empty")
    if len(text) > MAX_TEXT:
        raise MacroError("the macro is too long")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"
    sections = ANY_SECTION.findall(text)
    names = SECTION.findall(text)
    before = text.split("[", 1)[0]
    if not names or len(sections) != len(names) or any(line.strip() and not line.strip().startswith("#") for line in before.splitlines()):
        raise MacroError("only [gcode_macro NAME] sections can be saved here")
    for name in names:
        if not NAME.match(name):
            raise MacroError("{name} is not a valid macro name", name=name)
    return [n.upper() for n in names], text


class PrinterMacros:
    def __init__(self, data_dir, config_dir, commands=None):
        """config_dir() -> the folder of printer.cfg (asked each time: it comes from Moonraker); commands() -> the G-code
        commands Klipper knows now (upper case), raising when Klipper does not answer."""
        self.commands = commands
        self.path = os.path.join(data_dir, "printer_macros.json")
        self.backup_dir = os.path.join(data_dir, "backups")
        self.config_dir = config_dir
        state = _read_json(self.path)
        self.macros = {k.upper(): v for k, v in (state.get("macros") or {}).items() if isinstance(v, str) and NAME.match(k)}
        self.wraps = [w.upper() for w in (state.get("wraps") or []) if isinstance(w, str) and NAME.match(w)]

    # ---------------------------------------------------------------- what is stored
    def summary(self):
        folder = self.config_dir()
        cfg = os.path.join(folder, FILE_NAME)
        return {"macros": dict(self.macros), "wraps": list(self.wraps), "file": cfg, "file_exists": os.path.isfile(cfg),
                "included": self.included(), "tag": TAG}

    def _save_state(self):
        _write(self.path, json.dumps({"macros": self.macros, "wraps": self.wraps}, indent=1, ensure_ascii=False))

    # ---------------------------------------------------------------- changes
    def set_macro(self, key, text):
        """Creates or replaces the macro saved under `key` (its name); text None removes it."""
        key = str(key or "").upper()
        if not NAME.match(key):
            raise MacroError("{name} is not a valid macro name", name=key)
        if text is None:
            self.macros.pop(key, None)
        else:
            names, text = clean_macro(text)
            known = self._known()
            taken = [n for n in names if n in known and n not in self.macros]
            if taken:
                raise MacroError("{name} already exists in your configuration: choose another name", name=taken[0])
            if key not in names:
                raise MacroError("the macro must be called {name}", name=key)
            clash = [n for n in names if n in self.wraps]
            if clash:
                raise MacroError("{name} is announced as a filament change: it cannot also be created here", name=clash[0])
            if key not in self.macros and len(self.macros) >= MAX_MACROS:
                raise MacroError("too many macros")
            self.macros[key] = text
        return self.write()

    def set_wraps(self, names):
        """The macros announced as a filament change (they must exist in Klipper and not be KlippEye's own)."""
        clean = []
        for name in names or []:
            name = str(name or "").upper()
            if not NAME.match(name) or name.startswith(ORIGINAL_PREFIX):
                raise MacroError("{name} is not a valid macro name", name=name)
            if name in self.macros:
                raise MacroError("{name} is announced as a filament change: it cannot also be created here", name=name)
            if name not in clean:
                clean.append(name)
        known = self._known()
        missing = [n for n in clean if n not in known]
        if missing:
            raise MacroError("{name} is not a command of your printer: Klipper would not start with it", name=missing[0])
        if len(clean) > MAX_WRAPS:
            raise MacroError("too many macros")
        self.wraps = clean
        return self.write()

    def _known(self):
        """The commands Klipper knows (a wrong announcer would stop Klipper from starting: it must be checked)."""
        if self.commands is None:
            return set()
        try:
            return {str(c).upper() for c in self.commands()}
        except Exception:
            raise MacroError("Klipper does not answer: it must be running to check the macros")

    # ---------------------------------------------------------------- the file
    def render(self):
        lines = ["# KlippEye: macros made from the dashboard (Settings -> Printer functions).",
                 "# This file is written again by KlippEye: change it from the dashboard, not here.", ""]
        for name in sorted(self.macros):
            lines += [self.macros[name].rstrip("\n"), ""]
        for name in self.wraps:
            lines += ["[gcode_macro %s]" % name,
                      "rename_existing: %s%s" % (ORIGINAL_PREFIX, name),
                      "description: %s announced to KlippEye as a filament change (the original runs right after)" % name,
                      "gcode:",
                      '  RESPOND MSG="%s (%s)"' % (TAG, name),
                      "  %s%s {rawparams}" % (ORIGINAL_PREFIX, name), ""]
        return "\n".join(lines)

    def write(self):
        """Writes klippeye_macros.cfg and makes sure printer.cfg includes it (at the end). -> summary + what changed."""
        folder = self.config_dir()
        if not os.path.isdir(folder):
            raise MacroError("the configuration folder was not found: {folder}", folder=folder)
        self._save_state()
        _write(os.path.join(folder, FILE_NAME), self.render())
        added = self.ensure_included()
        return dict(self.summary(), include_added=added, restart_needed=True)

    def included(self):
        printer_cfg = os.path.join(self.config_dir(), "printer.cfg")
        try:
            with open(printer_cfg, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return False
        return re.search(r"^\s*\[include\s+%s\s*\]" % re.escape(FILE_NAME), text, re.MULTILINE) is not None

    def ensure_included(self):
        """Adds [include klippeye_macros.cfg] at the end of printer.cfg (before the SAVE_CONFIG block), with a backup.
        At the end, so that the macros it announces are already defined when Klipper reads it. -> True when it was added."""
        printer_cfg = os.path.join(self.config_dir(), "printer.cfg")
        if self.included():
            return False
        try:
            with open(printer_cfg, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            raise MacroError("printer.cfg was not found in {folder}", folder=self.config_dir())
        os.makedirs(self.backup_dir, exist_ok=True)
        shutil.copy2(printer_cfg, os.path.join(self.backup_dir, "printer.cfg.%s" % time.strftime("%Y%m%d-%H%M%S")))
        block = "\n# KlippEye (Settings -> Printer functions)\n%s\n" % INCLUDE_LINE
        at = text.find(SAVE_CONFIG_MARK)
        if at >= 0:
            text = text[:at].rstrip("\n") + "\n" + block + "\n" + text[at:]
        else:
            text = text.rstrip("\n") + "\n" + block
        _write(printer_cfg, text)
        return True


# ---------------------------------------------------------------- templates
TEMPLATES = {
    "park": ("KLIPPEYE_PARK", """[gcode_macro KLIPPEYE_PARK]
description: Park the toolhead at the back, a little higher (made by KlippEye: change it as you like)
# where it goes: mm from the back right corner of the travel, and how much it goes up
variable_from_right: 10
variable_from_back: 10
variable_lift: 10
gcode:
  {% if "xyz" not in printer.toolhead.homed_axes %}
    G28
  {% endif %}
  {% set me = printer["gcode_macro KLIPPEYE_PARK"] %}
  {% set x = printer.toolhead.axis_maximum.x - me.from_right %}
  {% set y = printer.toolhead.axis_maximum.y - me.from_back %}
  {% set z = [printer.toolhead.position.z + me.lift, printer.toolhead.axis_maximum.z]|min %}
  SAVE_GCODE_STATE NAME=klippeye_park
  G90
  G1 Z{z} F900
  G1 X{x} Y{y} F6000
  RESTORE_GCODE_STATE NAME=klippeye_park
"""),
    "wipe": ("KLIPPEYE_WIPE", """[gcode_macro KLIPPEYE_WIPE]
description: Wipe the nozzle on a brush (made by KlippEye: SET THE POSITION OF YOUR BRUSH first)
# the brush: its centre (X, Y), its length along X and the height of the nozzle when it rubs on it
variable_brush_x: 50
variable_brush_y: 300
variable_brush_length: 30
variable_brush_z: 2
variable_strokes: 6
gcode:
  {% if "xyz" not in printer.toolhead.homed_axes %}
    G28
  {% endif %}
  {% set me = printer["gcode_macro KLIPPEYE_WIPE"] %}
  SAVE_GCODE_STATE NAME=klippeye_wipe
  G90
  G1 Z{me.brush_z + 10} F900
  G1 X{me.brush_x - me.brush_length / 2} Y{me.brush_y} F6000
  G1 Z{me.brush_z} F900
  {% for i in range(me.strokes) %}
    G1 X{me.brush_x + me.brush_length / 2} F8000
    G1 X{me.brush_x - me.brush_length / 2} F8000
  {% endfor %}
  G1 Z{me.brush_z + 10} F900
  RESTORE_GCODE_STATE NAME=klippeye_wipe
"""),
    "load": ("KLIPPEYE_LOAD_FILAMENT", """[gcode_macro KLIPPEYE_LOAD_FILAMENT]
description: Load the filament: heats if needed, then pushes it to the nozzle (made by KlippEye: change it as you like)
# TEMP=... chooses the temperature (default below); the lengths in mm: fast to the hotend, then slowly through the nozzle
variable_temperature: 220
variable_fast_length: 50
variable_slow_length: 30
gcode:
  {% set me = printer["gcode_macro KLIPPEYE_LOAD_FILAMENT"] %}
  {% set t = params.TEMP|default(me.temperature)|float %}
  {% if printer.extruder.temperature < t - 5 %}
    M109 S{t}
  {% endif %}
  SAVE_GCODE_STATE NAME=klippeye_load
  M83
  G1 E{me.fast_length} F1200
  G1 E{me.slow_length} F300
  RESTORE_GCODE_STATE NAME=klippeye_load
"""),
    "unload": ("KLIPPEYE_UNLOAD_FILAMENT", """[gcode_macro KLIPPEYE_UNLOAD_FILAMENT]
description: Unload the filament: heats if needed, pushes a little, then pulls it out (made by KlippEye: change it as you like)
# TEMP=... chooses the temperature (default below); the length in mm that brings the filament out of the extruder
variable_temperature: 220
variable_length: 80
gcode:
  {% set me = printer["gcode_macro KLIPPEYE_UNLOAD_FILAMENT"] %}
  {% set t = params.TEMP|default(me.temperature)|float %}
  {% if printer.extruder.temperature < t - 5 %}
    M109 S{t}
  {% endif %}
  SAVE_GCODE_STATE NAME=klippeye_unload
  M83
  G1 E5 F300
  G1 E-15 F3000
  G1 E-{me.length} F1800
  RESTORE_GCODE_STATE NAME=klippeye_unload
"""),
    "light_on": ("KLIPPEYE_LIGHT_ON", """[gcode_macro KLIPPEYE_LIGHT_ON]
description: Switch the light on (made by KlippEye: write here what switches YOUR light on)
gcode:
  # for example, a light on [output_pin caselight]:  SET_PIN PIN=caselight VALUE=1
  # a LED strip [neopixel lights]:                    SET_LED LED=lights RED=1 GREEN=1 BLUE=1
  RESPOND MSG="KLIPPEYE_LIGHT_ON: write the command of your light in this macro"
"""),
    "light_off": ("KLIPPEYE_LIGHT_OFF", """[gcode_macro KLIPPEYE_LIGHT_OFF]
description: Switch the light off (made by KlippEye: write here what switches YOUR light off)
gcode:
  # for example, a light on [output_pin caselight]:  SET_PIN PIN=caselight VALUE=0
  # a LED strip [neopixel lights]:                    SET_LED LED=lights RED=0 GREEN=0 BLUE=0
  RESPOND MSG="KLIPPEYE_LIGHT_OFF: write the command of your light in this macro"
"""),
}


def template(kind):
    """(name, text) of the macro KlippEye proposes for a function."""
    if kind not in TEMPLATES:
        raise MacroError("unknown function")
    return TEMPLATES[kind]
