"""
How often the AI's verdict matches the real state of the print (roadmap phase 6a, part 4, release 1.28.0).

Every alarm the person judged (Recordings, or the print card) says whether the print really had a problem ("right") or not
("false"); the alarm also keeps what the AI answered ("action", after the minimum confidence; "original_action", what it
proposed before that; "confidence", the highest confidence of a defect). Put together:

    the AI said             the print had a problem   the print was fine
    pause / cancel          stop, right               stop, wrong (a false stop)
    continue                continue, wrong (missed)  continue, right

and, for each minimum confidence the menu offers, what the same answers would have given: a stop is kept when the AI proposed
it and its confidence reaches that minimum. That shows whether the threshold in use has margin (fewer false stops with no
problem missed) or is too high (problems missed).
Alarms with no verdict of the AI (an error of the AI service) are counted apart: they say nothing about the AI.
"""

STOPS = ("PAUSE", "CANCEL")
THRESHOLDS = (50, 60, 70, 80, 90, 95)
ENOUGH = 10   # judged alarms below which the numbers are shown as a first idea only


def merge(history, sessions):
    """The alarms of the alert history and of the recordings, once each (the history's label wins when it has one)."""
    out = {}
    for session in sessions or []:
        for alert in (session.get("alerts") or []) if isinstance(session, dict) else []:
            if isinstance(alert, dict) and alert.get("id"):
                out[alert["id"]] = dict(alert)
    for alert in history or []:
        if isinstance(alert, dict) and alert.get("id"):
            before = out.get(alert["id"]) or {}
            merged = dict(before, **alert)
            merged["label"] = alert.get("label", before.get("label"))   # as /api/recordings/<id> shows it
            out[alert["id"]] = merged
    return list(out.values())


def _verdict(alert):
    action = str(alert.get("action") or "").upper()
    return action if action in STOPS + ("CONTINUE",) else None


def precision(alerts, current=None):
    """-> {judged, no_verdict, enough, stop_right, stop_wrong, continue_right, continue_wrong, correct_pct, stop_pct,
    caught_pct, thresholds: [{threshold, judged, false_stops, missed, correct_pct}], current, advice}."""
    rows = [a for a in alerts if a.get("label") in ("right", "false")]
    judged = [a for a in rows if _verdict(a)]
    out = {"judged": len(judged), "no_verdict": len(rows) - len(judged), "enough": len(judged) >= ENOUGH,
           "stop_right": 0, "stop_wrong": 0, "continue_right": 0, "continue_wrong": 0}
    for a in judged:
        stop = _verdict(a) in STOPS
        problem = a["label"] == "right"
        key = ("stop_" if stop else "continue_") + ("right" if stop == problem else "wrong")
        out[key] += 1
    stops = out["stop_right"] + out["stop_wrong"]
    problems = out["stop_right"] + out["continue_wrong"]
    out["correct_pct"] = round(100.0 * (out["stop_right"] + out["continue_right"]) / len(judged)) if judged else None
    out["stop_pct"] = round(100.0 * out["stop_right"] / stops) if stops else None          # of the stops, how many were right
    out["caught_pct"] = round(100.0 * out["stop_right"] / problems) if problems else None  # of the problems, how many stopped
    # what each minimum confidence would have given, on the alarms whose proposal and confidence are known
    known = [a for a in judged if isinstance(a.get("confidence"), (int, float)) and not isinstance(a.get("confidence"), bool)]
    table = []
    for threshold in sorted(set(THRESHOLDS) | ({current} if isinstance(current, (int, float)) else set())):
        false_stops = missed = right = 0
        for a in known:
            proposed = str(a.get("original_action") or a.get("action") or "").upper()
            stop = proposed in STOPS and a["confidence"] >= threshold
            problem = a["label"] == "right"
            if stop and not problem:
                false_stops += 1
            elif problem and not stop:
                missed += 1
            else:
                right += 1
        table.append({"threshold": threshold, "judged": len(known), "false_stops": false_stops, "missed": missed,
                      "correct_pct": round(100.0 * right / len(known)) if known else None})
    out["thresholds"] = table
    out["current"] = current
    out["advice"] = advice(table, current) if known else None
    return out


def advice(table, current):
    """{kind: "keep" | "lower" | "raise", threshold}: the minimum that misses the fewest problems and, among those, gives the
    fewest false stops; the one in use is kept when it is as good."""
    if not table or not isinstance(current, (int, float)):
        return None
    best = min(table, key=lambda row: (row["missed"], row["false_stops"], abs(row["threshold"] - current)))
    now = next((row for row in table if row["threshold"] == current), None)
    if now is None or (now["missed"], now["false_stops"]) <= (best["missed"], best["false_stops"]):
        return {"kind": "keep", "threshold": current}
    return {"kind": "lower" if best["threshold"] < current else "raise", "threshold": best["threshold"],
            "false_stops": best["false_stops"], "missed": best["missed"]}
