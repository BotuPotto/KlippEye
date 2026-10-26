#!/bin/bash
# Runs every browser test of the dashboard against frontend/klippeye_frontend.html (Playwright + Chromium).
# Usage: bash tests/ui/run_all.sh [output folder]   (screenshots and logs go to the output folder, default /tmp/klippeye-ui)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HTML="$HERE/../../frontend/klippeye_frontend.html"
OUT="${1:-/tmp/klippeye-ui}"
mkdir -p "$OUT"
TESTS="klipper_state_test icons_test editor_comment_test editor_undo_test editor_scroll_test configfiles_test tools_test endstops_test zoffset_test downloads_test desktop_test motion_test light_test live_test traffic_test title_icon_test settings_test software_test app_test access_test"
failed=0
i=0
for t in $TESTS; do
  i=$((i+1))
  if (cd "$HERE" && timeout 900 python3 "$t.py" "$HTML" "$OUT/$t" $((9910+i*3)) > "$OUT/$t.log" 2>&1) && ! grep -q "^FAIL " "$OUT/$t.log"; then
    echo "ok    $t"
  else
    echo "FAIL  $t  (log: $OUT/$t.log)"; grep -E "^FAIL" "$OUT/$t.log" | head -5
    failed=$((failed+1))
  fi
done
echo "$failed failed"
exit $((failed > 0))
