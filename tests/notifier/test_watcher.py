"""Unit tests of the pure logic of klippeye_notifier.py (Watcher, verdict reading, RS256, message). Usage: python3 test_watcher.py"""
import copy, json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "notifier"))
import klippeye_notifier as vn

FAILS = []
def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))

# the Italian texts the notifications were asked with (release 1.0): they stay the Italian ones
ITALIAN_TEXTS = {
    "error": "Stampante in errore! Effettuare riavvio.",
    "complete": "Stampa completata!",
    "cancelled": "Stampa interrotta!",
    "paused": "Stampante in pausa!",
    "runout": "Filamento esaurito, effettuare cambio bobina!",
    "ai_pause": "Difetti di stampa rilevati, verificare e mettere in pausa la stampa!",
    "ai_cancel": "Difetti gravi di stampa rilevati, verificare e interrompere la stampa",
}
USER_TEXTS = vn.MESSAGES["en"]  # with no language chosen the notifications are in English
RUNOUT = "echo: O2S: Printer paused due to filament runout!"

def cfg(**over):
    c = vn.merge(vn.DEFAULT_CONFIG, over)
    return c

class Sim:
    """Drives a Watcher with snapshots and a clock."""
    def __init__(self, **over):
        self.w = vn.Watcher(cfg(**over)); self.t = 1000.0
        self.lines = []; self.state = "standby"; self.klippy = "ready"; self.ai = None
        self.log = []
    def step(self, dt=2.0, **kw):
        self.t += dt
        for k, v in kw.items(): setattr(self, k, v)
        snap = vn.Snapshot(klippy=self.klippy, print_state=self.state, lines=list(self.lines), ai=self.ai)
        out = self.w.step(snap, self.t)
        self.log += [(self.t, n.kind, n.text) for n in out]
        return [n.kind for n in out]
    def line(self, text, when=None):
        self.lines.append((when if when is not None else 2e9 + len(self.lines), text))
def ai(key, action): return vn.AiVerdict(key=key, action=action)

# --------------------------------------------------------------------------------------------------- the texts
ok("the Italian texts are exactly the ones asked for", all(vn.MESSAGES["it"][k] == v for k, v in ITALIAN_TEXTS.items()), {k: vn.MESSAGES["it"][k] for k in ITALIAN_TEXTS if vn.MESSAGES["it"][k] != ITALIAN_TEXTS[k]})
# the dashboard lists the same texts (Settings -> Notifications) in the same languages
import re as _re
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_dash = dict(_re.findall(r'id: "(\w+)", title: [^}]*?text: txn\("([^"]+)"\)', open(os.path.join(_root, "frontend", "src", "app", "16-settings.js"), encoding="utf-8").read()))
_it = json.load(open(os.path.join(_root, "frontend", "src", "i18n", "it.json"), encoding="utf-8"))
ok("the dashboard shows the same English texts the service sends", len(_dash) == 7 and all(vn.MESSAGES["en"][k] == v for k, v in _dash.items()), _dash)
ok("... and the same Italian ones", all(_it.get(v) == vn.MESSAGES["it"][k] for k, v in _dash.items()), {k: _it.get(v) for k, v in _dash.items()})
ok("every language has every text", all(set(texts) == set(vn.MESSAGES["en"]) and all(texts.values()) for texts in vn.MESSAGES.values()), {k: set(vn.MESSAGES["en"]) ^ set(t) for k, t in vn.MESSAGES.items()})

# --------------------------------------------------------------------------------------------------- starting up says nothing
s = Sim(); s.lines = [(1.0, RUNOUT)]; s.state = "complete"; s.ai = ai("old", "CANCELLA")
ok("start: a finished print, an old runout line and an old verdict are not news", s.step() == [] and s.step() == [] and s.step() == [])
s = Sim(); s.klippy = "shutdown"; s.state = None
ok("start: Klipper already in shutdown -> silent", s.step() == [] and s.step() == [])
s = Sim(); s.klippy = None; s.state = None
ok("Moonraker down at the start, then a print state that was there all along -> silent", s.step() == [] and s.step(klippy="ready", state="complete") == [] and s.step() == [])
s = Sim(); s.ai = None
ok("AI monitor unreachable at the start, then an old verdict shows up -> silent", s.step() == [] and s.step(ai=ai("old", "PAUSA")) == [] and s.step() == [])

# --------------------------------------------------------------------------------------------------- print end states
def started(**kw):
    s = Sim(**kw); s.step(); s.step(state="printing"); return s
s = started(); ok("complete: printing -> complete", s.step(state="complete") == ["complete"] and s.log[-1][2] == USER_TEXTS["complete"])
ok("complete: nothing more while it stays complete", s.step() == [] and s.step() == [])
s = started(); ok("cancelled state", s.step(state="cancelled") == ["cancelled"] and s.log[-1][2] == USER_TEXTS["cancelled"])
s = started(); ok("cancelled by a reset: printing -> standby", s.step(state="standby") == ["cancelled"])
s = started(); s.step(state="paused"); s.step(); ok("cancelled from pause: paused -> standby", s.step(state="standby") == ["cancelled"])
s = Sim(); s.step(state="complete"); ok("complete -> standby (a macro resets the file) is not a cancel", s.step(state="standby") == [])
s = started(); ok("error state of a print", s.step(state="error") == ["error"] and s.log[-1][2] == USER_TEXTS["error"])

# --------------------------------------------------------------------------------------------------- pause
s = started(); a = s.step(state="paused", dt=1); b = s.step(dt=1); c = s.step(dt=3)
ok("pause: announced after the grace time (4 s), not before", a == [] and b == [] and c == ["paused"] and s.log[-1][2] == USER_TEXTS["paused"], (a, b, c))
ok("pause: only once", s.step() == [] and s.step() == [])
s = started(); s.step(state="paused", dt=1); ok("pause + resume within the grace time: nothing", s.step(state="printing", dt=1) == [] and s.step(dt=10) == [])
s = started(); s.step(state="paused", dt=1); ok("pause then cancel within the grace time: only 'interrotta'", s.step(state="cancelled", dt=1) == ["cancelled"] and s.step(dt=10) == [])
s = started(); s.step(state="paused", dt=1); s.step(dt=10); s.step(state="printing", dt=20); ok("a second pause later is announced again (cooldown 15 s passed)", s.step(state="paused", dt=1) == [] and s.step(dt=5) == ["paused"])

# --------------------------------------------------------------------------------------------------- filament runout
s = started(); s.line(RUNOUT); k1 = s.step(state="paused", dt=1); k2 = s.step(dt=10)
ok("runout: line and pause in the same step -> only the runout text", k1 == ["runout"] and k2 == [] and s.log[-1][2] == USER_TEXTS["runout"], s.log)
s = started(); s.line(RUNOUT); k1 = s.step(dt=1); k2 = s.step(state="paused", dt=1); k3 = s.step(dt=10)
ok("runout: line first, pause a moment later -> only the runout text", k1 == ["runout"] and k2 == [] and k3 == [], (k1, k2, k3))
s = started(); k1 = s.step(state="paused", dt=1); s.line(RUNOUT); k2 = s.step(dt=1); k3 = s.step(dt=10)
ok("runout: pause seen first, line within the grace time -> only the runout text", k1 == [] and k2 == ["runout"] and k3 == [], (k1, k2, k3))
s = started(); s.step(state="paused", dt=1); s.step(dt=5); s.line(RUNOUT); k = s.step(dt=1)
ok("runout line long after a normal pause: both are announced", [x[1] for x in s.log] == ["paused", "runout"], s.log)
s = started(events={"runout": False}); s.line(RUNOUT); a = s.step(state="paused", dt=1); b = s.step(dt=6)
ok("runout notices switched off: the pause is announced as a pause", a == [] and b == ["paused"], (a, b))
s = started(); s.line(RUNOUT); s.step(dt=1); s.line(RUNOUT); k = s.step(dt=1)
ok("the same runout twice within a minute -> once", [x[1] for x in s.log] == ["runout"], s.log)
s.step(dt=80); s.line(RUNOUT); ok("... and again after the cooldown", s.step(dt=1) == ["runout"])
s = started(); s.line("O2S: Filament runout is disabled in the sensor config file!"); ok("the 'runout disabled' line is not an alarm", s.step() == [])
s = started(); s.line("echo: something else"); ok("unrelated lines are ignored", s.step() == [])
s = started(); s.line("PAUSED DUE TO FILAMENT RUNOUT"); ok("the match ignores the case", s.step() == ["runout"])

# --------------------------------------------------------------------------------------------------- errors
s = Sim(); s.step(); ok("error: Klipper ready -> shutdown", s.step(klippy="shutdown") == ["error"] and s.log[-1][2] == USER_TEXTS["error"])
ok("error: shutdown -> error right after: not again", s.step(klippy="error") == [] and s.step() == [])
s = started(); s.step(klippy="shutdown"); ok("error: shutdown in a print, the print then turns 'error' -> one notice", [x[1] for x in s.log] == ["error"] and s.step(klippy="ready", state="error") == [])
s = started(); k1 = s.step(state="error"); k2 = s.step(klippy="shutdown")
ok("error: print 'error' first, shutdown a moment later -> one notice", k1 == ["error"] and k2 == [], (k1, k2))
s = Sim(); s.step(); s.step(klippy="shutdown"); s.step(klippy="startup"); s.step(klippy="ready"); s.step(dt=200)
ok("error: a new shutdown after the cooldown is announced again", s.step(klippy="shutdown") == ["error"])
s = Sim(); s.step(); ok("a normal restart (ready -> startup -> ready) is not an error", s.step(klippy="startup") == [] and s.step(klippy="disconnected") == [] and s.step(klippy="ready") == [])
s = started(); s.step(klippy="startup", state=None); ok("a restart in the middle of a print: it comes back 'standby' and that is NOT 'interrotta'", s.step(klippy="ready", state="standby") == [] and s.step() == [])
s = Sim(); s.step(); ok("Moonraker unreachable for a while: nothing", s.step(klippy=None, state=None, lines=[]) == [] and s.step() == [])
s = started(); s.step(klippy=None, state=None); ok("... and a print that ends meanwhile is announced when it is back", s.step(klippy="ready", state="complete") == ["complete"])

# --------------------------------------------------------------------------------------------------- AI
s = started(); s.ai = ai("v0", "CONTINUA"); s.step()
ok("AI: a new verdict that says CONTINUA is not announced", s.step(ai=ai("v1", "CONTINUA")) == [])
ok("AI: PAUSA", s.step(ai=ai("v2", "PAUSA")) == ["ai_pause"] and s.log[-1][2] == USER_TEXTS["ai_pause"])
ok("AI: the same verdict again: nothing", s.step() == [] and s.step() == [])
ok("AI: then CANCELLA right away is announced (different notice)", s.step(ai=ai("v3", "CANCELLA")) == ["ai_cancel"] and s.log[-1][2] == USER_TEXTS["ai_cancel"])
ok("AI: another PAUSA within 3 minutes: not repeated", s.step(ai=ai("v4", "PAUSA"), dt=10) == [])
ok("AI: ... and after 3 minutes it is", s.step(ai=ai("v5", "PAUSA"), dt=200) == ["ai_pause"])
s = started(); s.ai = ai("v0", "CONTINUA"); s.step(); ok("AI: 'Pausa' in lower case / with words around it", s.step(ai=ai("v1", "pausa consigliata")) == ["ai_pause"])
s = Sim(); s.ai = ai("v0", "CONTINUA"); s.step(); s.step()
ok("AI: a verdict while no print is running is ignored", s.step(ai=ai("v1", "CANCELLA")) == [])
s = started(); s.ai = ai("none", ""); s.step(); ok("AI: no verdict yet, then a first one during the print -> announced", s.step(ai=ai("t|{...}", "PAUSA")) == ["ai_pause"])
s = started(); s.ai = ai("v0", "PAUSA"); s.step(); ok("AI: Brain unreachable (None) and back with the same verdict: nothing", s.step(ai=None) == [] and s.step(ai=ai("v0", "PAUSA")) == [])
s = started(); s.step(state="paused"); s.ai = ai("v0", "CONTINUA"); s.step(); ok("AI: during a pause the verdicts still count", "ai_cancel" in s.step(ai=ai("v1", "CANCELLA")))

# --------------------------------------------------------------------------------------------------- switches
for kind, drive in (("complete", lambda s: s.step(state="complete")), ("cancelled", lambda s: s.step(state="cancelled")), ("error", lambda s: s.step(klippy="shutdown"))):
    s = started(events={kind: False}); ok(f"switched off: {kind}", drive(s) == [])
s = started(events={"ai_pause": False}); s.ai = ai("v0", "CONTINUA"); s.step(); ok("switched off: ai_pause (ai_cancel still on)", s.step(ai=ai("v1", "PAUSA")) == [] and s.step(ai=ai("v2", "CANCELLA")) == ["ai_cancel"])
s = started(messages={"complete": "Fatto!"}); ok("a message can be changed in the config, the others stay", s.step(state="complete") == ["complete"] and s.log[-1][2] == "Fatto!" and vn.message_text(cfg(messages={"complete": "x"}), None, "error") == USER_TEXTS["error"])
s = started(language="it"); ok("language 'it' in notifier.json: Italian texts", s.step(state="complete") == ["complete"] and s.log[-1][2] == "Stampa completata!")
s = started(language="xx"); ok("an unknown language in notifier.json: English", s.step(state="complete") == ["complete"] and s.log[-1][2] == "Print completed!")

# --------------------------------------------------------------------------------------------------- the console lines
s = Sim(); s.lines = [(5000.0, "old")]; s.step(); s.line(RUNOUT, 4000.0)
ok("a line older than what was seen at the start is not new", s.step() == [])
s = Sim(); s.lines = [(5000.0, "a")]; s.step(); s.line(RUNOUT, 1000.0)
ok("the clock went back (time sync) -> start over from the new time, no false alarm", s.step() == [] and s.w.last_line_time == 5000.0, s.w.last_line_time)
s = Sim(); s.step(); s.lines = [(2e9, RUNOUT)]
ok("an empty console at the start: the first line is news", s.step() == ["runout"])

# --------------------------------------------------------------------------------------------------- reading the AI answer
cases = [
    ({"analysis": {"action": "PAUSA"}}, "PAUSA"),
    ({"analysis": {"analysis": json.dumps({"action": "CANCELLA", "summary": "x"}), "action": ""}}, "CANCELLA"),
    ({"analysis": {"analysis": "Ecco il verdetto: " + json.dumps({"spaghetti": {}, "action": "PAUSA"}) + " fine"}}, "PAUSA"),
    ({"analysis": {"analysis": {"action": "cancella"}}}, "CANCELLA"),
    ({"analysis": json.dumps({"action": "CONTINUA"})}, "CONTINUA"),
    ({"action": "pausa"}, "PAUSA"),
    ({"analysis": {"analysis": "testo senza json"}}, ""),
    ({}, ""),
]
for resp, want in cases:
    ok(f"ai_action({json.dumps(resp)[:70]}) = {want!r}", vn.ai_action(resp) == want, vn.ai_action(resp))

# --------------------------------------------------------------------------------------------------- RS256 (the Google sign-in) against a real implementation
try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes, serialization
    rng = random.Random(7)
    good = 0; total = 0
    for bits in (1024, 2048, 3072):
        key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
        for fmt, label in ((serialization.PrivateFormat.PKCS8, "PKCS8"), (serialization.PrivateFormat.TraditionalOpenSSL, "PKCS1")):
            pem = key.private_bytes(serialization.Encoding.PEM, fmt, serialization.NoEncryption()).decode()
            n, d = vn.rsa_private_numbers(pem)
            nums = key.private_numbers()
            ok(f"RSA {bits} {label}: modulus and private exponent read correctly", n == nums.public_numbers.n and d == nums.d)
            for _ in range(5):
                msg = bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 300)))
                mine = vn.rs256_sign(msg, n, d)
                theirs = key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
                total += 1; good += mine == theirs
                key.public_key().verify(mine, msg, padding.PKCS1v15(), hashes.SHA256())
    ok("RS256: 30 signatures identical to the cryptography library's (and they verify)", good == total, (good, total))
except ImportError:
    print("SKIP RS256 tests: cryptography not installed")

# --------------------------------------------------------------------------------------------------- the FCM message
msg = vn.build_message(cfg(topic="vzbot-abc"), vn.Notice("runout", USER_TEXTS["runout"]))["message"]
ok("message: topic, title and body", msg["topic"] == "vzbot-abc" and msg["notification"] == {"title": "KlippEye", "body": USER_TEXTS["runout"]}, msg)
ok("message: high priority, channel 'allarmi', tag and collapse key = kind, ttl 6 h", msg["android"]["priority"] == "HIGH" and msg["android"]["notification"]["channel_id"] == "allarmi" and msg["android"]["notification"]["tag"] == "runout" and msg["android"]["collapse_key"] == "runout" and msg["android"]["ttl"] == "21600s", msg["android"])
ok("message: channels by kind", {k: vn.build_message(cfg(topic="t"), vn.Notice(k, "x"))["message"]["android"]["notification"]["channel_id"] for k in vn.KIND_CHANNEL} == vn.KIND_CHANNEL)
AUTO_ONLY = {"ai_pause_auto", "ai_cancel_auto"}
ok("every kind has a channel (the two 'automatically' texts belong to the AI kinds)", set(vn.DEFAULT_MESSAGES) - AUTO_ONLY == set(vn.KIND_CHANNEL) and AUTO_ONLY <= set(vn.DEFAULT_MESSAGES))

# --------------------------------------------------------------------------------------------------- config
c = vn.merge(vn.DEFAULT_CONFIG, {"messages": {"complete": "Ok"}, "events": {"paused": False}, "topic": "t"})
ok("config: nested dictionaries are merged, not replaced", c["messages"] == {"complete": "Ok"} and c["events"]["paused"] is False and c["events"]["error"] is True)
ok("config: the defaults dictionary is not changed", vn.DEFAULT_CONFIG["events"]["paused"] is True and vn.DEFAULT_CONFIG["messages"] == {})


# =================================================================================================== version 1.1: the dashboard's settings
def doc(**kw):
    """A settings document like the dashboard writes it (only what the test changes)."""
    d = {"notifications": {}, "ai": {"defects": {}}, "_t": 5}
    for k, v in kw.items():
        if k in ("autoPause", "autoCancel", "confirmations", "minConfidence"): d["ai"][k] = v
        elif k == "defects": d["ai"]["defects"] = v
        elif k == "notifications": d["notifications"] = v
        else: d[k] = v
    return d
def verdict(key, action, **defects):
    """A verdict with details: defects as name=(detected, confidence)."""
    return vn.AiVerdict(key=key, action=action, defects=defects or None)

class Sim2(Sim):
    """Sim with the dashboard's settings and the actions the Watcher asks for."""
    def __init__(self, **over):
        super().__init__(**over); self.settings = None; self.actions = []
    def step(self, dt=2.0, **kw):
        self.t += dt
        for k, v in kw.items(): setattr(self, k, v)
        snap = vn.Snapshot(klippy=self.klippy, print_state=self.state, lines=list(self.lines), ai=self.ai, settings=self.settings)
        out = self.w.step(snap, self.t)
        self.log += [(self.t, n.kind, n.text) for n in out]
        self.actions += [a.kind for a in self.w.take_actions()]
        return [n.kind for n in out]
    def printing(self):
        self.step(); self.step(state="printing"); self.step(ai=vn.AiVerdict(key="base", action="CONTINUA"))
def printing2(**over):
    s = Sim2(**over); s.printing(); return s

# ---- sanitising: the document comes from a browser
ok("settings: nothing stored -> every notification as in notifier.json, automatic actions off, 1 verdict, no filters",
   vn.dash_settings({}) == {"events": {}, "ai": {"auto_pause": False, "auto_cancel": False, "confirmations": 1, "min_confidence": 0, "defects": {k: True for k in vn.DASH_DEFECTS}}, "language": None, "stamp": 0})
for junk in (None, "x", 5, [], {"ai": "x", "notifications": 3}, {"ai": {"autoPause": "yes", "autoCancel": 1, "confirmations": "2", "minConfidence": 60, "defects": {"warping": 0}}}):
    d = vn.dash_settings(junk)
    ok("settings: garbage %r changes nothing (no automatic action, defaults)" % (junk,), not d["ai"]["auto_pause"] and not d["ai"]["auto_cancel"] and d["ai"]["confirmations"] == 1 and d["ai"]["min_confidence"] == 0 and all(d["ai"]["defects"].values()) and d["events"] == {}, d)
ok("settings: only a real true switches an automatic action on (not 1, not 'true')", vn.dash_settings({"ai": {"autoPause": True}})["ai"]["auto_pause"] is True and not vn.dash_settings({"ai": {"autoPause": 1}})["ai"]["auto_pause"] and not vn.dash_settings({"ai": {"autoCancel": "true"}})["ai"]["auto_cancel"])
ok("settings: confirmations only 1-3, confidence only 0/50/70/85, True is not a number", vn.dash_settings({"ai": {"confirmations": 3, "minConfidence": 85}})["ai"]["confirmations"] == 3 and vn.dash_settings({"ai": {"confirmations": 9, "minConfidence": 60}})["ai"]["confirmations"] == 1 and vn.dash_settings({"ai": {"minConfidence": 60}})["ai"]["min_confidence"] == 0 and vn.dash_settings({"ai": {"confirmations": True}})["ai"]["confirmations"] == 1)
ok("settings: a notification switch must be a real boolean", vn.dash_settings({"notifications": {"error": False, "paused": "no", "complete": 0, "bogus": False}})["events"] == {"error": False})

# ---- the language of the notifications chosen in the dashboard (1.3)
ok("settings: the language is one the service has, else not chosen", vn.dash_settings({"language": "it"})["language"] == "it" and vn.dash_settings({"language": "fr"})["language"] is None and vn.dash_settings({"language": 1})["language"] is None)
s = Sim2(); s.step(); s.step(state="printing"); s.settings = doc(language="it")
ok("language: Italian chosen in the dashboard -> Italian push", s.step(state="complete") == ["complete"] and s.log[-1][2] == "Stampa completata!", s.log)
s = Sim2(language="it"); s.step(); s.step(state="printing"); s.settings = doc(language="en")
ok("language: the dashboard's choice wins over notifier.json", s.step(state="complete") == ["complete"] and s.log[-1][2] == "Print completed!", s.log)
s = Sim2(messages={"complete": "Finito"}); s.step(); s.step(state="printing"); s.settings = doc(language="it")
ok("language: a text written in notifier.json wins over the language", s.step(state="complete") == ["complete"] and s.log[-1][2] == "Finito", s.log)
s = Sim2(); s.printing(); s.settings = doc(language="it", autoPause=True); s.step(ai=verdict("p1", "PAUSA")); s.w.report_action("pause", True); s.step(state="paused")
ok("language: the 'automatically' text is Italian too", [x[2] for x in s.log if x[1] == "ai_pause"] == ["Difetti di stampa rilevati: stampa messa in pausa automaticamente."], s.log)

# ---- the notification switches of the dashboard win over notifier.json
s = started2 = Sim2(); s.step(); s.step(state="printing"); s.settings = doc(notifications={"complete": False})
ok("switch: 'Print completed' off in the dashboard -> no push", s.step(state="complete") == [] and s.step() == [])
s = Sim2(events={"complete": False}); s.step(); s.step(state="printing"); s.settings = doc(notifications={"complete": True})
ok("switch: on in the dashboard wins over 'false' in notifier.json", s.step(state="complete") == ["complete"])
s = Sim2(events={"complete": False}); s.step(); s.step(state="printing"); s.settings = {}
ok("switch: nothing stored in the dashboard -> notifier.json decides", s.step(state="complete") == [])
s = Sim2(); s.step(); s.step(state="printing"); s.settings = doc(notifications={"complete": False}); s.step(); s.settings = None
ok("switch: settings not readable for a moment (None) -> the last ones stay", s.step(state="complete") == [])
s = Sim2(); s.step(); s.step(state="printing"); s.settings = doc(notifications={"complete": False}); s.step(); s.settings = {}
ok("switch: the document emptied -> back to notifier.json (on)", s.step(state="complete") == ["complete"])

# ---- the filters on the AI verdict: nothing changes while they are at their defaults
s = printing2(); s.settings = doc()
ok("filters at their defaults: a PAUSA verdict notifies, whatever its details", s.step(ai=verdict("a", "PAUSA", warping=(False, 0))) == ["ai_pause"])
s = printing2(); s.settings = doc(minConfidence=70)
ok("min confidence 70: a PAUSA whose only defect is at 61% is ignored", s.step(ai=verdict("a", "PAUSA", warping=(True, 61), spaghetti=(False, 10))) == [])
ok("... and one at 72% counts", s.step(ai=verdict("b", "PAUSA", warping=(True, 72))) == ["ai_pause"])
s = printing2(); s.settings = doc(minConfidence=70)
ok("min confidence: a verdict without details (plain text) is trusted: nothing to filter on", s.step(ai=vn.AiVerdict(key="a", action="PAUSA")) == ["ai_pause"])
s = printing2(); s.settings = doc(defects={"warping": False})
ok("defect off: a PAUSA caused only by warping is ignored", s.step(ai=verdict("a", "PAUSA", warping=(True, 90), spaghetti=(False, 5))) == [])
ok("... but spaghetti at the same time counts", s.step(ai=verdict("b", "CANCELLA", warping=(True, 90), spaghetti=(True, 80))) == ["ai_cancel"])
s = printing2(); s.settings = doc(defects={"empty_bed": False, "warping": False}, minConfidence=50)
ok("filters together: only enabled defects at or above the minimum count", s.step(ai=verdict("a", "PAUSA", empty_bed=(True, 99), warping=(True, 99), layer_shift=(True, 49))) == [] and s.step(ai=verdict("b", "PAUSA", layer_shift=(True, 50))) == ["ai_pause"])

# ---- verdicts in a row
s = printing2(); s.settings = doc(confirmations=2)
ok("2 in a row: the first PAUSA verdict only waits", s.step(ai=verdict("a", "PAUSA")) == [])
ok("... the second one notifies", s.step(ai=verdict("b", "PAUSA")) == ["ai_pause"])
s = printing2(); s.settings = doc(confirmations=2)
s.step(ai=verdict("a", "PAUSA")); s.step(ai=verdict("b", "CONTINUA"))
ok("2 in a row: a CONTINUA in between starts the count again", s.step(ai=verdict("c", "PAUSA")) == [] and s.step(ai=verdict("d", "PAUSA")) == ["ai_pause"])
s = printing2(); s.settings = doc(confirmations=3)
ok("3 in a row", s.step(ai=verdict("a", "PAUSA")) == [] and s.step(ai=verdict("b", "PAUSA")) == [] and s.step(ai=verdict("c", "PAUSA")) == ["ai_pause"])
s = printing2(); s.settings = doc(confirmations=2)
ok("2 in a row: PAUSA then CANCELLA counts as pause (the lower of the two)", s.step(ai=verdict("a", "PAUSA")) == [] and s.step(ai=verdict("b", "CANCELLA")) == ["ai_pause"])
s = printing2(); s.settings = doc(confirmations=2)
ok("2 in a row: CANCELLA twice -> the cancel notice", s.step(ai=verdict("a", "CANCELLA")) == [] and s.step(ai=verdict("b", "CANCELLA")) == ["ai_cancel"])
s = printing2(); s.settings = doc(confirmations=2)
s.step(ai=verdict("a", "PAUSA")); s.step(state="complete"); s.step(state="printing"); s.step()
ok("2 in a row: the verdicts of the last print do not carry over to a new one", s.step(ai=verdict("b", "PAUSA")) == [])
s = printing2(); s.settings = doc(confirmations=2); s.step(ai=verdict("a", "PAUSA"))
ok("2 in a row: the same verdict seen again is not a second one", s.step(ai=verdict("a", "PAUSA")) == [] and s.step() == [])

# ---- automatic pause / cancel
s = printing2(); s.settings = doc(autoPause=True)
k = s.step(ai=verdict("a", "PAUSA"))
ok("auto pause ON: a PAUSA verdict asks for a pause, and no notice goes out yet", k == [] and s.actions == ["pause"], (k, s.actions))
s.w.report_action("pause", True); s.step(state="paused", dt=0.1); k = s.step(dt=0.1)
ok("... when it is done the notice says it was done automatically (the ai_pause kind, the 'automatically' text)", [x for x in s.log if x[1] == "ai_pause"] and s.log[-1][2] == vn.DEFAULT_MESSAGES["ai_pause_auto"] and s.log[-1][1] == "ai_pause", s.log)
s.step(dt=10); s.step(dt=10)
ok("... and the plain 'Printer paused' is NOT sent on top (the pause was ours)", [x[1] for x in s.log] == ["ai_pause"], s.log)
ok("... and the dashboard is told what happened", s.w.last_action and s.w.last_action["kind"] == "pause" and s.w.last_action["ok"] is True, s.w.last_action)
s.step(state="printing"); n = len(s.actions)
s.step(ai=verdict("b", "PAUSA"), dt=200)
ok("... once per print: after the person resumed, a new PAUSA verdict only notifies", s.actions == ["pause"] and [x[1] for x in s.log][-1] == "ai_pause" and s.log[-1][2] == vn.DEFAULT_MESSAGES["ai_pause"], (s.actions, s.log[-1]))
s.step(state="complete"); s.step(state="printing"); s.step(ai=vn.AiVerdict(key="z", action="CONTINUA")); k = s.step(ai=verdict("c", "PAUSA"), dt=200)
ok("... and in the next print it is available again", s.actions == ["pause", "pause"], s.actions)

s = printing2(); s.settings = doc(autoPause=True)
s.step(ai=verdict("a", "PAUSA")); s.w.report_action("pause", False); k = s.step(dt=0.1)
ok("auto pause that FAILS (print still going): the ordinary notice goes out, so the person acts", k == ["ai_pause"] and s.log[-1][2] == vn.DEFAULT_MESSAGES["ai_pause"], s.log)
k = s.step(ai=verdict("b", "PAUSA"), dt=200)
ok("... and the next verdict may try again", s.actions == ["pause", "pause"], s.actions)

s = printing2(); s.settings = doc(autoPause=True)
s.step(ai=verdict("a", "PAUSA")); s.step(state="paused", dt=0.1); s.w.report_action("pause", False); s.step(dt=0.1)
ok("auto pause: Klipper answered with an error but the print IS paused -> counts as done", s.log[-1][2] == vn.DEFAULT_MESSAGES["ai_pause_auto"], s.log)

s = printing2(); s.settings = doc()
s.step(ai=verdict("a", "PAUSA")); s.step(ai=verdict("b", "CANCELLA"), dt=200)
ok("auto actions OFF (the default): nothing is ever paused or cancelled, only notices", s.actions == [] and [x[1] for x in s.log] == ["ai_pause", "ai_cancel"], (s.actions, s.log))

s = printing2(); s.settings = doc(autoCancel=True)
k = s.step(ai=verdict("a", "PAUSA"))
ok("auto cancel only: a PAUSA verdict is NOT cancelled (just notified)", s.actions == [] and k == ["ai_pause"], (s.actions, k))
k = s.step(ai=verdict("b", "CANCELLA"), dt=200)
ok("auto cancel ON: a CANCELLA verdict asks for the cancel, no notice yet", s.actions == ["cancel"] and k == [], (s.actions, k))
s.step(state="cancelled", dt=0.1); s.w.report_action("cancel", True); s.step(dt=0.1)
ok("... then: the 'automatically' text, and no plain 'Print cancelled!' on top", [x[1] for x in s.log] == ["ai_pause", "ai_cancel"] and s.log[-1][2] == vn.DEFAULT_MESSAGES["ai_cancel_auto"], s.log)
s.step(dt=10)

s = printing2(); s.settings = doc(autoPause=True)
s.step(ai=verdict("a", "CANCELLA"))
ok("auto pause only: a CANCELLA verdict pauses (the careful half) instead of cancelling", s.actions == ["pause"], s.actions)
s.step(state="paused", dt=0.1); s.w.report_action("pause", True); s.step(dt=0.1)
k = s.step(ai=verdict("b", "CANCELLA"), dt=200)
ok("... and when it still says CANCELLA the person is told, nothing is cancelled", s.actions == ["pause"] and k == ["ai_cancel"] and s.log[-1][2] == vn.DEFAULT_MESSAGES["ai_cancel"], (s.actions, s.log[-1]))

s = printing2(); s.settings = doc(autoPause=True, autoCancel=True)
s.step(ai=verdict("a", "CANCELLA"))
ok("both ON: CANCELLA cancels (it does not pause first)", s.actions == ["cancel"], s.actions)
s = printing2(); s.settings = doc(autoPause=True, autoCancel=True)
s.step(ai=verdict("a", "PAUSA"))
ok("both ON: PAUSA pauses", s.actions == ["pause"], s.actions)
s.step(state="paused", dt=0.1); s.w.report_action("pause", True); s.step(dt=0.1); s.step(ai=verdict("b", "CANCELLA"), dt=200)
ok("both ON: after the auto pause, a CANCELLA verdict cancels the paused print", s.actions == ["pause", "cancel"], s.actions)

s = printing2(); s.settings = doc(autoPause=True, autoCancel=True, confirmations=2)
s.step(ai=verdict("a", "CANCELLA"))
ok("automatic actions also wait for the verdicts in a row", s.actions == [])
s.step(ai=verdict("b", "CANCELLA")); ok("... and happen on the second", s.actions == ["cancel"], s.actions)
s = printing2(); s.settings = doc(autoPause=True, autoCancel=True, defects={"warping": False})
s.step(ai=verdict("a", "CANCELLA", warping=(True, 99)))
ok("automatic actions respect the defect filter (warping switched off -> nothing)", s.actions == [])

s = Sim2(); s.settings = doc(autoPause=True, autoCancel=True); s.step(); s.step(ai=verdict("x", "CANCELLA"))
s.step(ai=verdict("a", "CANCELLA")); ok("no print running (standby): a verdict never pauses or cancels anything", s.actions == [] and s.log == [], (s.actions, s.log))
s = Sim2(); s.settings = doc(autoPause=True, autoCancel=True); s.step(state="complete"); s.step(ai=verdict("x", "CONTINUA")); s.step(ai=verdict("a", "CANCELLA"))
ok("a finished print (complete): same", s.actions == [], s.actions)
s = Sim2(); s.settings = doc(autoPause=True, autoCancel=True); s.step(state="paused"); s.step(ai=verdict("x", "CONTINUA")); s.step(ai=verdict("a", "PAUSA"))
ok("print already paused when the service started: PAUSA does not pause again (it only notifies)", s.actions == [] and [x[1] for x in s.log] == ["ai_pause"], (s.actions, s.log))
s = Sim2(); s.settings = doc(autoPause=True); s.klippy = None; s.state = None; s.step(); s.step(ai=verdict("x", "CONTINUA")); s.step(ai=verdict("a", "PAUSA"))
ok("Moonraker not reachable (state unknown): it does not act blindly", s.actions == [], s.actions)

s = printing2(); s.settings = doc(autoPause=True, notifications={"ai_pause": False})
s.step(ai=verdict("a", "PAUSA")); s.step(state="paused", dt=0.1); s.w.report_action("pause", True); k = s.step(dt=0.1)
ok("auto pause with the 'IA: difetti' notification switched off: it pauses, and says nothing", s.actions == ["pause"] and k == [] and s.log == [], (s.actions, s.log))

# ---- reading the details of a verdict, as the Brain delivers it (see the dashboard mock)
inner = json.dumps({"spaghetti": {"detected": False, "confidence": 12, "note": "ok"}, "empty_bed": {"detected": False, "confidence": 3}, "layer_shift": {"detected": False, "confidence": 5}, "warping": {"detected": True, "confidence": 61}, "action": "PAUSA", "summary": "x"})
want = {"spaghetti": (False, 12.0), "empty_bed": (False, 3.0), "layer_shift": (False, 5.0), "warping": (True, 61.0)}
ok("details: verdict object whose 'analysis' is JSON text", vn.ai_defects({"analysis": {"analysis": inner, "action": "PAUSA"}}) == want)
ok("details: JSON text with words around it", vn.ai_defects({"analysis": {"analysis": "Ecco il verdetto:\n" + inner + "\nFine."}}) == want)
ok("details: the analysis is the text itself", vn.ai_defects({"analysis": inner}) == want)
ok("details: the analysis is already the object", vn.ai_defects({"analysis": json.loads(inner)}) == want)
ok("details: plain words -> None", vn.ai_defects({"analysis": "Tutto ok."}) is None and vn.ai_defects({}) is None and vn.ai_defects({"analysis": {"action": "PAUSA"}}) is None)
ok("details: a confidence that is not a number counts as 0, 'detected' must be a real true", vn.ai_defects({"analysis": {"warping": {"detected": "yes", "confidence": "high"}}}) == {"warping": (False, 0.0)})

# ---- version 1.2: the service notices that an update replaced its own file
import tempfile, threading, time
tmpdir = tempfile.mkdtemp()
src = os.path.join(tmpdir, "prog.py")
open(src, "w").write("x = 1\n")
sw = vn.SelfWatch(src)
ok("self-watch: untouched file -> no change", sw.changed() is False)
time.sleep(0.02)
open(src, "w").write("x = 2\n")
ok("self-watch: replaced file with valid code -> changed", sw.changed() is True)
sw2 = vn.SelfWatch(src)
time.sleep(0.02)
open(src, "w").write("def broken(:\n")
ok("self-watch: replaced by a file that is NOT valid python -> keeps running (no change)", sw2.changed() is False)
ok("self-watch: ... and says so only once", (sw2.changed(), sw2.changed()) == (False, False))
time.sleep(0.02)
open(src, "w").write("x = 3\n")
ok("self-watch: ... then fixed -> changed", sw2.changed() is True)
sw3 = vn.SelfWatch(os.path.join(tmpdir, "missing.py"))
ok("self-watch: a missing file never counts as a change", sw3.changed() is False)
os.remove(src)
ok("self-watch: file removed during the update -> no change (waits for the new one)", sw.changed() is False)

# run() ends by itself when its file changes (against a fake Moonraker that answers nothing: the loop still turns)
cfg2 = cfg(poll_seconds=0.2, moonraker_url="http://127.0.0.1:9", brain_url="http://127.0.0.1:9")
watched = os.path.join(tmpdir, "watched.py")
open(watched, "w").write("y = 1\n")
stop = threading.Event()
runner = threading.Thread(target=lambda: vn.run(cfg2, True, stop, watch_file=watched), daemon=True)
runner.start()
time.sleep(1.0)
ok("run(): file untouched -> keeps running", runner.is_alive() and not stop.is_set())
time.sleep(0.02)
open(watched, "w").write("y = 2\n")
runner.join(5)
ok("run(): file replaced -> the service ends by itself (systemd restarts it)", not runner.is_alive() and stop.is_set())
ok("version is 1.3", vn.__version__ == "1.3", vn.__version__)

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
