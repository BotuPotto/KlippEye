/* ============================================================================
   16a · PRINTER FUNCTIONS
   The buttons of the dashboard that run something of the printer itself (park, wipe the nozzle, load and unload the
   filament, the case light) and the filament-change notification. Every printer does these with its own macros, or not
   at all, so nothing here is fixed: for each function the settings say (59g-printer-functions.js)
     · "auto"   KlippEye looks for the usual macro names in Klipper (PARK, LOAD_FILAMENT, M701...) and uses what it finds;
     · "macro"  a macro chosen by the person;
     · "gcode"  a few lines of G-code written by the person;
     · "off"    the button is not shown.
   The lights (1.37: as many as the printer has) can also be switched directly on a Klipper output ("object": [output_pin],
   [led], [neopixel]...), with their brightness and colour, and their switch always shows the state of that output (and
   of the klipper-led_effect effects drawn on it), whoever changed it. Until the person changes the list, it is what
   KlippEye finds: every pair of light macros (LUCI_ON / LUCI_OFF...) and every LED output (and the pins named as lights).
   ========================================================================== */

const FUNCTION_CANDIDATES = {
  park: ["KLIPPEYE_PARK", "PARK", "PARK_TOOLHEAD", "TOOLHEAD_PARK", "PARK_CENTER", "G27"],
  wipe: ["KLIPPEYE_WIPE", "WIPE", "CLEAN_NOZZLE", "NOZZLE_CLEAN", "WIPE_NOZZLE", "NOZZLE_WIPE"],
  load: ["KLIPPEYE_LOAD_FILAMENT", "LOAD_FILAMENT", "FILAMENT_LOAD", "M701"],
  unload: ["KLIPPEYE_UNLOAD_FILAMENT", "UNLOAD_FILAMENT", "FILAMENT_UNLOAD", "M702"],
};
const LIGHT_WORDS = /light|luci|luce|lamp|case|chamber|led/i;

/** The first of `names` that Klipper knows as a command. */
const firstRegistered = (names, commands) => names.find((name) => name in (commands || {})) || "";

/** The output that most likely drives the light: one whose name says so, else the only one there is. */
function findLightObject(lights) {
  return lights.find((light) => LIGHT_WORDS.test(light.name) && light.kind !== "output_pin") || lights.find((light) => LIGHT_WORDS.test(light.name)) || (lights.length === 1 ? lights[0] : null);
}

/** Every pair of macros that switch a light (LIGHTS_ON / LIGHTS_OFF, LUCI_ON / LUCI_OFF...), KlippEye's own first. */
function findAllLightMacros(macros) {
  const upper = new Set(macros);
  const pairs = [];
  for (const name of ["KLIPPEYE_LIGHT_ON", ...macros]) {
    const match = /^(.*?)(_?)ON$/.exec(name);
    if (!match || !LIGHT_WORDS.test(match[1]) || !upper.has(name) || pairs.some((pair) => pair.on === name)) continue;
    const off = match[1] + match[2] + "OFF";
    if (upper.has(off)) pairs.push({ on: name, off, stem: match[1] });
  }
  return pairs;
}

const lightSlug = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 36) || "light";
/** "LUCI" -> "Luci", "case_light" -> "Case light", "KLIPPEYE_LIGHT" -> "Light". */
const lightLabel = (text) => {
  const words = String(text).replace(/^KLIPPEYE_/i, "").replace(/[_-]+/g, " ").trim().toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : tx("Light");
};
/** The output whose name is the macro's stem (LUCI_ON -> neopixel LUCI), or null. */
const outputNamed = (outputs, stem) => {
  const key = lightSlug(stem);
  return outputs.find((output) => lightSlug(output.name) === key) || outputs.find((output) => key && (lightSlug(output.name).includes(key) || key.includes(lightSlug(output.name)))) || null;
};

/**
 * The lights KlippEye finds by itself: each pair of light macros (read on the output of the same name, when there is one)
 * and each LED output not driven by those macros (pins only when their name says light: a pin can be a buzzer or a relay).
 */
function detectLights(capabilities) {
  const outputs = capabilities.lights || [];
  const pairs = findAllLightMacros(capabilities.macros || []);
  const used = new Set();
  const items = [];
  for (const pair of pairs) {
    let reads = outputNamed(outputs, pair.stem);
    if (!reads && pairs.length === 1) reads = findLightObject(outputs.filter((output) => !used.has(output.object)));
    if (reads) used.add(reads.object);
    items.push({ id: "m-" + lightSlug(pair.on), name: lightLabel(pair.stem), mode: "macro", onMacro: pair.on, offMacro: pair.off, stateFrom: reads ? reads.object : "", main: true });
  }
  for (const output of outputs) {
    if (used.has(output.object) || (output.kind === "output_pin" && !LIGHT_WORDS.test(output.name))) continue;
    items.push({ id: "o-" + lightSlug(output.object), name: lightLabel(output.name), mode: "object", object: output.object, main: true });
  }
  return items.map(cleanLightItem);
}

/** The lights in use: the person's list, or (never changed) what KlippEye finds. */
const lightItems = (lights, capabilities) => (lights.configured ? lights.items : capabilities.known ? detectLights(capabilities) : []);

/**
 * One light as it works now: { id, name, main, mode, object (the output to read, or null), on, off (the G-code),
 * confirmable, dim, color, white } — mode "off" when it cannot be switched (an output Klipper does not have...).
 */
function resolveLightItem(item, capabilities) {
  const outputs = capabilities.lights || [];
  const commands = capabilities.commands || {};
  let mode = item.mode;
  let object = null;
  let on = "";
  let off = "";
  if (mode === "object") {
    object = lightByObject(outputs, item.object);
    if (object) ({ on, off } = lightCommands(object, commands));
  } else {
    on = mode === "macro" ? item.onMacro : item.onGcode.trim();
    off = mode === "macro" ? item.offMacro : item.offGcode.trim();
    if (item.stateFrom === "auto") object = (mode === "macro" && outputNamed(outputs, item.onMacro.replace(/_?ON$/, ""))) || findLightObject(outputs);
    else if (item.stateFrom) object = lightByObject(outputs, item.stateFrom);
  }
  if (!on || !off) mode = "off";
  const direct = mode === "object" && object;
  return {
    id: item.id,
    name: item.name || (object ? lightLabel(object.name) : tx("Light")),
    main: item.main,
    mode,
    object,
    on,
    off,
    confirmable: Boolean(object),
    dim: Boolean(direct && object.dim),
    color: Boolean(direct && object.color),
    white: Boolean(direct && object.white),
  };
}

/**
 * What each function does now: { mode, command, chosen } for park / wipe / load / unload, where `command` is the G-code
 * to send ("" when the function is off or nothing was found) and `chosen` false when it was found by KlippEye ("auto").
 * `lights`: the lights that can be switched (resolveLightItem), in the order of the list.
 */
function resolveFunctions(functions, capabilities) {
  const commands = capabilities.commands || {};
  const out = {};
  for (const id of ACTION_FUNCTIONS) {
    const one = functions[id];
    if (one.mode === "auto") {
      const found = capabilities.known ? firstRegistered(FUNCTION_CANDIDATES[id], commands) : "";
      out[id] = { mode: found ? "macro" : "off", command: found, chosen: false, found };
    } else if (one.mode === "macro") out[id] = { mode: "macro", command: one.macro, chosen: true };
    else if (one.mode === "gcode") out[id] = { mode: "gcode", command: one.gcode.trim(), chosen: true };
    else out[id] = { mode: "off", command: "", chosen: true };
  }
  out.lightItems = lightItems(functions.lights, capabilities);
  out.lights = out.lightItems.map((item) => resolveLightItem(item, capabilities)).filter((light) => light.mode !== "off");
  return out;
}

const lightByObject = (lights, name) => lights.find((light) => light.object === name) || null;

/** The standard Klipper commands that switch an output on and off (and stop the effects drawn on it). */
function lightCommands(light, commands) {
  if (light.kind === "output_pin") return { on: "SET_PIN PIN=" + light.name + " VALUE=1", off: "SET_PIN PIN=" + light.name + " VALUE=0" };
  const set = (value) => "SET_LED LED=" + light.name + " RED=" + value + " GREEN=" + value + " BLUE=" + value + " WHITE=" + value;
  const stop = light.effects.length && "STOP_LED_EFFECTS" in (commands || {}) ? 'STOP_LED_EFFECTS LEDS="' + light.kind + ":" + light.name + '"\n' : "";
  return { on: set(1), off: stop + set(0) };
}

/** "#rrggbb" -> [r, g, b] from 0 to 1. */
const hexToUnit = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const unitToHex = (rgb) => "#" + rgb.map((c) => Math.round(clamp(c, 0, 1) * 255).toString(16).padStart(2, "0")).join("");

/**
 * The G-code that sets an output's brightness (0-100) and colour ("#rrggbb"; white on a LED with a white channel uses
 * it). A pin without PWM only knows on and off. The effects drawn on a LED are stopped first.
 */
function lightLevelCommand(light, level, color, commands) {
  const object = light.object;
  const k = clamp(level, 0, 100) / 100;
  if (object.kind === "output_pin") return "SET_PIN PIN=" + object.name + " VALUE=" + (object.dim ? Number(k.toFixed(3)) : k > 0 ? 1 : 0);
  const [r, g, b] = hexToUnit(LIGHT_HEX.test(color || "") ? color : "#ffffff");
  const pureWhite = r === 1 && g === 1 && b === 1;
  const channel = (value) => Number((value * k).toFixed(3));
  const stop = object.effects.length && "STOP_LED_EFFECTS" in (commands || {}) ? 'STOP_LED_EFFECTS LEDS="' + object.kind + ":" + object.name + '"\n' : "";
  return stop + "SET_LED LED=" + object.name + " RED=" + channel(r) + " GREEN=" + channel(g) + " BLUE=" + channel(b) + " WHITE=" + (object.white && pureWhite ? channel(1) : object.white ? 0 : channel(1));
}

/** What an output does now: { on, level (0-100), color ("#rrggbb" or "") }; null when Klipper did not say. */
function lightDetails(status, light) {
  const object = light.object;
  const own = object && status[object.object];
  if (!own) return null;
  const effect = object.effects.some((name) => status[name] && status[name].enabled);
  if (object.kind === "output_pin") {
    const value = Number(own.value) || 0;
    return { on: value > 0 || effect, level: Math.round(value * 100), color: "" };
  }
  const first = (Array.isArray(own.color_data) ? own.color_data : []).find((led) => Array.isArray(led)) || [0, 0, 0, 0];
  const [r, g, b, w] = [0, 1, 2, 3].map((i) => Number(first[i]) || 0);
  const top = Math.max(r, g, b, w);
  const color = top > 0.001 ? (r < 0.001 && g < 0.001 && b < 0.001 ? "#ffffff" : unitToHex([r / top, g / top, b / top])) : "";
  return { on: top > 0.001 || effect, level: Math.round(top * 100), color };
}

/** Is the light on? From the output itself: a pin above 0, a LED with some colour, or an effect running on it. null: unknown. */
function lightIsOn(status, light) {
  const own = status[light.object];
  if (!own) return null;
  if (light.effects.some((effect) => status[effect] && status[effect].enabled)) return true;
  if (light.kind === "output_pin") return Number(own.value) > 0;
  const colours = Array.isArray(own.color_data) ? own.color_data : [];
  return colours.some((led) => Array.isArray(led) && led.some((channel) => Number(channel) > 0.001));
}

/** The query of Moonraker that reads the light: the output and its effects. */
const lightQuery = (light) => [light.object, ...light.effects].map(encodeURIComponent).join("&");

/** The functions as resolved now (settings + what Klipper has); updates when either changes. */
function usePrinterFunctions() {
  const { settings } = useSettings();
  const capabilities = usePrinterCapabilities();
  return useMemo(() => resolveFunctions(settings.functions, capabilities), [settings.functions, capabilities]);
}
