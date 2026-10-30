#!/bin/bash
# Runs the automatic tests of KlippEye. Usage: bash tests/run_all.sh [--quick] [--no-ui]
#   backend   tests/backend/test_backend.py   (Flask test client, real OpenCV on synthetic pictures, fake Moonraker)
#   notifier  tests/notifier/                 (pure logic + integration with a fake Moonraker and a fake Google)
#   app CI    tests/app/app_ci_test.py        (the steps of the Android build workflow, with fake Android tools)
#   frontend  rebuilds frontend/klippeye_frontend.html from frontend/src and checks it is the committed one
#   i18n      frontend/tools/i18n.py check: every text of the dashboard has its Italian translation
#   paths     tests/test_no_fixed_paths.py: no fixed home folder (/home/<user>) in the program
#   ui        tests/ui/run_all.sh             (browser tests, Playwright + Chromium; skipped with --no-ui)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
QUICK=""; UI=1
for a in "$@"; do case "$a" in --quick) QUICK="--quick";; --no-ui) UI=0;; esac; done
failed=0
step() {
  local name="$1"; shift
  echo; echo "=== $name"
  local log; log="$(mktemp)"
  if "$@" 2>&1 | tee "$log"; [ "${PIPESTATUS[0]}" = 0 ]; then echo "=== ok"
  else
    echo "=== FAILED"; failed=$((failed+1))
    if [ -n "${GITHUB_ACTIONS:-}" ]; then   # readable on the pull request page without downloading the logs
      lines="$(grep -E "^FAIL |Traceback|Error" "$log" | head -4 | cut -c1-500 | tr '\n' ' ')"
      echo "::error title=$name::${lines:-exit code without FAIL lines, see the log}"
    fi
  fi
  rm -f "$log"
}
step "frontend build is reproducible" bash -c "cp '$ROOT/frontend/klippeye_frontend.html' /tmp/klippeye-committed.html && python3 '$ROOT/frontend/build.py' /tmp/klippeye-rebuilt.html >/dev/null && cmp /tmp/klippeye-committed.html /tmp/klippeye-rebuilt.html"
step "dashboard translations" python3 "$ROOT/frontend/tools/i18n.py" check
step "no fixed home folders" python3 "$HERE/test_no_fixed_paths.py"
step "backend" python3 "$HERE/backend/test_backend.py" $QUICK
step "notifier: logic" python3 "$HERE/notifier/test_watcher.py"
step "notifier: integration" python3 "$HERE/notifier/test_integration.py" "$ROOT/frontend/klippeye_frontend.html" 9701
step "app CI" python3 "$HERE/app/app_ci_test.py"
step "release tags" python3 "$HERE/app/release_test.py"
[ "$UI" = 1 ] && step "ui" bash "$HERE/ui/run_all.sh"
echo; echo "$failed group(s) failed"
exit $((failed > 0))
