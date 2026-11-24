"""Proof K10: the macro parameter form builds `NAME KEY=value` with the value as typed (57-calibration.js `run`). Klipper reads
extended commands with shlex.split + split('=', 1) (klippy/gcode.py _get_extended_params): a value with a space is cut in two
and the whole command is refused as «Malformed command». Quoting the value (KEY="a b") works.
Run: python3 .superpowers/audit/proofs/K/macro_param_space.py
"""
import shlex
def klipper_params(line):                     # the same two lines Klipper runs
    parts = line.split(None, 1)
    return {k.upper(): v for k, v in [a.split("=", 1) for a in shlex.split(parts[1])]}
macro, typed = "SHOW_MESSAGE", {"MSG": "hello world"}
built = " ".join([macro] + [k + "=" + v.strip() for k, v in typed.items()])     # the dashboard's own line
print("sent   :", built)
for line in (built, 'SHOW_MESSAGE MSG="hello world"'):
    try:
        print("Klipper:", klipper_params(line))
    except ValueError as e:
        print("Klipper: Malformed command (%s)" % e)
