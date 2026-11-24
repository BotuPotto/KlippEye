# Audit fixes implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. One task = one PR.

**Goal:** Fix every Must and Should finding of `docs/audits/2026-11-24-full-audit.md`, in the order of its section 8.

**Architecture:** One PR per task, each from `origin/main`, following CLAUDE.md section 4. The proof command of a finding in `docs/audits/2026-11-24-proofs/` is the failing test (turn it into a `check(...)` named `"<release>: ..."`).

**Spec:** `docs/audits/2026-11-24-full-audit.md` (findings, with failing cases and proofs), `CLAUDE.md`.

## Global Constraints

- Owner's rulings (24 Nov): the automatic pause/cancel acts on the local model alone only when the online AI is switched off or every online service has used its quota; otherwise it needs the online verdict. `android/chiave/vzbot.p12` and its GitHub secret can go.
- Versions from 1.137.0 on, in the order of the table; one section per PR in `CHANGELOG.md` (/humanizer); 9 dashboard languages; `python3 frontend/build.py` committed; `ruff check .`; tests of the area; no change to the printer's behaviour that was not asked for.
- Never push to main; merge a PR only when its CI is fully green, in order.

## Tasks (section 8 of the report)

| # | PR | Closes |
|---|---|---|
| 1 | Dashboard: nothing moves or restarts the printer unseen | 20, 21, 17, 18; 57, 58, 63, 64, 65 |
| 2 | Calibration: no moves during a print, right Z guess | 6; 38 |
| 3 | Scheduled prints: a late print is missed, not started | 12; 87 |
| 4 | Notifier: queue prints, announced automatic pauses (+ owner's ruling on local-only pauses) | 13; 49, 50 |
| 5 | Install and repair scripts | 14, 15; 51, 52, 53 |
| 6 | Printer macros file: Klipper always starts | 11; 45 |
| 7 | False-alarm memory and personal layer files | 4; 29-33, 72 |
| 8 | Dashboard settings sync between devices | 16 |
| 9 | Config editor: never overwrite newer text | 19; 66, 67 |
| 10 | Access and network | 8, 9, 10; 40-44, 86 |
| 11 | Monitor loop: no crash, no hang, says when it is blind | 1, 2, 3; 28, 82 |
| 12 | Online AI chain | 5; 34-37 |
| 13 | Training chain | 22; 27, 70, 79, 83 |
| 14 | Calibration fit prior (needs measurement Q2 on camera.json) | 7; 39, 73 |
| 15 | Android app (+ remove vzbot.p12) | 24, 25, 26, 69 |
| 16 | Backend rest: MQTT and monitor settings | 46, 47, 48 |
| 17 | Dashboard small fixes | 23, 54-56, 59-62, 68, 71 |
| 18 | Look | 74-78 |
| 19 | Tests and CI | 80, 81, 84, 85 |

Each task's steps: read its findings in the report; write the failing test from the proof; fix; bump `VERSION` + CHANGELOG; rebuild the page; run `ruff` and the area's tests; push, open the PR (what, why, measured, tests).
