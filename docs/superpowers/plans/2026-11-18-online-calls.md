# Fewer wasted online AI calls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The personal layer's weight is capped at 0.25 and an online «fine» is remembered 10 minutes instead of 6 hours.

**Architecture:** Two constants: `BLEND_MAX` in `backend/personal_layer.py`, `ONLINE_HOURS` → `ONLINE_MINUTES` in `backend/false_alarms.py`.

**Tech Stack:** Python 3.11, numpy; plain-script tests with `check()`.

**Spec:** `docs/superpowers/specs/2026-11-18-online-calls-design.md`

## Global Constraints

- Release 1.134.3 (patch); new check names start with `"1.134.3: "`.
- CHANGELOG with `/humanizer`; English in code and docs; `python3 frontend/build.py` after the VERSION bump.
- The person's false alarms stay until forgotten.

## Review Focus

1. An online «fine» learned 11 minutes ago no longer silences the same scene (Task 2 test).
2. A personal layer with many failed examples (500) still weighs 0.25 at most (Task 1 test).
3. Items saved by an older release with a 6-hour `until` keep their stored `until` (accepted: they expire within 6 h).
4. The person's own marks never expire (Task 2 test).
5. None other found.

---

### Task 1: personal layer weight at most 0.25

**Files:** Modify `backend/personal_layer.py:13,39-40,174-178`; Test `tests/backend/test_personal_layer.py:100-102`.

- [ ] **Step 1:** Replace the check at line 101-102 with
  `check("1.134.3: the weight: none below the minimum, then 0.25 at most however many failed examples", pl.weight_for(pl.MIN_FAILED - 1) == 0 and pl.weight_for(pl.MIN_FAILED) == 0.25 and pl.weight_for(500) == 0.25)`.
- [ ] **Step 2:** `python3 tests/backend/test_personal_layer.py` → FAIL on that check.
- [ ] **Step 3:** `BLEND_MAX = 0.25` (comment why: measured, a heavier layer made the monitor blind); fix the docstring at line 13.
- [ ] **Step 4:** run again → all pass.
- [ ] **Step 5:** commit.

### Task 2: an online «fine» kept 10 minutes

**Files:** Modify `backend/false_alarms.py:10,31,114`; Test `tests/backend/test_personal_layer.py` (end).

- [ ] **Step 1:** Add checks with a `FalseAlarms(tmpdir, np)`: `add(v, 80, "online", "a", "m")` at `now`; `match(v, 80, "m", now + 9 * 60)` is not None, `match(..., now + 11 * 60)` is None
  (`"1.134.3: an online «fine» silences the same scene for 10 minutes, then no more"`); `add(v2, 80, "person", "b", "m")` still matches a day later (`"... the person's marks stay"`). Read `add`'s signature first.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** `ONLINE_MINUTES = 10`, `until = now + ONLINE_MINUTES * 60`; docstring line 10.
- [ ] **Step 4:** run → PASS; `grep -rn ONLINE_HOURS` empty.
- [ ] **Step 5:** commit.

### Task 3: release 1.134.3

- [ ] VERSION 1.134.3; CHANGELOG section; CLAUDE.md section 2 points 4–5 and section 8 (AI monitor); `python3 frontend/build.py`; `ruff check .`; `python3 tests/backend/test_backend.py` (background) and `bash tests/run_all.sh --no-ui`; commit, push, PR, CI, merge.
