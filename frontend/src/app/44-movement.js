/* ============================================================================
   44 · MOVEMENT
   Jog pad (XY rings with 10 mm and 1 mm steps), Z buttons, homing buttons and
   the live X/Y/Z read-out. 1.31: the Z arrows follow the part that moves (the bed,
   or the toolhead: Settings → Motion, automatic from Klipper's configuration), and
   the pad and the Z buttons may also have 50 and 100 mm steps (at most four). Tapping an axis in the read-out opens a "go to
   position" dialog; the centre button homes everything (long press = PARK).
   Under the home row: motors off (M84) and the "Calibra" menu (44a).
   ========================================================================== */

const LONG_PRESS_MS = 600;
const VIBRATE_MS = 50;
const GREEN = "log--ok";

/* ---------------------------------------------------------------------------
   Commands
   ------------------------------------------------------------------------- */
const feedrateFor = (axis) => (axis === "Z" ? FEEDRATE.z : FEEDRATE.xy);

/** Relative move of `delta` mm on one axis. */
const jogGcode = (axis, delta) => `G91\nG1 ${axis}${signed(delta)} F${feedrateFor(axis)}\nG90`;
/** Absolute move to `target` mm on one axis. */
const goToGcode = (axis, target) => `G90\nG1 ${axis}${target} F${feedrateFor(axis)}`;

/**
 * Motion actions. `echo(lines)` writes lines to the console view,
 * each line being { msg, color }.
 */
function useMotion(echo, capabilities) {
  const limits = (capabilities && capabilities.axisLimits) || DEFAULT_AXIS_LIMITS;
  const { settings } = useSettings();
  const zMoves = settings.motion.zMoves === "auto" ? (capabilities && capabilities.zMoves) || "bed" : settings.motion.zMoves;
  const xySteps = MOTION_BASE_STEPS.concat(settings.motion.xyExtra);
  const zSteps = MOTION_BASE_STEPS.concat(settings.motion.zExtra);
  const parkCommand = usePrinterFunctions().park.command; // Settings → Printer functions ("" = no park)
  const [positionDialog, setPositionDialog] = useState({ open: false, axis: null, value: "" });
  // Where the "go to position" dialog starts. As in the original dashboard this is NOT the live
  // read-out: it is the last position this page commanded (homing or a go-to), initially the
  // centre of the bed.
  const [commandedByPage, setCommanded] = useState(null);
  const commanded = commandedByPage || centrePosition(limits);

  const jog = (axis, delta) => {
    toast.action(`${axis}${signed(delta)}mm`);
    fireGcode(jogGcode(axis, delta));
  };

  const homeAxes = (axes) => {
    const gcode = axes === "XY" ? "G28 X Y" : `G28 ${axes}`;
    toast.action(`⌖ ${gcode}`);
    echo([{ msg: `${gcode} - Homing ${axes}`, color: GREEN }]);
    const axis = axes.toLowerCase();
    const centre = centrePosition(limits);
    setCommanded(axes === "XY" ? centre : (position) => ({ ...(position || centre), [axis]: centre[axis] }));
    fireGcode(gcode);
  };
  const homeAll = () => {
    setCommanded(centrePosition(limits));
    toast.action("⌖ G28");
    echo([{ msg: "G28 - Homing all axes", color: GREEN }]);
    fireGcode("G28");
  };
  const park = parkCommand
    ? () => {
        toast.action(tx("Park"));
        echo([{ msg: parkCommand.split("\n")[0] + " - Park", color: GREEN }]);
        fireGcode(parkCommand);
      }
    : null;
  const motorsOff = () => {
    toast.action(tx("M84 - Motors disabled"));
    echo([{ msg: "M84 - Motors off", color: GREEN }]);
    fireGcode("M84");
  };

  const openPositionDialog = (axis) => setPositionDialog({ open: true, axis, value: String(commanded[axis.toLowerCase()]) });
  const closePositionDialog = () => setPositionDialog({ open: false, axis: null, value: "" });
  const setPositionValue = (value) => setPositionDialog((d) => ({ ...d, value }));

  const goToPosition = () => {
    const requested = parseFloat(positionDialog.value);
    const axis = positionDialog.axis;
    if (isNaN(requested) || !axis) return;
    const target = clamp(requested, limits[axis][0], limits[axis][1]);
    const gcode = goToGcode(axis, target);
    setCommanded((position) => ({ ...position, [axis.toLowerCase()]: target }));
    echo([
      { msg: `> ${gcode.replace("\n", " ")}`, color: "log--input" },
      { msg: "ok", color: "log--dim" },
    ]);
    closePositionDialog();
    toast.action(`${axis} → ${target}mm`);
    fireGcode(gcode);
  };

  return { jog, homeAxes, homeAll, park, motorsOff, positionDialog, openPositionDialog, closePositionDialog, setPositionValue, goToPosition, zMoves, xySteps, zSteps };
}

/* ---------------------------------------------------------------------------
   Jog pad geometry (SVG 280 × 280, centre at 140,140)
   ------------------------------------------------------------------------- */
const PAD_CENTER = 140;
const PAD_RING_FROM = 44; // the home button sits inside
const PAD_RING_TO = 136;
const PAD_RING_GAP = 5;
/** The rings of the pad, one per step (smallest inside): { from, to, step, className }. */
function padRings(steps) {
  const width = (PAD_RING_TO - PAD_RING_FROM + PAD_RING_GAP) / steps.length;
  return steps.map((step, index) => ({
    from: PAD_RING_FROM + index * width,
    to: PAD_RING_FROM + (index + 1) * width - PAD_RING_GAP,
    step,
    className: (index % 2 === 0 ? "bambu-inner" : "bambu-outer") + " cursor-pointer",
  }));
}
/** Quadrants of each ring: which axis and direction a tap on it moves. */
const PAD_QUADRANTS = [
  { axis: "Y", sign: 1, a0: 225, a1: 315 },
  { axis: "X", sign: 1, a0: 315, a1: 405 },
  { axis: "Y", sign: -1, a0: 45, a1: 135 },
  { axis: "X", sign: -1, a0: 135, a1: 225 },
];
/** The step of each ring written on the diagonal gaps: +step up-right, −step down-left. */
function padStepLabels(rings) {
  const size = rings.length > 3 ? 10 : rings.length > 2 ? 10.5 : 11;
  return rings.flatMap((ring) => {
    const middle = (ring.from + ring.to) / 2;
    const up = polar(middle, -45);
    const down = polar(middle, 135);
    return [
      { x: up.x, y: up.y, size, text: "+" + ring.step },
      { x: down.x, y: down.y, size, text: "-" + ring.step },
    ];
  });
}
/** Axis letters drawn on the pad, as offsets from its centre (in the gap after the first ring). */
function padAxisLabels(rings) {
  const at = rings.length > 1 ? (rings[0].to + rings[1].from) / 2 : rings[0].to + 3;
  return [
    { text: "Y", dx: 0, dy: -at },
    { text: "-Y", dx: 0, dy: at },
    { text: "X", dx: at, dy: 0 },
    { text: "-X", dx: -at - 5, dy: 0 },
  ];
}

/** The four cuts between quadrants, in degrees. */
const PAD_DIAGONALS = [45, 135, 225, 315];

const polar = (radius, degrees) => {
  const radians = (degrees * Math.PI) / 180;
  return { x: PAD_CENTER + radius * Math.cos(radians), y: PAD_CENTER + radius * Math.sin(radians) };
};

/** SVG path of a ring segment between two radii and two angles. */
function ringSegmentPath(innerRadius, outerRadius, startDeg, endDeg) {
  let end = endDeg;
  while (end < startDeg) end += 360;
  const largeArc = end - startDeg > 180 ? 1 : 0;
  const a = polar(innerRadius, startDeg);
  const b = polar(outerRadius, startDeg);
  const c = polar(outerRadius, end);
  const d = polar(innerRadius, end);
  return `M ${a.x} ${a.y} L ${b.x} ${b.y} A ${outerRadius} ${outerRadius} 0 ${largeArc} 1 ${c.x} ${c.y} L ${d.x} ${d.y} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${a.x} ${a.y} Z`;
}

function JogPad({ onJog, onHomeAll, onPark, steps = MOTION_BASE_STEPS }) {
  const rings = padRings(steps);
  const pressTimer = useRef(null);
  const wasLongPress = useRef(false);
  const stopTimer = () => {
    if (pressTimer.current) {
      clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
  };
  const gestures = {
    onPointerDown: (e) => {
      wasLongPress.current = false;
      stopTimer();
      if (onPark) pressTimer.current = window.setTimeout(() => {
        wasLongPress.current = true;
        onPark();
        try {
          navigator.vibrate && navigator.vibrate(VIBRATE_MS);
        } catch (err) {}
      }, LONG_PRESS_MS);
      try {
        e.currentTarget.setPointerCapture?.(e.pointerId);
      } catch (err) {}
    },
    onPointerUp: (e) => {
      stopTimer();
      try {
        e.currentTarget.releasePointerCapture?.(e.pointerId);
      } catch (err) {}
      if (!wasLongPress.current) onHomeAll();
      wasLongPress.current = false;
    },
    onPointerCancel: () => {
      stopTimer();
      wasLongPress.current = false;
    },
    onPointerLeave: () => {
      stopTimer();
      wasLongPress.current = false;
    },
    onContextMenu: (e) => e.preventDefault(),
  };

  const ringSegments = (ring) =>
    PAD_QUADRANTS.map((q) =>
      h("path", {
        key: `ring${ring.step}-${q.axis}${q.sign}`,
        d: ringSegmentPath(ring.from, ring.to, q.a0, q.a1),
        className: ring.className,
        "data-jog": q.axis + (q.sign > 0 ? "+" : "-") + ring.step,
        onClick: () => onJog(q.axis, q.sign * ring.step),
      }),
    );

  return h(
    "div",
    { className: "jog-pad relative w-[280px] h-[280px] shrink-0" },
    h(
      "svg",
      { width: "280", height: "280", viewBox: "0 0 280 280", className: "absolute inset-0 w-full h-full select-none" },
      rings.map(ringSegments),
      PAD_DIAGONALS.map((degrees) => {
        const from = polar(rings[0].from, degrees);
        const to = polar(rings[rings.length - 1].to, degrees);
        return h("line", { key: degrees, x1: from.x, y1: from.y, x2: to.x, y2: to.y, className: "pad-gap", strokeWidth: "3" });
      }),
      padStepLabels(rings).map((label) =>
        h(
          "text",
          {
            key: label.text,
            x: String(label.x),
            y: String(label.y),
            textAnchor: "middle",
            dominantBaseline: "central",
            className: "bambu-num",
            style: { fontSize: label.size + "px" },
            transform: `rotate(-45 ${label.x} ${label.y})`,
          },
          label.text,
        ),
      ),
    ),
    padAxisLabels(rings).map((label) =>
      h(
        "div",
        {
          key: label.text,
          className: "absolute left-1/2 top-1/2 pointer-events-none select-none",
          style: { transform: `translate(-50%, -50%) translate(${label.dx}px, ${label.dy}px)` },
        },
        h("span", { className: "pad-axis" }, label.text),
      ),
    ),
    h(
      "button",
      {
        ...gestures,
        className:
          "jog-home absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full flex items-center justify-center select-none touch-manipulation",
        "aria-label": "Home all - long press PARK",
      },
      h(Svg, { size: 26, strokeWidth: "2", stroke: "currentColor" }, h("path", { d: HOUSE_PATH }), h("path", { d: "M9 21V14H15V21" })),
    ),
  );
}

/**
 * The Z buttons, the biggest step at the ends. The arrows show where the part that moves goes: on a printer whose bed moves
 * (most CoreXY) ↑ brings the bed up, towards the nozzle (Z−); where the toolhead moves (Voron 2.4, i3 style) ↑ lifts the
 * toolhead (Z+). 1.31
 */
function zButtons(steps, zMoves) {
  const upSign = zMoves === "toolhead" ? 1 : -1;
  const biggest = steps[steps.length - 1];
  const up = steps.slice().reverse().map((step) => ({ label: "↑ " + step, delta: upSign * step, big: step >= 10 && step === biggest }));
  const down = steps.map((step) => ({ label: "↓ " + step, delta: -upSign * step, big: step >= 10 && step === biggest }));
  return { up, down };
}

function ZControls({ onJog, steps = MOTION_BASE_STEPS, zMoves = "bed" }) {
  const { up, down } = zButtons(steps, zMoves);
  const compact = steps.length > 2;
  const button = (spec) =>
    h("button", { key: spec.label, onClick: () => onJog("Z", spec.delta), title: "Z" + signed(spec.delta), "data-z": signed(spec.delta), className: cx("z-btn", spec.big && "z-btn--big", compact && "z-btn--compact") }, spec.label);
  return h(
    "div",
    { className: "flex flex-col items-center gap-2 z-controls", "data-z-moves": zMoves },
    h("div", { className: "oui-label mb-1 z-controls__title" }, "Z", h("span", { className: "z-controls__part" }, zMoves === "toolhead" ? tx("toolhead") : tx("bed"))),
    up.map(button),
    h("div", { className: "z-divider" }),
    down.map(button),
  );
}

/* ---------------------------------------------------------------------------
   Live X / Y / Z read-out
   Each axis letter is blue (the home button's colour) once homed, grey otherwise; the value
   shows "-" until the axis is homed.
   ------------------------------------------------------------------------- */
const AXES = ["X", "Y", "Z"];

function PositionReadout({ position, homedAxes, onPickAxis }) {
  const shown = position || centrePosition(DEFAULT_AXIS_LIMITS);
  const value = (axis) => shown[axis.toLowerCase()];
  const isHomed = (axis) => (homedAxes || "").includes(axis.toLowerCase());
  const axisState = (axis) => (homedAxes === undefined ? "" : isHomed(axis) ? "is-homed" : "is-unhomed");

  return h(
    "div",
    { className: "position-readout" },
    h(
      "div",
      { className: "grid grid-cols-3 gap-2" },
      AXES.map((axis) =>
        h(
          "button",
          { key: axis, onClick: () => onPickAxis(axis), className: cx("axis-tile", axisState(axis)), title: tx("Tap to move ") + axis },
          h("span", { id: `pos${axis}Label`, className: "axis-tile__name" }, axis + ":"),
          h("span", { className: "axis-tile__value" }, position && !isHomed(axis) ? "-" : value(axis).toFixed(1)),
        ),
      ),
    ),
    h("div", { className: "oui-caption text-center mt-2" }, tx("Tap X/Y/Z to move to a position")),
  );
}

const HOME_BUTTONS = [
  { axes: "X", label: "Home X" },
  { axes: "Y", label: "Home Y" },
  { axes: "XY", label: "Home XY" },
  { axes: "Z", label: "Home Z" },
];

/** Motors off, and the calibration menu when the printer has something to offer there. */
function MovementActions({ motion, bedTools, lockReason }) {
  return h(
    "div",
    { className: "movement-actions" },
    h("button", { className: "oui-btn", disabled: Boolean(lockReason), title: lockReason || tx("Disable the motors (M84)"), onClick: motion.motorsOff }, h(Icons.Power), tx("Motors off")),
    bedTools.tools.length > 0 && h(BedToolsMenuButton, { bedTools }),
  );
}

function MovementCard({ position, homedAxes, motion, bedTools, lockReason }) {
  return h(
    Card,
    null,
    h(CardHeader, { title: tx("Motion") }),
    h(PositionReadout, { position, homedAxes, onPickAxis: motion.openPositionDialog }),
    h(
      "div",
      { className: "flex items-center gap-6 justify-center my-3" },
      h(JogPad, { onJog: motion.jog, onHomeAll: motion.homeAll, onPark: motion.park, steps: motion.xySteps }),
      h(ZControls, { onJog: motion.jog, steps: motion.zSteps, zMoves: motion.zMoves }),
    ),
    h(
      "div",
      { className: "grid grid-cols-4" },
      HOME_BUTTONS.map((spec) =>
        h("button", { key: spec.axes, onClick: () => motion.homeAxes(spec.axes), className: "home-btn" }, h(Icons.House, { size: 18 }), h("span", null, spec.label)),
      ),
    ),
    h(MovementActions, { motion, bedTools, lockReason }),
  );
}

/* ---------------------------------------------------------------------------
   "Go to position" dialog
   ------------------------------------------------------------------------- */
function PositionDialog({ dialog, onChange, onClose, onConfirm }) {
  const inputRef = useRef(null);
  useEffect(() => {
    if (!dialog.open) return;
    const timer = setTimeout(() => inputRef.current && inputRef.current.focus(), 100);
    return () => clearTimeout(timer);
  }, [dialog.open]);

  if (!dialog.open) return null;
  return h(
    "div",
    { className: "modal", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "modal-card", onClick: (e) => e.stopPropagation() },
      h("div", { className: "dialog-title mb-4" }, tx("Set "), dialog.axis, tx(" - Go to position")),
      h("input", {
        ref: inputRef,
        autoFocus: true,
        type: "number",
        step: "0.1",
        inputMode: "decimal",
        value: dialog.value,
        onChange: (e) => onChange(e.target.value),
        onKeyDown: (e) => e.key === "Enter" && onConfirm(),
        className: "oui-field oui-field--num modal-input",
      }),
      h("div", { className: "oui-caption mt-2" }, tx("Enter an absolute position in mm")),
      h(
        "div",
        { className: "oui-btn-row mt-5" },
        h("button", { onClick: onClose, className: "oui-btn" }, tx("Cancel")),
        h("button", { onClick: onConfirm, className: "oui-btn oui-btn--primary" }, tx("Go")),
      ),
    ),
  );
}
