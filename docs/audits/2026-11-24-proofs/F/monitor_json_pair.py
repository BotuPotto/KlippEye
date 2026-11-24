"""Proof: a hand-edited monitor.json with «Sure from» below «In doubt from» is loaded as it is; the page refuses the
same pair (MonitorConfig.update). Reads only the CONFIG_SPEC / MonitorConfig code of the backend (no Flask app run)."""
import ast, json, os, re, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../backend"))
src = open(os.path.join(os.path.dirname(__file__), "../../../../backend/klippeye_backend.py"), encoding="utf-8").read()
start = src.index("CONFIG_SPEC = ["); end = src.index("backend_config = MonitorConfig(")
ns = {}
exec("import copy, json, math, os, re, threading, time\nimport atomic\n" + "def write_json_atomic(p, d, private=False):\n    open(p,'w').write(json.dumps(d))\n"
     + "LOCAL_DOUBT_DEFAULT, LOCAL_SURE_DEFAULT = 35, 80\n" + src[start:end], ns)
path = os.path.join(tempfile.mkdtemp(), "monitor.json")
json.dump({"values": {"local_doubt": 90, "local_sure": 50}}, open(path, "w"))
cfg = ns["MonitorConfig"](path)
print("loaded from the file:", {k: cfg.values[k] for k in ("local_doubt", "local_sure")})
print("the same pair through the page:", cfg.update({"local_doubt": 90, "local_sure": 50}))
