#!/bin/bash
# Runs every browser test of the dashboard against frontend/klippeye_frontend.html (Playwright + Chromium).
# Usage: bash tests/ui/run_all.sh [output folder]   (screenshots and logs go to the output folder, default /tmp/klippeye-ui)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HTML="$HERE/../../frontend/klippeye_frontend.html"
OUT="${1:-/tmp/klippeye-ui}"
mkdir -p "$OUT"
# Every *_test.py of this folder runs (a new test is picked up by itself; before 1.155.0 a hand-written list left five out).
# SKIP: tests that must not run here, with the reason next to each name. None for now.
SKIP=""
TESTS=""
for f in "$HERE"/*_test.py; do
  t="$(basename "$f" .py)"
  case " $SKIP " in *" $t "*) continue;; esac
  TESTS="$TESTS $t"
done
failed=0
i=0
for t in $TESTS; do
  i=$((i+1))
  if (cd "$HERE" && timeout 900 python3 "$t.py" "$HTML" "$OUT/$t" $((9910+i*3)) > "$OUT/$t.log" 2>&1) && ! grep -q "^FAIL " "$OUT/$t.log"; then
    echo "ok    $t"
  else
    echo "FAIL  $t  (log: $OUT/$t.log)"; grep -E "^FAIL" "$OUT/$t.log" | head -5
    if [ -n "${GITHUB_ACTIONS:-}" ]; then   # annotations: readable on the pull request page without downloading the logs
      lines="$(grep -E "^FAIL |Traceback|Error" "$OUT/$t.log" | head -3 | cut -c1-600 | tr '\n' ' ' )"
      echo "::error title=$t::${lines:-exit code without FAIL lines, see the log}"
    fi
    failed=$((failed+1))
  fi
done
echo "$failed failed"
exit $((failed > 0))
