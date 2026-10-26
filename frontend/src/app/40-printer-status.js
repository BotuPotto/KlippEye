/* ============================================================================
   40 · PRINTER STATUS
   One poll of the backend's /api/printer snapshot feeds everything the Home tab
   shows live: heater temperatures, toolhead position, which axes are homed and
   the live Z offset.
   ========================================================================== */

/** A heater is drawn "hot" (red) from this temperature, current or target. */
const HOT_THRESHOLD_C = 50;
const isHot = (heater) => heater.cur >= HOT_THRESHOLD_C || heater.target >= HOT_THRESHOLD_C;

const heaterFromSnapshot = (data) => {
  const source = data || {};
  return { cur: source.temperature ?? source.cur ?? 0, target: source.target ?? 0 };
};

/** Toolhead position [x, y, z] from a snapshot, or null when unavailable. */
function positionFromSnapshot(snapshot) {
  const raw = snapshot.raw || {};
  const toolhead = raw.toolhead || snapshot.toolhead || {};
  const position = toolhead.position || (raw.gcode_move && raw.gcode_move.gcode_position);
  return position ? { x: position[0], y: position[1], z: position[2] } : null;
}

/** The live Z offset (G-code offset on Z, "homing_origin"), or `fallback` when the snapshot has none. */
function zOffsetFromSnapshot(snapshot, fallback) {
  const gcodeMove = (snapshot.raw && snapshot.raw.gcode_move) || {};
  const origin = gcodeMove.homing_origin;
  return Array.isArray(origin) && typeof origin[2] === "number" ? origin[2] : fallback;
}

function usePrinterStatus() {
  const [status, setStatus] = useState({
    hotend: { cur: 0, target: 0 },
    bed: { cur: 0, target: 0 },
    position: null, // { x, y, z } once the printer has reported one
    homedAxes: undefined, // e.g. "xyz" or "xy" once known
    zOffset: 0, // the live G-code Z offset (baby stepping), mm
  });
  const pollRef = useRef(noop);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const snapshot = await brain.printer();
        if (cancelled) return;
        const toolhead = (snapshot.raw && snapshot.raw.toolhead) || snapshot.toolhead || {};
        const position = positionFromSnapshot(snapshot);
        setStatus((previous) => ({
          hotend: heaterFromSnapshot(snapshot.extruder),
          bed: heaterFromSnapshot(snapshot.heater_bed),
          position: position || previous.position,
          homedAxes: typeof toolhead.homed_axes === "string" ? toolhead.homed_axes.toLowerCase() : previous.homedAxes,
          zOffset: zOffsetFromSnapshot(snapshot, previous.zOffset),
        }));
      } catch (e) {}
    };
    pollRef.current = poll;
    const stopPolling = startPolling(poll, POLL_MS.printerStatus);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  // `refresh()` asks again right away, e.g. after a command whose effect the screen should show at once.
  return { ...status, refresh: () => pollRef.current() };
}
