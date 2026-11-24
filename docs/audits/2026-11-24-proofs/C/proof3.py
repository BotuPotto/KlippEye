import os as _os; exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "proof.py")).read().split("# 1. a 200")[0])
run("5 first look: Groq 200 with prose (not JSON), Gemini backup would answer PAUSE", {"groq": [R(content="I cannot tell from this picture.")], "gemini": [R(content=verdict("PAUSE"))]})
m, _ = load()
print("== 6 apply_min_confidence with confidence 0.9 (0-1 scale):", m.apply_min_confidence({"action": "PAUSE", "spaghetti": {"detected": True, "confidence": 0.9}}, 70)[0]["action"])
print("== 6b confidence '90' as text:", m.apply_min_confidence({"action": "PAUSE", "spaghetti": {"detected": True, "confidence": "90"}}, 70)[0]["action"])
# 7 record_alert in the same second: ids and pictures
a = m.record_alert({"outcome": "one"}, "/tmp/zoneC/a1.jpg"); b = m.record_alert({"outcome": "two"})
print("== 7 two alerts in one second, ids:", a["id"], b["id"])
