import re
reason = "no app published"  # backend/klippeye_backend.py:3436, btn("no app published"), English or translated
print("matches:", bool(re.search(r"nessuna app", reason, re.I)))
