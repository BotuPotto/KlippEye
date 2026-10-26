"""Mock Moonraker + KlippEye backend backend used ONLY to run the dashboard headless for A/B tests."""
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

def default_state():
    return {
        "printing": False, "paused": False,
        "webhooks": "ready", "webhooks_msg": "",
        "homed": "xyz",
        "light": 0,
        "ext_t": 215.3, "ext_target": 220, "bed_t": 60.1, "bed_target": 60,
        "gcode_log": [],           # received scripts
        "calib_selected": ["PARK_TEST", "SHAPER_CALIBRATE"],
        "long_macro": False,        # adds a macro with a very long name and parameters (the parameter form must fit its buttons)
        "ai_key_ok": True,
        "deleted": [], "delete_error": "",
        "detector_status": "scanning",
        "has_analysis": True,
        "analysis_action": "CONTINUA",
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
        "brain_release": "1.0.0", "brain_started": 1760000000,
        "brain_restart_s": 2.5,     # seconds the backend is away when it restarts
        "brain_cfg": None,          # {key: value} of the thresholds (None: the usual ones)
        "brain_cfg_saved": False, "brain_cfg_log": [], "brain_cfg_fail": 0,  # brain_cfg_fail: HTTP status the next POSTs answer with (0: they work)
        "brain_running": True, "brain_has_cv2": True,
        "app_apk": None,            # what /api/app/version offers: None (nothing published) or {"available": ..., version, code, size, sha256, built, url} / {"available": False, "reason": ...}
        "app_apk_status": 200,      # HTTP status of /api/app/version (404: a backend that does not know apps; 500: broken)
        "app_apk_hits": 0, "app_apk_downloads": 0,
        "logos": [],                # files of the logos/ folder the backend lists in /api/logos (e.g. ["voron.svg"])
        "program_key": "klippeye",   # the name of the program in Moonraker's update manager ("vzbot": an install that has not moved yet)
        "migrate": {"state": "none"},   # the state scripts/passa-a-klippeye.sh writes (and /api/migrate/status reports)
        "migrate_mode": "ok",       # ok | no_sudo (501) | fail (the script stops at step 4) | slow (1.5 s per step)
        "migrate_starts": 0,
        "brain_legacy": False,      # /api/version says this install still lives in ~/vzbot (KlippEye offers the move)
        "klippeye_info": klippeye_default_info(),   # Moonraker's entry for the update manager component "klippeye" (None: Moonraker does not know it)
        "klippeye_incoming": [],       # commits that appear in "commits_behind" once "Controlla" (refresh) is pressed
        "klippeye_new_release": "1.0.1", "klippeye_old_release": "1.0.0",
        "update_log": [],           # (action, component) of every /machine/update/* POST
        "update_error": "",         # non-empty: upgrade / rollback / recover are refused with this message (HTTP 500)
        "update_restart": "yes",    # yes: the backend restarts as Moonraker would; no: the work is done but the backend is not restarted
        "update_delay": 0.0,        # seconds before an update / rollback / recover answers
        "service_error": "",        # non-empty: service actions fail with this message (HTTP 400)
        "actions": [],              # (path, query) of every /machine/services|reboot|shutdown + restart request
        # --- Moonraker database (dashboard settings, notification service status) and Mainsail's webcams
        "db": {},                   # {"namespace/key": value}
        "db_mode": "ok",            # ok | no_route (the backend does not pass /server/database on: Flask 404 page) | refuse (403) | down (502)
        "db_log": [],               # (method, namespace, key) of every request
        "webcams": [{"name": "KlippEye", "service": "webrtc-camerastreamer", "enabled": True, "stream_url": "/webcam/webrtc", "snapshot_url": "/webcam/snapshot", "flip_horizontal": False, "flip_vertical": False, "target_fps": 15},
                    {"name": "Piatto", "service": "mjpegstreamer", "enabled": True, "stream_url": "/webcam2/?action=stream", "snapshot_url": "/webcam2/?action=snapshot", "flip_horizontal": True, "flip_vertical": False, "target_fps": 10},
                    {"name": "Go2rtc", "service": "webrtc-go2rtc", "enabled": True, "stream_url": "/go2rtc/api/webrtc?src=cam", "snapshot_url": "", "flip_horizontal": False, "flip_vertical": False, "target_fps": 15}],
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
}
OBJECTS = ["webhooks","print_stats","toolhead","extruder","heater_bed","fan","fan_generic Aux_Fan","heater_fan hotend_fan",
           "controller_fan drivers_fan","virtual_sdcard","display_status","gcode_move","bed_mesh","configfile",
           "gcode_macro PARK_TEST","gcode_macro SHAPER_CALIBRATE","gcode_macro CLEAN_NOZZLE","gcode_macro VAR_LUCI",
           "mcu","mcu EBBCan"]

def settings_now():
    out = dict(CONFIG)
    out["stepper_z"] = {"endstop_pin": S["z_pin"], "position_max": 300}
    out["cartographer"] = {"serial": "/dev/serial/by-id/usb-cartographer"}
    if S["has_screws"]:
        out["screws_tilt_adjust"] = {"screw1": [30, 30], "screw1_name": "front left", "screw2": [320, 30], "screw2_name": "front right",
                                     "screw3": [320, 320], "screw3_name": "rear right", "screw4": [30, 320], "screw4_name": "rear left", "horizontal_move_z": 5}
    if S["has_twist_section"]:
        out["axis_twist_compensation"] = {"calibrate_start_x": 30, "calibrate_end_x": 320, "calibrate_y": 175}
    return out

def commands_now():
    names = ["G28", "M84", "SAVE_CONFIG", "SET_GCODE_OFFSET", "QUERY_PROBE", "CARTOGRAPHER_AXIS_TWIST_COMPENSATION"]
    if S["has_screws"]:
        names.append("SCREWS_TILT_CALCULATE")
    names.append("Z_OFFSET_APPLY_PROBE" if S["z_apply"] == "probe" else "Z_OFFSET_APPLY_ENDSTOP")
    return {n: "help for " + n for n in names}

def status_for(keys, fields=None):
    st = {}
    p = S["printing"]
    for k in keys:
        if k == "webhooks":
            st[k] = {"state": S["webhooks"], "state_message": S["webhooks_msg"]}
        elif k == "print_stats":
            state = S.get("print_state") or ("paused" if S["paused"] else ("printing" if p else "standby"))
            st[k] = {"state": state, "filename": "Benchy_0.2mm_PLA.gcode" if p else "", "print_duration": 1260 if p else 0,
                     "total_duration": 1300 if p else 0, "filament_used": 3200 if p else 0,
                     "info": {"current_layer": 42 if p else None, "total_layer": 100 if p else None}}
        elif k == "virtual_sdcard":
            st[k] = {"progress": 0.42 if p else 0, "is_active": p, "file_position": 1000, "file_path": "Benchy_0.2mm_PLA.gcode" if p else ""}
        elif k == "display_status":
            st[k] = {"progress": 0.42 if p else 0, "message": None}
        elif k == "toolhead":
            st[k] = {"position": [120.5, 80.2, 15.3, 0], "homed_axes": S["homed"]}
        elif k == "gcode_move":
            st[k] = {"gcode_position": [120.5, 80.2, 15.3, 0], "homing_origin": [0, 0, S["z_offset"], 0]}
        elif k == "extruder":
            st[k] = {"temperature": S["ext_t"], "target": S["ext_target"]}
        elif k == "heater_bed":
            st[k] = {"temperature": S["bed_t"], "target": S["bed_target"]}
        elif k in FANS:
            st[k] = FANS[k]
        elif k == "gcode_macro VAR_LUCI":
            st[k] = {"stato_luci": S["light"]}
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
            if S["mesh"]:
                rows = []
                for r in range(7):
                    rows.append([round(0.02*((c-3)**2)/9 - 0.015*(r-3) + 0.005*((r*c)%3), 4) for c in range(7)])
                st[k] = {"profile_name": "default", "probed_matrix": rows, "mesh_matrix": rows, "profiles": {"default": {}, "adaptive": {}}}
            else:
                st[k] = {"profile_name": "", "probed_matrix": [[]], "profiles": {}}
        elif k == "output_pin caselight":
            st[k] = {"value": float(S["light"])}
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
    return jsonify({k: v for k, v in S.items() if k in ("light", "light_cmds", "light_reads", "actions", "webhooks", "webhooks_msg", "disconnected", "moonraker_down", "host_off", "services", "update_log", "brain_cfg_log", "brain_release", "brain_started", "klippeye_info", "pending_release", "logos", "migrate", "migrate_starts", "brain_legacy", "app_apk_hits", "app_apk_downloads")})
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
    if "gcode_macro VAR_LUCI" in keys:
        S["light_reads"] += 1
        if S["light_read_delay"]:
            time.sleep(S["light_read_delay"])   # slow answer: the value above is already old when it leaves
    return jsonify(result={"eventtime": 1.0, "status": snapshot})
@app.route("/printer/objects/list")
def obj_list():
    return jsonify(result={"objects": OBJECTS})
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
@app.route("/api/gcode", methods=["POST"])
def api_gcode():
    body = request.get_json(force=True, silent=True) or {}
    script = body.get("script", "")
    S["gcode_log"].append(script)
    if script in ("luci_on", "luci_off"):
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
        if name in ("klippeye", "vzbot"):
            brain_restart(S.pop("pending_release", None))
            return cut_response()
        if name == "moonraker":
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
    return jsonify(result={"gcode_store": entries})

GCODES = [("Benchy_0.2mm_PLA.gcode", NOW-3600, 123456), ("Calibration_cube_long_filename_for_wrapping_test.gcode", NOW-86400, 654321),
          ("Vase_mode.gcode", NOW-200000, 45000), ("Bracket.gcode", NOW-400000, 3456789), ("Test/Nested_part.gcode", NOW-500000, 9999)]
@app.route("/server/files/list")
def files_list():
    root = request.args.get("root", "gcodes")
    if root == "gcodes":
        return jsonify(result=[{"path": p, "modified": m, "size": s, "permissions": "rw"} for p, m, s in GCODES if p not in S.get("deleted", [])])
    files = S["cfg"]["files"]
    return jsonify(result=[{"path": p, "modified": f["modified"], "size": f["size"], "permissions": "rw"} for p, f in files.items()])
@app.route("/server/files/metadata")
def files_meta():
    fn = request.args.get("filename", "")
    return jsonify(result={"filename": fn, "estimated_time": 7260 if "Benchy" in fn else 1800, "filament_weight_total": 12.4 if "Benchy" in fn else 0,
                           "filament_total": 4200, "layer_count": 100, "thumbnails": [] if any(k in fn for k in S.get("no_thumbs", [])) else [
                               {"width": 32, "height": 32, "size": 100, "relative_path": ".thumbs/thumb-32x32.png"},
                               {"width": 300, "height": 300, "size": 900, "relative_path": ".thumbs/thumb-300x300.png"}]})
def png(w=64, h=64, color=(200, 90, 40)):
    im = Image.new("RGB", (w, h), color)
    for x in range(w):
        for y in range(h):
            im.putpixel((x, y), (color[0], (color[1]+x*2) % 255, (color[2]+y*3) % 255))
    b = io.BytesIO(); im.save(b, "PNG"); b.seek(0); return b
def gcode_text(p, size):
    head = "; generated by OrcaSlicer 2.1\n; file: %s\nM140 S60\nM104 S215\nG28\nM190 S60\nM109 S215\nSET_PRESSURE_ADVANCE ADVANCE=0.04\nG1 Z0.3 F1200\n" % p
    body = "".join("G1 X%.3f Y%.3f E%.4f F1800 ; layer %d\n" % (10 + (i % 97) * 0.5, 10 + (i % 89) * 0.5, i * 0.0123, i // 100) for i in range(60000))
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
    # like Moonraker, which always hands a file out as an attachment
    return Response(CFG_TEXT if content is None else content, mimetype="text/plain", headers={"Content-Disposition": attachment_header(p.rsplit("/", 1)[-1])})
@app.route("/server/files/content")
def cfg_content():
    p = request.args.get("path", "")
    f = S["cfg"]["files"].get(p)
    if f is None: return cfg_error(404, "File does not exist (config/%s)" % p)
    return Response(CFG_TEXT if f["content"] is None else f["content"], mimetype="text/plain")

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
        info[S["program_key"]] = copy.deepcopy(S["klippeye_info"])
    return jsonify(result={"busy": False, "version_info": info})

def brain_restart(release=None):
    """The backend goes away for a while and comes back with another start time (and release, when the work changed it)."""
    S["brain_down"] = True
    def back():
        S["brain_down"] = False
        S["brain_started"] += 17
        if release: S["brain_release"] = release
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
    if name != S["program_key"] or info is None:
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
    return jsonify(ok=True, release=S["brain_release"], api=2, git={"commit": "a1b2c3d", "branch": "main"}, started=S["brain_started"], legacy=S["brain_legacy"], uptime=int(time.time()) % 5000 + 600,
                   python="3.11.2", has_cv2=S["brain_has_cv2"], data_dir="/home/pi/printer_data/klippeye", frontend="/home/pi/klippeye/frontend/klippeye_frontend.html")

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
    offer = S["app_apk"] or {"available": False, "reason": "no app published"}
    return jsonify(dict(offer, ok=True))

MIGRATE_STEPS = ["Controllo che si possa fare", "Copio le tue impostazioni", "Fermo VzBot e sposto il programma", "Installo i servizi KlippEye", "Tolgo i vecchi servizi e comandi", "Controllo che KlippEye risponda"]

@app.route("/api/migrate/status")
def api_migrate_status():
    if S["brain"] == "old":
        return Response("<!doctype html><title>404 Not Found</title>", status=404, mimetype="text/html")
    return jsonify(dict(S["migrate"], ok=True, legacy=S["brain_legacy"], command="bash ~/vzbot/scripts/passa-a-klippeye.sh"))

@app.route("/api/migrate/start", methods=["POST"])
def api_migrate_start():
    if not S["brain_legacy"]:
        return jsonify(ok=False, error="Sei gia' in ~/klippeye: non c'e' niente da spostare."), 400
    if S["migrate_mode"] == "no_sudo":
        return jsonify(ok=False, error="no_sudo", command="bash ~/vzbot/scripts/passa-a-klippeye.sh", message="serve sudo"), 501
    if S["migrate"].get("state") == "running":
        return jsonify(ok=False, error="Il passaggio e' gia' in corso."), 409
    S["migrate_starts"] += 1
    S["migrate"] = {"state": "running", "step": 0, "steps": 6, "message": "Parto..."}
    mode, epoch = S["migrate_mode"], EPOCH[0]
    def run():
        gap = 1.5 if mode == "slow" else 0.6
        for step, text in enumerate(MIGRATE_STEPS, 1):
            if EPOCH[0] != epoch: return
            S["migrate"] = {"state": "running", "step": step, "steps": 6, "message": text}
            if step == 3: S["brain_down"] = True
            time.sleep(gap)
            if mode == "fail" and step == 4:
                S["brain_down"] = False
                S["migrate"] = {"state": "error", "step": 4, "steps": 6, "message": "L'installazione di KlippEye non e' riuscita (dettagli in /tmp/x.log).", "command": "bash ~/vzbot/scripts/passa-a-klippeye.sh"}
                return
            if step == 4: S["brain_down"] = False
        S["brain_legacy"] = False; S["brain_started"] = int(S["brain_started"]) + 77
        S["migrate"] = {"state": "done", "step": 6, "steps": 6, "message": "Fatto: ora sei su KlippEye 1.1.0. Ricarica la pagina."}
    threading.Thread(target=run, daemon=True).start()
    return jsonify(ok=True, started=True)

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
@app.route("/app/VzBot.apk")
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
def api_brain_config_reset():
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
    return jsonify(ok=True, count=3 + len(extra), shaketune_found=0, macros=extra + [
        {"name": "CLEAN_NOZZLE", "file": "macros/clean.cfg", "description": "Clean", "params": [], "has_params": False, "source": "brain"},
        {"name": "PARK_TEST", "file": "macros/park.cfg", "description": "Park test", "params": [{"name": "X", "default": "100", "type": "int"}, {"name": "Y", "default": "50", "type": "int"}], "has_params": True, "source": "brain"},
        {"name": "SHAPER_CALIBRATE", "file": "macros/shaper.cfg", "description": "dummy", "params": [], "has_params": False, "source": "shaketune_scan"}])
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
- **Moonraker 404**: un client (Mainsail o un'app) chiede `printer.cfg` con un percorso che non esiste nella root `config`.
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
        return jsonify(error="API key non configurata", howto="Imposta la key"), 401
    if request.args.get("simple") or S.get("ai_simple"):
        return jsonify(analysis="Conclusione rapida: tutto ok, nessun errore critico.\n- klippy.log: avvio normale\n- Warning: fallback camera\n- Error: TMC error su driver", used_files=["klippy.log", "moonraker.log"], model="llama-3", provider="groq")
    if request.args.get("file"):
        return jsonify(analysis=SINGLE_MD, used_files=[request.args.get("file")], model="openai/gpt-oss-20b", provider="groq")
    return jsonify(analysis=ALL_MD, used_files=["klippy.log", "moonraker.log", "crowsnest.log", "telegram.log", "mainsail.log", "KlipperScreen.log", "webrtc.log", "sonar.log"], model="openai/gpt-oss-20b", provider="groq")
@app.route("/api/ai/config", methods=["GET", "POST"])
def ai_config():
    return jsonify(ok=True)
@app.route("/api/print/detector/status")
def det_status():
    return jsonify(ok=True, enabled=True, running=True, stats={"status": S["detector_status"], "last_score": 12, "frames_checked": 34},
                   real_print_started=True, progress=42)
@app.route("/api/print/last_analysis")
def last_analysis():
    if not S["has_analysis"]:
        return jsonify(ok=True, has_analysis=False)
    inner = json.dumps({"spaghetti": {"detected": False, "confidence": 12, "note": "layers regolari"}, "empty_bed": {"detected": False, "confidence": 3},
                        "layer_shift": {"detected": False, "confidence": 5}, "warping": {"detected": S["analysis_action"] != "CONTINUA", "confidence": 61},
                        "action": S["analysis_action"], "summary": "Stampa regolare, nessun difetto rilevato."})
    return jsonify(ok=True, has_analysis=True, timestamp="2026-10-20 14:00:00", model="llama-vision", progress=42,
                   analysis={"analysis": inner, "action": S["analysis_action"], "summary": "Stampa regolare."})

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

@app.route("/webcam/<path:p>")
def webcam(p):
    return Response("<html><body style='background:#123;color:#fff'>cam</body></html>", mimetype="text/html")

if __name__ == "__main__":
    import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=PORT, threaded=True)
