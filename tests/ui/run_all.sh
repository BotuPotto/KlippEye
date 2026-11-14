#!/bin/bash
# Runs every browser test of the dashboard against frontend/klippeye_frontend.html (Playwright + Chromium).
# Usage: bash tests/ui/run_all.sh [output folder]   (screenshots and logs go to the output folder, default /tmp/klippeye-ui)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HTML="$HERE/../../frontend/klippeye_frontend.html"
OUT="${1:-/tmp/klippeye-ui}"
mkdir -p "$OUT"
TESTS="klipper_state_test icons_test configfiles_test tools_test endstops_test zoffset_test downloads_test desktop_test motion_test light_test live_test traffic_test title_icon_test settings_test software_test recordings_test camcal_test functions_test notifications_test setup_test back_test ai_alarm_test app_test access_test ai_services_test print_info_test motion_steps_test tune_test macros_test twist_test console_test camera_full_test bedmesh_test lights_test notify_test cfgview_test gcodeview_test editor_test history_test temps_test queue_test devices_test timelapse_test spoolman_test cameras_test gcodeviewer_test layout_test colors_test narrow_test camera_settings_test printers_test update_notice_test console_input_test macro_prompt_test schedule_test maintenance_test peripherals_test shaper_test config_versions_test print_checks_test mmu_test afc_test web_address_test a11y_test mqtt_test local_model_test monitor_card_test ai_backups_test live_test"
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
