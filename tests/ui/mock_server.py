"""Mock Moonraker + KlippEye backend used ONLY to run the dashboard headless for A/B tests."""
import io, json, sys, time, copy, threading, os, ast, math, re
from flask import Flask, request, jsonify, Response, send_file
from PIL import Image

HTML = sys.argv[1]
PORT = int(sys.argv[2])
app = Flask(__name__)
NOW = 1760000000  # fixed epoch so file dates are deterministic

def klippeye_default_info():
    return {"name": "klippeye", "configured_type": "git_repo", "detected_type": "git_repo", "repo_detected": True, "remote_alias": "origin", "branch": "main",
            "owner": "prova", "repo_name": "klippeye", "remote_url": "https://github.com/prova/klippeye.git", "recovery_url": "https://github.com/prova/klippeye.git",
            "version": "v0.0.0-3", "remote_version": "v0.0.0-3", "rollback_version": "v0.0.0-3", "current_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            "remote_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678", "is_dirty": False, "is_valid": True, "detached": False, "commits_behind": [], "commits_behind_count": 0,
            "git_messages": [], "pristine": True, "corrupt": False, "warnings": [], "anomalies": [], "channel": "dev"}

def default_history():
    """Moonraker's [history] (1.42): the jobs newest first, timed from the real clock (the page draws the last 14 days): the
    Benchy a minute ago, the others whole days before, so each falls on its own day whatever the hour."""
    now = time.time()
    day = 86400
    thumbs = [{"width": 32, "height": 32, "size": 100, "relative_path": ".thumbs/thumb-32x32.png"}, {"width": 300, "height": 300, "size": 900, "relative_path": ".thumbs/thumb-300x300.png"}]
    def job(uid, name, status, ago, duration, filament, exists=True):
        start = now - ago
        meta = {"size": 123456, "slicer": "OrcaSlicer", "slicer_version": "2.1.1", "layer_height": 0.2, "object_height": 48.0, "estimated_time": duration * 1.1,
                "filament_total": filament * 1.05, "filament_type": "PLA", "filament_name": "Generic PLA", "thumbnails": thumbs}
        return {"job_id": uid, "user": "_TRUSTED_USER_", "filename": name, "exists": exists, "status": status, "start_time": start,
                "end_time": start + duration + 300, "print_duration": duration, "total_duration": duration + 300, "filament_used": filament, "metadata": meta, "auxiliary_data": []}
    return [job("000006", "Benchy_0.2mm_PLA.gcode", "completed", 60, 7000, 4200.0),
            job("000005", "Calibration_cube_long_filename_for_wrapping_test.gcode", "cancelled", 1 * day, 1200, 800.0),
            job("000004", "Vase_mode.gcode", "completed", 2 * day, 3600, 9000.0),
            job("000003", "Bracket.gcode", "klippy_shutdown", 3 * day, 5400, 3000.0),
            job("000002", "Old_deleted.gcode", "completed", 5 * day, 1800, 1500.0, exists=False),
            job("000001", "Test/Nested_part.gcode", "completed", 20 * day, 600, 500.0)]

def default_history_totals(jobs):
    return {"total_jobs": len(jobs), "total_time": sum(j["total_duration"] for j in jobs), "total_print_time": sum(j["print_duration"] for j in jobs),
            "total_filament_used": sum(j["filament_used"] for j in jobs), "longest_job": max(j["total_duration"] for j in jobs), "longest_print": max(j["print_duration"] for j in jobs)}

# 1.43: more heaters and sensors (with extra_temps); the last one starts with _ and stays hidden
EXTRA_TEMPS = ["heater_generic chamber_heater", "temperature_sensor chamber", "temperature_sensor raspberry_pi", "temperature_fan mcu_fan", "temperature_sensor _internal"]
def default_extra_temps():
    return {"heater_generic chamber_heater": {"temperature": 38.0, "target": 45.0, "power": 0.6}, "temperature_sensor chamber": {"temperature": 36.5},
            "temperature_sensor raspberry_pi": {"temperature": 52.3}, "temperature_fan mcu_fan": {"temperature": 41.0, "target": 40.0, "speed": 0.5},
            "temperature_sensor _internal": {"temperature": 30.0}}

def default_state():
    history = default_history()
    return {"history_made": time.time(),
        "power_on": False, "power_devices": [{"device": "printer", "status": "on", "locked_while_printing": True, "type": "tplink_smartplug", "is_shutdown": False},
                                              {"device": "led_strip", "status": "off", "locked_while_printing": False, "type": "gpio", "is_shutdown": False},
                                              {"device": "_hidden_relay", "status": "off", "locked_while_printing": False, "type": "gpio", "is_shutdown": False}],
        "power_log": [],
        "extra_devices": False, "pins": {"relay": 0.0, "_secret": 0.0}, "sensors": {"runout": {"filament_detected": True, "enabled": True}, "encoder": {"filament_detected": False, "enabled": True}},   # 1.45
        "spoolman_on": False, "spoolman_connected": True, "spool_id": 2, "spool_log": [],   # 1.47: Spoolman through Moonraker
        "spools": [{"id": 1, "filament": {"id": 1, "name": "PLA Basic Black", "material": "PLA", "color_hex": "1a1a1a", "diameter": 1.75, "weight": 1000, "vendor": {"name": "Bambu"}},
                    "remaining_weight": 120.0, "initial_weight": 1000, "remaining_length": 40200.0, "used_weight": 880.0, "location": "Shelf", "last_used": "2026-10-20T10:00:00Z", "archived": False},
                   {"id": 2, "filament": {"id": 2, "name": "PETG Orange", "material": "PETG", "color_hex": "f07020", "settings_extruder_temp": 235, "settings_bed_temp": 75, "diameter": 1.75, "weight": 1000, "vendor": {"name": "Sunlu"}},
                    "remaining_weight": 640.0, "initial_weight": 1000, "remaining_length": 211000.0, "used_weight": 360.0, "location": "", "last_used": "2026-11-03T10:00:00Z", "archived": False},
                   {"id": 3, "filament": {"id": 3, "name": "ASA White", "material": "ASA", "color_hex": "f4f4f4", "diameter": 1.75, "weight": 750},
                    "remaining_weight": 750.0, "initial_weight": None, "remaining_length": 0, "used_weight": 0, "location": "Dry box", "last_used": None, "archived": False}],
        "timelapse_on": False, "timelapse_macro": True, "timelapse_frames": 0, "timelapse_log": [],   # 1.46: moonraker-timelapse
        "timelapse_settings": {"enabled": True, "mode": "layermacro", "camera": "", "snapshoturl": "http://localhost:8080/?action=snapshot", "gcode_verbose": False, "parkhead": False, "parkpos": "back_left",
                               "park_custom_pos_x": 10.0, "park_custom_pos_y": 10.0, "park_custom_pos_dz": 0.0, "park_travel_speed": 100, "park_retract_speed": 15, "park_extrude_speed": 15,
                               "park_retract_distance": 1.0, "park_extrude_distance": 1.0, "hyperlapse_cycle": 30, "autorender": True, "constant_rate_factor": 23, "output_framerate": 30,
                               "pixelformat": "yuv420p", "time_format_code": "%Y%m%d_%H%M", "extraoutputparams": "", "variable_fps": False, "targetlength": 10, "variable_fps_min": 5,
                               "variable_fps_max": 60, "rotation": 0, "flip_x": False, "flip_y": False, "duplicatelastframe": 0, "previewimage": True, "saveframes": False,
                               "wait_for_snapshot": False, "stream_delay_compensation": 0.05, "park_time": 0.1, "fw_retract": False, "blockedsettings": ["snapshoturl"]},
        "timelapse_files": {"timelapse_Benchy_20261103_2210.mp4": NOW - 3600, "timelapse_Benchy_20261103_2210.jpg": NOW - 3600, "timelapse_Vase_20261101_1010.mp4": NOW - 200000},
        "queue_on": False, "queue": [], "queue_state": "ready", "queue_log": [], "queue_ids": 0,   # 1.44: Moonraker's [job_queue] (queue_on False: 404)
        "extra_temps": False, "extra_temp_values": default_extra_temps(),
        "history": history, "history_totals": default_history_totals(history), "history_log": [], "history_mode": "ok",  # ok | missing (no [history]: 404)
        "printing": False, "paused": False,
        "schedule": [], "schedule_log": [],   # 1.70: scheduled prints
        "webhooks": "ready", "webhooks_msg": "",
        "homed": "xyz",
        "light": 0,
        "ext_t": 215.3, "ext_target": 220, "bed_t": 60.1, "bed_target": 60,
        "gcode_log": [],           # received scripts
        "calib_selected": [],         # 1.33: the old "Calibrations" choice (macros_test: it becomes a group)
        "long_macro": False,        # adds a macro with a very long name and parameters (the parameter form must fit its buttons)
        "ai_key_ok": True,
        # 1.32: the Tune card and the leveling tools
        "speed_factor": 1.1, "extrude_factor": 0.95,
        "tune": {"pa": 0.04, "smooth": 0.04, "vel": 300.0, "accel": 3000.0, "scv": 5.0, "mcr": 0.5, "rl": 0.8, "rs": 35.0, "ue": 0.0, "us": 30.0},
        "shaper_files": True,   # 1.80: SHAPER_CALIBRATE left its files in /tmp (x and y)
        "has_retraction": True, "old_limits": False,    # old_limits: Klipper before 2024 (max_accel_to_decel, no minimum cruise ratio)
        "has_bed_screws": False, "has_level": False,    # [bed_screws]; [z_tilt] / [quad_gantry_level] (by z_kind)
        "level_delay": 1.2, "level_busy_until": 0.0, "level_applied": False,
        "bs": {"is_active": False, "state": None, "current_screw": 0, "accepted_screws": 0}, "bs_adjusted": False,
        "twist_kind": "cartographer",   # 1.33.1: "klipper": Klipper's own AXIS_TWIST_COMPENSATION_CALIBRATE (paper test), no Cartographer
        "twist_y": False,               # [axis_twist_compensation] has the Y options (calibrate_start_y...)
        "mp": {"is_active": False, "z_position": 0.0, "z_position_lower": None, "z_position_upper": None}, "mp_points": 0, "mp_axis": "X",
        "extra_lights": False,          # 1.37: also a white+RGB neopixel STRIP and a PWM output_pin caselight
        "strip": [0.0, 0.0, 0.0, 0.0], "caselight": 0.0,
        "z_kind": "bed",            # 1.31: "bed" (z_tilt) or "toolhead" (quad_gantry_level) in Klipper's settings
        "print_objects": [],        # 1.30: exclude_object objects of the print ([{name, center, polygon}])
        "excluded": [],             # their names excluded with EXCLUDE_OBJECT
        "ai_cfg": None,             # ai.json of the backend (1.27, ai_services); None: a Groq key when ai_key_ok
        "ai_posts": [],             # the bodies of POST /api/ai/config
        "ai_models_fail": "",       # a service whose list of models cannot be read
        "ai_model_reads": [],       # the services whose models were asked for
        "deleted": [], "delete_error": "",
        "detector_status": "scanning",
        "has_analysis": True,
        "analysis_action": "CONTINUA",
        "ai_answer": None, "ai_answers": [],   # the person's answers to the alarm (/api/print/last_analysis/answer, 1.25)
        "review": None, "review_answers": [],
        "personal_posts": [],       # 1.107: what the page sent to /api/local_model/personal*
        "local_model": {"available": False, "error": ""},   # 1.106: GET /api/local_model  # 1.103: the print waiting for «how did it go?» and the answers
        "update_channel": "dev",   # the channel of [update_manager klippeye] (None: not listed)
        "channel_posts": [],
        "mesh": True,
        # --- printer capabilities / tools (new features)
        "has_screws": True, "has_twist_section": True, "z_pin": "probe:z_virtual_endstop", "z_apply": "probe",
        "tool_delay": 1.2,          # seconds a screws tilt / axis twist run "takes"
        "tool_error": "",           # non-empty: the command fails with this message
        "tool_timeout_502": False,  # answer like the backend proxy does after 10 s on a long command
        "screws": None,             # last screws_tilt_adjust status
        "pending": {},              # configfile.save_config_pending_items
        "z_offset": 0.0,
        "console_extra": [],
        "caps_down": False,         # configfile / gcode help unavailable (klipper not ready)
        "endstops": {"x": "open", "y": "open", "z": "open"}, "probe_triggered": False, "endstops_error": "", "has_probe": True,
        # --- config files tree (file manager)
        "cfg": default_cfg_tree(),
        "cfg_error": "",            # non-empty: every change to the config tree fails with this message (HTTP 403)
        "cfg_delay": 0.0,           # seconds every change takes
        # --- case light (macros luci_on / luci_off, variable VAR_LUCI.stato_luci)
        "light_exec_delay": 0.0,    # seconds the macro needs before the variable changes
        "light_block": True,        # /api/gcode answers only when Klipper is done (Moonraker's script endpoint does)
        "light_read_delay": 0.0,    # seconds a VAR_LUCI read takes; the value is taken when the request ARRIVES (stale if slow)
        "light_fail": False,        # the macro runs but the variable never changes
        "light_cmds": [],           # (script, time) of every luci_* command received
        "pm_macros": {}, "pm_wraps": [], "pm_posts": [],   # KlippEye's own macros (/api/printer-macros)
        "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "has_token": False, "click": ""},   # notifier.json (/api/notifications)
        "firebase_on": False, "ntfy_posts": [], "ntfy_tests": 0, "ntfy_test_fail": "",
        "extra_commands": [],       # commands Klipper knows besides the usual ones (a macro KlippEye made)
        "light_reads": 0,
        # --- Klipper / Moonraker / Raspberry outages and restarts
        "disconnected": False,      # Moonraker has no Klipper: every /printer/* answers 503
        "moonraker_down": False,    # Moonraker (or the whole Raspberry) does not answer: the backend's proxy says 502
        "host_off": False,          # the Raspberry was shut down
        "restart_lag": 0.8,         # seconds between the restart request and Klipper going away
        "restart_down": 2.0,        # seconds Klipper stays "disconnected"
        "restart_startup": 1.5,     # seconds it stays in "startup"
        "restart_result": "ready",  # what it is afterwards: ready | error | shutdown
        "restart_result_msg": "",
        "restart_refuse": 0,        # HTTP status the restart endpoints answer with instead of restarting (0: they work)
        "gcode_refuse": False,      # RESTART / FIRMWARE_RESTART sent as G-code fail too
        "reboot_down": 4.0,         # seconds the whole machine does not answer after /machine/reboot
        "services": default_services(),
        # --- KlippEye backend release 1.0: /api/version, thresholds of the AI monitor, update manager entry "klippeye"
        "brain": "ok",              # ok | old (no /api/version, no /api/backend/*: a backend before release 1.0)
        "brain_down": False,        # the backend does not answer at all (restarting)
        "backend_release": "1.0.0", "brain_started": 1760000000,
        "brain_restart_s": 2.5,     # seconds the backend is away when it restarts
        "brain_cfg": None,          # {key: value} of the thresholds (None: the usual ones)
        "recordings": [],           # session.json of the recorded prints (backend/recorder.py), oldest first
        "rec_frames": {},           # {id: [frame lines]}
        "rec_status": "waiting for a print",
        "rec_posts": [],            # [(what, id, body)] labels and deletions the page sent
        "alerts": [],               # the alert history (/api/print/alerts/history), newest first
        "measure": {"state": "idle"},
        "measure_starts": 0,
        "measure_bodies": [],       # the bodies of POST /api/recordings/measure
        "detector_extra": {},       # more stats of /api/print/detector/status (check_ms, cpu_percent)
        "brain_cfg_saved": False, "brain_cfg_log": [], "brain_cfg_fail": 0,  # brain_cfg_fail: HTTP status the next POSTs answer with (0: they work)
        "brain_running": True, "brain_has_cv2": True,
        "app_apk": None,            # what /api/app/version offers: None (nothing published) or {"available": ..., version, code, size, sha256, built, url} / {"available": False, "reason": ...}
        "app_apk_status": 200,      # HTTP status of /api/app/version (404: a backend that does not know apps; 500: broken)
        "app_apk_hits": 0, "app_apk_downloads": 0,
        "logos": [],                # files of the logos/ folder the backend lists in /api/logos (e.g. ["voron.svg"])
        "klippeye_info": klippeye_default_info(),   # Moonraker's entry for the update manager component "klippeye" (None: Moonraker does not know it)
        "klippeye_incoming": [],       # commits that appear in "commits_behind" once "Controlla" (refresh) is pressed
        "klippeye_new_release": "1.0.1", "klippeye_old_release": "1.0.0",
        "update_log": [],           # (action, component) of every /machine/update/* POST
        "update_error": "",         # non-empty: upgrade / rollback / recover are refused with this message (HTTP 500)
        "update_restart": "yes",    # yes: the backend restarts as Moonraker would; no: the work is done but the backend is not restarted
        "update_delay": 0.0,        # seconds before an update / rollback / recover answers
        "service_error": "",        # non-empty: service actions fail with this message (HTTP 400)
        "actions": [],              # (path, query) of every /machine/services|reboot|shutdown + restart request
        # --- Moonraker database (dashboard settings, notification service status) and the printer's webcams
        "db": {},                   # {"namespace/key": value}
        "db_mode": "ok",            # ok | no_route (the backend does not pass /server/database on: Flask 404 page) | refuse (403) | down (502)
        "db_log": [],               # (method, namespace, key) of every request
        "webcams": [{"name": "KlippEye", "uid": "u-klippeye", "source": "database", "service": "webrtc-camerastreamer", "enabled": True, "stream_url": "/webcam/webrtc", "snapshot_url": "/webcam/snapshot", "flip_horizontal": False, "flip_vertical": False, "target_fps": 15},
                    {"name": "Piatto", "uid": "u-piatto", "source": "database", "service": "mjpegstreamer", "enabled": True, "stream_url": "/webcam2/?action=stream", "snapshot_url": "/webcam2/?action=snapshot", "flip_horizontal": True, "flip_vertical": False, "target_fps": 10},
                    {"name": "Go2rtc", "uid": "u-go2rtc", "source": "config", "service": "webrtc-go2rtc", "enabled": True, "stream_url": "/go2rtc/api/webrtc?src=cam", "snapshot_url": "", "flip_horizontal": False, "flip_vertical": False, "target_fps": 15}],
        "webcam_log": [],           # 1.59: ("post" | "delete", body or uid)
        "peers": {},                # 1.61: other printers, by host: what their KlippEye answers ({"ok": False, "error": ...} or a summary)
        "peek_log": [],
    }

def default_services():
    return {"klipper": ["active", "running"], "klipper_mcu": ["active", "running"], "moonraker": ["active", "running"],
            "crowsnest": ["active", "running"], "sonar": ["inactive", "dead"], "KlipperScreen": ["failed", "failed"]}

CFG_FILES = [("printer.cfg", 52000), ("moonraker.conf", 4100), ("printer-20240101.cfg", 100), ("crowsnest.conf", 900),
             ("crowsnest.conf.bak", 900), ("macros/park.cfg", 1200), ("macros/led.cfg", 800), ("img/bed.png", 2048), ("notes.txt", 77), ("README", 10)]
def default_cfg_tree():
    files = {p: {"size": s, "modified": NOW - 1000 * i, "content": None} for i, (p, s) in enumerate(CFG_FILES)}
    return {"dirs": {"macros": NOW - 5000, "img": NOW - 7000}, "files": files}
S = default_state()

FANS = {
    "fan": {"speed": 0.5},
    "fan_generic Aux_Fan": {"speed": 0.3},
    "heater_fan hotend_fan": {"speed": 1.0},
    "controller_fan drivers_fan": {"speed": 0.6},
}
CONFIG = {
    "fan_generic Aux_Fan": {"max_power": "0.8"},
    "gcode_macro PARK_TEST": {"gcode": "G28\nG1 X{params.X|default(100)} Y{params.Y|default(50)}", "description": "Park test"},
    "gcode_macro SHAPER_CALIBRATE": {"gcode": "SHAPER", "description": "Shaper"},
    "gcode_macro CLEAN_NOZZLE": {"gcode": "G1 X0", "description": "Clean"},
    "gcode_macro _HIDDEN": {"gcode": "", "description": ""},
    # the case light of the VzBot: a neopixel strip driven by klipper-led_effect effects, switched by two macros
    "gcode_macro VAR_LUCI": {"variable_stato_luci": "1", "gcode": ""},
    "gcode_macro LUCI_ON": {"gcode": "SET_LED_EFFECT EFFECT=IDLE REPLACE=1"},
    "gcode_macro LUCI_OFF": {"gcode": "stop_led_effects"},
    "neopixel LUCI": {"pin": "PE6", "chain_count": "60", "color_order": "GRB"},
    "led_effect IDLE": {"leds": "\nneopixel:LUCI", "autostart": "false"},
}
OBJECTS = ["webhooks","print_stats","toolhead","extruder","heater_bed","fan","fan_generic Aux_Fan","heater_fan hotend_fan",
           "controller_fan drivers_fan","virtual_sdcard","display_status","gcode_move","bed_mesh","configfile",
           "gcode_macro PARK_TEST","gcode_macro SHAPER_CALIBRATE","gcode_macro CLEAN_NOZZLE","gcode_macro VAR_LUCI",
           "gcode_macro LUCI_ON","gcode_macro LUCI_OFF","neopixel LUCI","led_effect IDLE",
           "mcu","mcu EBBCan"]

def mesh_rows(shift=0.0, n=7):
    rows = []
    for r in range(n):   # row 0 = the front (Y min), as Klipper lists them; the back right corner is the highest
        rows.append([round(0.02*((c-3)**2)/9 + 0.015*(r-3) + 0.005*((r*c)%3) + shift, 4) for c in range(n)])
    return rows

def mesh_status():
    """Klipper's bed_mesh object (1.36: profiles with their points, mesh_min / mesh_max, loaded / cleared)."""
    m = S.get("mesh_profiles")
    if m is None:
        m = S["mesh_profiles"] = {"default": mesh_rows(), "adaptive": mesh_rows(0.01, 5)} if S["mesh"] else {}
        S["mesh_active"] = "default" if S["mesh"] else ""
    active = S.get("mesh_active", "")
    profiles = {name: {"points": pts, "mesh_params": {"min_x": 30.0, "max_x": 320.0, "min_y": 30.0, "max_y": 320.0, "x_count": len(pts[0]), "y_count": len(pts)}} for name, pts in m.items()}
    rows = m.get(active) or S.get("mesh_current")
    if not active and not S.get("mesh_current"):
        return {"profile_name": "", "mesh_min": [0, 0], "mesh_max": [0, 0], "probed_matrix": [[]], "mesh_matrix": [[]], "profiles": profiles}
    rows = rows or mesh_rows()
    fine = [[round(v, 4) for v in row for _ in (0, 1)][:2 * len(row) - 1] for row in rows for _ in (0, 1)][:2 * len(rows) - 1]
    return {"profile_name": active, "mesh_min": [30.0, 30.0], "mesh_max": [320.0, 320.0], "probed_matrix": rows, "mesh_matrix": fine, "profiles": profiles}

def settings_now():
    out = dict(CONFIG)
    out["stepper_z"] = {"endstop_pin": S["z_pin"], "position_max": 300}
    out["stepper_x"] = {"position_min": -5, "position_max": 350}
    out["stepper_y"] = {"position_max": 350}
    out["extruder"] = dict(out.get("extruder") or {}, max_temp=285, nozzle_diameter=0.4)
    out["heater_bed"] = dict(out.get("heater_bed") or {}, max_temp=110)
    if S.get("extra_temps"):
        out["heater_generic chamber_heater"] = {"max_temp": 70}
    if S["twist_kind"] == "cartographer":
        out["cartographer"] = {"serial": "/dev/serial/by-id/usb-cartographer"}
    out["printer"] = {"kinematics": "corexy", "max_velocity": 300.0, "max_accel": 3000.0, "square_corner_velocity": 5.0}   # 1.31: the Motion card guesses what Z moves from these
    if S["old_limits"]:
        out["printer"]["max_accel_to_decel"] = 1500.0
    else:
        out["printer"]["minimum_cruise_ratio"] = 0.5
    out["extruder"] = dict(out["extruder"], pressure_advance=0.05, pressure_advance_smooth_time=0.04)
    if S.get("shaper_files"):
        out["input_shaper"] = {"shaper_type_x": "mzv", "shaper_freq_x": 52.4, "shaper_type_y": "ei", "shaper_freq_y": 55.0}
    out["resonance_tester"] = {"accel_chip": "adxl345", "probe_points": "150, 150, 20", "max_freq": 120.0}
    if S["has_retraction"]:
        out["firmware_retraction"] = {"retract_length": 0.8, "retract_speed": 35.0, "unretract_extra_length": 0.0, "unretract_speed": 30.0}
    if S.get("extra_devices"):
        out["output_pin relay"] = {"pin": "PC1", "pwm": False}
        out["output_pin _secret"] = {"pin": "PC2", "pwm": False}
    if S.get("extra_lights"):
        out["neopixel STRIP"] = {"pin": "PB0", "chain_count": "20", "color_order": "GRBW"}
        out["output_pin caselight"] = {"pin": "PA1", "pwm": True}
        out["output_pin beeper"] = {"pin": "PA2", "pwm": False}
    if S["has_bed_screws"]:
        out["bed_screws"] = {"screw1": "30, 30", "screw1_name": "front left", "screw2": "320, 30", "screw2_name": "front right", "screw3": "175, 320", "screw3_name": "rear"}
    if S.get("z_kind", "bed") == "bed":
        out["z_tilt"] = {"z_positions": "0, 0"}
    else:
        out["quad_gantry_level"] = {"gantry_corners": "0, 0"}
    if S["has_screws"]:
        out["screws_tilt_adjust"] = {"screw1": [30, 30], "screw1_name": "front left", "screw2": [320, 30], "screw2_name": "front right",
                                     "screw3": [320, 320], "screw3_name": "rear right", "screw4": [30, 320], "screw4_name": "rear left", "horizontal_move_z": 5}
    if S["has_twist_section"]:
        out["axis_twist_compensation"] = {"calibrate_start_x": 30, "calibrate_end_x": 320, "calibrate_y": 175}
        if S["twist_y"]:
            out["axis_twist_compensation"].update(calibrate_start_y=30, calibrate_end_y=320, calibrate_x=175)
    return out

def commands_now():
    names = ["G28", "M84", "SAVE_CONFIG", "SET_GCODE_OFFSET", "QUERY_PROBE", "PARK_TEST", "SHAPER_CALIBRATE",
             "CLEAN_NOZZLE", "VAR_LUCI", "LUCI_ON", "LUCI_OFF", "SET_LED", "SET_PIN", "SET_LED_EFFECT", "STOP_LED_EFFECTS"] + S.get("extra_commands", [])
    if S["has_screws"]:
        names.append("SCREWS_TILT_CALCULATE")
    if S["twist_kind"] == "cartographer":
        names.append("CARTOGRAPHER_AXIS_TWIST_COMPENSATION")
    elif S["has_twist_section"]:
        names.append("AXIS_TWIST_COMPENSATION_CALIBRATE")
    names += ["M220", "M221", "SET_PRESSURE_ADVANCE", "SET_VELOCITY_LIMIT"] + (["SET_RETRACTION"] if S["has_retraction"] else [])
    if S["has_level"]:
        names.append("Z_TILT_ADJUST" if S.get("z_kind", "bed") == "bed" else "QUAD_GANTRY_LEVEL")
    if S["has_bed_screws"]:
        names += ["BED_SCREWS_ADJUST", "ACCEPT", "ADJUSTED", "ABORT"]
    names.append("Z_OFFSET_APPLY_PROBE" if S["z_apply"] == "probe" else "Z_OFFSET_APPLY_ENDSTOP")
    return {n: "help for " + n + (", a longer description that needs two lines on a phone to be read in full" if n.startswith("SET_") else "") for n in names}

def status_for(keys, fields=None):
    st = {}
    p = S["printing"]
    for k in keys:
        if k == "webhooks":
            st[k] = {"state": S["webhooks"], "state_message": S["webhooks_msg"]}
        elif k == "print_stats" and S.get("done_print"):   # 1.33.1: a print that has just finished (file still loaded, 100 %)
            st[k] = {"state": "complete", "filename": "Benchy_0.2mm_PLA.gcode", "print_duration": 8000, "total_duration": 8100, "filament_used": 5000, "info": {"current_layer": 100, "total_layer": 100}}
        elif k == "virtual_sdcard" and S.get("done_print"):
            st[k] = {"progress": 1.0, "is_active": False, "file_position": 5000, "file_path": "Benchy_0.2mm_PLA.gcode"}
        elif k == "print_stats":
            state = S.get("print_state") or ("paused" if S["paused"] else ("printing" if p else "standby"))
            st[k] = {"state": state, "filename": "Benchy_0.2mm_PLA.gcode" if p else "", "print_duration": 1260 if p else 0,
                     "total_duration": 1300 if p else 0, "filament_used": 3200 if p else 0,
                     "info": {"current_layer": 42 if p else None, "total_layer": 100 if p else None}}
        elif k == "virtual_sdcard":
            st[k] = {"progress": 0.42 if p else 0, "is_active": p, "file_position": S.get("file_position", 1000), "file_path": "Benchy_0.2mm_PLA.gcode" if p else ""}
        elif k == "display_status":
            st[k] = {"progress": 0.42 if p else 0, "message": None}
        elif k == "toolhead":
            t = S["tune"]
            st[k] = {"position": [120.5, 80.2, 15.3, 0], "homed_axes": S["homed"], "max_velocity": t["vel"], "max_accel": t["accel"], "square_corner_velocity": t["scv"]}
            if S["old_limits"]:
                st[k]["max_accel_to_decel"] = t.get("a2d", 1500.0)
            else:
                st[k]["minimum_cruise_ratio"] = t["mcr"]
        elif k == "gcode_move":
            st[k] = {"gcode_position": [120.5, 80.2, 15.3, 0], "homing_origin": [0, 0, S["z_offset"], 0], "speed_factor": S["speed_factor"], "extrude_factor": S["extrude_factor"], "speed": 6000.0}
        elif k == "firmware_retraction":
            if S["has_retraction"]:
                t = S["tune"]
                st[k] = {"retract_length": t["rl"], "retract_speed": t["rs"], "unretract_extra_length": t["ue"], "unretract_speed": t["us"]}
        elif k == "idle_timeout":
            st[k] = {"state": "Printing" if (p or time.time() < S["level_busy_until"]) else "Ready", "printing_time": 0.0}
        elif k in ("z_tilt", "quad_gantry_level"):
            if S["has_level"] and (k == "z_tilt") == (S.get("z_kind", "bed") == "bed"):
                st[k] = {"applied": S["level_applied"]}
        elif k == "manual_probe":
            st[k] = dict(S["mp"])
        elif k == "bed_screws":
            if S["has_bed_screws"]:
                st[k] = dict(S["bs"])
        elif k == "motion_report":
            st[k] = {"live_velocity": 87.4 if p else 0.0, "live_extruder_velocity": 2.6 if p else 0.0, "live_position": [120.5, 80.2, 15.3, 0]}
        elif k == "exclude_object":
            if S["print_objects"]:
                st[k] = {"objects": S["print_objects"], "excluded_objects": list(S["excluded"]), "current_object": next((o["name"] for o in S["print_objects"] if o["name"] not in S["excluded"]), None)}
        elif k == "extruder":
            st[k] = {"temperature": S["ext_t"], "target": S["ext_target"], "power": 0.45 if S["ext_target"] else 0.0, "pressure_advance": S["tune"]["pa"], "smooth_time": S["tune"]["smooth"]}
        elif k == "heater_bed":
            st[k] = {"temperature": S["bed_t"], "target": S["bed_target"], "power": 0.3 if S["bed_target"] else 0.0}
        elif k in EXTRA_TEMPS and S.get("extra_temps"):
            st[k] = dict(S["extra_temp_values"][k])
        elif k in FANS:
            st[k] = FANS[k]
        elif k == "gcode_macro VAR_LUCI":
            st[k] = {"stato_luci": S["light"]}
        elif k == "neopixel LUCI":   # the effects draw on the strip: its own colour stays 0 (only an effect says it is on)
            st[k] = {"color_data": [[0.0, 0.0, 0.0, 0.0]] * 3}
        elif k == "led_effect IDLE":
            st[k] = {"enabled": S["light"] == 1, "frame_rate": 60.0}
        elif k == "mmu":   # 1.85: a multi-material unit (Happy Hare), when a test sets one
            if S.get("mmu"):
                st[k] = S["mmu"]
        elif k == "AFC":   # 1.91: an AFC unit, when a test sets one (its lanes below)
            if S.get("afc"):
                st[k] = S["afc"]
        elif (k.startswith("AFC_stepper ") or k.startswith("AFC_lane ")) and S.get("afc"):
            lane = (S.get("afc_lanes") or {}).get(k.split(" ", 1)[1])
            if lane is not None:
                st[k] = lane
        elif k == "configfile":
            if S["caps_down"]:
                continue
            full = {"config": CONFIG, "settings": settings_now(), "save_config_pending": bool(S["pending"]), "save_config_pending_items": S["pending"]}
            st[k] = {f: full[f] for f in fields["configfile"]} if fields and fields.get("configfile") else full
        elif k == "probe":
            if S["has_probe"]:
                st[k] = {"name": "cartographer", "last_query": 1 if S["probe_triggered"] else 0, "last_z_result": 0.0}
        elif k == "screws_tilt_adjust":
            if S["has_screws"]:
                st[k] = S["screws"] or {"error": False, "results": {}, "max_deviation": None}
        elif k == "bed_mesh":
            st[k] = mesh_status()
        elif k == "output_pin caselight":
            st[k] = {"value": float(S["caselight"]) if S.get("extra_lights") else float(S["light"])}
        elif k == "neopixel STRIP" and S.get("extra_lights"):
            st[k] = {"color_data": [list(S["strip"])] * 3}
        elif k == "output_pin beeper" and S.get("extra_lights"):
            st[k] = {"value": 0.0}
        elif k.startswith("output_pin ") and S.get("extra_devices") and k[11:] in S["pins"]:
            st[k] = {"value": S["pins"][k[11:]]}
        elif k.startswith("filament_") and S.get("extra_devices") and k.split(" ", 1)[1] in S["sensors"]:
            st[k] = dict(S["sensors"][k.split(" ", 1)[1]])
        elif k.startswith("mcu"):
            st[k] = {"mcu_version": "v0.12.0-100-gabcd", "version": "v0.12.0-100"}
    return st

@app.route("/")
def index():
    return send_file(HTML)

# ---- mock control ----
@app.route("/__mock/set", methods=["POST"])
def mock_set():
    S.update(request.get_json(force=True))
    return jsonify(ok=True)
@app.route("/__mock/reset", methods=["POST"])
def mock_reset():
    EPOCH[0] += 1
    S.clear(); S.update(default_state()); return jsonify(ok=True)
@app.route("/__mock/state")
def mock_state():
    return jsonify({k: v for k, v in S.items() if k in ("light", "light_cmds", "light_reads", "actions", "webhooks", "webhooks_msg", "disconnected", "moonraker_down", "host_off", "services", "update_log", "brain_cfg_log", "backend_release", "brain_started", "klippeye_info", "pending_release", "logos", "app_apk_hits", "app_apk_downloads", "update_channel", "channel_posts", "rec_posts", "measure_starts", "measure_bodies", "ai_cfg", "ai_posts", "ai_model_reads", "excluded", "strip", "caselight", "mesh_profiles", "mesh_active", "mp", "mp_points", "tune", "speed_factor", "extrude_factor", "bs", "level_applied", "recordings", "alerts", "pm_macros", "pm_wraps", "pm_posts", "gcode_log", "ntfy", "ntfy_posts", "ntfy_tests", "ntfy_app_reads", "ai_answers", "ai_answer", "history_log", "queue", "queue_state", "queue_log", "power_devices", "power_log", "pins", "sensors", "timelapse_settings", "timelapse_log", "timelapse_conf_reads", "cfg", "timelapse_files", "spool_id", "spool_log", "webcams", "webcam_log", "peek_log", "schedule", "schedule_log", "metascan_log", "versions_log", "web", "web_log", "review", "review_answers", "personal_posts", "local_model", "local_tests", "false_alarms_forgotten")})
@app.route("/__mock/print_actions")
def mock_print_actions():
    return jsonify(S.get("print_actions", []))
@app.route("/__mock/db")
def mock_db():
    return jsonify(db=S["db"], log=S["db_log"])
@app.route("/__mock/gcode")
def mock_gcode():
    return jsonify(S["gcode_log"])

@app.route("/printer/objects/query", methods=["GET", "POST"])
def obj_query():
    keys = []
    fields = {}
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        keys = list((body.get("objects") or {}).keys())
    else:
        keys = [k for k in request.args.keys()]
        fields = {k: [f for f in v.split(",") if f] for k, v in request.args.items() if v}
    if S["caps_down"] and "configfile" in keys:
        return jsonify(error={"code": 503, "message": "Klippy Host not ready"}), 503
    snapshot = status_for(keys, fields)
    if "gcode_macro VAR_LUCI" in keys or "neopixel LUCI" in keys:
        S["light_reads"] += 1
        if S["light_read_delay"]:
            time.sleep(S["light_read_delay"])   # slow answer: the value above is already old when it leaves
    return jsonify(result={"eventtime": 1.0, "status": snapshot})
# --- KlippEye's own macros (backend /api/printer-macros: klippeye_macros.cfg), in memory
@app.route("/api/printer-macros", methods=["GET"])
def printer_macros_get():
    return jsonify(ok=True, macros=S["pm_macros"], wraps=S["pm_wraps"], file="/home/x/printer_data/config/klippeye_macros.cfg", file_exists=bool(S["pm_macros"] or S["pm_wraps"]), included=True, tag="KlippEye: filament change")
@app.route("/api/printer-macros/template", methods=["GET"])
def printer_macros_template():
    kind = request.args.get("kind", "")
    name = {"park": "KLIPPEYE_PARK", "wipe": "KLIPPEYE_WIPE", "load": "KLIPPEYE_LOAD_FILAMENT", "unload": "KLIPPEYE_UNLOAD_FILAMENT", "light_on": "KLIPPEYE_LIGHT_ON", "light_off": "KLIPPEYE_LIGHT_OFF"}.get(kind)
    if not name:
        return jsonify(ok=False, error="unknown function"), 400
    return jsonify(ok=True, name=name, text="[gcode_macro %s]\ndescription: made by KlippEye\ngcode:\n  G28\n" % name)
@app.route("/api/printer-macros/macro", methods=["POST"])
def printer_macros_macro():
    body = request.get_json(force=True, silent=True) or {}
    S["pm_posts"].append(("macro", body.get("name"), body.get("text")))
    if body.get("text") is None:
        S["pm_macros"].pop(body.get("name"), None)
    else:
        S["pm_macros"][body["name"]] = body["text"]
        S.setdefault("extra_commands", []).append(body["name"])
    return printer_macros_get()
@app.route("/api/printer-macros/wraps", methods=["POST"])
def printer_macros_wraps():
    body = request.get_json(force=True, silent=True) or {}
    S["pm_posts"].append(("wraps", body.get("names")))
    S["pm_wraps"] = list(body.get("names") or [])
    return printer_macros_get()
# --- where the notifications go (backend /api/notifications: notifier.json), in memory
def _channels():
    n = S["ntfy"]
    host = n["server"].split("://", 1)[1]
    link = ("ntfy://%s/%s?display=KlippEye%s" % (host, n["topic"], "" if n["server"].startswith("https://") else "&secure=false")) if n["topic"] else ""
    return jsonify(ok=True, ntfy=dict(n, default_server=n["server"] == "https://ntfy.sh", link=link, web=n["server"] + "/" + n["topic"] if n["topic"] else ""),
                   firebase={"on": S["firebase_on"], "topic_set": S["firebase_on"], "key_found": S["firebase_on"]}, install_command="bash /home/x/klippeye/scripts/install.sh")
# --- the camera's photo as the Raspberry gets it (backend /api/camera/snapshot, 1.23): a tiny PNG for "snapshot" addresses
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000201a5a9d5e70000000049454e44ae426082")
@app.route("/api/camera/snapshot", methods=["GET"])
def camera_snapshot():
    url = request.args.get("url") or "/webcam/?action=snapshot"
    S.setdefault("snapshot_tries", []).append(url)
    if "snapshot" not in url and not url.endswith(".jpg"):
        return jsonify(ok=False, error="la camera non ha mandato una foto (HTTP 404, text/html, 12 bytes)"), 502
    resp = Response(_PNG * 10, mimetype="image/png")
    resp.headers["X-Snapshot-Url"] = "http://127.0.0.1" + url if url.startswith("/") else url
    return resp
@app.route("/api/notifications/channels", methods=["GET"])
def notify_channels():
    return _channels()
@app.route("/api/notifications/ntfy", methods=["POST"])
def notify_ntfy():
    body = request.get_json(force=True, silent=True) or {}
    S["ntfy_posts"].append(body)
    n = S["ntfy"]
    if "server" in body:
        server = (body["server"] or "").strip().rstrip("/") or "https://ntfy.sh"
        if not server.startswith(("http://", "https://")):
            return jsonify(ok=False, error="l'indirizzo del server deve iniziare con http:// o https://"), 400
        n["server"] = server
    if "token" in body: n["has_token"] = bool(body["token"])
    if "click" in body: n["click"] = body["click"]
    if body.get("enabled") in (True, False): n["enabled"] = body["enabled"]
    if body.get("new_topic") or (n["enabled"] and not n["topic"]):
        n["topic"] = "klippeye-%016d" % len(S["ntfy_posts"])
    return _channels()
@app.route("/api/notifications/app", methods=["GET"])
def notify_app():
    n = S["ntfy"]
    S["ntfy_app_reads"] = S.get("ntfy_app_reads", 0) + 1
    ntfy = {"server": n["server"], "topic": n["topic"], "token": ""} if n["enabled"] and n["topic"] else None
    return jsonify(ok=True, ntfy=ntfy, firebaseTopic="klippeye-fb-secret0000000000" if S["firebase_on"] else "")
@app.route("/api/notifications/test", methods=["POST"])
def notify_test():
    S["ntfy_tests"] += 1
    results = []
    if S["ntfy"]["enabled"]: results.append({"channel": "ntfy", "ok": not S["ntfy_test_fail"], "error": S["ntfy_test_fail"]})
    if S["firebase_on"]: results.append({"channel": "firebase", "ok": True, "error": ""})
    return jsonify(ok=True, results=results)
@app.route("/printer/objects/list")
def obj_list():
    return jsonify(result={"objects": OBJECTS + (["neopixel STRIP", "output_pin caselight", "output_pin beeper"] if S.get("extra_lights") else []) + (EXTRA_TEMPS if S.get("extra_temps") else [])
                           + (["output_pin relay", "output_pin _secret", "filament_switch_sensor runout", "filament_motion_sensor encoder"] if S.get("extra_devices") else [])
                           + (["gcode_macro TIMELAPSE_TAKE_FRAME"] if S.get("timelapse_on") and S.get("timelapse_macro") else [])
                           + (["AFC", "AFC_BoxTurtle Turtle_1", "AFC_hub Turtle_1"] + [("AFC_lane " if n == "lane4" else "AFC_stepper ") + n for n in (S.get("afc_lanes") or {})] if S.get("afc") else [])})
@app.route("/machine/device_power/devices")
def power_devices():
    if not S["power_on"]: return jsonify(error={"code": 404, "message": "Not Found"}), 404
    return jsonify(result={"devices": S["power_devices"]})
@app.route("/machine/device_power/device", methods=["GET", "POST"])
def power_device():
    name, action = request.args.get("device", ""), request.args.get("action", "")
    dev = next((d for d in S["power_devices"] if d["device"] == name), None)
    if not dev: return jsonify(error={"code": 404, "message": "No device: " + name}), 404
    if request.method == "POST":
        if dev["locked_while_printing"] and S["printing"]: return jsonify(error={"code": 400, "message": "Unable to change power for %s while printing" % name}), 400
        dev["status"] = "on" if action == "on" else "off"
        S["power_log"].append(name + ":" + action)
    return jsonify(result={name: dev["status"]})
@app.route("/server/temperature_store")
def temperature_store():
    """Moonraker's last 20 minutes, a sample a second: the nozzle heated up to its target 10 minutes ago, the bed 15."""
    n = 1200
    def ramp(start, end, at):
        return [round(start + (end - start) * min(1.0, max(0.0, (i - at) / 120.0)), 2) for i in range(n)]
    out = {"extruder": {"temperatures": ramp(25, S["ext_t"], n - 600), "targets": [0.0] * (n - 600) + [float(S["ext_target"])] * 600, "powers": [0.0] * (n - 600) + [0.45] * 600},
           "heater_bed": {"temperatures": ramp(24, S["bed_t"], n - 900), "targets": [0.0] * (n - 900) + [float(S["bed_target"])] * 900, "powers": [0.0] * (n - 900) + [0.3] * 900}}
    if S.get("extra_temps"):
        for name, v in S["extra_temp_values"].items():
            entry = {"temperatures": ramp(25, v["temperature"], 300)}
            if "target" in v: entry["targets"] = [v["target"]] * n
            if "power" in v: entry["powers"] = [v["power"]] * n
            out[name] = entry
    return jsonify(result=out)
@app.route("/printer/config")
def printer_config():
    return jsonify(result={"config": CONFIG})
@app.route("/printer/info")
def printer_info():
    return jsonify(result={"state": S["webhooks"], "state_message": S["webhooks_msg"], "software_version": "v0.12.0-100-gabcdef", "hostname": "klippeye"})
def console_line(message, kind="response"):
    S["console_extra"].append({"message": message, "time": NOW + 100 + len(S["console_extra"]), "type": kind})

EPOCH = [0]
def later(delay, fn):
    epoch = EPOCH[0]
    t = threading.Timer(delay, lambda: fn() if epoch == EPOCH[0] else None); t.daemon = True; t.start()

def klippy_restart():
    """Klipper goes away, comes back as 'startup', and ends as restart_result (like a real RESTART / FIRMWARE_RESTART)."""
    lag, down, startup = S["restart_lag"], S["restart_down"], S["restart_startup"]
    result, msg = S["restart_result"], S["restart_result_msg"]
    def go_down(): S["disconnected"] = True
    def go_startup():
        S["disconnected"] = False; S["webhooks"] = "startup"
        S["webhooks_msg"] = "Printer is not ready\nThe klippy host software is attempting to connect.  Please\nretry in a few moments."
    def go_final(): S["webhooks"] = result; S["webhooks_msg"] = msg
    later(lag, go_down); later(lag + down, go_startup); later(lag + down + startup, go_final)

def host_outage(seconds):
    """The whole machine is away for a while and comes back with Klipper starting."""
    S["moonraker_down"] = True
    def back():
        S["moonraker_down"] = False; S["disconnected"] = True
        later(S["restart_down"], lambda: S.update(disconnected=False, webhooks="startup"))
        later(S["restart_down"] + S["restart_startup"], lambda: S.update(webhooks=S["restart_result"], webhooks_msg=S["restart_result_msg"]))
    later(seconds, back)

@app.before_request
def simulate_outages():
    path = request.path
    if path.startswith("/__mock"):
        return None
    if S.get("brain_down"):
        return Response("Bad Gateway (mock: the backend is restarting)", status=502, mimetype="text/plain")
    if path == "/":
        return None
    if S.get("moonraker_down") or S.get("host_off"):
        return jsonify(error="HTTPConnectionPool(host='127.0.0.1', port=7125): Max retries exceeded"), 502
    if S.get("disconnected") and (path.startswith("/printer/") or path == "/api/gcode"):
        return jsonify(error={"code": 503, "message": "Klippy Disconnected"}), 503
    return None

def finish_screws(jitter=0.0):
    S["screws"] = {"error": False, "max_deviation": None, "results": {
        "screw1": {"z": 1.0, "sign": "CW", "adjust": "00:00", "is_base": True},
        "screw2": {"z": 1.04 + jitter, "sign": "CW", "adjust": "00:12", "is_base": False},
        "screw3": {"z": 0.93 + jitter, "sign": "CCW", "adjust": "01:15", "is_base": False},
        "screw4": {"z": 1.0, "sign": "CW", "adjust": "00:00", "is_base": False}}}

def finish_twist(axis):
    S["pending"] = dict(S["pending"], axis_twist_compensation={"z_compensations": "0.01, 0.0, -0.01, 0.0, 0.01", "compensation_start_" + axis.lower(): 30})

@app.route("/printer/print/<action>", methods=["POST"])
def print_action(action):
    """pause / cancel / resume as Moonraker offers them (the notification service uses pause and cancel)."""
    S.setdefault("print_actions", []).append(action)
    if S.get("print_action_delay"):
        time.sleep(S["print_action_delay"])
    if S.get("print_action_fail"):
        return jsonify(error={"code": 400, "message": S["print_action_fail"]}), 400
    S["print_state"] = {"pause": "paused", "cancel": "cancelled", "resume": "printing"}.get(action, S.get("print_state"))
    return jsonify(result="ok")

@app.route("/printer/gcode/script", methods=["POST"])
def gcode_script():
    body = request.get_json(force=True, silent=True) or {}
    script = body.get("script", request.args.get("script", ""))
    S["gcode_log"].append(script)
    words = script.strip().split()
    cmd = words[0].upper() if words else ""
    if cmd == "M84":
        S["homed"] = ""
    elif cmd in ("SET_HEATER_TEMPERATURE", "SET_TEMPERATURE_FAN_TARGET"):   # 1.43: the targets of the other heaters
        args = {w.split("=")[0].upper(): w.split("=", 1)[1] for w in words[1:] if "=" in w}
        name = ("heater_generic " + args.get("HEATER", "")) if cmd == "SET_HEATER_TEMPERATURE" else ("temperature_fan " + args.get("TEMPERATURE_FAN", ""))
        if name in S["extra_temp_values"]:
            S["extra_temp_values"][name]["target"] = float(args.get("TARGET", 0))
    elif cmd == "EXCLUDE_OBJECT" and len(words) > 1 and words[1].upper().startswith("NAME="):
        S["excluded"].append(words[1][5:])
    elif cmd in ("SCREWS_TILT_CALCULATE", "CARTOGRAPHER_AXIS_TWIST_COMPENSATION"):
        if S["tool_error"]:
            def fail():
                console_line("!! " + S["tool_error"])
            if S["tool_timeout_502"]:
                later(S["tool_delay"], fail)
                return jsonify(error="HTTPConnectionPool(host='127.0.0.1', port=7125): Read timed out. (read timeout=10)"), 502
            console_line("!! " + S["tool_error"])
            return jsonify(error={"code": 400, "message": S["tool_error"]}), 400
        axis = next((w.split("=")[1] for w in words if w.upper().startswith("AXIS=")), "X")
        S["runs"] = S.get("runs", 0) + 1
        work = (lambda: finish_screws(0.001 * S["runs"])) if cmd == "SCREWS_TILT_CALCULATE" else (lambda: finish_twist(axis))
        if S["tool_timeout_502"]:
            # the proxy gives up after 10 s while the command keeps running
            later(S["tool_delay"], work)
            return jsonify(error="HTTPConnectionPool(host='127.0.0.1', port=7125): Read timed out. (read timeout=10)"), 502
        time.sleep(S["tool_delay"]); work()  # Moonraker answers when the command is over
    elif cmd in ("M220", "M221"):
        value = next((float(w[1:]) for w in words[1:] if w.upper().startswith("S")), 100.0)
        S["speed_factor" if cmd == "M220" else "extrude_factor"] = value / 100.0
    elif cmd in ("SET_PRESSURE_ADVANCE", "SET_VELOCITY_LIMIT", "SET_RETRACTION"):
        keys = {"ADVANCE": "pa", "SMOOTH_TIME": "smooth", "VELOCITY": "vel", "ACCEL": "accel", "SQUARE_CORNER_VELOCITY": "scv", "MINIMUM_CRUISE_RATIO": "mcr",
                "ACCEL_TO_DECEL": "a2d", "RETRACT_LENGTH": "rl", "RETRACT_SPEED": "rs", "UNRETRACT_EXTRA_LENGTH": "ue", "UNRETRACT_SPEED": "us"}
        for w in words[1:]:
            if "=" in w and w.split("=")[0].upper() in keys:
                S["tune"][keys[w.split("=")[0].upper()]] = float(w.split("=")[1])
    elif cmd in ("Z_TILT_ADJUST", "QUAD_GANTRY_LEVEL"):
        S["level_busy_until"] = time.time() + S["level_delay"]
        def levelled():
            if S["tool_error"]:
                console_line("!! " + S["tool_error"])
            else:
                S["level_applied"] = True
                console_line("// Retries: 1/5 Probed points range: 0.002100 tolerance: 0.007500")
            S["level_busy_until"] = 0.0
        if S["tool_timeout_502"]:
            later(S["level_delay"], levelled)
            return jsonify(error="HTTPConnectionPool(host='127.0.0.1', port=7125): Read timed out. (read timeout=10)"), 502
        time.sleep(S["level_delay"]); levelled()
        if S["tool_error"]:
            return jsonify(error={"code": 400, "message": S["tool_error"]}), 400
    elif cmd in ("BED_MESH_PROFILE", "BED_MESH_CLEAR", "BED_MESH_CALIBRATE"):
        for line in script.strip().split("\n"):   # a rename is three lines
            w = line.strip().split()
            c = w[0].upper() if w else ""
            args = {x.split("=")[0].upper(): x.split("=", 1)[1] for x in w[1:] if "=" in x}
            mesh_status()
            prof = S["mesh_profiles"]
            if c == "BED_MESH_CLEAR":
                S["mesh_active"] = ""; S["mesh_current"] = None
            elif c == "BED_MESH_CALIBRATE":
                name = args.get("PROFILE", "default")
                prof[name] = mesh_rows(0.002, 5 if args.get("ADAPTIVE") == "1" else 7); S["mesh_active"] = name
                S["pending"] = dict(S["pending"], **{"bed_mesh " + name: {"version": 1}})
            elif "LOAD" in args:
                if args["LOAD"] not in prof:
                    console_line("!! bed_mesh: Unknown profile [%s]" % args["LOAD"])
                    return jsonify(error={"code": 400, "message": "bed_mesh: Unknown profile [%s]" % args["LOAD"]}), 400
                S["mesh_active"] = args["LOAD"]
            elif "SAVE" in args:
                prof[args["SAVE"]] = prof.get(S["mesh_active"]) or mesh_rows(); S["mesh_active"] = args["SAVE"]
                S["pending"] = dict(S["pending"], **{"bed_mesh " + args["SAVE"]: {"version": 1}})
            elif "REMOVE" in args:
                prof.pop(args["REMOVE"], None)
                S["pending"] = dict(S["pending"], **{"bed_mesh " + args["REMOVE"]: None})
    elif cmd in ("SET_LED", "SET_PIN", "STOP_LED_EFFECTS", "SET_FILAMENT_SENSOR"):
        apply_led_lines(script)
    elif cmd == "AXIS_TWIST_COMPENSATION_CALIBRATE":
        time.sleep(0.4)   # probes the first point, then waits for the paper test there
        S["mp_axis"] = next((w.split("=")[1] for w in words if w.upper().startswith("AXIS=")), "X")
        S["mp_points"] = 0
        S["mp"] = {"is_active": True, "z_position": 1.0, "z_position_lower": None, "z_position_upper": None}
    elif cmd == "RESPOND":   # 1.71: as Klipper's [respond]: TYPE=command → "// msg", error → "!! msg", echo → "echo: msg"
        import re as _re
        m = _re.search(r'MSG="(.*)"\s*$', script, _re.I) or _re.search(r"MSG=(\S+)", script, _re.I)
        t = _re.search(r"TYPE=\"?(\w+)", script, _re.I)
        kind = (t.group(1).lower() if t else "echo")
        msg = m.group(1) if m else ""
        console_line({"command": "// ", "error": "!! "}.get(kind, "echo: ") + msg)
    elif cmd in ("PROBE_CALIBRATE", "Z_ENDSTOP_CALIBRATE", "MANUAL_PROBE"):
        S["mp_points"] = 99  # one height only: ACCEPT ends it
        S["mp"] = {"is_active": True, "z_position": 1.0, "z_position_lower": None, "z_position_upper": None}
    elif S["mp"]["is_active"] and cmd in ("TESTZ", "ACCEPT", "ABORT"):
        if cmd == "TESTZ":
            S["mp"]["z_position"] = round(S["mp"]["z_position"] + float(words[1].split("=")[1]), 4)
        elif cmd == "ABORT":
            S["mp"] = dict(S["mp"], is_active=False)
            console_line("!! Manual probe aborted")
        else:
            S["mp"] = dict(S["mp"], is_active=False)
            S["mp_points"] += 1
            if S["mp_points"] >= 100:
                console_line("// probe: z_offset: 1.100\n// The SAVE_CONFIG command will update the printer config file")
            elif S["mp_points"] >= 3:
                later(0.6, lambda: finish_twist(S["mp_axis"]))
            else:
                later(0.8, lambda: S.__setitem__("mp", {"is_active": True, "z_position": 1.0, "z_position_lower": None, "z_position_upper": None}))
    elif cmd == "BED_SCREWS_ADJUST":
        S["bs"] = {"is_active": True, "state": "adjust", "current_screw": 0, "accepted_screws": 0}; S["bs_adjusted"] = False
    elif cmd in ("ACCEPT", "ADJUSTED", "ABORT"):
        bs = S["bs"]
        if not bs["is_active"]:
            return jsonify(error={"code": 400, "message": "Unknown command:\"%s\"" % cmd}), 400
        time.sleep(0.3)   # the nozzle goes to the next screw
        if cmd == "ABORT":
            S["bs"] = {"is_active": False, "state": None, "current_screw": 0, "accepted_screws": 0}
        else:
            if cmd == "ADJUSTED":
                S["bs_adjusted"] = True
            else:
                bs["accepted_screws"] += 1
            bs["current_screw"] += 1
            if bs["current_screw"] >= 3:
                if S["bs_adjusted"]:
                    bs.update(current_screw=0, accepted_screws=0); S["bs_adjusted"] = False
                else:
                    S["bs"] = {"is_active": False, "state": None, "current_screw": 0, "accepted_screws": 0}
    elif cmd == "SET_GCODE_OFFSET":
        args = {w.split("=")[0].upper(): w.split("=")[1] for w in words[1:] if "=" in w}
        if "Z_ADJUST" in args:
            S["z_offset"] = round(S["z_offset"] + float(args["Z_ADJUST"]), 4)
        elif "Z" in args:
            S["z_offset"] = float(args["Z"])
    elif cmd in ("Z_OFFSET_APPLY_PROBE", "Z_OFFSET_APPLY_ENDSTOP"):
        if S.get("apply_error"):
            return jsonify(error={"code": 400, "message": S["apply_error"]}), 400
        section = "probe" if cmd.endswith("PROBE") else "stepper_z"
        option = "z_offset" if cmd.endswith("PROBE") else "position_endstop"
        S["pending"] = dict(S["pending"], **{section: {option: round(-S["z_offset"], 4)}})
    elif cmd == "QUERY_PROBE":
        console_line("// probe: " + ("TRIGGERED" if S["probe_triggered"] else "open"))
    elif cmd == "SAVE_CONFIG":
        S["pending"] = {}; S["z_offset"] = 0.0
        klippy_restart()
    elif cmd in ("RESTART", "FIRMWARE_RESTART"):
        if S["gcode_refuse"]:
            return jsonify(error={"code": 500, "message": "restart refused (mock)"}), 500
        S["actions"].append(("gcode:" + cmd, ""))
        klippy_restart()
    return jsonify(result="ok")

@app.route("/printer/query_endstops/status")
def query_endstops():
    S["gcode_log"].append("QUERY_ENDSTOPS")
    if S["endstops_error"]:
        return jsonify(error={"code": 400, "message": S["endstops_error"]}), 400
    return jsonify(result=S["endstops"])

@app.route("/printer/gcode/help")
def gcode_help():
    if S["caps_down"]:
        return jsonify(error={"code": 503, "message": "Klippy Host not ready"}), 503
    return jsonify(result=commands_now())
def apply_led_lines(script):
    """SET_LED / SET_PIN on the extra lights (1.37) change what the mock reports."""
    for line in script.strip().split("\n"):
        w = line.strip().split()
        args = {x.split("=")[0].upper(): x.split("=", 1)[1] for x in w[1:] if "=" in x}
        if w and w[0].upper() == "SET_LED" and args.get("LED") == "STRIP":
            S["strip"] = [float(args.get(c, 0)) for c in ("RED", "GREEN", "BLUE", "WHITE")]
        elif w and w[0].upper() == "SET_PIN" and args.get("PIN") == "caselight":
            S["caselight"] = float(args.get("VALUE", 0))
        elif w and w[0].upper() == "SET_PIN" and args.get("PIN") in S["pins"]:
            S["pins"][args["PIN"]] = float(args.get("VALUE", 0))
        elif w and w[0].upper() == "SET_FILAMENT_SENSOR" and args.get("SENSOR") in S["sensors"]:
            S["sensors"][args["SENSOR"]]["enabled"] = args.get("ENABLE") == "1"

@app.route("/api/gcode", methods=["POST"])
def api_gcode():
    body = request.get_json(force=True, silent=True) or {}
    script = body.get("script", "")
    S["gcode_log"].append(script)
    apply_led_lines(script)
    if script.lower() in ("luci_on", "luci_off"):
        script = script.lower()
        S["light_cmds"].append((script, time.time()))
        target = 1 if script == "luci_on" else 0
        def apply():
            if not S["light_fail"]:
                S["light"] = target
        if S["light_exec_delay"] > 0 and not S["light_block"]:
            later(S["light_exec_delay"], apply)
        else:
            if S["light_exec_delay"] > 0:
                time.sleep(S["light_exec_delay"])
            apply()
    return jsonify(result="ok", sent=script)
@app.route("/printer/<path:p>", methods=["POST"])
def printer_post(p):
    if p in ("restart", "firmware_restart"):
        S["actions"].append(("printer/" + p, ""))
        if S["restart_refuse"]:
            return jsonify(error={"code": S["restart_refuse"], "message": "refused (mock)"}), S["restart_refuse"]
        klippy_restart()
    elif p == "emergency_stop":
        S["webhooks"] = "shutdown"; S["webhooks_msg"] = "Shutdown due to M112 command\nOnce the underlying issue is corrected, use the\n\"FIRMWARE_RESTART\" command to reset the firmware,\nreload the config, and restart the host software.\nPrinter is shutdown"
    return jsonify(result="ok")

@app.route("/machine/services/<action>", methods=["POST"])
def machine_service(action):
    name = request.args.get("service", "")
    S["actions"].append(("services/" + action, name))
    if S["service_error"]:
        return jsonify(error={"code": 400, "message": S["service_error"]}), 400
    if name not in S["services"]:
        return jsonify(error={"code": 400, "message": "Service " + name + " not allowed"}), 400
    if action == "stop":
        S["services"][name] = ["inactive", "dead"]
        if name == "klipper": S["disconnected"] = True
    else:
        S["services"][name] = ["active", "running"]
        if name == "klipper": klippy_restart()
        if name == "klippeye":
            brain_restart(S.pop("pending_release", None))
            return cut_response()
        if name == "moonraker":
            timelapse_read_config()  # 1.67: moonraker-timelapse reads its [timelapse] section when Moonraker starts
            S["moonraker_down"] = True
            later(S["restart_down"] + 1.0, lambda: S.update(moonraker_down=False))
            return jsonify(error="Connection aborted (mock: Moonraker restarted itself)"), 502
    return jsonify(result="ok")

@app.route("/machine/reboot", methods=["POST"])
def machine_reboot():
    S["actions"].append(("reboot", ""))
    host_outage(S["reboot_down"])
    return jsonify(result="ok")

@app.route("/machine/shutdown", methods=["POST"])
def machine_shutdown():
    S["actions"].append(("shutdown", ""))
    later(1.0, lambda: S.update(host_off=True))
    return jsonify(result="ok")
@app.route("/machine/save_config", methods=["POST"])
def save_config():
    return jsonify(result="ok")

@app.route("/api/printer")
@app.route("/api/status")
def api_printer():
    st = status_for(["heater_bed","extruder","print_stats","toolhead","virtual_sdcard","display_status","gcode_move","output_pin caselight"])
    return jsonify(state=S["webhooks"], heater_bed=st["heater_bed"], extruder=st["extruder"], print_stats=st["print_stats"],
                   toolhead=st["toolhead"], virtual_sdcard=st["virtual_sdcard"], display_status=st["display_status"],
                   raw={"toolhead": st["toolhead"], "gcode_move": st["gcode_move"], "output_pin": {"caselight": st["output_pin caselight"]}})

@app.route("/server/gcode_store")
def gcode_store():
    base = NOW
    entries = [
        {"message": "G28", "time": base+1, "type": "command"},
        {"message": "ok", "time": base+2, "type": "response"},
        {"message": "// Homed: X Y Z", "time": base+3, "type": "response"},
        {"message": "B:60.1 /60.0 T0:215.3 /220.0", "time": base+4, "type": "response"},
        {"message": "!! Error: sample error", "time": base+5, "type": "response"},
        {"message": "// warning: something", "time": base+6, "type": "response"},
        {"message": "M104 S220", "time": base+7, "type": "command"},
        {"message": "plain info line", "time": base+8, "type": "response"},
    ]
    if S["webhooks"] == "shutdown":
        entries.append({"message": "Klipper state: SHUTDOWN", "time": base+9, "type": "response"})
    entries.extend(S["console_extra"])
    count = request.args.get("count", type=int)
    if count:
        entries = entries[-count:]  # like Moonraker: the newest `count` lines
    return jsonify(result={"gcode_store": entries})

GCODES = [("Benchy_0.2mm_PLA.gcode", NOW-3600, 123456), ("Calibration_cube_long_filename_for_wrapping_test.gcode", NOW-86400, 654321),
          ("Vase_mode.gcode", NOW-200000, 45000), ("Bracket.gcode", NOW-400000, 3456789), ("Test/Nested_part.gcode", NOW-500000, 9999)]
@app.route("/server/files/list")
def files_list():
    root = request.args.get("root", "gcodes")
    if root == "timelapse":
        return jsonify(result=[{"path": p, "modified": m, "size": 2400000 if p.endswith(".mp4") else 50000, "permissions": "rw"} for p, m in S["timelapse_files"].items()])
    if root == "gcodes":
        return jsonify(result=[{"path": p, "modified": m, "size": s, "permissions": "rw"} for p, m, s in GCODES if p not in S.get("deleted", [])])
    files = S["cfg"]["files"]
    return jsonify(result=[{"path": p, "modified": f["modified"], "size": f["size"], "permissions": "rw"} for p, f in files.items()])
@app.route("/server/files/metadata")
def files_meta():
    fn = request.args.get("filename", "")
    # 1.40: every file its own figures (the sort by print time / filament / last print, the details); the Benchy as before
    size = next((g[2] for g in GCODES if g[0] == fn), 50000)
    extra = {"slicer": "OrcaSlicer", "slicer_version": "2.1.1", "layer_height": 0.2, "first_layer_height": 0.25, "nozzle_diameter": 0.4,
             "filament_type": "PLA", "filament_name": "Generic PLA", "first_layer_extr_temp": 215.0, "first_layer_bed_temp": 60.0}
    if "Benchy" in fn:
        extra["print_start_time"] = NOW - 7200
    result = dict(extra, **{"filename": fn, "estimated_time": 7260 if "Benchy" in fn else 600 + size // 1000, "filament_weight_total": 12.4 if "Benchy" in fn else 0,
                           "filament_total": 4200 if "Benchy" in fn else size // 10, "layer_count": 100, "object_height": 48.0, "thumbnails": [] if any(k in fn for k in S.get("no_thumbs", [])) else [
                               {"width": 32, "height": 32, "size": 100, "relative_path": ".thumbs/thumb-32x32.png"},
                               {"width": 300, "height": 300, "size": 900, "relative_path": ".thumbs/thumb-300x300.png"}]})
    result.update(S.get("meta_extra") or {})   # 1.83: a file sliced differently (the checks before a print)
    return jsonify(result=result)
def png(w=64, h=64, color=(200, 90, 40)):
    im = Image.new("RGB", (w, h), color)
    for x in range(w):
        for y in range(h):
            im.putpixel((x, y), (color[0], (color[1]+x*2) % 255, (color[2]+y*3) % 255))
    b = io.BytesIO(); im.save(b, "PNG"); b.seek(0); return b
def vase_text():
    """1.63: a spiral vase: the height rises at every move; the slicer marks each of its 20 turns with ;LAYER_CHANGE."""
    import math
    out = ["; generated by OrcaSlicer 2.1\nG28\nG1 Z0.2 F1200\n"]
    e = 0.0
    for turn in range(20):
        out.append(";LAYER_CHANGE\n;Z:%.2f\n;TYPE:Outer wall\n" % (0.2 * (turn + 1)))
        for k in range(60):
            a = 2 * math.pi * k / 60
            e += 0.05
            out.append("G1 X%.3f Y%.3f Z%.4f E%.4f\n" % (50 + 20 * math.cos(a), 50 + 20 * math.sin(a), 0.2 * (turn + 1) + 0.2 * k / 60, e))
    return "".join(out)

def gcode_text(p, size):
    if p == "Vase_mode.gcode":
        return vase_text()
    head = "; generated by OrcaSlicer 2.1\n; file: %s\nM140 S60\nM104 S215\nG28\nM190 S60\nM109 S215\nSET_PRESSURE_ADVANCE ADVANCE=0.04\nG1 Z0.3 F1200\n" % p
    # 1.49: a new height every 100 moves and the slicer's ;TYPE: comments, for the G-code viewer
    kinds = ["Outer wall", "Inner wall", "Sparse infill", "Support"]
    body = "".join(("G1 Z%.2f F600\n;TYPE:%s\n" % (0.2 * (i // 100 + 1), kinds[(i // 25) % 4]) if i % 100 == 0 else (";TYPE:%s\n" % kinds[(i // 25) % 4] if i % 25 == 0 else ""))
                   + "G1 X%.3f Y%.3f E%.4f F1800 ; layer %d\n" % (10 + (i % 97) * 0.5, 10 + (i % 89) * 0.5, i * 0.0123, i // 100) for i in range(60000))
    return (head + body)[:max(size, len(head))]
@app.route("/server/files/gcodes/<path:p>", methods=["GET", "DELETE"])
def gcode_file(p):
    if request.method == "DELETE":
        S["gcode_log"].append("DELETE:" + p)
        if S.get("delete_error"):
            return jsonify(error={"code": 403, "message": S["delete_error"]}), 403
        S["deleted"].append(p)
        return jsonify(result={"item": {"path": p, "root": "gcodes"}, "action": "delete_file"})
    if ".thumbs" in p or p.lower().endswith(".png"):
        return send_file(png(), mimetype="image/png")
    size = next((s for q, m, s in GCODES if q == p), 2000)
    return Response(gcode_text(p, size), mimetype="application/octet-stream")
MOONRAKER_TEXT = """[server]
host: 0.0.0.0
port: 7125

[authorization]
trusted_clients:
    192.168.0.0/16
cors_domains:
    *.local

[timelapse]
# made by the installer
output_path: ~/printer_data/timelapse/

[update_manager timelapse]
type: git_repo
primary_branch: main
path: ~/moonraker-timelapse
origin: https://github.com/mainsail-crew/moonraker-timelapse.git
managed_services: klipper moonraker
"""


def timelapse_read_config():
    """Like moonraker-timelapse at start: a setting in moonraker.conf's [timelapse] wins and is locked (blockedsettings)."""
    f = S["cfg"]["files"].get("moonraker.conf")
    text = MOONRAKER_TEXT if not f or f["content"] is None else f["content"]
    inside, found = False, {}
    for line in text.split("\n"):
        if re.match(r"^\s*\[", line):
            inside = line.strip().lower() == "[timelapse]"
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*[:=]\s*(.*)$", line)
        if inside and m: found[m.group(1).lower()] = m.group(2).strip()
    sett = S["timelapse_settings"]
    blocked = list(sett.get("blockedsettings", []))
    for k, v in found.items():
        if k not in sett: continue
        old = sett[k]
        if isinstance(old, bool): v = v.lower() in ("true", "1", "yes", "on")
        elif isinstance(old, int): v = int(float(v))
        elif isinstance(old, float): v = float(v)
        sett[k] = v
        if k not in blocked: blocked.append(k)
    sett["blockedsettings"] = blocked
    S["timelapse_conf_reads"] = S.get("timelapse_conf_reads", 0) + 1
    if S.get("timelapse_on"):  # and then, Klipper ready, it sends its settings to its macros (a console line)
        console_line("_SET_TIMELAPSE_SETUP  ENABLE=%s VERBOSE=%s PARK_ENABLE=%s PARK_POS=%s" % (sett["enabled"], sett["gcode_verbose"], sett["parkhead"], sett["parkpos"]), "command")


CFG_TEXT = """# KlippEye printer config
[include macros/*.cfg]
[stepper_x]
step_pin: PB13
dir_pin: !PB12
enable_pin: !PB14
microsteps: 32
position_max: 350
homing_speed: 40 # fast

[gcode_macro PARK]
description: Park the toolhead
variable_x: 10
gcode:
    {% if printer.toolhead.homed_axes != "xyz" %}
        G28
    {% endif %}
    SAVE_GCODE_STATE NAME=park
    G90
    G1 X{params.X|default(10)} Y100 F6000
    M118 "Parked"
"""
def cfg_error(code, message):
    return jsonify(error={"code": code, "message": message}), code
def cfg_rel(path):
    """'config/macros/a.cfg' -> 'macros/a.cfg'; '' for the root; None when not under config."""
    path = (path or "").strip("/")
    if path == "config": return ""
    if path.startswith("config/"): return path[len("config/"):]
    return None
def cfg_is_dir(rel):
    return rel == "" or rel in S["cfg"]["dirs"]
def cfg_parent(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else ""
def cfg_guard():
    if S["cfg_delay"]: time.sleep(S["cfg_delay"])
    if S["cfg_error"]: return cfg_error(403, S["cfg_error"])
    return None

def attachment_header(name):
    """What Moonraker sends: an ASCII fallback plus the real name (RFC 5987), which is what browsers use."""
    import unicodedata, urllib.parse
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "attachment; filename=%s; filename*=UTF-8''%s" % (ascii_name, urllib.parse.quote(name))

@app.route("/server/files/config/<path:p>", methods=["GET", "DELETE"])
def cfg_file(p):
    files = S["cfg"]["files"]
    if request.method == "DELETE":
        bad = cfg_guard()
        if bad: return bad
        if p not in files: return cfg_error(404, "File does not exist (config/%s)" % p)
        del files[p]
        S["gcode_log"].append("DELETE_CFG:" + p)
        return jsonify(result={"item": {"path": p, "root": "config"}, "action": "delete_file"})
    if p not in files: return cfg_error(404, "File does not exist (config/%s)" % p)
    if p.lower().endswith((".png", ".jpg")):
        return send_file(png(120, 80), mimetype="image/png")
    content = files[p]["content"]
    if content is None and p == "moonraker.conf": content = MOONRAKER_TEXT
    # like Moonraker, which always hands a file out as an attachment
    return Response(CFG_TEXT if content is None else content, mimetype="text/plain", headers={"Content-Disposition": attachment_header(p.rsplit("/", 1)[-1])})
@app.route("/server/files/content")
def cfg_content():
    p = request.args.get("path", "")
    f = S["cfg"]["files"].get(p)
    if f is None: return cfg_error(404, "File does not exist (config/%s)" % p)
    return Response((MOONRAKER_TEXT if p == "moonraker.conf" else CFG_TEXT) if f["content"] is None else f["content"], mimetype="text/plain")

@app.route("/server/files/directory", methods=["GET", "POST", "DELETE"])
def cfg_directory():
    tree = S["cfg"]
    if request.method == "GET":
        rel = cfg_rel(request.args.get("path", "config"))
        if rel is None or not cfg_is_dir(rel): return cfg_error(404, "Directory does not exist (%s)" % request.args.get("path"))
        dirs = [{"dirname": d.split("/")[-1], "modified": m, "size": 4096, "permissions": "rw"} for d, m in tree["dirs"].items() if cfg_parent(d) == rel]
        files = [{"filename": f.split("/")[-1], "modified": v["modified"], "size": v["size"], "permissions": "rw"} for f, v in tree["files"].items() if cfg_parent(f) == rel]
        return jsonify(result={"dirs": dirs, "files": files, "disk_usage": {"total": 10**10, "used": 10**9, "free": 9 * 10**9}, "root_info": {"name": "config", "permissions": "rw"}})
    bad = cfg_guard()
    if bad: return bad
    if request.method == "POST":
        rel = cfg_rel((request.get_json(force=True) or {}).get("path"))
        if not rel: return cfg_error(400, "Invalid path")
        if rel in tree["dirs"] or rel in tree["files"]: return cfg_error(409, "Directory already exists (config/%s)" % rel)
        if not cfg_is_dir(cfg_parent(rel)): return cfg_error(404, "Parent directory does not exist")
        tree["dirs"][rel] = NOW
        S["gcode_log"].append("MKDIR:" + rel)
        return jsonify(result={"item": {"path": rel, "root": "config"}, "action": "create_dir"})
    rel = cfg_rel(request.args.get("path"))
    if not rel or rel not in tree["dirs"]: return cfg_error(404, "Directory does not exist")
    inside = [d for d in tree["dirs"] if d.startswith(rel + "/")] + [f for f in tree["files"] if f.startswith(rel + "/")]
    if inside and request.args.get("force", "false") != "true": return cfg_error(403, "Directory is not empty")
    for d in [rel] + [d for d in tree["dirs"] if d.startswith(rel + "/")]: tree["dirs"].pop(d, None)
    for f in [f for f in tree["files"] if f.startswith(rel + "/")]: tree["files"].pop(f)
    S["gcode_log"].append("RMDIR:" + rel)
    return jsonify(result={"item": {"path": rel, "root": "config"}, "action": "delete_dir"})

@app.route("/server/files/move", methods=["POST"])
def cfg_move():
    bad = cfg_guard()
    if bad: return bad
    tree = S["cfg"]
    body = request.get_json(force=True) or {}
    src, dst = cfg_rel(body.get("source")), cfg_rel(body.get("dest"))
    if not src or not dst: return cfg_error(400, "Invalid path")
    is_dir = src in tree["dirs"]
    if not is_dir and src not in tree["files"]: return cfg_error(404, "Source does not exist (config/%s)" % src)
    if dst in tree["dirs"] or dst in tree["files"]: return cfg_error(409, "Destination already exists (config/%s)" % dst)
    if not cfg_is_dir(cfg_parent(dst)): return cfg_error(404, "Destination directory does not exist")
    if is_dir and (dst == src or dst.startswith(src + "/")): return cfg_error(400, "Cannot move a directory into itself")
    if is_dir:
        tree["dirs"] = {(dst + d[len(src):] if d == src or d.startswith(src + "/") else d): m for d, m in tree["dirs"].items()}
        tree["files"] = {(dst + f[len(src):] if f.startswith(src + "/") else f): v for f, v in tree["files"].items()}
    else:
        tree["files"] = {(dst if f == src else f): v for f, v in tree["files"].items()}
    S["gcode_log"].append("MOVE:%s>%s" % (src, dst))
    return jsonify(result={"item": {"path": dst, "root": "config"}, "source_item": {"path": src, "root": "config"}, "action": "move_dir" if is_dir else "move_file"})

@app.route("/server/files/upload", methods=["POST"])
def upload():
    root = request.form.get("root", "config")
    tag = "UPLOAD:" if root != "gcodes" else "UPLOAD_GCODES:"
    folder = str(request.form.get("path", ""))
    name = request.files["file"].filename if "file" in request.files else "?"
    S["gcode_log"].append(tag + folder + "/" + name)
    if root == "config" and "file" in request.files:
        bad = cfg_guard()
        if bad: return bad
        rel = (folder + "/" + name).strip("/")
        if not cfg_is_dir(cfg_parent(rel)): return cfg_error(404, "Directory does not exist")
        if rel in S["cfg"]["dirs"]: return cfg_error(409, "A directory with this name exists")
        data = request.files["file"].read()
        S["cfg"]["files"][rel] = {"size": len(data), "modified": NOW + 10, "content": data.decode("utf-8", "replace")}
    return jsonify(result={"item": {"path": "x"}})

@app.route("/machine/system_info")
def sysinfo():
    return jsonify(result={"system_info": {"cpu_info": {"model": "Raspberry Pi 4 Model B"}, "distribution": {"name": "Debian GNU/Linux 12"},
                                           "available_services": list(S["services"].keys()),
                                           "service_state": {k: {"active_state": v[0], "sub_state": v[1]} for k, v in S["services"].items()}}})
@app.route("/machine/proc_stats")
def procstats():
    return jsonify(result={"system_cpu_usage": {"cpu": 23.5}, "cpu_temp": 48.2, "system_memory": {"total": 3900000, "used": 1650000}})
@app.route("/machine/update/status")
def upd_status():
    info = {
        "klipper": {"name": "klipper", "version": "v0.12.0-100", "remote_version": "v0.12.0-120", "commits_behind": [{}, {}, {}], "rollback_version": "v0.12.0-90", "is_valid": True},
        "moonraker": {"name": "moonraker", "version": "v0.9.0-10", "remote_version": "v0.9.0-10", "commits_behind": [], "is_valid": True},
        "system": {"name": "system", "configured_type": "system", "package_count": 3, "package_list": ["libc6", "openssl", "curl"]}}
    if S.get("klippeye_info") is not None:
        info["klippeye"] = copy.deepcopy(S["klippeye_info"])
    return jsonify(result={"busy": False, "version_info": info})

def brain_restart(release=None):
    """The backend goes away for a while and comes back with another start time (and release, when the work changed it)."""
    S["brain_down"] = True
    def back():
        S["brain_down"] = False
        S["brain_started"] += 17
        if release: S["backend_release"] = release
    later(S["brain_restart_s"], back)

def cut_response():
    """A reply that is cut off half way, as when the backend is killed under the request: the browser's fetch fails."""
    def body():
        yield b'{"result":'
        raise RuntimeError("mock: the backend was restarted under the request")
    return Response(body(), mimetype="application/json")

@app.route("/machine/update/<action>", methods=["POST"])
def machine_update(action):
    body = request.get_json(silent=True) or {}
    name = body.get("name") or request.args.get("name") or ""
    S["update_log"].append((action, name))
    info = S.get("klippeye_info")
    if action == "refresh":
        if info is not None and S["klippeye_incoming"]:
            info["commits_behind"] = copy.deepcopy(S["klippeye_incoming"]); info["commits_behind_count"] = len(info["commits_behind"])
            info["remote_version"] = "v0.0.0-%d" % (3 + len(info["commits_behind"])); info["remote_hash"] = "ffee" + "0" * 36
        return jsonify(result="ok")
    if S["update_delay"]:
        time.sleep(S["update_delay"])
    if S["update_error"]:
        return jsonify(error={"code": 500, "message": S["update_error"]}), 500
    if name != "klippeye" or info is None:
        return jsonify(result="ok")
    if action == "upgrade":
        if info["is_dirty"] or not info["is_valid"]:
            return jsonify(error={"code": 500, "message": "Update aborted, repo not valid"}), 500
        info.update(commits_behind=[], commits_behind_count=0, rollback_version=info["version"], version=info["remote_version"], current_hash=info["remote_hash"])
        release = S["klippeye_new_release"]
    elif action == "rollback":
        info.update(version=info["rollback_version"], remote_version=info["rollback_version"])
        release = S["klippeye_old_release"]
    elif action == "recover":
        info.update(is_dirty=False, is_valid=True, corrupt=False, warnings=[], pristine=True)
        release = None
    else:
        return jsonify(result="ok")
    if S["update_restart"] == "yes":
        brain_restart(release)
        return cut_response()
    if release: S["pending_release"] = release   # done, but the backend still runs the old code
    return jsonify(result="ok")

BRAIN_GROUPS, BRAIN_SPEC, BRAIN_COERCE = None, None, None
def load_brain_spec():
    """The thresholds exactly as the real backend declares them (and its own validation), read from its source."""
    global BRAIN_GROUPS, BRAIN_SPEC, BRAIN_COERCE
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "klippeye_backend.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "CONFIG_GROUPS": BRAIN_GROUPS = ast.literal_eval(node.value)
            if node.targets[0].id == "CONFIG_SPEC": BRAIN_SPEC = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == "coerce_config_value":
            ns = {"math": math, "re": re}
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)
            BRAIN_COERCE = ns["coerce_config_value"]
load_brain_spec()

def brain_values():
    if S["brain_cfg"] is None:
        S["brain_cfg"] = {spec["key"]: copy.deepcopy(spec["default"]) for spec in BRAIN_SPEC}
    return S["brain_cfg"]

def brain_cfg_reply(ok=True, status=200, **extra):
    body = {"ok": ok, "api": 2, "values": copy.deepcopy(brain_values()), "saved": S["brain_cfg_saved"], "save_error": ""}
    body.update(extra)
    return jsonify(body), status

@app.route("/api/version")
def api_version():
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    return jsonify(ok=True, release=S["backend_release"], api=2, git={"commit": "a1b2c3d", "branch": "main"}, started=S["brain_started"], uptime=int(time.time()) % 5000 + 600,
                   python="3.11.2", has_cv2=S["brain_has_cv2"], data_dir="/home/pi/printer_data/klippeye", frontend="/home/pi/klippeye/frontend/klippeye_frontend.html")

@app.route("/api/https", methods=["GET", "POST"])
def mock_https():
    """1.93: the encrypted entrance, off (its real behaviour is tested by access_test.py with the real backend)."""
    web = S.get("web") or {}
    return jsonify(ok=True, enabled=bool(web.get("https")), port=8443, running=bool(web.get("https")), fingerprint="AB:" * 31 + "CD" if web.get("https") else None, error=None,
                   addresses=["192.168.1.50"], secure=False, nginx=bool(web.get("main")))


@app.route("/api/mqtt", methods=["GET", "POST"])
def mock_mqtt():
    """1.100: Home Assistant / MQTT, off (its real behaviour is tested by mqtt_test.py with the real backend and a broker)."""
    return jsonify(ok=True, enabled=False, host="", port=1883, tls=False, username="", base_topic="", discovery=True, discovery_prefix="homeassistant",
                   commands=True, allow_cancel=False, has_password=False, node="voron", default_base_topic="klippeye/voron", running=None)


@app.route("/api/web", methods=["GET", "POST"])
def mock_web():
    """1.94: KlippEye at the Raspberry's own address (scripts/web_front.py is tested by the backend tests)."""
    web = S.setdefault("web", {"nginx": True, "main": False, "https": False, "moved": [], "sites": {"webui": [80], "webui2": [81]}})
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        S.setdefault("web_log", []).append(bool(body.get("main")))
        if S.get("web_sudo") is False:
            return jsonify(ok=False, error="Servono i permessi di amministratore: sul Raspberry esegui  klippeye web main", command="klippeye web main", **web), 409
        if body.get("main"):
            web.update(main=True, moved=["webui"], sites={"webui": [82], "webui2": [81]})
        else:
            web.update(main=False, moved=[], sites={"webui": [80], "webui2": [81]})
    return jsonify(ok=True, port=8085, **web)


@app.route("/api/auth/status")
def mock_auth_status():
    """Release 1.2.0: password facoltativa (qui sempre spenta: la password vera si prova con access_test.py e il backend vero)."""
    return jsonify({"ok": True, "enabled": False, "logged_in": True, "network_checks": True, "allowed_hosts": [], "min_length": 6})


@app.route("/api/app/version")
def api_app_version():
    S["app_apk_hits"] += 1
    if S["brain"] == "old" or S["app_apk_status"] == 404:
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    if S["app_apk_status"] != 200:
        return jsonify(error="mock failure"), S["app_apk_status"]
    offer = S["app_apk"] or {"available": False, "reason": "nessuna app pubblicata"}
    return jsonify(dict(offer, ok=True))

# ---- recordings (backend/recorder.py, scripts/replay.py): the same answers as the real backend
REC_ID = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9._-]{1,40})?$")


def rec_find(sid):
    return next((r for r in S["recordings"] if r["id"] == sid), None)


@app.route("/api/recordings")
def mock_recordings():
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    values = brain_values()
    rows = []
    for r in sorted(S["recordings"], key=lambda x: x["id"], reverse=True):  # newest first, as the backend lists them
        row = {k: r.get(k) for k in ("id", "file", "started", "ended", "end_state", "frames", "label", "truncated", "cpu")}
        row.update(bytes=r.get("bytes", 0), live_triggers=len(r.get("live_triggers") or []), alerts=len(r.get("alerts") or []), recording=r.get("ended") is None)
        rows.append(row)
    return jsonify(ok=True, enabled=bool(values.get("record")), max_bytes=int(values.get("record_max_mb", 2000)) * 1024 ** 2,
                   used_bytes=sum(r.get("bytes", 0) for r in S["recordings"]), free_bytes=12 * 1024 ** 3,
                   status=S["rec_status"] if values.get("record") else "off", current=None, sessions=rows)


@app.route("/api/recordings/measure", methods=["GET", "POST"])
def mock_measure():
    if request.method == "POST":
        S["measure_starts"] += 1
        body = request.get_json(silent=True) or {}
        S["measure_bodies"].append(body)
        if "ids" in body and not (isinstance(body["ids"], list) and body["ids"] and all(rec_find(i) for i in body["ids"])):
            return jsonify(ok=False, error="choose at least one recording"), 400
        S["measure"] = {"state": "running", "started": int(time.time())}
        result = S.get("measure_result")
        if body.get("compare") and result:   # 1.28: the variants
            result = dict(result, compare=S.get("measure_compare") or [])
        def finish():
            S["measure"] = {"state": "done", "started": int(time.time()), "result": result}
        later(1.5, finish)
        return jsonify(ok=True, state="running")
    return jsonify(dict(S["measure"], ok=True))


@app.route("/api/recordings/delete", methods=["POST"])
def mock_recordings_delete_many():   # 1.125
    ids = (request.get_json(silent=True) or {}).get("ids") or []
    deleted = [i for i in ids if rec_find(i) is not None]
    S["recordings"] = [x for x in S["recordings"] if x["id"] not in ids]
    S["rec_posts"].append(["delete_many", ids, None])
    return jsonify(ok=True, deleted=deleted, missing=[i for i in ids if i not in deleted])


@app.route("/api/recordings/<sid>", methods=["GET", "DELETE"])
def mock_recording(sid):
    r = rec_find(sid)
    if r is None or not REC_ID.match(sid):
        return jsonify(ok=False, error="no such recording"), 404
    if request.method == "DELETE":
        S["recordings"] = [x for x in S["recordings"] if x["id"] != sid]
        S["rec_posts"].append(["delete", sid, None])
        return jsonify(ok=True)
    history = {a["id"]: a for a in S["alerts"]}  # as the backend: image and label from the alert history
    alerts = [dict(a, image=history.get(a.get("id"), {}).get("image") or a.get("image"), label=history.get(a.get("id"), {}).get("label", a.get("label"))) for a in r.get("alerts") or []]
    for a in alerts:   # 1.26.1: the picture to show (the history's, else the recorded frame of the alarm)
        a["picture"] = "/api/print/alerts/image/" + a["image"] if a.get("image") else ("/api/recordings/%s/frames/%d.jpg" % (sid, a["frame"]) if isinstance(a.get("frame"), int) else None)
    return jsonify(ok=True, session=dict(r, alerts=alerts), frames=S["rec_frames"].get(sid, []))


@app.route("/api/recordings/<sid>/frames/<int:n>.jpg")
def mock_recording_frame(sid, n):
    shade = 40 + (n * 13) % 180
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 360"><rect width="540" height="360" fill="rgb(%d,%d,%d)"/><text x="20" y="60" font-size="48" fill="white">%d</text></svg>' % (shade, shade, shade, n)
    return Response(svg, mimetype="image/svg+xml")


@app.route("/api/recordings/<sid>/label", methods=["POST"])
def mock_recording_label(sid):
    r = rec_find(sid)
    body = request.get_json(silent=True) or {}
    if r is None:
        return jsonify(ok=False, error="no such recording"), 404
    if body.get("outcome") not in ("ok", "failed", None):
        return jsonify(ok=False, error="outcome must be ok, failed or null"), 400
    r["label"] = {"outcome": body.get("outcome"), "failed_at": body.get("failed_at") if body.get("outcome") == "failed" else None}
    S["rec_posts"].append(["label", sid, body])
    return jsonify(ok=True, label=r["label"])


@app.route("/api/camera/calibration")
def mock_camera_calibration():
    """Not calibrated, nothing being taken (the calibration itself is tried with the real backend: camcal_test.py)."""
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    return jsonify(ok=True, saved=None, watch={"state": "unknown"}, usable=False, draft={}, marks={"state": "idle"}, printer=None, targets=[], has_cv2=True)


@app.route("/api/local_model", methods=["GET", "POST"])
def mock_local_model():
    body = request.get_json(silent=True) or {}
    if request.method == "POST" and body.get("test"):   # 1.124: «Try the local model now»
        S["local_tests"] = S.get("local_tests", 0) + 1
        if not S["local_model"].get("available"):
            return jsonify(ok=False, error="There is no local model in use"), 409
        return jsonify(ok=True, **S.get("local_test_result", {"score": 62.5, "views": {"whole": 18.0, "part": 62.5}, "best": "part", "doubt": 35, "sure": 80}))
    if request.method == "POST" and body.get("forget_false_alarms"):   # 1.125
        S["local_tests"] = S.get("local_tests", 0)
        S["false_alarms_forgotten"] = S.get("false_alarms_forgotten", 0) + 1
        S["false_alarms"] = {"person": 0, "online": 0}
        return jsonify(ok=True, forgotten=3, false_alarms=S["false_alarms"])
    return jsonify(dict(S["local_model"], ok=True, enabled=True, last=S["local_model"].get("last", {}), folders={},
                        false_alarms=S.get("false_alarms", {"person": 0, "online": 0})))


@app.route("/api/local_model/personal", methods=["POST"])
def mock_local_model_personal():
    """1.107: {"train": true} trains (the mock: trained, 31 examples); {"forget_imported": true} forgets the imported ones."""
    body = request.get_json(silent=True) or {}
    S["personal_posts"].append(body)
    personal = S["local_model"].setdefault("personal", {})
    if body.get("forget_imported"):
        personal["imported"] = []
    if body.get("train"):
        personal.update(trained=True, examples=31, failed=9, fine=22, measured={"right": 0.94})
    return jsonify(ok=True, personal=personal)


@app.route("/api/local_model/personal/export")
def mock_local_model_personal_export():
    S["personal_posts"].append({"export": True})
    import io, zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("labels.json", json.dumps({"format": 1, "pictures": {}}))
    return Response(buffer.getvalue(), mimetype="application/zip", headers={"Content-Disposition": 'attachment; filename="klippeye-examples.zip"'})


@app.route("/api/local_model/personal/import", methods=["POST"])
def mock_local_model_personal_import():
    upload = request.files.get("file")
    data = upload.read() if upload else b""
    S["personal_posts"].append({"import": upload.filename if upload else None, "bytes": len(data)})
    if not data.startswith(b"PK"):
        return jsonify(ok=False, error="not a file exported by KlippEye"), 400
    personal = S["local_model"].setdefault("personal", {})
    personal["imported"] = (personal.get("imported") or []) + [{"origin": "voron", "printer": "voron", "pictures": 40}]
    return jsonify(ok=True, imported=40, personal=personal)


@app.route("/api/print/review")
def mock_print_review():
    """1.103: the last print that ended and is not answered yet (S["review"]; the real one: print_review.py)."""
    return jsonify(ok=True, enabled=S.get("review_enabled", True), review=S.get("review"), problems=["spaghetti", "detached", "layer_shift", "nozzle_blob", "clog", "warping", "stringing", "under_extrusion", "over_extrusion", "elephant_foot", "ghosting", "overhangs", "supports", "rough_surface", "other"])


@app.route("/api/print/review/<rid>/<int:n>.jpg")
def mock_print_review_picture(rid, n):
    shade = 40 + (n * 13) % 180
    return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 214"><rect width="320" height="214" fill="rgb(%d,%d,%d)"/></svg>' % (shade, shade, shade), mimetype="image/svg+xml")


@app.route("/api/print/review/<rid>", methods=["POST"])
def mock_print_review_answer(rid):
    body = request.get_json(force=True) or {}
    S["review_answers"].append(dict(body, id=rid))
    S["review"] = None
    return jsonify(ok=True, review=None, alarms_marked=2 if body.get("outcome") == "ok" else 0)


@app.route("/api/print/alerts/image/<name>")
def mock_alert_image(name):
    return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 90 60"><rect width="90" height="60" fill="#555"/></svg>', mimetype="image/svg+xml")


@app.route("/api/print/alerts/precision")
def mock_alert_precision():
    """1.28: the same computation as the backend (ai_precision.py) on the mock's alarms and recordings."""
    import ai_precision
    current = (S.get("brain_cfg") or {}).get("ai_min_confidence", 70)
    return jsonify(dict(ai_precision.precision(ai_precision.merge(S["alerts"], S["recordings"]), current), ok=True))


@app.route("/api/print/alerts/history")
def mock_alert_history():
    return jsonify(ok=True, alerts=S["alerts"][: int(request.args.get("limit", 20))])


@app.route("/api/print/alerts/<aid>/label", methods=["POST"])
def mock_alert_label(aid):
    body = request.get_json(silent=True) or {}
    for alert in S["alerts"]:
        if alert["id"] == aid:
            alert["label"] = body.get("label")
            S["rec_posts"].append(["alert", aid, body])
            return jsonify(ok=True, alert=alert)
    for r in S["recordings"]:   # 1.26.2: an alarm no longer in the history, labelled in its recording
        for alert in r.get("alerts") or []:
            if alert.get("id") == aid and body.get("session") in (None, r["id"]):
                alert["label"] = body.get("label")
                S["rec_posts"].append(["alert", aid, body])
                return jsonify(ok=True, alert=alert)
    return jsonify(ok=False, error="no such alarm"), 404


@app.route("/api/logos")
def api_logos():
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    return jsonify(ok=True, files=list(S["logos"]))

@app.route("/logos/<name>")
def logo_file(name):
    if name not in S["logos"]:
        return jsonify(ok=False, error="logo non trovato"), 404
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><rect width="100" height="40" fill="#e0b000"/><path d="M10 10h20v20H10z" fill="#111"/></svg>'
    return Response(svg, mimetype="image/svg+xml")

@app.route("/app/KlippEye.apk")
def app_apk_file():
    S["app_apk_downloads"] += 1
    return Response(b"PK\x03\x04" + b"\0" * 2000, mimetype="application/vnd.android.package-archive", headers={"Content-Disposition": "attachment; filename=KlippEye-1.0.1.apk"})

@app.route("/api/backend/config", methods=["GET", "POST"])
def api_brain_config():
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    if request.method == "GET":
        return brain_cfg_reply(defaults={spec["key"]: spec["default"] for spec in BRAIN_SPEC}, groups=BRAIN_GROUPS,
                               spec=[{k: v for k, v in spec.items() if k != "pattern"} for spec in BRAIN_SPEC], path="/home/pi/printer_data/klippeye/brain.json",
                               running=S["brain_running"], has_cv2=S["brain_has_cv2"])
    if S["brain_cfg_fail"]:
        return jsonify(error="mock failure"), S["brain_cfg_fail"]
    body = request.get_json(silent=True) or {}
    changes = body.get("values") if isinstance(body.get("values"), dict) else body
    S["brain_cfg_log"].append(copy.deepcopy(changes))
    errors, clean = {}, {}
    by_key = {spec["key"]: spec for spec in BRAIN_SPEC}
    for key, raw in changes.items():
        if key not in by_key: errors[key] = "impostazione sconosciuta"; continue
        try: clean[key] = BRAIN_COERCE(by_key[key], raw)
        except ValueError as error: errors[key] = str(error)
    if errors:
        return brain_cfg_reply(False, 400, errors=errors)
    changed = [k for k, v in clean.items() if brain_values().get(k) != v]
    brain_values().update(clean)
    S["brain_cfg_saved"] = True
    return brain_cfg_reply(changed=changed)

@app.route("/api/backend/config/reset", methods=["POST"])
def api_backend_config_reset():
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    body = request.get_json(silent=True) or {}
    keys = body.get("keys") if isinstance(body.get("keys"), list) else [spec["key"] for spec in BRAIN_SPEC]
    S["brain_cfg_log"].append({"reset": keys})
    for spec in BRAIN_SPEC:
        if spec["key"] in keys: brain_values()[spec["key"]] = copy.deepcopy(spec["default"])
    S["brain_cfg_saved"] = True
    return brain_cfg_reply(changed=keys)

@app.route("/api/print/snapshot")
def api_print_snapshot():
    buf = io.BytesIO(); Image.new("RGB", (108, 72), (70, 90, 120)).save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png")

@app.route("/api/macros/list")
def macros_list():
    extra = [{"name": "AXES_SHAPER_CALIBRATION", "file": "macros/shaper.cfg", "description": "Axes shaper calibration", "params": [{"name": "FREQ_START", "default": "5", "type": "int"}, {"name": "FREQ_END", "default": "133", "type": "int"}], "has_params": True, "source": "brain"}] if S.get("long_macro") else []
    return jsonify(ok=True, count=6 + len(extra), shaketune_found=0, macros=extra + [
        {"name": "CLEAN_NOZZLE", "file": "macros/clean.cfg", "description": "Clean", "params": [], "has_params": False, "source": "brain"},
        {"name": "PARK_TEST", "file": "macros/park.cfg", "description": "Park test", "params": [{"name": "X", "default": "100", "type": "int"}, {"name": "Y", "default": "50", "type": "int"}], "has_params": True, "source": "brain"},
        {"name": "SHAPER_CALIBRATE", "file": "macros/shaper.cfg", "description": "dummy", "params": [], "has_params": False, "source": "shaketune_scan"}]
        + [{"name": name, "file": "", "description": "", "params": [], "has_params": False, "source": "klipper"} for name in ("LUCI_OFF", "LUCI_ON", "VAR_LUCI")])
@app.route("/api/calibration/selected", methods=["GET", "POST"])
def calib_selected():
    if request.method == "POST":
        S["calib_selected"] = (request.get_json(force=True, silent=True) or {}).get("selected", [])
        return jsonify(ok=True, count=len(S["calib_selected"]))
    return jsonify(ok=True, selected=S["calib_selected"], count=len(S["calib_selected"]))
@app.route("/api/logs/list")
def logs_list():
    files = [{"name": "klippy.log", "size": 2048000, "size_h": "2.0 MB", "modified": NOW, "modified_str": "20/10 14:00"},
             {"name": "moonraker.log", "size": 51200, "size_h": "50.0 KB", "modified": NOW-10, "modified_str": "20/10 13:59"},
             {"name": "crowsnest.log", "size": 900, "size_h": "0.9 KB", "modified": NOW-20, "modified_str": "20/10 13:58"}]
    return jsonify(dir="/home/pi/printer_data/logs", files=files, count=len(files))
@app.route("/api/logs/content")
def logs_content():
    return jsonify(file=request.args.get("file"), content="line1\nline2 error here\nline3\n", lines=3)
@app.route("/api/update/channel", methods=["GET", "POST"])
def api_update_channel():
    if request.method == "POST":
        channel = (request.get_json(silent=True) or {}).get("channel")
        S["channel_posts"].append(channel)
        if channel not in ("stable", "dev"):
            return jsonify(ok=False, error="Unknown update channel."), 400
        changed = channel != S["update_channel"]
        S["update_channel"] = channel
        return jsonify(ok=True, channel=channel, changed=changed)
    return jsonify(ok=True, channel=S["update_channel"], listed=S["update_channel"] is not None, channels=["stable", "dev"])


@app.route("/api/diagnose")
def api_diagnose():
    return Response("KlippEye diagnostic report\n== KlippEye\nrelease: 1.0.0\n", mimetype="text/plain", headers={"Content-Disposition": 'attachment; filename="klippeye-diagnose-20261027-1200.txt"'})


@app.route("/api/logs/download")
def logs_download():
    # like the backend's send_file(as_attachment=True)
    return Response("log of " + request.args.get("file", ""), mimetype="text/plain", headers={"Content-Disposition": "attachment; filename=" + request.args.get("file", "")})
ALL_MD = """## 1. Errori / warning / stack-trace rilevanti

| File | Messaggio | Gravità | Spiegazione |
|------|-----------|---------|-------------|
| **telegram.log** | `telegram.error.InvalidToken: The token `...` was rejected by the server.` | **Error** | Il bot Telegram non è più valido (token revocato o errato). Non blocca Klipper ma impedisce le notifiche. |
| **moonraker.log** | `404 GET /server/files/content?root=config&path=printer.cfg` | **Warning** | Moonraker non trova il file richiesto dall'API. Di solito indica un percorso sbagliato o che il file non esiste. |
| **moonraker.log** | `Git Repo klipper: Warnings detected: Repo has untracked source files [...]` | **Warning** | File non tracciati nel repo Klipper (non committati). |
| **moonraker.log** | `Git Repo crowsnest: Warnings detected: Repo not on official remote/branch, expected: origin/master, detected: origin/main` | **Warning** | Il repo crowsnest è su un branch non ufficiale; può causare incompatibilità con le versioni future. |
| **webrtc.log** | `ConnectionError: HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: /bot123456789:AAAALONGTOKENabcdefghijklmnopqrstuvwxyz0123456789/getUpdates` | **Error** | Impossibile raggiungere /home/pi/printer_data/logs/webrtc_very_long_unbroken_path_name_for_overflow_testing/stream_manager_worker_0001.log |
| **klippy.log** | `TMC 'stepper_x' reports error: GSTAT: 00000001 reset=1(Reset)` | **Critico** | Il driver TMC ha subito un reset: tipico di un calo di tensione o di un cablaggio instabile. |

## 2. Cause probabili

- **Telegram**: il token del bot è stato rigenerato da BotFather oppure è stato copiato male in `telegram.conf`.
- **Moonraker 404**: un client (un'interfaccia o un'app) chiede `printer.cfg` con un percorso che non esiste nella root `config`.
- **Git warnings**: aggiornamenti manuali dei repo o branch diverso da quello atteso da Moonraker.
  - Per Klipper: file locali modificati senza commit.
  - Per crowsnest: branch `main` al posto di `master`.
- **TMC reset**: alimentazione 24 V instabile o connettore del driver allentato.

## 3. Fix concreti

1. Rigenera il token con BotFather e aggiornalo:

```bash
nano ~/printer_data/config/telegram.conf
sudo systemctl restart moonraker-telegram-bot
curl -s "https://api.telegram.org/bot<TOKEN>/getMe" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['username'])"
```

2. Riallinea il repo di crowsnest al branch ufficiale:

```bash
cd ~/crowsnest
git fetch origin
git checkout master
git pull
```

3. Dopo aver controllato i cablaggi del driver, esegui dalla console:

```gcode
FIRMWARE_RESTART
```

## 4. Serve un riavvio?

| Azione | Necessaria | Motivo |
|--------|------------|--------|
| FIRMWARE_RESTART | Sì | Dopo il reset del driver TMC |
| KLIPPER RESTART | No | Nessuna modifica a printer.cfg |
| Controllo hardware | Consigliato | Cablaggio e alimentazione del driver X |

## 5. Priorità

1. **Prima**: controllare alimentazione e cablaggio del driver X (rischio durante la stampa).
2. **Poi**: sistemare il branch di crowsnest.
3. **Infine**: rigenerare il token Telegram, solo se vuoi le notifiche.

**Conclusione rapida:** nessun errore blocca la stampante ora, ma il reset del driver TMC va verificato prima della prossima stampa lunga.
"""
SINGLE_MD = """**1) Tipo di log**
Registro di Moonraker: API, aggiornamenti e plugin.

**2) Stato generale**
Il servizio funziona, con alcuni avvisi non bloccanti.

**3) Errori critici**
Nessun errore critico in questo file.

**4) Avvisi e fix immediato**
- `404 GET /server/files/content?root=config&path=printer.cfg`: il file non esiste con quel percorso. Controlla che `printer.cfg` sia nella root `config`.
- `Git Repo crowsnest: Repo not on official remote/branch`: esegui `git checkout master` in `~/crowsnest`.

**5) Conclusione**
Tutto a posto, solo manutenzione consigliata.
"""
@app.route("/api/logs/analyze", methods=["GET", "POST"])
def logs_analyze():
    if not S["ai_key_ok"]:
        return jsonify(error="Chiave API non configurata", howto="Imposta la key"), 401
    if request.args.get("simple") or S.get("ai_simple"):
        return jsonify(analysis="Conclusione rapida: tutto ok, nessun errore critico.\n- klippy.log: avvio normale\n- Warning: fallback camera\n- Error: TMC error su driver", used_files=["klippy.log", "moonraker.log"], model="llama-3", provider="groq")
    if request.args.get("file"):
        return jsonify(analysis=SINGLE_MD, used_files=[request.args.get("file")], model="openai/gpt-oss-20b", provider="groq")
    return jsonify(analysis=ALL_MD, used_files=["klippy.log", "moonraker.log", "crowsnest.log", "telegram.log", "webui.log", "KlipperScreen.log", "webrtc.log", "sonar.log"], model="openai/gpt-oss-20b", provider="groq")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import ai_services  # noqa: E402  (the same rules as the real backend)

AI_MODELS = {
    "groq": [{"id": "qwen/qwen3.8-27b", "vision": True}, {"id": "openai/gpt-oss-20b", "vision": None}, {"id": "llama-3.1-8b-instant", "vision": False}],
    "gemini": [{"id": "gemini-3.8-flash", "vision": True}, {"id": "gemini-3.8-flash-lite", "vision": True}],
}


def ai_cfg():
    if S["ai_cfg"] is None:
        S["ai_cfg"] = {"keys": {"groq": "gsk_" + "x" * 40 + "AB12"}} if S["ai_key_ok"] else {}
    return S["ai_cfg"]


@app.route("/api/ai/config", methods=["GET", "POST"])
def ai_config():
    if S["brain"] == "old":
        return jsonify(configured=S["ai_key_ok"], provider="groq", model="", key_preview="…AB12")
    if request.method == "GET":
        return jsonify(ai_services.summary(ai_cfg()))
    body = request.get_json(silent=True) or {}
    S["ai_posts"].append(body)
    cfg, problem = ai_services.apply(ai_cfg(), body)
    if problem:
        return jsonify(ok=False, error={"key_short": "chiave API troppo corta"}.get(problem, problem)), 400
    S["ai_cfg"] = cfg
    return jsonify(dict(ai_services.summary(cfg), ok=True))


@app.route("/api/ai/models")
def ai_models():
    provider = request.args.get("provider", "")
    S["ai_model_reads"].append(provider)
    if not ai_services.normalize(ai_cfg())["keys"].get(provider):
        return jsonify(ok=False, code="no_key", error="nessuna chiave salvata per questo servizio"), 400
    if S["ai_models_fail"] == provider:
        return jsonify(ok=False, code="http_401", error="Invalid API Key"), 502
    return jsonify(ok=True, provider=provider, models=AI_MODELS.get(provider, [{"id": provider + "-model-1", "vision": None}]))
@app.route("/api/print/detector/status")
def det_status():
    return jsonify(ok=True, enabled=True, running=True, stats=dict({"status": S["detector_status"], "last_score": 12, "frames_checked": 34}, **S["detector_extra"]),
                   real_print_started=True, progress=42, local_available=bool(S["local_model"].get("available")), local_enabled=True)
@app.route("/api/print/last_analysis")
def last_analysis():
    if not S["has_analysis"]:
        return jsonify(ok=True, has_analysis=False)
    inner = json.dumps({"spaghetti": {"detected": False, "confidence": 12, "note": "layers regolari"}, "empty_bed": {"detected": False, "confidence": 3},
                        "layer_shift": {"detected": False, "confidence": 5}, "warping": {"detected": S["analysis_action"] != "CONTINUA", "confidence": 61},
                        "action": S["analysis_action"], "summary": "Stampa regolare, nessun difetto rilevato."})
    return jsonify(ok=True, has_analysis=True, timestamp="2026-10-20 14:00:00", model="llama-vision", progress=42,
                   analysis={"analysis": inner, "action": S["analysis_action"], "summary": "Stampa regolare." if S["analysis_action"] in ("CONTINUA", "CONTINUE") else "Spaghetti sul piatto, il pezzo si è staccato."},
                   alert_id="20261020-140000", image="20261020-140000-now.jpg", answer=S["ai_answer"])
@app.route("/api/print/last_analysis/answer", methods=["POST"])
def last_analysis_answer():
    answer = (request.get_json(force=True, silent=True) or {}).get("answer")
    if answer not in ("right", "false", "ignore"):
        return jsonify(ok=False, error="answer must be right, false or ignore"), 400
    S["ai_answer"] = answer
    S["ai_answers"].append(answer)
    return jsonify(ok=True, answer=answer)

@app.route("/server/info")
def server_info():
    """Moonraker's components (1.44: the dashboard shows the queue, the power devices… only when Moonraker has them)."""
    components = ["database", "file_manager", "klippy_apis", "machine", "data_store", "shell_command", "proc_stats", "history", "octoprint_compat", "update_manager"]
    components += [name for flag, name in (("queue_on", "job_queue"), ("power_on", "power"), ("spoolman_on", "spoolman"), ("timelapse_on", "timelapse")) if S.get(flag)]
    return jsonify(result={"klippy_connected": True, "klippy_state": S["webhooks"], "components": components, "failed_components": [], "moonraker_version": "v0.9.3-0-g000000", "api_version": [1, 5, 0]})
def queue_status():
    now = time.time()
    return {"queued_jobs": [{"filename": j["filename"], "job_id": j["job_id"], "time_added": j["time_added"], "time_in_queue": now - j["time_added"]} for j in S["queue"]], "queue_state": S["queue_state"]}
@app.route("/server/job_queue/status")
def job_queue_status():
    if not S["queue_on"]: return jsonify(error={"code": 404, "message": "Not Found"}), 404
    return jsonify(result=queue_status())
@app.route("/server/job_queue/job", methods=["POST", "DELETE"])
def job_queue_job():
    if not S["queue_on"]: return jsonify(error={"code": 404, "message": "Not Found"}), 404
    if request.method == "DELETE":
        if request.args.get("all") == "true":
            S["queue"] = []; S["queue_log"].append("CLEAR")
        else:
            ids = request.args.get("job_ids", "").split(",")
            S["queue"] = [j for j in S["queue"] if j["job_id"] not in ids]; S["queue_log"].append("DELETE:" + ",".join(ids))
        return jsonify(result=queue_status())
    body = request.get_json(force=True, silent=True) or {}
    if body.get("reset"): S["queue"] = []
    for name in body.get("filenames", []):
        S["queue_ids"] += 1
        S["queue"].append({"filename": name, "job_id": "%010X" % S["queue_ids"], "time_added": time.time()})
    S["queue_log"].append(("RESET:" if body.get("reset") else "ADD:") + ",".join(body.get("filenames", [])))
    return jsonify(result=queue_status())
@app.route("/server/job_queue/<action>", methods=["POST"])
def job_queue_action(action):
    if not S["queue_on"]: return jsonify(error={"code": 404, "message": "Not Found"}), 404
    if action == "pause": S["queue_state"] = "paused"
    elif action == "start": S["queue_state"] = "ready"
    elif action == "jump":
        uid = request.args.get("job_id", "")
        S["queue"] = [j for j in S["queue"] if j["job_id"] == uid] + [j for j in S["queue"] if j["job_id"] != uid]
    S["queue_log"].append(action.upper())
    return jsonify(result=queue_status())

@app.route("/server/files/timelapse/<path:p>", methods=["GET", "DELETE"])
def timelapse_file(p):
    if p not in S["timelapse_files"]: return jsonify(error={"code": 404, "message": "File does not exist"}), 404
    if request.method == "DELETE":
        del S["timelapse_files"][p]; S["timelapse_log"].append("DELETE:" + p)
        return jsonify(result={"item": {"path": p, "root": "timelapse"}, "action": "delete_file"})
    if p.endswith(".jpg"): return send_file(png(160, 120), mimetype="image/png")
    return Response(b"\x00" * 64, mimetype="video/mp4")
@app.route("/machine/timelapse/settings", methods=["GET", "POST"])
def timelapse_settings():
    if not S["timelapse_on"]: return jsonify(error={"code": 404, "message": "Not Found"}), 404
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        for k, v in body.items():
            if k in S["timelapse_settings"] and k not in S["timelapse_settings"]["blockedsettings"]:
                S["timelapse_settings"][k] = v
        S["timelapse_log"].append("SET:" + json.dumps(body, sort_keys=True))
    return jsonify(result=S["timelapse_settings"])
@app.route("/machine/timelapse/lastframeinfo")
def timelapse_frames():
    return jsonify(result={"count": S["timelapse_frames"], "lastframefile": "frame%06d.jpg" % S["timelapse_frames"] if S["timelapse_frames"] else ""})
@app.route("/machine/timelapse/render", methods=["POST"])
def timelapse_render():
    S["timelapse_log"].append("RENDER")
    def done():
        S["timelapse_files"]["timelapse_Bracket_new.mp4"] = time.time(); S["timelapse_files"]["timelapse_Bracket_new.jpg"] = time.time(); S["timelapse_frames"] = 0
    later(1.0, done)
    return jsonify(result={"status": "started"})

@app.route("/server/spoolman/status")
def spoolman_status():
    if not S["spoolman_on"]: return jsonify(error={"code": 404, "message": "Not Found"}), 404
    return jsonify(result={"spoolman_connected": S["spoolman_connected"], "pending_reports": [], "spool_id": S["spool_id"]})
@app.route("/server/spoolman/spool_id", methods=["GET", "POST"])
def spoolman_spool_id():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        S["spool_id"] = body.get("spool_id")
        S["spool_log"].append("SET:%s" % S["spool_id"])
    return jsonify(result={"spool_id": S["spool_id"]})
@app.route("/server/spoolman/proxy", methods=["POST"])
def spoolman_proxy():
    body = request.get_json(force=True, silent=True) or {}
    path = body.get("path", "")
    if not S["spoolman_connected"]:
        return jsonify(result={"response": None, "error": {"status_code": 503, "message": "Spoolman server not available"}})
    if path == "/v1/spool":
        return jsonify(result={"response": S["spools"], "error": None})
    if path.startswith("/v1/spool/"):
        spool = next((x for x in S["spools"] if str(x["id"]) == path.rsplit("/", 1)[1]), None)
        if spool: return jsonify(result={"response": spool, "error": None})
        return jsonify(result={"response": None, "error": {"status_code": 404, "message": "No spool"}})
    return jsonify(result={"response": None, "error": {"status_code": 404, "message": "Unknown path"}})

def history_now(job):
    """A copy of the job timed from this request, not from the reset (1.99): the Benchy stays "a minute ago" and on the
    page's today even when a test starts just before midnight in Rome (the browser's time zone) and loads just after."""
    out = copy.deepcopy(job)
    now = time.time()
    try:
        from zoneinfo import ZoneInfo
        import datetime
        local = datetime.datetime.fromtimestamp(now, ZoneInfo("Europe/Rome"))
        since_midnight = local.hour * 3600 + local.minute * 60 + local.second
    except Exception:
        since_midnight = 86400
    shift = (now - S.get("history_made", now)) + max(0, 120 - since_midnight)
    for key in ("start_time", "end_time"):
        if isinstance(out.get(key), (int, float)):
            out[key] += shift
    return out

@app.route("/server/history/list")
def history_list():
    if S["history_mode"] == "missing": return jsonify(error={"code": 404, "message": "Not Found"}), 404
    limit, start = int(request.args.get("limit", 50)), int(request.args.get("start", 0))
    jobs = S["history"] if request.args.get("order", "desc") == "desc" else list(reversed(S["history"]))
    return jsonify(result={"count": len(jobs), "jobs": [history_now(j) for j in jobs[start:start + limit]]})
@app.route("/server/history/totals")
def history_totals():
    if S["history_mode"] == "missing": return jsonify(error={"code": 404, "message": "Not Found"}), 404
    return jsonify(result={"job_totals": S["history_totals"], "auxiliary_totals": []})
@app.route("/server/history/job", methods=["GET", "DELETE"])
def history_job():
    uid = request.args.get("uid", "")
    found = [j for j in S["history"] if j["job_id"] == uid]
    if not found: return jsonify(error={"code": 404, "message": "Invalid job uid: %s" % uid}), 404
    if request.method == "DELETE":
        S["history"] = [j for j in S["history"] if j["job_id"] != uid]
        S["history_log"].append("DELETE:" + uid)
        return jsonify(result={"deleted_jobs": [uid]})
    return jsonify(result={"job": history_now(found[0])})
@app.route("/server/history/reset_totals", methods=["POST"])
def history_reset_totals():
    last = S["history_totals"]
    S["history_totals"] = {k: 0 for k in last}
    S["history_log"].append("RESET")
    return jsonify(result={"last_totals": last})

@app.route("/server/database/item", methods=["GET", "POST"])
def db_item():
    mode = S["db_mode"]
    if mode == "no_route":
        return Response("<!doctype html><title>404 Not Found</title><h1>Not Found</h1>", status=404, mimetype="text/html")
    if mode == "down":
        return Response("Bad Gateway", status=502)
    if request.method == "GET":
        ns, key = request.args.get("namespace", ""), request.args.get("key", "")
        S["db_log"].append(("GET", ns, key))
        if key:
            k = ns + "/" + key
            if k not in S["db"]:
                return jsonify(error={"code": 404, "message": "Key '%s' in namespace '%s' not found" % (key, ns)}), 404
            return jsonify(result={"namespace": ns, "key": key, "value": copy.deepcopy(S["db"][k])})
        whole = {k.split("/", 1)[1]: copy.deepcopy(v) for k, v in S["db"].items() if k.split("/", 1)[0] == ns}
        if not whole:
            return jsonify(error={"code": 404, "message": "Namespace '%s' not found" % ns}), 404
        return jsonify(result={"namespace": ns, "value": whole})
    body = request.get_json(silent=True) or {}
    ns, key = body.get("namespace", ""), body.get("key", "")
    S["db_log"].append(("POST", ns, key))
    if mode == "refuse":
        return jsonify(error={"code": 403, "message": "Forbidden"}), 403
    S["db"][ns + "/" + key] = copy.deepcopy(body.get("value"))
    return jsonify(result={"namespace": ns, "key": key, "value": body.get("value")})

@app.route("/server/webcams/list")
def webcams_list():
    return jsonify(result={"webcams": S["webcams"]})

# 1.79: Moonraker reads a file's metadata again
@app.route("/server/files/metascan", methods=["GET", "POST"])
def metascan():
    S.setdefault("metascan_log", []).append(request.args.get("filename", ""))
    return jsonify(result={"filename": request.args.get("filename", ""), "estimated_time": 7260})

# 1.76: what is plugged into the Raspberry (Moonraker's /machine/peripherals/*)
# 1.80: the files of SHAPER_CALIBRATE, made up (a resonance at 52 Hz on X, at 44 Hz on Y) and read by the real
# backend/shaper_data.py, so the page draws what the service would give.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import shaper_data  # noqa: E402

def shaper_pulses(name, freq, z=0.1):
    df = math.sqrt(1 - z * z)
    t_d = 1.0 / (freq * df)
    K = math.exp(-z * math.pi / df)
    if name == "zv":
        return [1, K], [0, 0.5 * t_d]
    if name == "mzv":
        K = math.exp(-0.75 * z * math.pi / df)
        a1 = 1 - 1 / math.sqrt(2)
        return [a1, (math.sqrt(2) - 1) * K, a1 * K * K], [0, 0.375 * t_d, 0.75 * t_d]
    if name == "ei":
        a1 = 0.25 * 1.05
        return [a1, 0.5 * 0.95 * K, a1 * K * K], [0, 0.5 * t_d, t_d]
    V2 = 0.05 ** 2
    X = (V2 * (math.sqrt(1 - V2) + 1)) ** (1 / 3)
    a1 = (3 * X * X + 2 * X + 3 * V2) / (16 * X)
    a2 = (0.5 - a1) * K
    return [a1, a2, a2 * K, a1 * K ** 3], [0, 0.5 * t_d, t_d, 1.5 * t_d]

def shaper_response(pulses, freq, z=0.1):
    A, T = pulses
    omega = 2 * math.pi * freq
    omega_d = omega * math.sqrt(1 - z * z)
    s = c = 0.0
    for a, t in zip(A, T):
        w = a * math.exp(-z * omega * (T[-1] - t))
        s += w * math.sin(omega_d * t)
        c += w * math.cos(omega_d * t)
    return math.sqrt(s * s + c * c) / sum(A)

def shaper_csv(peak):
    shapers = [("zv", peak * 1.12), ("mzv", peak), ("ei", peak * 1.25), ("2hump_ei", peak * 1.6)]
    pulses = [shaper_pulses(n, f) for n, f in shapers]
    rows = ["freq,psd_x,psd_y,psd_z,psd_xyz," + ",".join("%s(%.1f)" % (n, f) for n, f in shapers)]
    freq = 5.0
    while freq <= 200:
        main = 4.0e3 / (1 + ((freq - peak) / 4.0) ** 2) + 3.0e2 / (1 + ((freq - peak * 1.8) / 6.0) ** 2) + 20.0
        rows.append("%.1f,%.3e,%.3e,%.3e,%.3e," % (freq, main, main * 0.1, main * 0.05, main * 1.15) + ",".join("%.3f" % shaper_response(p, freq) for p in pulses))
        freq += 0.78
    return "\n".join(rows) + "\n"

SHAPER_DIR = os.path.join("/tmp", "klippeye-mock-shaper-%d" % PORT)

def shaper_dirs():
    os.makedirs(SHAPER_DIR, exist_ok=True)
    wanted = {"calibration_data_x_20261109_221500.csv": 52.0, "calibration_data_y_20261109_222300.csv": 44.0} if S.get("shaper_files") else {}
    for name in os.listdir(SHAPER_DIR):
        if name not in wanted:
            os.remove(os.path.join(SHAPER_DIR, name))
    for index, (name, peak) in enumerate(wanted.items()):
        full = os.path.join(SHAPER_DIR, name)
        if not os.path.exists(full):
            with open(full, "w") as handle:
                handle.write(shaper_csv(peak))
            os.utime(full, (NOW - 600 + index * 480, NOW - 600 + index * 480))
    return [SHAPER_DIR]

@app.route("/api/shaper/files")
def api_shaper_files():
    return jsonify(files=shaper_data.list_files(shaper_dirs()))

@app.route("/api/shaper/data")
def api_shaper_data():
    try:
        args = request.args
        shaper_data.KLIPPER_FOUND.clear()  # the mock's console changes between tests
        return jsonify(shaper_data.read(args.get("name", ""), shaper_dirs(), scv=shaper_data.number_arg(args.get("scv"), 5.0, 0.1, 100.0),
                                        mode="klipper" if args.get("mode") == "klipper" else "measured",
                                        max_smoothing=shaper_data.number_arg(args.get("max_smoothing"), None, 0.05, 1.0),
                                        sources=[lambda: [entry["message"] for entry in S["console_extra"]]]))
    except shaper_data.ShaperError as error:
        return jsonify(error=str(error)), 404 if str(error) == "file not found" else 400

# 1.81: the earlier versions of the config files, kept by the real backend/config_versions.py (a fresh folder at each reset)
import config_versions  # noqa: E402
VERSION_STORES = {}

def versions_store():
    if EPOCH[0] not in VERSION_STORES:
        VERSION_STORES[EPOCH[0]] = config_versions.ConfigVersions(os.path.join("/tmp", "klippeye-mock-versions-%d-%d-%d" % (PORT, os.getpid(), EPOCH[0])))
    return VERSION_STORES[EPOCH[0]]

@app.route("/api/config/versions", methods=["GET", "POST"])
def api_config_versions():
    try:
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            S.setdefault("versions_log", []).append(body.get("path"))
            return jsonify(ok=True, version=versions_store().add(body.get("path"), body.get("content"), body.get("reason") or "save"))
        return jsonify(ok=True, versions=versions_store().list(request.args.get("path")))
    except config_versions.VersionError as error:
        return jsonify(ok=False, error=str(error)), 400

@app.route("/api/config/versions/<version_id>")
def api_config_version(version_id):
    try:
        return jsonify(ok=True, content=versions_store().read(request.args.get("path"), version_id))
    except config_versions.VersionError as error:
        return jsonify(ok=False, error=str(error)), 404

@app.route("/machine/peripherals/serial")
def periph_serial():
    return jsonify(result={"serial_devices": [{"device_type": "usb", "device_path": "/dev/ttyACM0", "device_name": "ttyACM0", "driver_name": "cdc_acm", "manufacturer": "Klipper", "product": "stm32h723xx",
        "path_by_id": "/dev/serial/by-id/usb-Klipper_stm32h723xx_1D0028000E51313433343333-if00", "path_by_hardware": "/dev/serial/by-path/platform-xhci-hcd.0-usb-0:1:1.0"}]})
@app.route("/machine/peripherals/usb")
def periph_usb():
    return jsonify(result={"usb_devices": [{"vendor_id": "1d50", "product_id": "614e", "manufacturer": "Klipper", "product": "stm32h723xx", "class": "Communications"},
        {"vendor_id": "046d", "product_id": "0825", "manufacturer": "Logitech", "product": "Webcam C270", "class": "Miscellaneous"}]})
@app.route("/machine/peripherals/video")
def periph_video():
    return jsonify(result={"v4l2_devices": [{"device_name": "video0", "device_path": "/dev/video0", "camera_name": "C270 HD WEBCAM", "driver_name": "uvcvideo", "hardware_bus": "usb-xhci-hcd.0-1.2", "path_by_id": "/dev/v4l/by-id/usb-046d_C270_HD_WEBCAM-video-index0"}], "libcamera_devices": []})
@app.route("/machine/peripherals/canbus")
def periph_can():
    S.setdefault("can_queries", 0)
    S["can_queries"] += 1
    return jsonify(error={"code": 404, "message": "Interface can0 not found"}), 404

# 1.70: scheduled prints, as the KlippEye service keeps them (backend/print_schedule.py); its clock ticks at each read here
@app.route("/api/schedule", methods=["GET", "POST"])
def schedule_api():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        name, at = str(body.get("filename") or "").lstrip("/"), body.get("at")
        if not name or ".." in name: return jsonify(ok=False, error="non è un file della stampante"), 400
        if not isinstance(at, (int, float)) or at < time.time() - 60: return jsonify(ok=False, error="quest'orario è già passato"), 400
        entry = {"id": "s%d" % (len(S["schedule"]) + 1), "filename": name, "at": int(at), "created": int(time.time()), "status": "waiting"}
        S["schedule"].append(entry)
        return jsonify(ok=True, entry=entry)
    now = time.time()
    for e in S["schedule"]:
        if e["status"] == "waiting" and e["at"] <= now:
            if S["printing"]: e.update(status="missed", reason="busy", finished=int(now))
            else: e.update(status="started", finished=int(now)); S["schedule_log"].append("START:" + e["filename"])
    return jsonify(ok=True, entries=sorted(S["schedule"], key=lambda e: e["at"]), now=int(now))

@app.route("/api/schedule/<entry_id>", methods=["DELETE"])
def schedule_remove(entry_id):
    before = len(S["schedule"])
    S["schedule"] = [e for e in S["schedule"] if e["id"] != entry_id]
    return jsonify(ok=len(S["schedule"]) != before)

@app.route("/api/printers/self")
def printers_self():
    printing = S.get("printing")
    return jsonify(ok=True, name="", brand="klippeye", release="1.61.0", state="printing" if printing else "standby", filename="Benchy_0.2mm_PLA.gcode" if printing else "",
                   progress=0.42 if printing else 0, duration=1260, extruder=[215.3, 220.0], bed=[60.1, 60.0])

@app.route("/api/printers/peek")
def printers_peek():
    host = request.args.get("host", "")
    S["peek_log"].append(host)
    return jsonify(S["peers"].get(host, {"ok": False, "error": "unreachable"}))

@app.route("/server/webcams/post_item", methods=["POST"])
def webcams_post():
    body = request.get_json(force=True, silent=True) or {}
    S["webcam_log"].append(("post", body))
    uid = body.get("uid")
    others = [c for c in S["webcams"] if c.get("uid") != uid]
    if any(c.get("name") == body.get("name") for c in others):
        return jsonify(error={"code": 400, "message": "Webcam named '%s' already exists" % body.get("name")}), 400
    old = next((c for c in S["webcams"] if uid and c.get("uid") == uid), None)
    if old is not None and old.get("source") == "config":
        return jsonify(error={"code": 400, "message": "Cannot overwrite webcam defined in moonraker.conf"}), 400
    cam = dict(old or {}, **body)
    if not cam.get("uid"):
        cam["uid"] = "u-new-%d" % len(S["webcam_log"])
    cam.setdefault("source", "database")
    S["webcams"] = [cam if c is old else c for c in S["webcams"]] if old is not None else S["webcams"] + [cam]
    return jsonify(result={"webcam": cam})

@app.route("/server/webcams/delete_item", methods=["DELETE"])
def webcams_delete():
    uid = request.args.get("uid")
    S["webcam_log"].append(("delete", uid))
    cam = next((c for c in S["webcams"] if c.get("uid") == uid), None)
    if cam is None:
        return jsonify(error={"code": 404, "message": "Webcam not found"}), 404
    S["webcams"] = [c for c in S["webcams"] if c is not cam]
    return jsonify(result={"webcam": cam})

@app.route("/webcam/<path:p>")
def webcam(p):
    return Response("<html><body style='background:#123;color:#fff'>cam</body></html>", mimetype="text/html")

if __name__ == "__main__":
    import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=PORT, threaded=True)
