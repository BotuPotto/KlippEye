import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
import sys, os
sys.path.insert(0, ROOT + "/ml")
import download as d
for t in ["CC BY 4.0","Public Domain","MIT","BY-NC-SA 4.0","CC BY-NC 4.0","CC BY-SA 4.0","CC BY SA 4.0","CC BY NC 4.0","CC BY ND 4.0","CC BY-ND 4.0","CC BY NC SA 4.0","Private","Unknown","ODbL v1.0","GPL-3.0","see the dataset's page","", "CC BY 4.0 (non-commercial use only)", "Attribution-NonCommercial 4.0", "CC BY 3.0"]:
    c, o = d.licence_is_closed(t), d.licence_is_open(t)
    action = "DELETED" if c else ("kept, trained, marked 'check'" if not o else "kept (open)")
    print("%-40r closed=%-5s open=%-5s -> %s" % (t, c, o, action))
