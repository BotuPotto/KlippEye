import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof I-5: pins that are not lights are offered as lights (the same words list is in the dashboard, 16a-printer-functions.js).
Run: python3 light_words.py"""
import sys
sys.path.insert(0, ROOT + "/backend")
import printer_lights as pl
objects = ["output_pin case_fan", "output_pin chamber_heater_relay", "output_pin psu_enabled", "output_pin beeper", "neopixel LUCI"]
outs = pl.outputs_from(objects, {})
for item in pl.detect(outs, []):
    print(item["name"], "->", pl.switch_commands(next(o for o in outs if o["object"] == item["object"]), {})[0])
