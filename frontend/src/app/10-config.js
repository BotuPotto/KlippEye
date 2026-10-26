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

/** Axis travel limits (mm) used by the on-screen jog controls. */
const AXIS_LIMITS = { X: [0, 350], Y: [0, 350], Z: [0, 300] };
/** Feed rates (mm/min) for jog and go-to moves. */
const FEEDRATE = { xy: 6000, z: 1500 };
/** Position shown before the printer has reported a real one. */
const DEFAULT_POSITION = { x: 163, y: 163, z: 5 };
