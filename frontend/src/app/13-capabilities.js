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
};

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
  };
}

/** Loads the capabilities; resolves null when Klipper does not answer (not ready yet). */
async function loadCapabilities() {
  try {
    const [configfile, commands] = await Promise.all([moonraker.configfile(), moonraker.gcodeCommands()]);
    return Object.keys(configfile.settings || {}).length === 0 ? null : deriveCapabilities(configfile, commands);
  } catch (error) {
    return null;
  }
}

/** The capabilities (UNKNOWN_CAPABILITIES until Klipper answers; asked again every few seconds until it does). */
function usePrinterCapabilities() {
  const [capabilities, setCapabilities] = useState(UNKNOWN_CAPABILITIES);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const attempt = async () => {
      const loaded = await loadCapabilities();
      if (cancelled) return;
      if (loaded) setCapabilities(loaded);
      else timer = setTimeout(attempt, CAPABILITIES_RETRY_MS);
    };
    attempt();
    // a restart may have changed the config (SAVE_CONFIG, an edited printer.cfg): read it again when Klipper is back
    const stopListening = onKlipperReady(() => {
      clearTimeout(timer);
      attempt();
    });
    return () => {
      cancelled = true;
      clearTimeout(timer);
      stopListening();
    };
  }, []);

  return capabilities;
}
