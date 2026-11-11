"""KlippEye on MQTT (1.100): the printer in Home Assistant and in any other home automation system.

With a broker set up in Settings › Phone and network › Home Assistant / MQTT, the KlippEye service publishes:

- <base>/availability            "online" / "offline" (retained; "offline" is the last will, so it shows when KlippEye
                                  or the Raspberry stops)
- <base>/state                   everything below in one JSON (retained), for Node-RED, openHAB, ioBroker...
- <base>/status/<name>           one value each (retained): state, progress, elapsed, remaining, eta, file, layer,
                                  total_layers, nozzle, nozzle_target, bed, bed_target, ai, ai_alarm, ai_summary
- <base>/light/<id>/state        "ON" / "OFF" for each light of Settings › Printer functions

and listens to:

- <base>/command                 "pause", "resume", "cancel" (only when «Allow cancel» is on)
- <base>/light/<id>/set          "ON" / "OFF"

With Home Assistant's discovery on, it also publishes the configuration of each entity under
<discovery>/<component>/<node>/<name>/config (retained), so a device with all of them appears in Home Assistant by
itself. An entity that goes away (a light removed, cancel no longer allowed, discovery switched off) is removed there too.

Only Python's standard library (mqtt_client.py). The commands come from whoever may publish on the broker: the broker's
own user and password protect them, and «Allow commands» switches them all off.
"""

import datetime
import json
import re
import socket
import threading
import time

import mqtt_client
import printer_lights

DEFAULTS = {
    "enabled": False, "host": "", "port": 1883, "tls": False, "username": "", "password": "",
    "base_topic": "", "discovery": True, "discovery_prefix": "homeassistant", "commands": True, "allow_cancel": False,
}
TOPIC_RE = re.compile(r"^[A-Za-z0-9_\-/.]{1,100}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,253}$")
STATUS_KEYS = ("state", "progress", "elapsed", "remaining", "eta", "file", "layer", "total_layers", "nozzle", "nozzle_target",
               "bed", "bed_target", "ai", "ai_alarm", "ai_summary")
PRINT_OBJECTS = {"print_stats": None, "display_status": None, "virtual_sdcard": ["progress", "is_active"], "extruder": ["temperature", "target"],
                 "heater_bed": ["temperature", "target"], "webhooks": None}


def node_id(hostname=None):
    name = re.sub(r"[^a-z0-9]+", "_", (hostname or socket.gethostname() or "printer").lower()).strip("_")
    return name[:40] or "printer"


def clean(raw):
    """The settings as saved (bad values back to the defaults); raises ValueError with a message for the page."""
    given = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    for key in ("enabled", "tls", "discovery", "commands", "allow_cancel"):
        if key in given:
            out[key] = bool(given[key])
    host = str(given.get("host", "")).strip()
    host = re.sub(r"^(mqtts?|tcp)://", "", host).rstrip("/")
    if host and not HOST_RE.match(host):
        raise ValueError("Not an address")
    out["host"] = host
    try:
        port = int(given.get("port", 1883))
    except (TypeError, ValueError):
        port = 0
    if not 1 <= port <= 65535:
        raise ValueError("Choose a port between 1 and 65535.")
    out["port"] = port
    for key, limit in (("username", 200), ("password", 500)):
        value = given.get(key, "")
        out[key] = value[:limit] if isinstance(value, str) else ""
    for key in ("base_topic", "discovery_prefix"):
        value = str(given.get(key, out[key]) or "").strip().strip("/")
        if value and (not TOPIC_RE.match(value) or "+" in value or "#" in value or "//" in value):
            raise ValueError("A topic has only letters, digits and _ - / . (no spaces, no + or #).")
        out[key] = value or DEFAULTS[key]
    if out["enabled"] and not out["host"]:
        raise ValueError("Write the address of the broker.")
    return out


def _round(value, digits=1):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def build_state(status, ai=None, now=None):
    """The values published, from Moonraker's status ({print_stats, display_status, virtual_sdcard, extruder, heater_bed,
    webhooks}) and the AI monitor's ({state, action, summary, alarm})."""
    status = status or {}
    now = time.time() if now is None else now
    stats = status.get("print_stats") or {}
    klippy = (status.get("webhooks") or {}).get("state") or "ready"
    state = stats.get("state") or "standby"
    if klippy in ("shutdown", "error"):
        state = "error"
    elif klippy == "startup":
        state = "startup"
    progress = (status.get("display_status") or {}).get("progress")
    if not isinstance(progress, (int, float)) or progress <= 0:
        progress = (status.get("virtual_sdcard") or {}).get("progress") or 0
    progress = max(0.0, min(1.0, float(progress or 0)))
    active = state in ("printing", "paused")
    elapsed = float(stats.get("print_duration") or 0) if active else 0.0
    remaining = None
    if active and progress > 0.01 and elapsed > 0:
        remaining = max(0, int(round(elapsed / progress - elapsed)))
    info = stats.get("info") or {}
    ai = ai or {}
    return {
        "state": state,
        "progress": round(progress * 100, 1) if active or state == "complete" else 0.0,
        "elapsed": int(elapsed),
        "remaining": remaining,
        "eta": datetime.datetime.fromtimestamp(now + remaining).astimezone().isoformat(timespec="seconds") if remaining is not None else None,
        "file": (stats.get("filename") or "") if active or state in ("complete", "cancelled", "error") else "",
        "layer": info.get("current_layer") if active else None,
        "total_layers": info.get("total_layer") if active else None,
        "nozzle": _round((status.get("extruder") or {}).get("temperature")),
        "nozzle_target": _round((status.get("extruder") or {}).get("target")),
        "bed": _round((status.get("heater_bed") or {}).get("temperature")),
        "bed_target": _round((status.get("heater_bed") or {}).get("target")),
        "ai": ai.get("state") or "off",
        "ai_alarm": bool(ai.get("alarm")),
        "ai_summary": ai.get("summary") or "",
    }


def text_of(value):
    if value is None:  # Home Assistant's own word for "no value now" (a number or a time that is not known)
        return "None"
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    return str(value)


def discovery_configs(node, base, prefix, device, settings, lights, say=lambda text: text):
    """{topic: config} of every Home Assistant entity (Home Assistant's MQTT discovery)."""
    avail = {"availability_topic": base + "/availability", "payload_available": "online", "payload_not_available": "offline"}
    out = {}

    def add(component, key, name, keep_name=False, **extra):
        cfg = {"name": name if keep_name else say(name), "unique_id": "klippeye_%s_%s" % (node, key), "device": device}
        cfg.update(avail)
        cfg.update(extra)
        out["%s/%s/klippeye_%s/%s/config" % (prefix, component, node, key)] = cfg

    st = base + "/status/"
    add("sensor", "state", "State", state_topic=st + "state", icon="mdi:printer-3d")
    add("sensor", "progress", "Progress", state_topic=st + "progress", unit_of_measurement="%", state_class="measurement", icon="mdi:progress-clock")
    add("sensor", "elapsed", "Print time", state_topic=st + "elapsed", unit_of_measurement="s", device_class="duration")
    add("sensor", "remaining", "Time left", state_topic=st + "remaining", unit_of_measurement="s", device_class="duration")
    add("sensor", "eta", "Ends at", state_topic=st + "eta", device_class="timestamp")
    add("sensor", "file", "File", state_topic=st + "file", icon="mdi:file")
    add("sensor", "layer", "Layer", state_topic=st + "layer", icon="mdi:layers")
    add("sensor", "total_layers", "Total layers", state_topic=st + "total_layers", icon="mdi:layers-triple")
    for key, name in (("nozzle", "Nozzle"), ("nozzle_target", "Nozzle target"), ("bed", "Bed"), ("bed_target", "Bed target")):
        add("sensor", key, name, state_topic=st + key, unit_of_measurement="°C", device_class="temperature", state_class="measurement")
    add("sensor", "ai", "AI monitor", state_topic=st + "ai", icon="mdi:eye")
    add("sensor", "ai_summary", "AI verdict", state_topic=st + "ai_summary", icon="mdi:message-alert")
    add("binary_sensor", "ai_alarm", "AI alarm", state_topic=st + "ai_alarm", device_class="problem", payload_on="ON", payload_off="OFF")
    if settings.get("commands"):
        add("button", "pause", "Pause", command_topic=base + "/command", payload_press="pause", icon="mdi:pause")
        add("button", "resume", "Resume", command_topic=base + "/command", payload_press="resume", icon="mdi:play")
        if settings.get("allow_cancel"):
            add("button", "cancel", "Cancel print", command_topic=base + "/command", payload_press="cancel", icon="mdi:stop")
    for light in lights:
        extra = {"state_topic": base + "/light/%s/state" % light["id"], "payload_on": "ON", "payload_off": "OFF"}
        if settings.get("commands"):
            extra["command_topic"] = base + "/light/%s/set" % light["id"]
            add("light", "light_" + light["id"].replace("-", "_"), light["name"], keep_name=True, **extra)
        else:
            add("binary_sensor", "light_" + light["id"].replace("-", "_"), light["name"], keep_name=True, device_class="light", **extra)
    return out


class Bridge:
    """Publishes the printer and takes the commands. `read_status(objects)` → Moonraker's status or None;
    `read_ai()` → {state, alarm, summary}; `read_lights()` → printer_lights.resolve(...) (asked every few minutes);
    `print_action(name)` pauses / resumes / cancels; `gcode(script)` sends G-code; `device()` → Home Assistant's device."""

    INTERVAL = 3
    LIGHTS_EVERY = 300

    def __init__(self, settings, read_status, read_ai, read_lights, print_action, gcode, device, node=None, say=lambda text: text):
        self.settings = settings
        self.read_status, self.read_ai, self.read_lights = read_status, read_ai, read_lights
        self.print_action, self.gcode, self.device, self.say = print_action, gcode, device, say
        self.node = node or node_id()
        self.base = settings.get("base_topic") or "klippeye/" + self.node
        self.prefix = settings.get("discovery_prefix") or "homeassistant"
        self.lights = []
        self.lights_at = 0
        self.last = {}
        self.last_lights = {}
        self.published_configs = set()
        self.last_command = None
        self._stop = threading.Event()
        self._thread = None
        self._fresh = threading.Event()
        self._busy = threading.Lock()  # held while publishing: stop() waits for it, so nothing is published after the removal
        self.client = mqtt_client.MqttClient(
            settings["host"], settings["port"], "klippeye-" + self.node, settings.get("username", ""), settings.get("password", ""),
            settings.get("tls"), will=(self.base + "/availability", "offline", True),
            subscriptions=[self.base + "/command", self.base + "/light/+/set"] if settings.get("commands") else [],
            on_message=self.on_message, on_connect=self.on_connect)

    # --- life --------------------------------------------------------------------------------------------------
    def start(self):
        self.client.start()
        self._thread = threading.Thread(target=self._loop, name="mqtt-bridge", daemon=True)
        self._thread.start()

    def stop(self, remove_discovery=False):
        self._stop.set()
        self._fresh.set()
        got = self._busy.acquire(timeout=10)  # a round already publishing (the discovery after a reconnection) ends first
        try:
            self._finish(remove_discovery)
        finally:
            if got:
                self._busy.release()

    def _finish(self, remove_discovery):
        if self.client.connected:
            if remove_discovery:
                for topic in list(self.published_configs):
                    self.client.publish(topic, "", retain=True)
            self.client.publish(self.base + "/availability", "offline", retain=True)
        self.client.stop()

    def status(self):
        return {"connected": self.client.connected, "error": self.client.error, "since": self.client.since, "base_topic": self.base,
                "node": self.node, "lights": [{"id": light["id"], "name": light["name"]} for light in self.lights], "last_command": self.last_command}

    def on_connect(self):
        if self._stop.is_set():
            return
        self.last, self.last_lights = {}, {}
        self.client.publish(self.base + "/availability", "online", retain=True)
        self.lights_at = 0
        self._fresh.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                with self._busy:
                    if self.client.connected and not self._stop.is_set():
                        self.tick()
            except Exception as error:  # noqa: BLE001 - the bridge goes on
                print("[MQTT] publishing failed: %s" % error)
            self._fresh.wait(self.INTERVAL)
            self._fresh.clear()

    # --- what is published -----------------------------------------------------------------------------------------
    def refresh_lights(self, force=False):
        if force or time.time() - self.lights_at >= self.LIGHTS_EVERY:
            try:
                found = self.read_lights()
                if found is not None:
                    self.lights = found
            except Exception as error:  # noqa: BLE001
                print("[MQTT] lights not read: %s" % error)
            self.lights_at = time.time()
            self.publish_discovery()

    def publish_discovery(self):
        wanted = discovery_configs(self.node, self.base, self.prefix, self.device(), self.settings, self.lights, self.say) if self.settings.get("discovery") else {}
        for topic in self.published_configs - set(wanted):
            self.client.publish(topic, "", retain=True)
        for topic, cfg in wanted.items():
            self.client.publish(topic, json.dumps(cfg, ensure_ascii=False), retain=True)
        self.published_configs = set(wanted)

    def tick(self):
        self.refresh_lights()
        objects = dict(PRINT_OBJECTS)
        for name in printer_lights.query_objects(self.lights):
            objects[name] = None
        status = self.read_status(objects)
        if status is None:
            return
        state = build_state(status, self.read_ai())
        changed = False
        for key in STATUS_KEYS:
            value = text_of(state[key])
            if self.last.get(key) != value:
                self.client.publish(self.base + "/status/" + key, value, retain=True)
                self.last[key] = value
                changed = True
        lights = {}
        for light in self.lights:
            on = printer_lights.is_on(status, light)
            if on is None:
                continue
            lights[light["id"]] = on
            value = "ON" if on else "OFF"
            if self.last_lights.get(light["id"]) != value:
                self.client.publish(self.base + "/light/%s/state" % light["id"], value, retain=True)
                self.last_lights[light["id"]] = value
                changed = True
        if changed:
            self.client.publish(self.base + "/state", json.dumps(dict(state, lights=lights), ensure_ascii=False), retain=True)

    # --- what comes in ---------------------------------------------------------------------------------------------
    def on_message(self, topic, payload):
        if not self.settings.get("commands"):
            return
        text = payload.decode("utf-8", "replace").strip()
        if topic == self.base + "/command":
            word = text.lower()
            if word in ("pause", "resume") or (word == "cancel" and self.settings.get("allow_cancel")):
                state = self.last.get("state")
                if (word == "pause" and state != "printing") or (word == "resume" and state != "paused") or (word == "cancel" and state not in ("printing", "paused")):
                    self.last_command = {"command": word, "ok": False, "at": time.time(), "why": "state %s" % state}
                    return
                ok = self.print_action(word)
                self.last_command = {"command": word, "ok": bool(ok), "at": time.time()}
                print("[MQTT] command %s: %s" % (word, "sent" if ok else "refused"))
                self._fresh.set()
            return
        match = re.match(re.escape(self.base) + r"/light/([a-z0-9-]{1,40})/set$", topic)
        if match:
            light = next((one for one in self.lights if one["id"] == match.group(1)), None)
            word = text.upper()
            if light and word in ("ON", "OFF"):
                ok = self.gcode(light["on"] if word == "ON" else light["off"])
                self.last_command = {"command": "light %s %s" % (light["id"], word), "ok": bool(ok), "at": time.time()}
                if ok and light.get("object") is None:  # no output to read: the state is what was asked
                    self.client.publish(self.base + "/light/%s/state" % light["id"], word, retain=True)
                    self.last_lights[light["id"]] = word
                self._fresh.set()
