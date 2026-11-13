"""
The printer's macros with their parameters: what /api/macros/list answers (the dashboard's macro cards).

Three sources, the first that knows a macro wins:
  1. Klipper's own configuration (the `configfile` object): every [gcode_macro] it loaded, with its G-code;
  2. Klipper's object list: macros a Klipper extension registers by itself, without a section in the files;
  3. the files: the .cfg/.conf files of the configuration folder and of Klippain Shake&Tune's folders, read for
     [gcode_macro] sections (also those of files Klipper has not loaded yet), and Shake&Tune's commands, which are
     not macros in a file: when its folder is there they are listed by name.
Macros whose name starts with "_" are helpers of other macros: never listed.

Nothing here knows Flask: `http` is the requests module (or a stand-in with get()).
"""
import os
import re

CONFIG_EXTENSIONS = (".cfg", ".conf")
SHAKETUNE_EXTENSIONS = CONFIG_EXTENSIONS + (".py",)
SHAKETUNE_COMMANDS = ("AXES_SHAPER_CALIBRATION", "AXES_MAP_CALIBRATION", "COMPARE_BELTS_RESPONSES", "CREATE_VIBRATIONS_PROFILE",
                      "EXCITATE_AXIS_AT_FREQ", "MEASURE_AXES_NOISE", "BELT_TUNING")
MACRO_PREFIX = "gcode_macro "
READ_LIMIT = 200000          # characters read of one file
SECTION_LINES = 300          # lines of one macro looked at for its parameters
FEW_FILES = 10               # fewer listed by Moonraker than this: the configuration folder is walked too

_PARAM = re.compile(r"params\.([A-Za-z0-9_]+)", re.IGNORECASE)
# the default must follow its own parameter (other filters may stand between): on a line with two parameters the
# second one's default is not given to the first
_PARAM_DEFAULT = re.compile(r"params\.([A-Za-z0-9_]+)(?:\s*\|\s*[a-z_]+(?:\([^)\n]*\))?)*?\s*\|\s*default\s*\(\s*([^),\n]+)", re.IGNORECASE)
_SECTION = re.compile(r"^\[\s*gcode_macro\s+([^\]\s]+)\s*\]", re.IGNORECASE)
_DESCRIPTION = re.compile(r"description\s*:\s*(.+)", re.IGNORECASE)


def params_of(gcode):
    """The `params.NAME` a macro reads, in order: [{name, default, type}]; the type ("int", "float", "text") is the
    default's (`params.SPEED|default(50)|int` → {"name": "SPEED", "default": "50", "type": "int"})."""
    defaults = {match.group(1).upper(): match.group(2).strip().strip("\"'") for match in _PARAM_DEFAULT.finditer(gcode)}
    params = []
    for name in dict.fromkeys(match.group(1).upper() for match in _PARAM.finditer(gcode)):
        default = defaults.get(name, "")
        params.append({"name": name, "default": default, "type": _type_of(default)})
    return params


def _type_of(default):
    try:
        float(default)
    except ValueError:
        return "text"
    return "float" if "." in default else "int"


def _entry(name, source, file="", filepath="", description="", gcode=""):
    params = params_of(gcode)
    return {"name": name, "file": file, "filepath": filepath, "description": description, "params": params, "has_params": bool(params), "source": source}


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return handle.read(READ_LIMIT)
    except OSError:
        return ""


def macros_in_text(text, path, source="filesystem"):
    """The [gcode_macro NAME] sections of a configuration file's text."""
    lines = text.splitlines(keepends=True)
    found = []
    for index, line in enumerate(lines):
        match = _SECTION.match(line.strip())
        if not match or match.group(1).startswith("_"):
            continue
        body = "".join(lines[index + 1:index + 1 + SECTION_LINES])
        end = body.find("\n[")
        if end != -1:
            body = body[:end]
        description = _DESCRIPTION.search(body)
        found.append(_entry(match.group(1), source, os.path.basename(path), path, description.group(1).strip()[:300] if description else "", body))
    return found


def from_klipper(moonraker_url, http):
    """{name: macro} of what Klipper itself knows (sources 1 and 2). Moonraker not answering: what could be read."""
    macros = {}
    try:
        answer = http.get(moonraker_url + "/printer/objects/query?configfile", timeout=4)
        config = answer.json().get("result", {}).get("status", {}).get("configfile", {}).get("config", {}) if answer.ok else {}
        for key, section in config.items():
            name = key[len(MACRO_PREFIX):].strip()
            if key.lower().startswith(MACRO_PREFIX) and not name.startswith("_") and isinstance(section, dict):
                macros[name] = _entry(name, "configfile", "configfile", "", section.get("description", ""), section.get("gcode", ""))
    except Exception as error:  # noqa: BLE001 - the files are still read
        print("[MACROS] Klipper's configuration not read: %s" % error)
    try:
        answer = http.get(moonraker_url + "/printer/objects/list", timeout=3)
        for key in (answer.json().get("result", {}).get("objects", []) if answer.ok else []):
            name = key[len(MACRO_PREFIX):].strip()
            if key.lower().startswith(MACRO_PREFIX) and not name.startswith("_"):
                macros.setdefault(name, _entry(name, "objects/list", description="registered by a Klipper extension"))
    except Exception as error:  # noqa: BLE001
        print("[MACROS] Klipper's objects not read: %s" % error)
    return macros


def _dated_copy(name):
    """A dated copy some tools leave next to the original (printer-20240101_120000.cfg, crowsnest.conf.2024-01-01)."""
    name = name.lower()
    return (name.startswith("printer-") and name.endswith(".cfg")) or "crowsnest.conf." in name


def _listed_by_moonraker(moonraker_url, http):
    """The configuration files as Moonraker lists them (paths relative to the configuration folder)."""
    try:
        answer = http.get(moonraker_url + "/server/files/list?root=config", timeout=3)
        files = answer.json().get("result", []) if answer.ok else []
    except Exception:  # noqa: BLE001
        return []
    return [str(item.get("path", "")) for item in files if isinstance(item, dict)]


def _walk(folder, extensions):
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            if name.lower().endswith(extensions):
                yield os.path.join(root, name)


def from_files(moonraker_url, http, config_dir, shaketune_dirs):
    """[macro] of the configuration files (source 3), then Shake&Tune's commands."""
    paths = {os.path.join(config_dir, path) for path in _listed_by_moonraker(moonraker_url, http) if path.lower().endswith(CONFIG_EXTENSIONS)}
    for folder in shaketune_dirs:
        paths.update(_walk(folder, CONFIG_EXTENSIONS))
    if len(paths) < FEW_FILES:
        paths.update(_walk(config_dir, CONFIG_EXTENSIONS))
    paths = {path for path in paths if os.path.isfile(path) and not _dated_copy(os.path.basename(path))}
    found = []
    for path in sorted(paths):
        found.extend(macros_in_text(_read(path), path))
    shaketune = any("axes_shaper_calibration" in _read(path).lower() for folder in shaketune_dirs for path in _walk(folder, SHAKETUNE_EXTENSIONS))
    if shaketune:
        found.extend(_entry(name, "shaketune_scan", description="Shake&Tune") for name in SHAKETUNE_COMMANDS)
    return found


def catalog(moonraker_url, http, config_dir, shaketune_dirs):
    """Every macro, sorted by name: [{name, file, filepath, description, params, has_params, source}]."""
    macros = from_klipper(moonraker_url, http)
    for macro in from_files(moonraker_url, http, config_dir, shaketune_dirs):
        macros.setdefault(macro["name"], macro)
    return sorted(macros.values(), key=lambda macro: macro["name"].lower())
