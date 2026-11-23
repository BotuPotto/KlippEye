# Install question and a real uninstall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The installer asks whether KlippEye is the Raspberry's main page (port 80) or a second one (port 8085), and `klippeye uninstall` removes everything KlippEye put on the Raspberry, its folders included, with no steps left to do by hand.

**Architecture:** Both changes live in `scripts/install.sh` (a new mode `--uninstall` next to `--undo`, a question before step 6) and `scripts/klippeye` (the `uninstall` command). The e2e test on the simulated Raspberry pins them.

**Tech Stack:** bash, Python standard library, `tests/e2e/e2e_test.py`.

**Spec:** `CLAUDE.md` section 8, «Owner's notes of 23 Nov», group 3. Branch `install-uninstall`, stacked on `calibration-markers-only` (PR #186): merge #186 first.

## Global Constraints

- Install runs as the normal user, never root; the service keeps the name `klippeye`; nothing may move, pause or restart the printer; while printing, Moonraker is not restarted (as `--undo` does today).
- Code, comments, docs in English; `docs/GUIDE.md` and `docs/GUIDA.md` change together; texts follow `/humanizer`.
- Non-interactive runs (no terminal on stdin, as in the e2e test and any script) never wait for an answer.
- Release 1.137.0: `VERSION`, a `CHANGELOG.md` section on top, `python3 frontend/build.py` and commit the page.
- New e2e check names start with `"1.137.0: "`.

## Review Focus

- A second run of `install.sh` with no option and no terminal must keep the current choice (KlippEye at port 80, or not), never flip it back to port 80.
- `uninstall` while a print runs: it must not restart Moonraker (as `--undo`), and must say so.
- `uninstall` run from inside the program folder it deletes: bash reads scripts as it goes, so the deletion must not cut the script.
- The data folder holds recordings and the person's labels: deleting it needs an explicit yes, and `--keep-data` keeps it.
- An answer typed at the question other than yes/no (empty, «s», «si») must lead to a clear default, not an error.

---

### Task 1: The question at install

**Files:** `scripts/install.sh` (options, step 6), `tests/e2e/e2e_test.py` (scenario `install`), `docs/GUIDE.md`, `docs/GUIDA.md` (install options).

- [ ] Options: `--web` (main page, port 80) and `--no-web` (second page, port 8085; today's option, kept). With neither: if stdin and stdout are a terminal, ask «Make KlippEye the Raspberry's main page (http://IP, without :8085)? [Y/n]» with the default = the current state on a re-run, «yes» on a first install; empty answer = default; `y`, `yes`, `s`, `si` = yes; `n`, `no` = no; anything else asks again. With no terminal: first install = main (today's behaviour), re-run = the current state. «First install» = the `klippeye` service file was not in `UNIT_DIR` before this run; «current state» = `web_front.py status` says KlippEye's site is in place.
- [ ] Second page chosen while KlippEye holds port 80: give port 80 back (`web_front.py restore`, as `--undo` does), say so.
- [ ] e2e checks: `"1.137.0: a second run with no option keeps the second page"` (install with `--no-web`, run again with no option, the site is not in place) and `"... --web puts KlippEye on port 80, --no-web gives it back"` (uses the fake nginx dir the scenario already has; if the e2e world has no nginx, test the decision with `KLIPPEYE_NGINX_DIR` pointed at a temp dir as other checks do, or report that it cannot be tested and why).
- [ ] Usage text at the top of `install.sh` and the guides' option list.
- [ ] Commit `1.137.0: the installer asks whether KlippEye is the main page`.

### Task 2: `klippeye uninstall`

**Files:** `scripts/install.sh` (mode `--uninstall`), `scripts/klippeye` (command and help), `tests/e2e/e2e_test.py` (scenario `undo`), guides, `CHANGELOG.md`, `VERSION`.

- [ ] `install.sh --uninstall [--yes] [--keep-data]`: first copies itself to a temp file and re-runs from there (the program folder is about to go); does everything `--undo` does; then, after `Delete the program folder <REPO> and the data folder <DATA> (settings, recordings, labels)? Type yes to delete:` (only «yes»; `--yes` skips the question; no terminal and no `--yes`: keep both and say how to delete them), removes `REPO` and, unless `--keep-data`, `DATA`. Refuses to delete a folder that is `/`, `$HOME`, or does not contain what it should (`REPO` without `backend/klippeye_backend.py`, `DATA` not named `klippeye` or `klippeye_data`).
- [ ] `klippeye uninstall` runs it (`--yes`, `--keep-data` passed through); help line `klippeye uninstall [--keep-data]   take KlippEye off this Raspberry, its folders included`; `undo-install` (and `annulla`) keep working and keep their old meaning, out of the help.
- [ ] e2e checks in the `undo` scenario: `"1.137.0: uninstall --yes removes services, commands, the update manager entry and both folders"`, `"... --keep-data keeps the data folder"`, `"... with no terminal and no --yes nothing is deleted"`.
- [ ] Guides: the «uninstall» part says `klippeye uninstall` and that nothing is left to do by hand. CHANGELOG 1.137.0 for both tasks, `VERSION` 1.137.0, rebuild the page.
- [ ] Run `python3 tests/e2e/e2e_test.py -k install` and `-k undo` (needs `python3 tests/e2e/setup.py` once; if it cannot run here, say so), `bash -n scripts/install.sh scripts/klippeye`, `shellcheck` if installed, `ruff check .`.
- [ ] Commit `1.137.0: klippeye uninstall takes everything off`.
