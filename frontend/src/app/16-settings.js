/* ============================================================================
   16 · DASHBOARD SETTINGS
   What the settings menu (app/59-settings.js) changes, and where it is kept.

   · The settings are one small JSON document. It is kept in Moonraker's own database (namespace "klippeye",
     key "settings"), which the backend passes through like the rest of Moonraker's API: every phone, tablet and PC
     then sees the same settings, and the notification service on the Raspberry (notifier/) reads the very same
     document. Nothing of the backend is touched.
   · This device keeps a copy in localStorage, so the page starts with its settings at once and keeps working when
     the Raspberry does not store them (then the menu says "solo su questo dispositivo").
   · Whatever comes from either place is cleaned first (sanitizeSettings): a wrong or missing value becomes the
     default, so a damaged document can never break the page.
   ========================================================================== */

const SETTINGS_NAMESPACE = "klippeye";
const SETTINGS_DB_KEY = "settings";
const NOTIFIER_DB_KEY = "notifier"; // written by the notification service: version, last sign of life, last automatic action
const SETTINGS_SAVE_DELAY_MS = 700; // changes closer than this are written as one
const SETTINGS_DB_TIMEOUT_MS = 8000;
const SETTINGS_RETRY_MS = 5000; // 1.61: a save that did not get through is tried again after this

/** How the camera is shown (the "service" of a webcam kept by Moonraker). */
const CAMERA_METHODS = [
  { id: "webrtc", label: "WebRTC", detail: tx("camera-streamer's WebRTC page: smooth and light"), field: tx("Address of the WebRTC page") },
  { id: "mjpeg", label: "MJPEG", detail: tx("Continuous video stream, works with almost every camera"), field: tx("Address of the stream") },
  { id: "adaptive", label: tx("MJPEG adaptive"), detail: tx("One picture after the other: for slow networks"), field: tx("Address of the snapshot") },
  { id: "iframe", label: tx("Web page"), detail: tx("Any page that shows the camera"), field: tx("Address of the page") },
];
const CAMERA_METHOD_IDS = CAMERA_METHODS.map((method) => method.id);
const CAMERA_ROUTES = ["auto", "local", "external"];
const CAMERA_FPS_MIN = 1;
const CAMERA_FPS_MAX = 30;

/** The brands whose name and logo the top bar can show (app/18-printer-brand.js has the labels and the logos). */
const PRINTER_BRAND_IDS = ["klippeye", "vzbot", "voron", "ratrig"];
const PRINTER_NAME_MAX = 24;

const Z_STEP_MIN = 0.001;
const Z_STEP_MAX = 1;
const Z_STEP_SLOTS = 4;

/**
 * The notifications of the Raspberry's notification service, in the order the menu lists them. `text` is the text of
 * the push in English (the same as MESSAGES in notifier/klippeye_notifier.py), shown in the notifications' language.
 */
const NOTIFICATION_KINDS = [
  { id: "error", title: tx("Printer error"), text: txn("Printer error! Restart it.") },
  { id: "complete", title: tx("Print completed"), text: txn("Print completed!") },
  { id: "cancelled", title: tx("Print cancelled"), text: txn("Print cancelled!") },
  { id: "paused", title: tx("Printer paused"), text: txn("Printer paused!") },
  { id: "runout", title: tx("Filament run out"), text: txn("Filament run out, change the spool!") },
  { id: "ai_pause", title: tx("AI: defects found"), text: txn("Print defects found, check and pause the print!") },
  { id: "ai_cancel", title: tx("AI: serious defects"), text: txn("Serious print defects found, check and cancel the print") },
];

/**
 * 1.38: notifications of your own (read by the notification service, notifier/klippeye_notifier.py "rules"). `defaultText`
 * is the service's own text of each kind (the same words: tests/notifier/test_watcher.py checks them).
 */
const NOTIFY_RULE_KINDS = [
  { id: "started", title: tx("Print started"), defaultText: txn("Print started: {file}") },
  { id: "progress", title: tx("Progress reached"), unit: "%", min: 1, max: 99, initial: 50, defaultText: txn("{file}: {progress}% done") },
  { id: "remaining", title: tx("Little time left"), unit: "min", min: 1, max: 600, initial: 10, defaultText: txn("{file}: about {remaining} left") },
  { id: "layer", title: tx("Layer reached"), unit: "layer", min: 1, max: 100000, initial: 3, defaultText: txn("{file}: layer {layer} of {total_layers}") },
  { id: "line", title: tx("A line in the console"), initial: "", defaultText: txn("{line}") },
  { id: "temp", title: tx("Temperature reached"), initial: "heater_bed", defaultText: txn("{heater} at temperature: {temp}°C") },
];
const NOTIFY_RULES_MAX = 20;
const NOTIFY_TEXT_MAX = 300;
const NOTIFY_PAUSE_DELAYS = [0, 4, 10, 30, 60];
/** The words that fill a text when it goes out (the service's PLACEHOLDERS). */
const NOTIFY_PLACEHOLDERS = ["file", "progress", "layer", "total_layers", "elapsed", "remaining", "message", "line", "heater", "temp", "target", "printer"];

/** What the AI print monitor looks for (the keys of its verdict, see app/53-ai-views.js). */
const AI_DEFECTS = [
  { id: "spaghetti", title: "Spaghetti", detail: tx("The filament does not stick and piles up") },
  { id: "empty_bed", title: tx("Empty bed"), detail: tx("The part came off or is gone") },
  { id: "layer_shift", title: tx("Layer shift"), detail: tx("The layers shift") },
  { id: "warping", title: "Warping", detail: tx("The corners lift from the bed") },
];
const AI_CONFIRMATIONS = [1, 2, 3];

/** "Printer functions" (16a-printer-functions.js): the buttons that run a macro of the printer, and how. */
const ACTION_FUNCTIONS = ["park", "wipe", "load", "unload"];
const ACTION_MODES = ["auto", "macro", "gcode", "off"];
/** 1.37: several lights, each switched in its own way; scenes. */
const LIGHT_HOWS = ["object", "macro", "gcode"];
const LIGHTS_MAX = 12;
const LIGHT_SCENES_MAX = 12;
const LIGHT_NAME_MAX = 30;
const LIGHT_HEX = /^#[0-9a-f]{6}$/;
const FUNCTION_GCODE_MAX = 4000;
const MACRO_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;

/** 1.33: the macro cards (57-calibration.js): every macro in one card, or groups of the person's own. */
const MACRO_MODES = ["simple", "groups"];
const MACRO_COLORS = ["none", "accent", "ok", "warn", "danger", "cool"];
const MACRO_HEX_COLOR = /^#[0-9a-f]{6}$/; // 1.33.1: any colour, chosen on the wheel
const MACRO_STATES = ["standby", "printing", "paused"];
const MACRO_GROUPS_MAX = 30;
const MACRO_GROUP_NAME_MAX = 40;

/**
 * 1.112: the usual materials of the temperature window (one tap: the nozzle and the bed together); 1.113: they are
 * the printer's own list, changed in Settings → Materials (the common starting points; a spool's may differ a little).
 */
const MATERIAL_PRESETS = [
  { name: "PLA", hotend: 210, bed: 60 },
  { name: "PETG", hotend: 240, bed: 80 },
  { name: "ABS", hotend: 250, bed: 100 },
  { name: "ASA", hotend: 255, bed: 100 },
  { name: "TPU", hotend: 225, bed: 50 },
];
const MATERIALS_MAX = 12;
const MATERIAL_NAME_MAX = 16;
const MATERIAL_HOTEND_MAX = 350;
const MATERIAL_BED_MAX = 150;

/** The materials as saved: up to MATERIALS_MAX, each with a name and two whole temperatures (not an array: the usual ones). */
function cleanMaterials(given) {
  if (!Array.isArray(given)) return MATERIAL_PRESETS.map((one) => ({ ...one }));
  return given
    .filter((one) => isPlainObject(one) && typeof one.name === "string" && one.name.trim())
    .slice(0, MATERIALS_MAX)
    .map((one) => ({
      name: one.name.trim().slice(0, MATERIAL_NAME_MAX),
      hotend: Math.round(asNumber(one.hotend, 0, MATERIAL_HOTEND_MAX, 0)),
      bed: Math.round(asNumber(one.bed, 0, MATERIAL_BED_MAX, 0)),
    }));
}

const SETTINGS_DEFAULTS = {
  camera: {
    method: "webrtc",
    urls: { webrtc: "/webcam/webrtc", mjpeg: "/webcam/?action=stream", adaptive: "/webcam/?action=snapshot", iframe: "/webcam/webrtc" },
    fps: 5, // "adaptive": photos per second
    snapshot: "", // the single photo (AI monitor, calibration, later the timelapse): "" = automatic, see defaultSnapshot (1.23)
    flipH: false,
    flipV: false,
  },
  // "" = not set: the camera uses the address the dashboard was opened at (1.22: before, the maintainer's own addresses)
  network: { localIp: "", externalIp: "", route: "auto" },
  zOffset: { steps: [0.01, 0.025, 0.05, 0.1] },
  // 1.31: the Motion card: which part Z moves ("auto": from Klipper's configuration) and the steps beyond 1 and 10 mm
  motion: { zMoves: "auto", xyExtra: [], zExtra: [] },
  printer: { brand: "klippeye", name: "" }, // name "": the brand's own
  printers: [], // 1.61: the other printers with KlippEye: [{ id, name, host }] (31b-printers.js)
  language: LANG, // of the notifications (shared by every phone): the language of the first device that saves the settings
  notifications: Object.fromEntries(NOTIFICATION_KINDS.map((kind) => [kind.id, true])),
  ai: {
    autoPause: false,
    autoCancel: false,
    confirmations: 1,
    minConfidence: 0,
    defects: Object.fromEntries(AI_DEFECTS.map((defect) => [defect.id, true])),
  },
  functions: {
    reviewed: false, // the person has looked at "Printer functions" (until then a reminder is shown)
    ...Object.fromEntries(ACTION_FUNCTIONS.map((id) => [id, { mode: "auto", macro: "", gcode: "" }])),
    // 1.37: the lights. `configured` false: the list is what KlippEye finds in Klipper (it follows the printer); the first
    // change the person makes keeps the list as it is then. `main`: switched by the round button on the camera.
    lights: { configured: false, items: [], scenes: [] },
    filament: { sensor: true, macros: [], phrases: [] }, // what tells the notification service that the filament ran out
  },
  // 1.38: the texts of the notifications ("" or missing: the service's own), the pause's delay (null: 4 s), your own ones
  notify: { texts: {}, pauseDelay: null, rules: [] },
  // 1.33: the macro cards (the old "Calibrations" choice, /api/calibration/selected, becomes a group: useMacroMigration)
  macros: { mode: "simple", hidden: [], groups: [] },
  // the guided set-up (59k, 1.22): shown by itself once on a new installation, until it is done or skipped
  setup: { done: false },
  materials: MATERIAL_PRESETS.map((one) => ({ ...one })), // 1.113: the temperature window's materials
};

/* ---------------------------------------------------------------------------
   Cleaning
   ------------------------------------------------------------------------- */
const isPlainObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const asBool = (value, fallback) => (typeof value === "boolean" ? value : fallback);
const asNumber = (value, min, max, fallback) => {
  const number = typeof value === "string" && value.trim() === "" ? NaN : Number(value);
  return Number.isFinite(number) ? clamp(number, min, max) : fallback;
};

/** "192.168.1.17", "klippeye.local", "10.0.0.5:8080" (a leading http:// or a path behind it are dropped); null when it is not an address. */
function cleanHost(value) {
  if (typeof value !== "string") return null;
  const text = value.trim().replace(/^https?:\/\//i, "").replace(/\/.*$/, "");
  if (!/^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$/.test(text)) return null;
  const port = /:(\d+)$/.exec(text);
  if (port && Number(port[1]) > 65535) return null;
  const name = text.replace(/:\d+$/, "");
  if (/^[\d.]+$/.test(name)) {
    const octets = name.split(".");
    if (octets.length !== 4 || octets.some((octet) => octet === "" || Number(octet) > 255)) return null; // only digits: it has to be a whole IPv4 address
  }
  return text;
}

/** A path on the printer ("/webcam/webrtc") or a full http(s) address; null when it is neither. */
function cleanCameraAddress(value) {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || text.length > 300 || /\s/.test(text)) return null;
  if (/^https?:\/\/[^/?#]+/i.test(text)) return text;
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(text)) return null; // javascript:, data:, ftp: ...
  return text.charAt(0) === "/" ? text : "/" + text;
}

/**
 * The snapshot that goes with the camera when none is chosen (the same rules as backend/camera_snapshot.py, keep them equal):
 * "/webcam2/webrtc" -> "/webcam2/?action=snapshot", "...?action=stream" -> "...?action=snapshot", the adaptive method's own
 * address; anything else -> "/webcam/?action=snapshot", which every streamer of crowsnest answers.
 */
const SNAPSHOT_DEFAULT = "/webcam/?action=snapshot";
function defaultSnapshot(camera) {
  const address = cleanCameraAddress(camera.urls[camera.method]) || "";
  if (!address) return SNAPSHOT_DEFAULT;
  if (camera.method === "adaptive") return address;
  if (address.indexOf("action=stream") >= 0) return address.replace("action=stream", "action=snapshot");
  const match = /^(.*\/)(webrtc|stream)\/?(\?.*)?$/.exec(address);
  if (match && (camera.method === "webrtc" || camera.method === "mjpeg" || match[2] === "webrtc")) return match[1] + "?action=snapshot";
  return SNAPSHOT_DEFAULT;
}

/** The snapshot address in use: the chosen one, or the automatic one. */
const snapshotAddress = (camera) => camera.snapshot || defaultSnapshot(camera);

/** Up to Z_STEP_SLOTS different step sizes in mm, smallest first; at least one. */
function cleanZSteps(value) {
  const numbers = Array.isArray(value) ? value.map((item) => (typeof item === "string" && item.trim() === "" ? NaN : Number(item))) : [];
  const valid = numbers.filter((number) => Number.isFinite(number) && number >= Z_STEP_MIN && number <= Z_STEP_MAX).map((number) => Math.round(number * 1000) / 1000);
  const steps = [...new Set(valid)].sort((a, b) => a - b).slice(0, Z_STEP_SLOTS);
  return steps.length ? steps : SETTINGS_DEFAULTS.zOffset.steps.slice();
}

/** The name of the printer for the top bar and the tab ("VzBot.287"): "" (use the brand's), a short text of letters, digits and . _ - ' space; null when it is not that. */
function cleanPrinterName(value) {
  if (typeof value !== "string") return null;
  const text = value.trim().replace(/\s+/g, " ");
  if (text === "") return "";
  return text.length <= PRINTER_NAME_MAX && /^[A-Za-z0-9][A-Za-z0-9 ._'-]*$/.test(text) ? text : null;
}

const pickOne = (value, allowed, fallback) => (allowed.includes(value) ? value : fallback);
const cleanMacroName = (value) => (typeof value === "string" && MACRO_NAME.test(value.trim()) ? value.trim().toUpperCase() : "");
const cleanGcode = (value) => (typeof value === "string" ? value.replace(/\r\n?/g, "\n").slice(0, FUNCTION_GCODE_MAX) : "");
const cleanObjectName = (value) => (typeof value === "string" && /^[A-Za-z_]+ [^\n]{1,80}$/.test(value.trim()) ? value.trim() : "");

/** The "functions" part of the settings, cleaned. */
/** Macro names, upper case, once each (Klipper does not tell "park" from "PARK"). */
const cleanMacroNames = (list) => (Array.isArray(list) ? [...new Set(list.filter((name) => typeof name === "string" && MACRO_NAME.test(name)).map((name) => name.toUpperCase()))].slice(0, 500) : []);

/** The settings of the macro cards: the mode, the macros hidden in "simple", the groups. */
function cleanMacroSettings(raw) {
  const given = isPlainObject(raw) ? raw : {};
  const ids = new Set();
  const groups = (Array.isArray(given.groups) ? given.groups : [])
    .filter(isPlainObject)
    .slice(0, MACRO_GROUPS_MAX)
    .map((group, index) => {
      let id = typeof group.id === "string" && /^[a-z0-9]{1,16}$/.test(group.id) ? group.id : "g" + index;
      while (ids.has(id)) id += "x";
      ids.add(id);
      const show = isPlainObject(group.show) ? group.show : {};
      return {
        id,
        name: typeof group.name === "string" ? group.name.trim().slice(0, MACRO_GROUP_NAME_MAX) : "",
        color: typeof group.color === "string" && MACRO_HEX_COLOR.test(group.color.toLowerCase()) ? group.color.toLowerCase() : pickOne(group.color, MACRO_COLORS, "none"),
        show: Object.fromEntries(MACRO_STATES.map((state) => [state, asBool(show[state], true)])),
        macros: cleanMacroNames(group.macros),
      };
    });
  return { mode: pickOne(given.mode, MACRO_MODES, "simple"), hidden: cleanMacroNames(given.hidden), groups };
}

/** One light of the list: how it is switched (an output, two macros, G-code), its name, whether the round button switches it. */
function cleanLightItem(raw, index) {
  const one = isPlainObject(raw) ? raw : {};
  return {
    id: typeof one.id === "string" && /^[a-z0-9-]{1,40}$/.test(one.id) ? one.id : "l" + index,
    name: typeof one.name === "string" ? one.name.trim().slice(0, LIGHT_NAME_MAX) : "",
    mode: pickOne(one.mode, LIGHT_HOWS, "object"),
    object: cleanObjectName(one.object),
    onMacro: cleanMacroName(one.onMacro),
    offMacro: cleanMacroName(one.offMacro),
    onGcode: cleanGcode(one.onGcode),
    offGcode: cleanGcode(one.offGcode),
    stateFrom: one.stateFrom === "auto" || one.stateFrom === "" ? one.stateFrom : cleanObjectName(one.stateFrom) || "auto",
    main: asBool(one.main, true),
  };
}

/**
 * The lights (1.37). Settings saved before have one `light`: chosen by hand it becomes the only item of the list (switched
 * off: an empty list), left on "automatic" the list follows what KlippEye finds.
 */
function cleanLights(raw, oldLight) {
  if (!isPlainObject(raw)) {
    const old = isPlainObject(oldLight) ? oldLight : {};
    if (!old.mode || old.mode === "auto") return { configured: false, items: [], scenes: [] };
    if (old.mode === "off") return { configured: true, items: [], scenes: [] };
    return { configured: true, items: [cleanLightItem({ ...old, id: "light", name: tx("Light") }, 0)], scenes: [] };
  }
  const ids = new Set();
  const items = (Array.isArray(raw.items) ? raw.items : []).slice(0, LIGHTS_MAX).map(cleanLightItem).filter((item) => !ids.has(item.id) && ids.add(item.id));
  const scenes = (Array.isArray(raw.scenes) ? raw.scenes : [])
    .filter(isPlainObject)
    .slice(0, LIGHT_SCENES_MAX)
    .map((scene, index) => ({
      id: typeof scene.id === "string" && /^[a-z0-9-]{1,40}$/.test(scene.id) ? scene.id : "s" + index,
      name: typeof scene.name === "string" ? scene.name.trim().slice(0, LIGHT_NAME_MAX) : "",
      set: Object.fromEntries(
        Object.entries(isPlainObject(scene.set) ? scene.set : {})
          .filter(([id, value]) => /^[a-z0-9-]{1,40}$/.test(id) && isPlainObject(value))
          .slice(0, LIGHTS_MAX * 2)
          .map(([id, value]) => [id, { on: asBool(value.on, false), level: Math.round(asNumber(value.level, 0, 100, 100)), color: typeof value.color === "string" && LIGHT_HEX.test(value.color) ? value.color : "" }]),
      ),
    }))
    .filter((scene) => scene.name);
  return { configured: asBool(raw.configured, false), items, scenes };
}

/** The "notify" part of the settings, cleaned. */
function cleanNotify(raw) {
  const given = isPlainObject(raw) ? raw : {};
  const texts = isPlainObject(given.texts) ? given.texts : {};
  const ids = new Set();
  const rules = (Array.isArray(given.rules) ? given.rules : [])
    .filter(isPlainObject)
    .map((rule) => {
      const kind = NOTIFY_RULE_KINDS.find((one) => one.id === rule.kind);
      if (!kind || typeof rule.id !== "string" || !/^[a-z0-9-]{1,40}$/.test(rule.id) || ids.has(rule.id)) return null;
      ids.add(rule.id);
      let value = null;
      if (kind.unit) value = Math.round(asNumber(rule.value, kind.min, kind.max, kind.initial));
      else if (kind.id === "line") value = typeof rule.value === "string" ? rule.value.slice(0, 120) : "";
      else if (kind.id === "temp") value = pickOne(rule.value, ["heater_bed", "extruder"], "heater_bed");
      return { id: rule.id, kind: kind.id, value, text: typeof rule.text === "string" ? rule.text.slice(0, NOTIFY_TEXT_MAX) : "", on: asBool(rule.on, true), high: asBool(rule.high, false) };
    })
    .filter(Boolean)
    .slice(0, NOTIFY_RULES_MAX);
  const delay = given.pauseDelay === null || given.pauseDelay === undefined ? null : asNumber(given.pauseDelay, 0, 120, null);
  return {
    texts: Object.fromEntries(NOTIFICATION_KINDS.map((kind) => [kind.id, typeof texts[kind.id] === "string" ? texts[kind.id].slice(0, NOTIFY_TEXT_MAX) : ""]).filter(([, text]) => text.trim())),
    pauseDelay: delay === null ? null : Math.round(delay),
    rules,
  };
}

function cleanFunctions(raw) {
  const given = isPlainObject(raw) ? raw : {};
  const light = isPlainObject(given.light) ? given.light : {};
  const filament = isPlainObject(given.filament) ? given.filament : {};
  const list = (value, clean, max) => [...new Set((Array.isArray(value) ? value : []).map(clean).filter(Boolean))].slice(0, max);
  return {
    reviewed: asBool(given.reviewed, false),
    ...Object.fromEntries(
      ACTION_FUNCTIONS.map((id) => {
        const one = isPlainObject(given[id]) ? given[id] : {};
        return [id, { mode: pickOne(one.mode, ACTION_MODES, "auto"), macro: cleanMacroName(one.macro), gcode: cleanGcode(one.gcode) }];
      }),
    ),
    lights: cleanLights(given.lights, light),
    filament: {
      sensor: asBool(filament.sensor, true),
      macros: list(filament.macros, cleanMacroName, 10),
      phrases: list(filament.phrases, (text) => (typeof text === "string" ? text.trim().slice(0, 120) : ""), 10),
    },
  };
}

const MOTION_Z_MOVES = ["auto", "bed", "toolhead"];
const MOTION_BASE_STEPS = [1, 10]; // always on the pad and the Z buttons
const MOTION_EXTRA_STEPS = [50, 100]; // optional: at most four steps in all
/** The optional steps chosen ([50], [100], [50, 100] or []), sorted, nothing else. */
function cleanExtraSteps(value) {
  return Array.isArray(value) ? MOTION_EXTRA_STEPS.filter((step) => value.map(Number).includes(step)) : [];
}

const PRINTERS_MAX = 12; // 1.61: the other printers (31b-printers.js)
/** The list of the other printers, clean: [{ id, name, host }] (no doubles, not this printer itself). */
function cleanPrinters(value) {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const out = [];
  for (const item of value) {
    if (!isPlainObject(item)) continue;
    const host = cleanHost(item.host);
    if (!host || seen.has(host.toLowerCase())) continue;
    seen.add(host.toLowerCase());
    out.push({ id: typeof item.id === "string" && /^[a-z0-9-]{1,24}$/.test(item.id) ? item.id : "p" + out.length, name: cleanPrinterName(item.name) || "", host });
    if (out.length >= PRINTERS_MAX) break;
  }
  return out;
}

/** `raw` (anything: a stored document, nothing at all) as a complete, valid settings object. */
function sanitizeSettings(raw) {
  const given = isPlainObject(raw) ? raw : {};
  const d = SETTINGS_DEFAULTS;
  const camera = isPlainObject(given.camera) ? given.camera : {};
  const urls = isPlainObject(camera.urls) ? camera.urls : {};
  const network = isPlainObject(given.network) ? given.network : {};
  const notifications = isPlainObject(given.notifications) ? given.notifications : {};
  const ai = isPlainObject(given.ai) ? given.ai : {};
  const defects = isPlainObject(ai.defects) ? ai.defects : {};
  const zOffset = isPlainObject(given.zOffset) ? given.zOffset : {};
  const motion = isPlainObject(given.motion) ? given.motion : {};
  const printer = isPlainObject(given.printer) ? given.printer : {};
  return {
    camera: {
      method: pickOne(camera.method, CAMERA_METHOD_IDS, d.camera.method),
      urls: Object.fromEntries(CAMERA_METHOD_IDS.map((id) => [id, cleanCameraAddress(urls[id]) || d.camera.urls[id]])),
      fps: Math.round(asNumber(camera.fps, CAMERA_FPS_MIN, CAMERA_FPS_MAX, d.camera.fps)),
      snapshot: cleanCameraAddress(camera.snapshot) || "",
      flipH: asBool(camera.flipH, d.camera.flipH),
      flipV: asBool(camera.flipV, d.camera.flipV),
    },
    network: {
      localIp: cleanHost(network.localIp) || d.network.localIp,
      externalIp: cleanHost(network.externalIp) || d.network.externalIp,
      route: pickOne(network.route, CAMERA_ROUTES, d.network.route),
    },
    zOffset: { steps: cleanZSteps(zOffset.steps) },
    motion: { zMoves: pickOne(motion.zMoves, MOTION_Z_MOVES, d.motion.zMoves), xyExtra: cleanExtraSteps(motion.xyExtra), zExtra: cleanExtraSteps(motion.zExtra) },
    printer: { brand: pickOne(printer.brand, PRINTER_BRAND_IDS, d.printer.brand), name: cleanPrinterName(printer.name) || "" },
    printers: cleanPrinters(given.printers),
    language: pickOne(given.language, I18N_LANGUAGES.map((language) => language.code), d.language),
    notifications: Object.fromEntries(NOTIFICATION_KINDS.map((kind) => [kind.id, asBool(notifications[kind.id], true)])),
    ai: {
      autoPause: asBool(ai.autoPause, d.ai.autoPause),
      autoCancel: asBool(ai.autoCancel, d.ai.autoCancel),
      confirmations: pickOne(Number(ai.confirmations), AI_CONFIRMATIONS, d.ai.confirmations),
      minConfidence: 0, // 1.19: the only threshold is the backend's (Settings → AI monitor); an old value here is dropped
      defects: Object.fromEntries(AI_DEFECTS.map((defect) => [defect.id, asBool(defects[defect.id], true)])),
    },
    functions: cleanFunctions(given.functions),
    macros: cleanMacroSettings(given.macros),
    notify: cleanNotify(given.notify),
    materials: cleanMaterials(given.materials),
    // settings saved before 1.22 (anything stored, without "setup"): an installation already set up, the guide is not forced on it
    setup: { done: isPlainObject(given.setup) ? asBool(given.setup.done, false) : Object.keys(given).length > 0 },
  };
}

const cloneJson = (value) => JSON.parse(JSON.stringify(value));

/* ---------------------------------------------------------------------------
   Moonraker's database
   ------------------------------------------------------------------------- */
/**
 * What is stored under `key`: the whole namespace is asked for (a missing key then simply is not in it, instead of
 * being an error). { ok: true, value } | { ok: true, missing: true } (nothing stored yet) | { ok: false, detail }.
 */
async function readSettingsDb(key) {
  const response = await fetchFresh("/server/database/item?namespace=" + SETTINGS_NAMESPACE, { timeout: SETTINGS_DB_TIMEOUT_MS });
  let json = null;
  try {
    json = await response.json();
  } catch (e) {}
  if (response.ok && isPlainObject(json) && isPlainObject(json.result)) {
    const stored = isPlainObject(json.result.value) ? json.result.value : {};
    return stored[key] === undefined ? { ok: true, missing: true } : { ok: true, value: stored[key] };
  }
  if (response.status === 404 && isPlainObject(json) && json.error) return { ok: true, missing: true }; // Moonraker's own "namespace not found": nothing stored yet
  return { ok: false, detail: "HTTP " + response.status };
}

async function writeSettingsDb(key, value) {
  const response = await fetchFresh("/server/database/item", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ namespace: SETTINGS_NAMESPACE, key, value }),
    timeout: SETTINGS_DB_TIMEOUT_MS,
  });
  return response.ok ? { ok: true } : { ok: false, detail: await errorMessageOf(response) };
}

/* ---------------------------------------------------------------------------
   The store
   `sync.state`: "loading" (not asked yet) | "saving" | "shared" (the Raspberry has them) | "local" (only this device).
   ------------------------------------------------------------------------- */
/** A time stamp for a change: the clock, but always later than the one before (a copy taken from a device whose clock is ahead must not be "newer" than our own change). */
const nextStamp = (previous) => Math.max(Date.now(), previous + 1);

function createSettingsStore() {
  const listeners = new Set();
  const remembered = storage.getJson(STORAGE_KEYS.settings);
  let current = sanitizeSettings(remembered && remembered.settings);
  let stamp = (remembered && Number(remembered.t)) || 0; // when they were last changed, in ms: the newer copy wins
  let dirty = Boolean(remembered && remembered.dirty); // changed here, the Raspberry has not got the change yet
  let sync = { state: "loading", detail: "" };
  let view = { settings: current, sync };
  let saveTimer = 0;
  let saving = false;
  let pulling = null; // the pull under way (a promise): whoever needs the Raspberry's answer can wait for it
  let known = Boolean(remembered); // these settings are really ours or the Raspberry's, not just the defaults of a device that has not asked yet

  /** The Android app is told the addresses once they are known (the defaults of a page that has not asked the Raspberry yet must not reach it). */
  const announce = () => {
    if (known) tellApp(current);
  };

  const emit = () => {
    view = { settings: current, sync };
    listeners.forEach((listener) => listener());
  };
  const remember = () => storage.set(STORAGE_KEYS.settings, JSON.stringify({ t: stamp, dirty, settings: current }));
  const setSync = (state, detail = "") => {
    if (sync.state === state && sync.detail === detail) return;
    sync = { state, detail };
    emit();
  };
  const failure = (error) => (error && error.name === "AbortError" ? tx("the Raspberry does not answer") : tx("Raspberry not reachable"));

  async function push() {
    if (saving) return;
    saving = true;
    const sentStamp = stamp;
    let aborted = false;
    let retry = false;
    let timedOut = false;
    const timeoutTimer = setTimeout(() => (timedOut = true), SETTINGS_DB_TIMEOUT_MS - 50);
    try {
      setSync("saving");
      const result = await writeSettingsDb(SETTINGS_DB_KEY, { ...cloneJson(current), _t: sentStamp });
      if (result.ok) {
        if (stamp === sentStamp) {
          dirty = false;
          remember();
        }
        setSync("shared");
      } else {
        setSync("local", result.detail);
      }
    } catch (error) {
      aborted = error && error.name === "AbortError" && !timedOut;
      if (!aborted) setSync("local", failure(error));
      // 1.61: a write cancelled (a wake-up cancels every request: 15-live.js) or lost on the way is tried again
      // (a refusal of the Raspberry, above, waits for the next change or the next pull)
      retry = true;
    } finally {
      saving = false;
      clearTimeout(timeoutTimer);
      if (dirty && retry) schedulePush(aborted ? SETTINGS_SAVE_DELAY_MS : SETTINGS_RETRY_MS);
      else if (dirty && stamp !== sentStamp && sync.state !== "local") schedulePush(); // changed while it was on its way
    }
  }

  function schedulePush(delay = SETTINGS_SAVE_DELAY_MS) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(push, delay);
  }

  /** Asks the Raspberry what it has: its copy is taken when it is newer, ours is sent when it is. Resolves when that is done. */
  function pull() {
    if (saving) return Promise.resolve();
    if (!pulling) {
      pulling = readFromRaspberry().finally(() => {
        pulling = null;
      });
    }
    return pulling;
  }

  async function readFromRaspberry() {
    try {
      const answer = await readSettingsDb(SETTINGS_DB_KEY);
      if (!answer.ok) return setSync("local", answer.detail);
      if (answer.missing || !isPlainObject(answer.value)) {
        known = true; // nothing there yet: this device's settings are the first
        announce();
        return push();
      }
      const remoteStamp = Number(answer.value._t) || 0;
      if (dirty && stamp > remoteStamp) {
        known = true;
        announce();
        return push();
      }
      const remote = sanitizeSettings(answer.value);
      known = true;
      if (typeof answer.value.language !== "string") {
        // saved by a release before 1.5.0: the notifications get this device's language, and the Raspberry is told
        current = remote;
        stamp = nextStamp(Math.max(stamp, remoteStamp));
        dirty = true;
        remember();
        announce();
        emit();
        return push();
      }
      if (JSON.stringify(remote) !== JSON.stringify(current) || remoteStamp !== stamp || dirty) {
        current = remote;
        stamp = remoteStamp;
        dirty = false;
        remember();
        announce();
        emit();
      } else {
        announce();
      }
      setSync("shared");
    } catch (error) {
      setSync("local", failure(error));
    }
  }

  return {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    snapshot: () => view,
    get: () => current,
    pull,
    announce,
    /** `change(draft)` edits a copy of the settings; nothing happens when the result is the same as before. */
    update(change) {
      const draft = cloneJson(current);
      change(draft);
      const next = sanitizeSettings(draft);
      if (JSON.stringify(next) === JSON.stringify(current)) return;
      current = next;
      stamp = nextStamp(stamp);
      dirty = true;
      known = true;
      remember();
      announce();
      emit();
      schedulePush();
    },
    reset() {
      current = sanitizeSettings(null);
      stamp = nextStamp(stamp);
      dirty = true;
      known = true;
      remember();
      announce();
      emit();
      clearTimeout(saveTimer);
      push();
    },
  };
}

const settingsStore = createSettingsStore();

/** { settings, sync, update(change), reset() }: re-renders when the settings change. */
function useSettings() {
  const view = useSyncExternalStore(settingsStore.subscribe, settingsStore.snapshot);
  return { settings: view.settings, sync: view.sync, update: settingsStore.update, reset: settingsStore.reset };
}

/** Keeps this device's settings in step with the Raspberry's: asked when the page opens and whenever it comes back to the front. */
function useSettingsSync() {
  useEffect(() => {
    settingsStore.announce();
    settingsStore.pull();
    return onResume(() => settingsStore.pull());
  }, []);
}

/**
 * What the notification service says about itself: null (nothing yet), or { version, seen (s), lastAction }.
 * `undefined` while the first answer is on its way. Read every few seconds while `active`.
 */
const NOTIFIER_POLL_MS = 8000;
function useNotifierStatus(active) {
  const [status, setStatus] = useState(undefined);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const read = async () => {
      try {
        const answer = await readSettingsDb(NOTIFIER_DB_KEY);
        if (cancelled) return;
        setStatus(answer.ok && isPlainObject(answer.value) ? answer.value : answer.ok ? null : undefined);
      } catch (e) {}
    };
    const stop = startPolling(read, NOTIFIER_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);
  return status;
}

/* ---------------------------------------------------------------------------
   Which address the camera is reached at
   The dashboard may be opened from the home network or through ZeroTier, and the camera page of the printer is
   served by the same Raspberry: it has to be asked at the address the phone can reach.
   ------------------------------------------------------------------------- */
const hostName = (host) => String(host).replace(/:\d+$/, "").toLowerCase();
/** "192.168" of "192.168.1.17" (the home network or the ZeroTier network), "" for a name. */
const networkOf = (host) => (/^\d+\.\d+\.\d+\.\d+$/.test(hostName(host)) ? hostName(host).split(".").slice(0, 2).join(".") : "");

/** { host, side: "local" | "external" } for the page opened at `hostname`. */
function pickCameraHost(settings, hostname = window.location.hostname) {
  const { localIp, externalIp, route } = settings.network;
  const here = hostName(hostname);
  // an address that is not set is the one the dashboard was opened at (the camera is on the same Raspberry)
  if (route === "local") return { host: localIp || here, side: "local" };
  if (route === "external") return { host: externalIp || here, side: "external" };
  if (!localIp && !externalIp) return { host: here, side: "same" };
  if (localIp && here === hostName(localIp)) return { host: localIp, side: "local" };
  if (externalIp && here === hostName(externalIp)) return { host: externalIp, side: "external" };
  const net = networkOf(here);
  if (net && localIp && net === networkOf(localIp)) return { host: localIp, side: "local" };
  if (net && externalIp && net === networkOf(externalIp)) return { host: externalIp, side: "external" };
  if (localIp && here.startsWith("192.168.")) return { host: localIp, side: "local" }; // as before the settings existed
  return externalIp ? { host: externalIp, side: "external" } : { host: here, side: "same" };
}

/** `address` (a path on the printer or a full address) as a full address. */
function cameraAddress(settings, address, hostname) {
  if (/^https?:\/\//i.test(address)) return address;
  // 1.93: on the encrypted entrance the camera comes through the service too (an https page cannot show http pictures)
  if (window.location.protocol === "https:" && /^\/webcam/.test(address)) return window.location.origin + address;
  const protocol = window.location.protocol === "https:" ? "https:" : "http:";
  return protocol + "//" + pickCameraHost(settings, hostname).host + address;
}

/* ---------------------------------------------------------------------------
   The Android app
   From version 4 the app does not have its addresses written inside any more: it keeps the ones of the settings
   (KlippEyeApp.setAddresses, which refuses anything that is not a private network) and uses them to connect at its
   next start. Its own "Indirizzi" window, which appears when it cannot connect, sets them here too (klippeyeSetAddresses).
   ------------------------------------------------------------------------- */
let lastTold = ""; // the pair of addresses the app was last told, "local|external"

/** The pair the app is told: an address not set is the one the app reached the dashboard at (the app wants both). */
function appPair(settings) {
  const local = hostName(settings.network.localIp) || hostName(window.location.hostname);
  const external = hostName(settings.network.externalIp) || local;
  return [local, external];
}

/**
 * App 1.7.0: the fingerprint of the Raspberry's HTTPS certificate ("" when HTTPS is off), told once per page: the app then
 * opens the dashboard with https and accepts that certificate only (KlippEye 1.93).
 */
let toldCertificate = false;
async function tellAppCertificate() {
  const bridge = nativeBridge();
  if (toldCertificate || !bridge || typeof bridge.setCertificate !== "function") return;
  toldCertificate = true;
  try {
    const response = await fetchFresh("/api/https", { timeout: 5000 });
    if (!response.ok) return;
    const info = await response.json();
    bridge.setCertificate(info.running && info.fingerprint ? String(info.fingerprint) : "");
  } catch (e) {
    toldCertificate = false; // the service did not answer: next time
  }
}

function tellApp(settings) {
  tellAppCertificate();
  const bridge = nativeBridge();
  if (!APP_KNOWS_ADDRESSES || !bridge || typeof bridge.setAddresses !== "function") return;
  const [local, external] = appPair(settings);
  if (local + "|" + external === lastTold) return;
  lastTold = local + "|" + external;
  try {
    bridge.setAddresses(local, external);
  } catch (e) {}
}

/** What the app has made of the addresses of `settings`: "browser" | "old" (an app that cannot) | "waiting" | "ok" | "refused". */
function appAddressesState(settings) {
  if (!IN_APP_WEBVIEW) return "browser";
  const bridge = nativeBridge();
  if (!APP_KNOWS_ADDRESSES || !bridge || typeof bridge.getAddresses !== "function") return "old";
  const pair = appPair(settings).join("|");
  if (pair !== lastTold) return "waiting";
  try {
    const app = JSON.parse(bridge.getAddresses());
    return app.local + "|" + app.external === pair ? "ok" : "refused";
  } catch (e) {
    return "waiting";
  }
}

if (APP_KNOWS_ADDRESSES) {
  // called by the KlippEye app
  window.klippeyeSetAddresses = async (local, external) => {
    const cleanLocal = cleanHost(local);
    const cleanExternal = typeof external === "string" && external.trim() === "" ? "" : cleanHost(external); // app 1.4.0: the external one is optional
    if (!cleanLocal || cleanExternal === null) return;
    await settingsStore.pull(); // the Raspberry's settings first: the new addresses go on top of them, not of the defaults
    settingsStore.update((draft) => {
      draft.network.localIp = cleanLocal;
      draft.network.externalIp = cleanExternal;
    });
  };
}
