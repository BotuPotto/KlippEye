/* ============================================================================
   13 · PRINTER CAPABILITIES
   What this particular printer can do, read once from Klipper: which config
   sections exist ([screws_tilt_adjust], [axis_twist_compensation], ...), which
   G-code commands are registered (CARTOGRAPHER_AXIS_TWIST_COMPENSATION,
   Z_OFFSET_APPLY_PROBE, QUERY_PROBE, ...) and what drives the Z endstop.
   Features use it to offer only what the machine understands, the way Mainsail
   and Fluidd do.
   ========================================================================== */

const CAPABILITIES_RETRY_MS = 5000;

/** Cartographer's own, fully automatic axis twist calibration (scan + touch). Klipper's stock
 *  AXIS_TWIST_COMPENSATION_CALIBRATE needs a manual TESTZ session, which this dashboard does not drive. */
const CARTOGRAPHER_TWIST_COMMAND = "CARTOGRAPHER_AXIS_TWIST_COMPENSATION";
/** Config sections that provide a Z probe (the last, `probe_eddy_current <name>`, is matched by prefix). */
const PROBE_SECTIONS = ["probe", "bltouch", "smart_effector", "cartographer", "scanner", "beacon"];

/**
 * While Klipper cannot be asked (it is starting, or the page just opened) nothing is hidden:
 * every feature is offered and Klipper has the last word. `known` turns true on the first answer.
 */
const UNKNOWN_CAPABILITIES = {
  known: false,
  screwsTilt: true,
  screwLayout: [],
  twistCommand: CARTOGRAPHER_TWIST_COMMAND,
  twistNeedsConfig: false,
  probe: true,
  zOffsetApply: "Z_OFFSET_APPLY_PROBE",
  axisLimits: DEFAULT_AXIS_LIMITS,
  maxTemp: DEFAULT_MAX_TEMP,
  macros: [],
  commands: {},
  lights: [],
  sensors: [],
};

/** Klipper objects that can be a light, and the command that switches each kind. */
const LIGHT_KINDS = ["output_pin", "led", "neopixel", "dotstar", "pca9533", "pca9632"];

/**
 * The parts of the printer that "Printer functions" (59g-printer-functions.js) can use, read from Klipper:
 *   macros:  every [gcode_macro] (the names as commands, upper case), sorted;
 *   lights:  [{ object: "neopixel LUCI", kind, name, effects: ["led_effect IDLE", ...] }]: the outputs that may drive a light,
 *            each with the klipper-led_effect effects drawn on it (an effect running = the light is on);
 *   sensors: the filament sensors ("filament_switch_sensor runout", "filament_motion_sensor ...").
 */
function deriveParts(configfile, commands, objects) {
  const settings = configfile.settings || {};
  const raw = configfile.config || {};
  const macros = Object.keys(settings)
    .filter((name) => name.startsWith("gcode_macro "))
    .map((name) => name.slice(12).toUpperCase())
    .filter((name) => !name.startsWith("_"))
    .sort();
  const rawSection = (name) => raw[Object.keys(raw).find((key) => key.toLowerCase() === name.toLowerCase())] || {};
  const lights = objects
    .filter((object) => LIGHT_KINDS.includes(object.split(" ")[0]) && object.includes(" "))
    .map((object) => {
      const [kind, ...rest] = object.split(" ");
      const name = rest.join(" ");
      const target = (kind + ":" + name).toLowerCase();
      const effects = objects.filter((other) => other.startsWith("led_effect ") && String(rawSection(other).leds || "").toLowerCase().split(/[\s,]+/).some((led) => led.replace(/\(.*$/, "") === target));
      return { object, kind, name, effects };
    });
  const sensors = objects.filter((object) => object.startsWith("filament_switch_sensor ") || object.startsWith("filament_motion_sensor "));
  return { macros, commands, lights, sensors };
}

/** The travel of each axis from [stepper_x] / [stepper_y] / [stepper_z] (position_min, default 0, and position_max). */
function axisLimitsFrom(settings) {
  const out = {};
  for (const axis of ["X", "Y", "Z"]) {
    const section = settings["stepper_" + axis.toLowerCase()] || {};
    const max = Number(section.position_max);
    const min = section.position_min === undefined ? 0 : Number(section.position_min);
    out[axis] = Number.isFinite(max) && Number.isFinite(min) && max > min ? [min, max] : DEFAULT_AXIS_LIMITS[axis];
  }
  return out;
}

/** The highest temperatures Klipper accepts ([extruder] and [heater_bed] max_temp). */
function maxTempFrom(settings) {
  const read = (section, fallback) => (Number.isFinite(Number((settings[section] || {}).max_temp)) ? Number(settings[section].max_temp) : fallback);
  return { hotend: read("extruder", DEFAULT_MAX_TEMP.hotend), bed: read("heater_bed", DEFAULT_MAX_TEMP.bed) };
}

/**
 * `configfile` is Klipper's config object (`settings`: every section, parsed); `commands` the map
 * of registered G-code commands.
 */
function deriveCapabilities(configfile, commands) {
  const settings = configfile.settings || {};
  const hasSection = (name) => name in settings;
  const registered = (name) => name in commands;

  // Z is homed on the probe ("probe:z_virtual_endstop") or on a physical switch.
  const endstopPin = String((settings.stepper_z && settings.stepper_z.endstop_pin) || "").replace(/\s+/g, "");
  const zHomesOnProbe = endstopPin.includes("probe:z_virtual_endstop");

  // Cartographer registers the twist command even without [axis_twist_compensation], where it only prints a reminder.
  const cartographerTwist = registered(CARTOGRAPHER_TWIST_COMMAND);
  const twistConfigured = hasSection("axis_twist_compensation");

  // The screws of [screws_tilt_adjust]: "screw1: x, y" and "screw1_name: front left".
  const screwSection = settings.screws_tilt_adjust || {};
  const screwLayout = Object.keys(screwSection)
    .filter((key) => /^screw\d+$/.test(key))
    .sort((a, b) => parseInt(a.slice(5)) - parseInt(b.slice(5)))
    .map((id) => ({ id, name: screwSection[id + "_name"] || id, x: (screwSection[id] || [])[0], y: (screwSection[id] || [])[1] }));

  // The command that writes the live Z offset into the config: for the probe or for the endstop, never the other.
  const applyCommand = zHomesOnProbe ? "Z_OFFSET_APPLY_PROBE" : "Z_OFFSET_APPLY_ENDSTOP";

  return {
    known: true,
    screwsTilt: hasSection("screws_tilt_adjust") && registered("SCREWS_TILT_CALCULATE"),
    screwLayout,
    twistCommand: cartographerTwist && twistConfigured ? CARTOGRAPHER_TWIST_COMMAND : null,
    twistNeedsConfig: cartographerTwist && !twistConfigured,
    probe: registered("QUERY_PROBE") || PROBE_SECTIONS.some(hasSection) || Object.keys(settings).some((name) => name.startsWith("probe_eddy_current ")),
    zOffsetApply: registered(applyCommand) ? applyCommand : null,
    axisLimits: axisLimitsFrom(settings),
    maxTemp: maxTempFrom(settings),
  };
}

/** Loads the capabilities; resolves null when Klipper does not answer (not ready yet). */
async function loadCapabilities() {
  try {
    const [configfile, commands, objects] = await Promise.all([moonraker.configfile(), moonraker.gcodeCommands(), moonraker.objectsList().catch(() => [])]);
    return Object.keys(configfile.settings || {}).length === 0 ? null : { ...deriveCapabilities(configfile, commands), ...deriveParts(configfile, commands, objects) };
  } catch (error) {
    return null;
  }
}

/**
 * The capabilities, shared by every part of the page (UNKNOWN_CAPABILITIES until Klipper answers; asked again every few
 * seconds until it does, and again after every restart of Klipper). The first component that needs them starts the loading.
 */
const capabilitiesStore = (() => {
  let current = UNKNOWN_CAPABILITIES;
  let started = false;
  let timer = null;
  const listeners = new Set();
  const attempt = async () => {
    const loaded = await loadCapabilities();
    if (loaded) {
      current = loaded;
      listeners.forEach((listener) => listener());
    } else timer = setTimeout(attempt, CAPABILITIES_RETRY_MS);
  };
  return {
    get: () => current,
    subscribe(listener) {
      listeners.add(listener);
      if (!started) {
        started = true;
        attempt();
        // a restart may have changed the config (SAVE_CONFIG, an edited printer.cfg): read it again when Klipper is back
        onKlipperReady(() => {
          clearTimeout(timer);
          attempt();
        });
      }
      return () => listeners.delete(listener);
    },
    /** Read again now (after KlippEye wrote macros and Klipper restarted). */
    reload() {
      clearTimeout(timer);
      return attempt();
    },
  };
})();

function usePrinterCapabilities() {
  const [capabilities, setCapabilities] = useState(capabilitiesStore.get);
  useEffect(() => {
    const update = () => setCapabilities(capabilitiesStore.get());
    const stop = capabilitiesStore.subscribe(update);
    update();
    return stop;
  }, []);
  return capabilities;
}
