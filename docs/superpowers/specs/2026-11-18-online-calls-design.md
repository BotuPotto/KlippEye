# Fewer wasted online AI calls, no blind monitor (design)

## Why

With a close camera the base local model scores almost every look 80–90 on fine prints, so it is «in doubt» all the
time. The monitor then asks the online AI about every 90 s (~40 calls an hour) and the free quotas (Groq ~60–100 calls
a day with pictures, Gemini 3.8 Flash 20 a day) run out halfway through a print. Raising the thresholds makes the
monitor miss failures. The owner wants the fewest false calls, real failures asked about quickly, and never a monitor
that stays blind after a false alarm.

## Measured (the owner's 19 judged recordings: 6 h of fine printing, 8 failures, 7 measurable)

| Rules | false calls/h | failures asked about | median delay |
|---|---|---|---|
| today, false-alarm memory off | 18.9 | 6 | 145 s |
| today (memory: online «fine» kept 6 h) | 4.7 | 4 | 312 s |
| personal layer weight 0.25 + memory 6 h | 2.3 | 4 | 101 s |
| personal layer weight 0.25 + memory 10 min | 3.3 | 4 | 101 s (worst 230 s) |
| personal layer weight 0.4 | 0.7–1.0 | 3–4 | 280–340 s |

Simulated (`scratchpad` scripts, not kept): leave-one-print-out personal layer, the online AI assumed right.
A per-print relative threshold was also tried and gave nothing more.

## Goals, non-goals, anti-goals

- Goal: fewer online calls on fine prints, failures still asked about within about 2 minutes.
- Non-goals: new settings, new rules in `_local_look`, a new model.
- Anti-goal: a scene the online AI called fine silencing the monitor for the rest of the print.

## Approaches (chosen: B)

- A. A per-print relative threshold and a growing pause after each «fine»: no gain measured; the growing pause makes
  the monitor blind. Dropped.
- **B. Two constants** (chosen): the personal layer's weight capped at 0.25; an online «fine» remembered 10 minutes.
- C. A heavier model on the phone: does not fix an unfamiliar scene; needs the phone awake all print. Dropped.

## Design

1. `backend/personal_layer.py`: `BLEND_MAX` 0.6 → 0.25, so the weight is 0.25 from `MIN_FAILED` failed examples on
   (above it the monitor went blind in the simulation). `weight_for` stays (it returns BLEND_MIN = BLEND_MAX).
2. `backend/false_alarms.py`: `ONLINE_HOURS = 6` → `ONLINE_MINUTES = 10`; docstring updated. The person's marks are
   unchanged (kept until forgotten).
3. One test per constant's behaviour (personal weight never above 0.25; an online «fine» expires after 10 minutes).
4. VERSION patch, CHANGELOG, the guide's lines on the personal layer and the false-alarm memory if they give numbers,
   CLAUDE.md section 2.
5. Re-run the simulation with the retrained base model when it exists; adjust if it disagrees.

## Left to the builder

Test placement; wording of the CHANGELOG.
