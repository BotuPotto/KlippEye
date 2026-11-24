import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Zone O proof: browser tests that exist but that tests/ui/run_all.sh never runs (so CI never runs them).
Run: python3 -I unlisted_ui_tests.py"""
import os, re
d = ROOT + "/tests/ui"
listed = set(re.search(r'^TESTS="([^"]+)"', open(os.path.join(d, "run_all.sh")).read(), re.M).group(1).split())
for f in sorted(os.listdir(d)):
    if f.endswith("_test.py") and f[:-3] not in listed:
        print("NOT RUN IN CI:", f)
