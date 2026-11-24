"""Proof: KlippEye's filament-change announcer for a macro defined in printer.cfg stops Klipper from starting.
Klipper reads every file into ONE RawConfigParser(strict=False) (klippy/configfile.py), so two [gcode_macro M600]
sections are merged into one; then klippy/extras/gcode_macro.py refuses the merged section."""
import configparser, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../backend"))
import printer_macros

def is_traditional_gcode(cmd):  # copied from klippy/gcode.py (Klipper master)
    try:
        cmd = cmd.upper().split()[0]
        float(cmd[1:])
        return cmd[0].isupper() and cmd[1].isdigit()
    except Exception:
        return False

data = tempfile.mkdtemp(); cfg = tempfile.mkdtemp()
open(os.path.join(cfg, "printer.cfg"), "w").write("[gcode_macro M600]\ngcode:\n  PAUSE\n  G1 X10 Y10\n\n[gcode_macro MY_RUNOUT]\ngcode:\n  PAUSE\n")
store = printer_macros.PrinterMacros(data, lambda: cfg, commands=lambda: ["M600", "MY_RUNOUT", "PAUSE"])
store.set_wraps(["M600", "MY_RUNOUT"])
parser = configparser.RawConfigParser(strict=False, inline_comment_prefixes=(";", "#"))
for name in ("printer.cfg", printer_macros.FILE_NAME):
    parser.read(os.path.join(cfg, name))
for section in ("gcode_macro M600", "gcode_macro MY_RUNOUT"):
    alias = section.split()[1].upper(); rename = parser.get(section, "rename_existing")
    print(section, "-> merged gcode:", repr(parser.get(section, "gcode")))
    if is_traditional_gcode(alias) != is_traditional_gcode(rename):
        print("  Klipper: config error \"G-Code macro rename of different types ('%s' vs '%s')\"" % (alias, rename))
    else:
        print("  Klipper: only one %s section exists, so at klippy:connect \"Existing command '%s' not found in gcode_macro rename\"" % (alias, alias))
