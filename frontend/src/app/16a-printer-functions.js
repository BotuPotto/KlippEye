/* ============================================================================
   16a · PRINTER FUNCTIONS
   The buttons of the dashboard that run something of the printer itself (park, wipe the nozzle, load and unload the
   filament, the case light) and the filament-change notification. Every printer does these with its own macros, or not
   at all, so nothing here is fixed: for each function the settings say (59g-printer-functions.js)
     · "auto"   KlippEye looks for the usual macro names in Klipper (PARK, LOAD_FILAMENT, M701...) and uses what it finds;
     · "macro"  a macro chosen by the person;
     · "gcode"  a few lines of G-code written by the person;
     · "off"    the button is not shown.
   The light can also be switched directly on a Klipper output ("object": [output_pin], [led], [neopixel]...), and its
   switch always shows the state of that output (and of the klipper-led_effect effects drawn on it), whoever changed it.
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

/** A pair of macros that switch a light: LIGHTS_ON / LIGHTS_OFF, LUCI_ON / LUCI_OFF, CASELIGHT_ON / CASELIGHT_OFF... */
function findLightMacros(macros) {
  const upper = new Set(macros);
  for (const name of ["KLIPPEYE_LIGHT_ON", ...macros]) {
    const match = /^(.*?)(_?)ON$/.exec(name);
    if (!match || !LIGHT_WORDS.test(match[1]) || !upper.has(name)) continue;
    const off = match[1] + match[2] + "OFF";
    if (upper.has(off)) return { on: name, off };
  }
  return null;
}

/** The output that most likely drives the light: one whose name says so, else the only one there is. */
function findLightObject(lights) {
  return lights.find((light) => LIGHT_WORDS.test(light.name) && light.kind !== "output_pin") || lights.find((light) => LIGHT_WORDS.test(light.name)) || (lights.length === 1 ? lights[0] : null);
}

/**
 * What each function does now: { mode, command, chosen } for park / wipe / load / unload, where `command` is the G-code
 * to send ("" when the function is off or nothing was found) and `chosen` false when it was found by KlippEye ("auto").
 * The light: { mode, chosen, object (the output to read, or null), on, off (the G-code), confirmable }.
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
  out.light = resolveLight(functions.light, capabilities);
  return out;
}

const lightByObject = (lights, name) => lights.find((light) => light.object === name) || null;

function resolveLight(light, capabilities) {
  const lights = capabilities.lights || [];
  const commands = capabilities.commands || {};
  let mode = light.mode;
  let object = null;
  let on = "";
  let off = "";
  if (mode === "auto") {
    const pair = findLightMacros(capabilities.macros || []);
    object = findLightObject(lights);
    if (pair) {
      mode = "macro";
      on = pair.on;
      off = pair.off;
    } else if (object) mode = "object";
    else mode = "off";
  } else if (mode === "object") object = lightByObject(lights, light.object);
  else if (mode === "macro") {
    on = light.onMacro;
    off = light.offMacro;
  } else if (mode === "gcode") {
    on = light.onGcode.trim();
    off = light.offGcode.trim();
  }
  if (mode === "macro" || mode === "gcode") {
    if (light.mode !== "auto") object = light.stateFrom === "auto" ? findLightObject(lights) : light.stateFrom ? lightByObject(lights, light.stateFrom) : null;
  }
  if (mode === "object") {
    if (!object) mode = "off";
    else {
      const commandsFor = lightCommands(object, commands);
      on = commandsFor.on;
      off = commandsFor.off;
    }
  }
  if (mode !== "off" && (!on || !off)) mode = "off";
  return { mode, chosen: light.mode !== "auto", object, on, off, confirmable: Boolean(object) };
}

/** The standard Klipper commands that switch an output on and off (and stop the effects drawn on it). */
function lightCommands(light, commands) {
  if (light.kind === "output_pin") return { on: "SET_PIN PIN=" + light.name + " VALUE=1", off: "SET_PIN PIN=" + light.name + " VALUE=0" };
  const set = (value) => "SET_LED LED=" + light.name + " RED=" + value + " GREEN=" + value + " BLUE=" + value + " WHITE=" + value;
  const stop = light.effects.length && "STOP_LED_EFFECTS" in (commands || {}) ? 'STOP_LED_EFFECTS LEDS="' + light.kind + ":" + light.name + '"\n' : "";
  return { on: set(1), off: stop + set(0) };
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
