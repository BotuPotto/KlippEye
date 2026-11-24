import sys; sys.argv=["x"]
import os as _os; exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "proof.py")).read().split("# 1. a 200")[0])
m = run("1b again: status after", {"groq": [R(content=verdict("PAUSE"))], "gemini": [R(html="<html>x</html>")]})
print("   stats.status:", m.detector.stats.get("status"))
# 4. two analyses at once: cooldown shorter than the second look (scaled: delay 2 s, cooldown 1 s; real: 40 s vs min 30 s)
m, cur = load()
m.AI_CONFIRM_DELAY_S = 2
m.detector.ai_cooldown = 1
calls = []
def post(url, headers=None, json=None, timeout=None):
    calls.append(("groq" if "groq" in url else "gemini", round(time.time() % 100, 1)))
    return R(content=verdict("PAUSE"))
m.requests.post = post
t1 = threading.Thread(target=m.detector.call_ai_analysis, args=(cur, None, None)); t1.start()
time.sleep(1.2)
t2 = threading.Thread(target=m.detector.call_ai_analysis, args=(cur, None, None)); t2.start()
t1.join(); t2.join()
print("== 4 two alarms 1.2 s apart, cooldown 1 s, second look after 2 s: calls", calls, "alerts", len(m.read_alert_history()))
