/* ============================================================================
   10 · CONFIGURATION
   Constants shared by the whole dashboard: tabs, storage keys, polling rates.
   ========================================================================== */

/** Dashboard pages, in bottom-navigation order. */
const TAB_IDS = ["home", "controllo", "files", "config", "sistema"];

/** localStorage keys (all owned by this dashboard). */
const STORAGE_KEYS = {
  currentTab: "ke_current_tab",
  lastAiAnalysis: "ke_last_ai",
  lastAiAnalysisTime: "ke_last_ai_time",
  calibrationSelected: "ke_calibration_selected",
  calibrationMacrosCache: "ke_calibration_macros_cache",
  calibrationCacheTime: "ke_calibration_cache_time",
  endstopsOpen: "ke_endstops_open",
  zOffsetStep: "ke_zoffset_step",
  settings: "ke_settings", // the dashboard settings as this device knows them (app/16-settings.js)
};

/** Polling periods in milliseconds. */
const POLL_MS = {
  printerStatus: 1000, // temperatures, position, homed axes
  consoleStore: 500,
  files: 8000,
  fans: 1200,
  printProgress: 2000,
  light: 1500, // the light rarely changes by itself; while a command waits for Klipper the engine asks every 250 ms (app/41-camera.js)
};

/** Axis travel limits (mm) until Klipper has said the real ones (13-capabilities.js reads position_min/max). */
const DEFAULT_AXIS_LIMITS = { X: [0, 250], Y: [0, 250], Z: [0, 250] };
/** Maximum temperatures (°C) until Klipper has said the real ones ([extruder] and [heater_bed] max_temp). */
const DEFAULT_MAX_TEMP = { hotend: 300, bed: 120 };
/** Feed rates (mm/min) for jog and go-to moves. */
const FEEDRATE = { xy: 6000, z: 1500 };
/** Position shown before the printer has reported a real one: the centre of the bed, 5 mm up. */
const centrePosition = (limits) => ({ x: Math.round((limits.X[0] + limits.X[1]) / 2), y: Math.round((limits.Y[0] + limits.Y[1]) / 2), z: 5 });
