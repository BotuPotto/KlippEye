/* ============================================================================
   59f · CAMERA CALIBRATION
   The page "Calibra la camera" of the settings menu (roadmap phase 4): the backend learns where every point of the
   printer appears in the camera picture (backend/camera_calibration.py, camera_model.py), so that the AI monitor can
   leave the toolhead out and know where the part is. The person:
     1. says how Z moves (the bed, or the toolhead);
     2. (Z moves the bed) puts six markers on the bed: six small pyramids printed from the STL made here (KlippEye then
        reads where they ended up in the G-code that printed them), or six quick blobs left by the printer itself;
     3. for each of about twelve points: the printer goes there, the person taps the nozzle tip (or the marker) in the
        picture, then taps again in the magnified view to be precise;
     4. "Calculate": the error in pixels and the points to redo; "Save" when it is good;
     5. checks it live: the toolhead outline and the bed are drawn over the picture while the toolhead moves;
     6. (phase 4b) adjusts the shape of the toolhead and of the gantry on the live picture, until the drawing covers them:
        the monitor leaves those parts out of its checks (backend/machine_masks.py). 1.29: by dragging the handles on the
        picture (each side of the toolhead box, its top, the edges of the gantry), or with the − / + buttons.
   1.29, "automatic": after the nozzle is tapped by hand once, KlippEye finds it by itself at the other nozzle points
   (backend/nozzle_finder.py: the toolhead moves aside for a moment, the tapped picture is looked for where it was); the
   person accepts the proposals, «Calculate» shows any that does not fit, to redo by hand.
   1.29.1: homing with the markers on the bed (backend/homing_safety.py): the STL keeps them clear of where homing Z touches,
   «Home» asks first when it could hit one, and the motors stay on during the calibration.
   The calibration is valid until the camera moves: the backend compares the picture with the one taken at calibration
   every ten minutes and, when the camera has moved, says so here and stops using the calibration.
   ========================================================================== */

const CAMCAL_POLL_MS = 3000;
const CAMCAL_LIVE_MS = 1500;
const LOUPE_ZOOM = 4;
const SHAPE_STEP_MM = 5;
const SHAPE_FIELDS = {
  toolhead: [
    { key: "left", label: tx("Left of the nozzle (X−)") },
    { key: "right", label: tx("Right of the nozzle (X+)") },
    { key: "front", label: tx("In front of the nozzle (Y−)") },
    { key: "back", label: tx("Behind the nozzle (Y+)") },
    { key: "top", label: tx("Above the nozzle tip") },
    { key: "below", label: tx("Below the nozzle tip") },
  ],
  gantry: [
    { key: "behind", label: tx("Starts behind the nozzle (Y+)"), min: -150 },
    { key: "depth", label: tx("Depth (Y)") },
    { key: "low", label: tx("Lower edge above the nozzle tip"), min: -50 },
    { key: "high", label: tx("Upper edge above the nozzle tip"), min: -50 },
  ],
};
const SHAPE_MAX = { left: 300, right: 300, front: 300, back: 300, top: 400, below: 50, behind: 300, depth: 300, low: 400, high: 400 };
const SHAPE_SEND_EVERY_MS = 400; // while a handle is dragged, the new size goes to the backend this often (the outline follows)
const QUALITY_TEXT = { good: tx("good"), fair: tx("acceptable"), poor: tx("not good enough") };

/** POST to the calibration API; resolves { ok, data, message } like backendPost, with a longer wait (moves take time). */
async function camcalPost(path, body) {
  try {
    const response = await fetch("/api/camera/" + path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body || {}) });
    let data = null;
    try {
      data = await response.json();
    } catch (error) {}
    return { ok: response.ok && !(data && data.ok === false), data, message: (data && data.error) || (response.ok ? "" : "HTTP " + response.status) };
  } catch (error) {
    return { ok: false, data: null, message: tx("the KlippEye service does not answer") };
  }
}

/** Where the tap is in the picture as the camera sends it (the page may show it flipped, like the camera card). */
function tapFraction(event, element, camera) {
  const box = element.getBoundingClientRect();
  let u = (event.clientX - box.left) / box.width;
  let v = (event.clientY - box.top) / box.height;
  if (camera.flipH) u = 1 - u;
  if (camera.flipV) v = 1 - v;
  return { u: Math.min(1, Math.max(0, u)), v: Math.min(1, Math.max(0, v)) };
}

const pointsAttr = (list) => list.map(([u, v]) => u + "," + v).join(" ");

/** The camera picture (raw, flipped like the camera card) with what is drawn over it in the camera's own fractions. */
function CameraFrame({ src, camera, onTap, children, label, onAspect, layer, frameRef }) {
  return h(
    "div",
    { ref: frameRef, className: cx("cal-frame", onTap && "cal-frame--tap"), style: flipStyle(camera) },
    h("img", {
      className: "cal-frame__img",
      src,
      alt: label || tx("Camera picture"),
      draggable: false,
      onLoad: onAspect ? (event) => event.currentTarget.naturalHeight && onAspect(event.currentTarget.naturalWidth / event.currentTarget.naturalHeight) : undefined,
      onClick: onTap ? (event) => onTap(tapFraction(event, event.currentTarget, camera)) : undefined,
    }),
    h("svg", { className: "cal-frame__draw", viewBox: "0 0 1 1", preserveAspectRatio: "none", "aria-hidden": "true" }, children),
    layer,
  );
}

const Cross = ({ u, v, tone = "tap" }) =>
  h("g", { className: "cal-cross cal-cross--" + tone }, h("line", { x1: u - 0.03, y1: v, x2: u + 0.03, y2: v }), h("line", { x1: u, y1: v - 0.045, x2: u, y2: v + 0.045 }));

/** The magnified view around the first tap: a second tap there sets the point precisely. */
function Loupe({ src, camera, tap, onTap, aspect }) {
  const size = 1 / LOUPE_ZOOM;
  const left = Math.min(1 - size, Math.max(0, tap.u - size / 2));
  const top = Math.min(1 - size, Math.max(0, tap.v - size / 2));
  const style = { ...(flipStyle(camera) || {}), aspectRatio: String(aspect || 16 / 9), backgroundImage: "url('" + src + "')", backgroundSize: LOUPE_ZOOM * 100 + "% " + LOUPE_ZOOM * 100 + "%", backgroundPosition: (left / (1 - size)) * 100 + "% " + (top / (1 - size)) * 100 + "%" };
  return h(
    "div",
    {
      className: "cal-loupe",
      style,
      role: "button",
      "aria-label": tx("Magnified picture: tap the exact point"),
      onClick: (event) => {
        const local = tapFraction(event, event.currentTarget, camera);
        onTap({ u: left + local.u * size, v: top + local.v * size });
      },
    },
    h("svg", { className: "cal-frame__draw", viewBox: "0 0 1 1", preserveAspectRatio: "none", "aria-hidden": "true" }, h(Cross, { u: (tap.u - left) / size, v: (tap.v - top) / size })),
  );
}

/** Live picture with the toolhead outline, the nozzle and the bed drawn from the calibration (saved, or the one just calculated). */
function LiveCheck({ camera, draft, editShape }) {
  const [stamp, setStamp] = useState(() => Date.now());
  const [overlay, setOverlay] = useState(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const readRef = useRef(noop);
  useEffect(() => {
    let cancelled = false;
    const read = async () => {
      try {
        const response = await fetchFresh("/api/camera/overlay" + (draft ? "?draft=1" : ""), { timeout: BACKEND_READ_TIMEOUT_MS });
        const data = await response.json();
        if (cancelled) return;
        if (response.ok && data.ok) {
          setOverlay(data);
          setProblem("");
        } else setProblem(data.error || "HTTP " + response.status);
      } catch (error) {}
      if (!cancelled) setStamp(Date.now());
    };
    readRef.current = read;
    const stop = startPolling(read, CAMCAL_LIVE_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [draft]);
  const jog = async (dx, dy, dz) => {
    setBusy(true);
    const reply = await camcalPost("calibration/jog", { dx, dy, dz });
    setBusy(false);
    setProblem(reply.ok ? "" : reply.message);
  };
  const step = (label, dx, dy, dz) => h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: busy, onClick: () => jog(dx, dy, dz) }, label);
  const frameRef = useRef(null);
  const [dragging, setDragging] = useState(null); // { key, value } while a handle is held
  return h(
    React.Fragment,
    null,
    h(
      CameraFrame,
      {
        src: "/api/print/snapshot?t=" + stamp,
        camera,
        frameRef,
        label: tx("Live picture with the calibration drawn over it"),
        layer: editShape && overlay && overlay.shape && Array.isArray(overlay.handles) ? h(ShapeHandles, { overlay, camera, frameRef, onDrag: setDragging, onSaved: () => readRef.current() }) : null,
      },
      overlay && overlay.bed.length > 2 && h("polygon", { className: "cal-bed", points: pointsAttr(overlay.bed) }),
      overlay && overlay.zone && overlay.zone.expected.map((piece, index) => h("polygon", { key: "z" + index, className: "cal-zone", points: pointsAttr(piece) })),
      overlay && (overlay.gantry || []).map((piece, index) => h("polygon", { key: "g" + index, className: "cal-gantry", points: pointsAttr(piece) })),
      overlay && overlay.toolhead.length > 2 && h("polygon", { className: "cal-toolhead", points: pointsAttr(overlay.toolhead) }),
      overlay && overlay.nozzle && h(Cross, { u: overlay.nozzle[0], v: overlay.nozzle[1], tone: "nozzle" }),
    ),
    editShape && h("div", { className: cx("cal-handle-line", dragging && "is-active"), "data-handle-line": dragging ? dragging.key : "" }, dragging ? handleLabel(dragging.key) + ": " + formatNumber(dragging.value) + " mm" : tx("Drag the dots on the picture to make the outlines bigger or smaller.")),
    h("p", { className: "set-group__note" }, tx("Purple: the toolhead; orange: the gantry; dashed: the bed. Move the toolhead: the drawing must follow it.") + (overlay ? " X " + overlay.position[0] + " • Y " + overlay.position[1] + " • Z " + overlay.position[2] : "")),
    overlay &&
      overlay.zone &&
      h("p", { className: "set-group__note", "data-zone": overlay.zone.source }, tx("Green: where the parts of this print are expected ({count} from {source}). The monitor watches the whole bed around them.", { count: overlay.zone.objects, source: overlay.zone.source === "exclude_object" ? tx("Klipper's exclude_object") : tx("the G-code") })),
    h("div", { className: "cal-jog" }, step("X −20", -20, 0, 0), step("X +20", 20, 0, 0), step("Y −20", 0, -20, 0), step("Y +20", 0, 20, 0), step("Z −10", 0, 0, -10), step("Z +10", 0, 0, 10)),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
    editShape && overlay && overlay.shape && h(ShapeEditor, { shape: overlay.shape, onSaved: () => readRef.current() }),
  );
}

/** "Toolhead • Above the nozzle tip": the name of the size a handle moves. */
function handleLabel(key) {
  const [part, field] = key.split(".");
  const found = (SHAPE_FIELDS[part] || []).find((f) => f.key === field);
  return (part === "toolhead" ? tx("Toolhead") : tx("Gantry")) + " • " + (found ? found.label : field);
}

/**
 * 1.29: the dots on the live picture, one per size (each side of the toolhead box and its top, the upper and lower edge of the
 * gantry; "below the tip" keeps only its − and +). A dot moves only along its own direction (as the backend projects it: `per_mm` is how far it goes in
 * the picture for 1 mm); the size follows the finger and is sent to the backend while dragging, so the outline follows too.
 */
function ShapeHandles({ overlay, camera, frameRef, onDrag, onSaved }) {
  const [held, setHeld] = useState(null); // { key, start, value, at, per, startX, startY }
  const lastSent = useRef(0);
  const send = async (key, value) => {
    const [part, field] = key.split(".");
    lastSent.current = Date.now();
    const reply = await camcalPost("shape", { [part]: { [field]: value } });
    if (reply.ok) onSaved();
  };
  const valueOf = (key) => {
    const [part, field] = key.split(".");
    return overlay.shape[part] ? overlay.shape[part][field] : undefined;
  };
  const down = (event, handle) => {
    const value = valueOf(handle.key);
    if (typeof value !== "number") return;
    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.setPointerCapture) event.currentTarget.setPointerCapture(event.pointerId);
    const next = { key: handle.key, start: value, value, at: handle.at, per: handle.per_mm, startX: event.clientX, startY: event.clientY };
    setHeld(next);
    onDrag({ key: handle.key, value });
  };
  const move = (event) => {
    if (!held || !frameRef.current) return;
    const box = frameRef.current.getBoundingClientRect();
    // the movement in the camera's own fractions (the frame may be shown flipped), measured in screen pixels
    const du = ((event.clientX - held.startX) / box.width) * (camera.flipH ? -1 : 1);
    const dv = ((event.clientY - held.startY) / box.height) * (camera.flipV ? -1 : 1);
    const pu = held.per[0] * box.width;
    const pv = held.per[1] * box.height;
    const length = pu * pu + pv * pv;
    if (length < 1e-9) return;
    const mm = (du * box.width * pu + dv * box.height * pv) / length;
    const [, field] = held.key.split(".");
    const low = (SHAPE_FIELDS.gantry.concat(SHAPE_FIELDS.toolhead).find((f) => f.key === field) || {}).min || 0;
    const value = Math.min(SHAPE_MAX[field] || 300, Math.max(low, Math.round(held.start + mm)));
    if (value !== held.value) {
      setHeld({ ...held, value });
      onDrag({ key: held.key, value });
      if (Date.now() - lastSent.current > SHAPE_SEND_EVERY_MS) send(held.key, value);
    }
  };
  const up = () => {
    if (!held) return;
    if (held.value !== held.start || Date.now() - lastSent.current > 0) send(held.key, held.value);
    setHeld(null);
    onDrag(null);
  };
  return h(
    "div",
    { className: "cal-handles", onPointerMove: move, onPointerUp: up, onPointerCancel: up },
    visibleHandles(overlay.handles, held, frameRef.current).map(({ handle, u, v }) => {
      const moving = held && held.key === handle.key;
      return h("button", {
        key: handle.key,
        type: "button",
        className: cx("cal-handle", handle.key.startsWith("gantry") ? "cal-handle--gantry" : "cal-handle--toolhead", moving && "is-held"),
        style: { left: u * 100 + "%", top: v * 100 + "%" },
        "aria-label": handleLabel(handle.key),
        title: handleLabel(handle.key),
        "data-handle": handle.key,
        onPointerDown: (event) => down(event, handle),
        onPointerMove: move,
        onPointerUp: up,
      });
    }),
  );
}

const HANDLE_ORDER = ["toolhead.top", "toolhead.left", "toolhead.right", "toolhead.front", "toolhead.back", "gantry.high", "gantry.low"];
const HANDLE_MIN_GAP_PX = 26; // a dot closer than this to one already shown is left out (its size keeps its − and +)

/** The dots to show, where they are now: in the picture, not on top of each other (the one being dragged always). */
function visibleHandles(handles, held, frame) {
  const width = frame ? frame.getBoundingClientRect().width : 360;
  const height = frame ? frame.getBoundingClientRect().height : 200;
  const kept = [];
  const order = (key) => (held && held.key === key ? -1 : HANDLE_ORDER.indexOf(key));
  [...handles]
    .sort((a, b) => order(a.key) - order(b.key))
    .forEach((handle) => {
      const shift = held && held.key === handle.key ? held.value - held.start : 0;
      const u = handle.at[0] + handle.per_mm[0] * shift;
      const v = handle.at[1] + handle.per_mm[1] * shift;
      if (u < -0.02 || u > 1.02 || v < -0.02 || v > 1.02) return;
      if (kept.some((k) => Math.hypot((k.u - u) * width, (k.v - v) * height) < HANDLE_MIN_GAP_PX)) return;
      kept.push({ handle, u, v });
    });
  return kept;
}

/**
 * The size of the toolhead and of the gantry around the nozzle, adjusted while looking at the drawing: what is inside the
 * purple and orange outlines is left out of the monitor's checks, so they must cover the parts (a little more is fine,
 * much more hides a problem near the nozzle).
 */
function ShapeEditor({ shape, onSaved }) {
  const [local, setLocal] = useState(shape);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!busy) setLocal(shape);
  }, [JSON.stringify(shape)]);
  const send = async (part, values) => {
    const next = { ...local, [part]: { ...local[part], ...values } };
    setLocal(next);
    setBusy(true);
    const reply = await camcalPost("shape", { [part]: values });
    setBusy(false);
    if (reply.ok) {
      setProblem("");
      setLocal(reply.data.shape);
      onSaved();
    } else setProblem(reply.message);
  };
  const row = (part, field) => {
    const value = local[part][field.key];
    return h(
      "div",
      { key: part + field.key, className: "cal-size" },
      h("span", { className: "cal-size__label" }, field.label),
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "aria-label": field.label + " −", "data-size": part + "." + field.key + ".minus", disabled: value <= (field.min || 0), onClick: () => send(part, { [field.key]: Math.max(field.min || 0, value - SHAPE_STEP_MM) }) }, "−"),
      h("span", { className: "cal-size__value", "data-value": part + "." + field.key }, formatNumber(value), " mm"),
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "aria-label": field.label + " +", "data-size": part + "." + field.key + ".plus", onClick: () => send(part, { [field.key]: value + SHAPE_STEP_MM }) }, "+"),
    );
  };
  return h(
    "div",
    { className: "cal-shape" },
    h("h3", { className: "cal-shape__title" }, tx("Toolhead")),
    h("p", { className: "set-group__note" }, tx("A box around the nozzle tip, with fan ducts and cables: make the purple outline cover the toolhead, with a little room (drag its dots on the picture, or use − and +; «Above the nozzle tip» is its height). Move the toolhead to a few places to check it.")),
    SHAPE_FIELDS.toolhead.map((field) => row("toolhead", field)),
    h("h3", { className: "cal-shape__title" }, tx("Gantry")),
    h(SwitchRow, { title: tx("Leave out the gantry too"), detail: tx("The bar that carries the toolhead across the whole printer (VzBot, Voron, most CoreXY)."), checked: local.gantry.on, onChange: (on) => send("gantry", { on }) }),
    local.gantry.on && h("p", { className: "set-group__note" }, tx("The orange bar goes from side to side and moves with the toolhead: make it cover the bar, with a little room.")),
    local.gantry.on && SHAPE_FIELDS.gantry.map((field) => row("gantry", field)),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

/** A small drawing of what to tap: the nozzle tip, or the tip of a marker. */
function TapHint({ kind }) {
  const cross = (x, y) => h("g", { className: "cal-hint__cross" }, h("circle", { cx: x, cy: y, r: 7 }), h("line", { x1: x - 12, y1: y, x2: x + 12, y2: y }), h("line", { x1: x, y1: y - 12, x2: x, y2: y + 12 }));
  return h(
    "svg",
    { className: "cal-hint", viewBox: "0 0 160 90", role: "img", "aria-label": kind === "mark" ? tx("Tap the top tip of the marker") : tx("Tap the lowest point of the nozzle") },
    kind === "mark"
      ? h(React.Fragment, null, h("line", { className: "cal-hint__bed", x1: 10, y1: 78, x2: 150, y2: 78 }), h("polygon", { className: "cal-hint__marker", points: "50,78 80,30 110,78" }), cross(80, 30))
      : h(
          React.Fragment,
          null,
          h("rect", { className: "cal-hint__block", x: 55, y: 4, width: 50, height: 26, rx: 3 }),
          h("polygon", { className: "cal-hint__nozzle", points: "68,30 92,30 86,46 74,46" }),
          h("polygon", { className: "cal-hint__nozzle", points: "74,46 86,46 80,56" }),
          h("polygon", { className: "cal-hint__marker cal-hint__marker--faint", points: "60,86 80,62 100,86" }),
          cross(80, 56),
        ),
  );
}

/* ---------------------------------------------------------------------------
   The steps
   ------------------------------------------------------------------------- */
function KindStep({ state, onChange, busy }) {
  const draft = state.draft || {};
  const chosen = draft.z_moves || "";
  const options = [
    { id: "bed", label: tx("Z moves the bed"), detail: tx("VzBot, Voron Trident, RatRig V-Core, most CoreXY") },
    { id: "toolhead", label: tx("Z moves the toolhead"), detail: tx("Voron 2.4 and other printers whose gantry goes up and down") },
  ];
  return h(
    SettingsGroup,
    { title: tx("How does the Z axis move?"), note: (state.guess && !chosen ? tx("From Klipper's configuration it looks like: {kind}.", { kind: options.find((o) => o.id === state.guess).label }) + " " : "") + tx("Printers whose bed moves in Y (Prusa, Ender) are not supported yet.") },
    h(ChoiceRows, { options, value: chosen || state.guess, label: tx("How does the Z axis move?"), onChange: (id) => onChange({ z_moves: id }) }),
    !chosen && h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: busy || !state.guess, onClick: () => onChange({ z_moves: state.guess }) }, tx("Go on")),
  );
}

/** Z moves the bed: the six markers, printed (the STL, then the G-code that printed them) or quick blobs. */
function MarkersStep({ state, run, busy }) {
  const draft = state.draft || {};
  const markers = draft.markers;
  const marks = state.marks || {};
  const [way, setWay] = useState(() => (markers && markers.source === "blobs" ? "blobs" : "file"));
  const [files, setFiles] = useState(null);
  const [file, setFile] = useState("");
  const [temps, setTemps] = useState({ nozzle: "210", bed: "60" });
  const [problem, setProblem] = useState("");
  const ask = async (path, body) => {
    setProblem("");
    const reply = await run(path, body, true);
    if (!reply.ok) setProblem(reply.message);
  };
  useEffect(() => {
    if (way !== "file") return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetchFresh("/api/camera/gcode-files", { timeout: BACKEND_READ_TIMEOUT_MS * 2 });
        const data = await response.json();
        if (cancelled || !data.ok) return;
        setFiles(data.files);
        const guess = data.files.find((f) => /marker|klippeye/i.test(f.path)) || data.files[0];
        setFile((previous) => previous || (guess ? guess.path : ""));
      } catch (error) {
        if (!cancelled) setFiles([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [way, markers && markers.time]);
  const ways = [
    { id: "file", label: tx("Print the markers (recommended)") },
    { id: "blobs", label: tx("Quick blobs") },
  ];
  return h(
    SettingsGroup,
    { title: tx("Markers on the bed"), note: tx("Z moves the bed, so for the camera the nozzle is always at the same height: six markers on the bed, tapped again with the bed lowered, give the second height.") },
    h(ChipChoice, { options: ways, value: way, label: tx("Markers on the bed"), onChange: (id) => (setWay(id), setProblem("")) }),
    way === "file"
      ? h(
          "div",
          { className: "cal-marks" },
          h("a", { className: "oui-btn oui-btn--block", href: "/api/camera/markers.stl", download: "klippeye-camera-markers.stl", "data-stl": "1" }, h(Icons.Download, { size: 18 }), tx("Download the markers (STL)")),
          h(HomingNote, { homing: state.homing }),
          h("p", { className: "set-group__note" }, tx("Six small pyramids sized for your bed. Slice the file with your usual settings (no supports, a colour that stands out on the bed), print it and leave it on the bed. Then choose here the file you printed: KlippEye reads where the pyramids ended up.")),
          files === null
            ? h("p", { className: "set-group__note" }, tx("Reading the files on the printer…"))
            : files.length === 0
              ? h("p", { className: "set-group__note" }, tx("No G-code files on the printer yet."))
              : h(
                  "label",
                  { className: "set-field" },
                  h("span", { className: "set-field__label" }, tx("The file you printed")),
                  h("select", { className: "oui-field set-field__input", value: file, "data-file": "1", onChange: (event) => setFile(event.target.value) }, files.map((f) => h("option", { key: f.path, value: f.path }, f.path + (f.modified ? " • " + formatFileDate(f.modified) : "")))),
                ),
          h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-read": "1", disabled: busy || !file, onClick: () => ask("calibration/markers", { file }) }, tx("Read the markers from this file")),
        )
      : h(
          "div",
          { className: "cal-marks" },
          h("p", { className: "set-group__note" }, tx("The printer itself leaves six small discs of filament (retraction and a Z hop between them). Faster, less precise than printed markers. Filament loaded.")),
          h(
            "div",
            { className: "set-grid" },
            [
              ["nozzle", tx("Nozzle °C")],
              ["bed", tx("Bed °C")],
            ].map(([key, label]) =>
              h("label", { key, className: "set-field" }, h("span", { className: "set-field__label" }, label), h("input", { className: "oui-field oui-field--num set-field__input", inputMode: "numeric", value: temps[key], "data-temp": key, onChange: (event) => /^\d{0,3}$/.test(event.target.value) && setTemps({ ...temps, [key]: event.target.value }) })),
            ),
          ),
          h(
            "button",
            { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-marks": "start", disabled: busy || marks.state === "running", onClick: () => ask("calibration/marks", { nozzle: Number(temps.nozzle), bed: Number(temps.bed) }) },
            marks.state === "running" ? tx("Making the blobs…") : tx("Make the 6 blobs"),
          ),
          marks.state === "error" && h("p", { className: "set-field__error", role: "alert" }, tx("The blobs were not made: ") + (marks.message || "")),
        ),
    problem && h("p", { className: "set-field__error", role: "alert", "data-markers-error": "1" }, problem),
    markers &&
      h(
        "div",
        { className: "set-status set-status--ok", "data-markers": markers.source },
        h("span", { className: "set-status__dot" }),
        markers.source === "file" ? tx("6 markers found in {file}. Leave them on the bed until the calibration is saved.", { file: markers.file }) : tx("6 blobs made. Leave them on the bed until the calibration is saved."),
      ),
  );
}

/** 1.29.1: what could go wrong when homing with the markers on the bed, in words (backend/homing_safety.py). */
function homingRiskText(risk) {
  const where = risk.at ? tx("X {x}, Y {y}", { x: formatNumber(risk.at[0]), y: formatNumber(risk.at[1]) }) : "";
  const before = risk.expected ? tx("If the printed markers are on the bed: ") : "";
  if (risk.kind === "hit")
    return (
      before +
      (risk.what === "probe"
        ? tx("homing Z brings the bed up under the probe (homing at {where}) and the marker at X {x}, Y {y} is right there.", { where, x: formatNumber(risk.x), y: formatNumber(risk.y) })
        : tx("homing Z brings the bed up under the toolhead at {where} and the marker at X {x}, Y {y} is right there.", { where, x: formatNumber(risk.x), y: formatNumber(risk.y) })) +
      " " +
      tx("Take that marker off before homing (the markers printed from the STL of this version stay clear of the homing point).")
    );
  if (risk.kind === "override") return before + tx("your printer homes with its own macro ([homing_override]): KlippEye cannot know where Z is homed. Check that no marker is under the toolhead or the probe there.");
  if (risk.kind === "unknown") return before + tx("KlippEye could not work out where Z is homed: check that no marker is under the toolhead there.");
  if (risk.kind === "no_hop") return tx("Z is not homed and Klipper does not lift the nozzle before homing (no z_hop in [safe_z_home]): make sure the nozzle is well above the markers (more than 10 mm) before homing.");
  return "";
}

/** «Home the printer», which first asks the backend whether homing could hit the markers on the bed. */
function SafeHomeButton({ run, busy }) {
  const [risks, setRisks] = useState(null);
  const [problem, setProblem] = useState("");
  const home = async (force) => {
    setProblem("");
    const reply = await run("calibration/home", force ? { force: true } : {}, true);
    if (reply.ok) return setRisks(null);
    if (reply.data && Array.isArray(reply.data.risks)) return setRisks(reply.data.risks);
    setProblem(reply.message);
  };
  return h(
    React.Fragment,
    null,
    risks
      ? h(
          "div",
          { className: "set-confirm cal-risks", role: "alertdialog", "aria-label": tx("Homing could hit the markers"), "data-risks": risks.map((r) => r.kind).join(",") },
          h("strong", null, tx("Before homing")),
          h("ul", null, risks.map((risk, index) => h("li", { key: index }, homingRiskText(risk)))),
          h(
            "div",
            { className: "set-confirm__buttons" },
            h("button", { type: "button", className: "oui-btn", onClick: () => setRisks(null) }, tx("Cancel")),
            h("button", { type: "button", className: "oui-btn oui-btn--danger", "data-home-anyway": "1", disabled: busy, onClick: () => home(true) }, tx("Checked: home")),
          ),
        )
      : h("button", { type: "button", className: "oui-btn oui-btn--block", "data-home": "1", disabled: busy, onClick: () => home(false) }, h(Icons.House, { size: 16 }), tx("Home the printer (G28)")),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

/** 1.29.1: where homing Z touches the bed, and that the markers of the STL stay clear of it. */
function HomingNote({ homing }) {
  if (!homing) return null;
  const at = homing.xy ? tx("X {x}, Y {y}", { x: formatNumber(homing.xy[0]), y: formatNumber(homing.xy[1]) }) : "";
  let text;
  if (homing.how === "top") text = tx("Your printer homes Z with the bed going down: homing never comes near the markers.");
  else if (homing.how === "override") text = tx("Your printer homes with its own macro ([homing_override]): before homing, check that no marker is where Z is homed.");
  else if (!homing.xy) text = tx("Where Z is homed is not known: before homing, check that no marker is under the toolhead there.");
  else text = (homing.layout_moved ? tx("Homing Z touches the bed at {at}: the pyramids of the STL are placed further out, so that the toolhead and the probe do not hit them.", { at }) : tx("Homing Z touches the bed at {at}: the pyramids of the STL are out of the way of the toolhead and the probe.", { at })) + (homing.probe ? " " + tx("Probe: {name}, {dx} / {dy} mm from the nozzle.", { name: homing.probe.name, dx: formatNumber(homing.probe.x_offset), dy: formatNumber(homing.probe.y_offset) }) : "");
  return h("p", { className: "set-group__note", "data-homing": homing.how + (homing.layout_moved ? "-moved" : "") }, text);
}

function PointsStep({ state, camera, run, busy }) {
  const draft = state.draft || {};
  const points = draft.points || {};
  const targets = state.targets || [];
  const [current, setCurrent] = useState(null);
  const [tap, setTap] = useState(null);
  const [stamp, setStamp] = useState(() => Date.now());
  const [aspect, setAspect] = useState(16 / 9);
  const fit = draft.fit;
  const todo = targets.find((t) => !points[t.id]);
  const target = targets.find((t) => t.id === current) || todo || targets[0];
  const at = draft.at === (target && target.id);
  const done = targets.filter((t) => points[t.id]).length;
  const needsMarks = draft.z_moves === "bed";
  const src = "/api/print/snapshot?t=" + stamp;
  useEffect(() => setTap(null), [target && target.id]);
  const go = async () => {
    setTap(null);
    await run("calibration/goto", { target: target.id });
    setStamp(Date.now());
  };
  const keep = async () => {
    const ok = await run("calibration/point", { target: target.id, u: tap.u, v: tap.v });
    if (ok) {
      setTap(null);
      setCurrent(null);
    }
  };
  const errors = (fit && fit.point_errors) || {};
  const redo = new Set((fit && fit.redo) || []);
  // 1.29: the nozzle found by itself (after one tap by hand)
  const proposals = draft.proposals || {};
  const auto = state.auto || { state: "idle" };
  const finding = auto.state === "running";
  const proposal = target ? proposals[target.id] : null;
  const [findNote, setFindNote] = useState("");
  const nozzleLeft = targets.filter((t) => t.kind === "nozzle" && !points[t.id]);
  const foundLeft = targets.filter((t) => !points[t.id] && proposals[t.id] && proposals[t.id].found);
  useEffect(() => setFindNote(""), [target && target.id]);
  const findHere = async () => {
    setTap(null);
    setFindNote("");
    const reply = await run("calibration/find", { target: target.id }, true);
    setStamp(Date.now());
    if (!reply.ok) return setFindNote(reply.message);
    const p = reply.data.proposal;
    if (p.found) {
      setTap({ u: p.u, v: p.v });
      setFindNote(tx("Found (match {score}%): check it in the magnified view, then keep it.", { score: Math.round(p.score * 100) }));
    } else setFindNote(p.moved ? tx("Not found with enough certainty: tap it by hand.") : tx("The toolhead did not show moving in the picture: tap it by hand."));
  };
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Before starting"), note: tx("Clean bed (only the markers on it); the light as during prints; the printer idle. The printer moves by itself: keep your hands out.") },
      !state.printer || !/x/.test(state.printer.homed) || !/z/.test(state.printer.homed)
        ? h(SafeHomeButton, { run, busy })
        : h("p", { className: "set-group__note" }, tx("Printer homed.")),
      h("p", { className: "set-group__note" }, tx("During the calibration the motors stay on (Klipper's idle timeout is made longer, and put back at the end), so the printer does not lose its homing.")),
    ),
    needsMarks && h(MarkersStep, { state, run, busy }),
    target &&
      h(
        SettingsGroup,
        { title: tx("Points: {done} of {total}", { done, total: targets.length }), note: tx("For each point: 1. «Go to point»: the printer moves and a new picture appears. 2. Tap the picture where the point is. 3. In the magnified view, tap exactly on it. 4. «Keep this point». Green numbers are done; tap a number to see or redo it.") },
        h(
          "div",
          { className: "cal-targets", role: "group", "aria-label": tx("Points") },
          targets.map((t, index) =>
            h(
              "button",
              {
                key: t.id,
                type: "button",
                "data-target": t.id,
                className: cx("cal-target", points[t.id] && "is-done", !points[t.id] && proposals[t.id] && proposals[t.id].found && "is-proposed", redo.has(t.id) && "is-redo", t.id === target.id && "is-current"),
                onClick: () => setCurrent(t.id),
                title: errors[t.id] !== undefined ? errors[t.id] + " px" : "",
              },
              index + 1,
            ),
          ),
        ),
        h(
          "div",
          { className: "cal-instruction-row" },
          h(TapHint, { kind: target.kind }),
          h(
            "p",
            { className: "set-group__note cal-instruction", "data-kind": target.kind },
            target.kind === "mark"
              ? tx("Point {n}: the bed goes down and the nozzle moves to the back. Tap the TOP TIP of the marker at X {x}, Y {y} (for a blob: its centre).", { n: targets.indexOf(target) + 1, x: target.x, y: target.y })
              : tx("Point {n}: the nozzle goes to X {x}, Y {y}, Z {z}. Tap the LOWEST POINT OF THE NOZZLE (the metal tip), not the marker under it.", { n: targets.indexOf(target) + 1, x: target.x, y: target.y, z: target.z }),
          ),
        ),
        h(AutoFind, { state, run, busy, finding, auto, nozzleLeft, foundLeft }),
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-go": target.id, disabled: busy || finding, onClick: go }, at ? tx("Go there again") : tx("Go to point {n}", { n: targets.indexOf(target) + 1 })),
        target.kind === "nozzle" && state.template && !points[target.id] && h("button", { type: "button", className: "oui-btn oui-btn--block", "data-find": target.id, disabled: busy || finding, onClick: findHere }, tx("Go there and find the nozzle by itself")),
        findNote && h("p", { className: "set-group__note", "data-find-note": "1" }, findNote),
        at &&
          h(
            "div",
            { className: "cal-pick" },
            h(
              CameraFrame,
              { src, camera, onTap: setTap, onAspect: setAspect },
              proposal && proposal.found && !tap && !points[target.id] && h(Cross, { u: proposal.u, v: proposal.v, tone: "proposal" }),
              tap && h(Cross, tap),
              points[target.id] && h(Cross, { u: points[target.id].u, v: points[target.id].v, tone: "saved" }),
            ),
            proposal && proposal.found && !tap && !points[target.id] && h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-use-proposal": target.id, onClick: () => setTap({ u: proposal.u, v: proposal.v }) }, tx("Check the point found")),
            h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", onClick: () => setStamp(Date.now()) }, h(Icons.Refresh, { size: 16 }), tx("Refresh the picture")),
            tap
              ? h(
                  React.Fragment,
                  null,
                  h("p", { className: "set-group__note" }, tx("Magnified: tap again exactly on the point, then keep it.")),
                  h(Loupe, { src, camera, tap, onTap: setTap, aspect }),
                  h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-keep": target.id, disabled: busy, onClick: keep }, h(Icons.Check, { size: 18 }), tx("Keep this point")),
                )
              : h("p", { className: "set-group__note" }, tx("Tap the picture where the point is.")),
          ),
        points[target.id] && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", onClick: () => run("calibration/forget", { target: target.id }) }, tx("Take this point again")),
      ),
    h(
      SettingsGroup,
      { title: tx("Calculate") },
      h("button", { type: "button", className: "oui-btn oui-btn--block", "data-fit": "1", disabled: busy || done < 8, onClick: () => run("calibration/fit") }, done < 8 ? tx("At least 8 points are needed") : tx("Calculate the calibration")),
      fit &&
        h(
          React.Fragment,
          null,
          h(
            "div",
            { className: cx("set-status", fit.quality === "good" ? "set-status--ok" : "set-status--warn") },
            h("span", { className: "set-status__dot" }),
            tx("Average error {px} px: {quality}.", { px: formatNumber(Math.round(fit.rms_px * 10) / 10), quality: QUALITY_TEXT[fit.quality] }) + (redo.size ? " " + tx("Take again the points in red ({count}).", { count: redo.size }) : ""),
          ),
          h(LiveCheck, { camera, draft: true }),
          h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-save": "1", disabled: busy || fit.quality === "poor", onClick: () => run("calibration/save") }, h(Icons.Save, { size: 18 }), tx("Save the calibration")),
        ),
    ),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", disabled: busy, onClick: () => run("calibration/reset") }, tx("Start again")),
  );
}

/** 1.29: «Find all the nozzle points by itself», its progress, and «Use the points found». */
function AutoFind({ state, run, busy, finding, auto, nozzleLeft, foundLeft }) {
  if (!state.template) {
    return nozzleLeft.length > 1 ? h("p", { className: "set-group__note", "data-auto": "no-template" }, tx("Tap the nozzle by hand at one point: then KlippEye can find it by itself at the other nozzle points.")) : null;
  }
  return h(
    "div",
    { className: "cal-auto", "data-auto": auto.state },
    finding
      ? h(
          React.Fragment,
          null,
          h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Finding the nozzle: point {done} of {total} ({found} found so far)…", { done: auto.done + 1, total: auto.total, found: auto.found })),
          h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-auto-stop": "1", onClick: () => run("calibration/find-all", { stop: true }) }, tx("Stop")),
        )
      : nozzleLeft.length > foundLeft.length &&
          h(
            React.Fragment,
            null,
            h("button", { type: "button", className: "oui-btn oui-btn--block", "data-find-all": "1", disabled: busy, onClick: () => run("calibration/find-all") }, tx("Find the nozzle by itself at the other {count} points", { count: nozzleLeft.length - foundLeft.length })),
            h("p", { className: "set-group__note" }, tx("The printer goes to each point and moves the toolhead aside for a moment: about 15 seconds per point. Keep your hands out.")),
          ),
    auto.state === "done" && h("p", { className: "set-group__note", "data-auto-done": "1" }, tx("Done: the nozzle found at {found} of {total} points. The others are to tap by hand.", { found: auto.found, total: auto.total })),
    auto.state === "error" && h("p", { className: "set-field__error", role: "alert" }, tx("Stopped: ") + (auto.message || "")),
    foundLeft.length > 0 &&
      !finding &&
      h(
        React.Fragment,
        null,
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-accept": foundLeft.length, disabled: busy, onClick: () => run("calibration/accept") }, h(Icons.Check, { size: 18 }), tx("Use the {count} points found", { count: foundLeft.length })),
        h("p", { className: "set-group__note" }, tx("Blue numbers are found, not checked yet: tap one to see it. «Calculate» then shows in red any that does not fit, to tap again by hand.")),
      ),
  );
}

/* ---------------------------------------------------------------------------
   The page
   ------------------------------------------------------------------------- */
function useCameraCalibration(active) {
  const [state, setState] = useState({ phase: "loading" });
  const reloadRef = useRef(noop);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const read = async () => {
      try {
        const response = await fetchFresh("/api/camera/calibration", { timeout: BACKEND_READ_TIMEOUT_MS * 2 });
        if (response.status === 404) return !cancelled && setState({ phase: "old" });
        const data = await response.json();
        if (!cancelled) setState(response.ok && data.ok ? { phase: "ok", ...data } : (previous) => (previous.phase === "ok" ? previous : { phase: "down" }));
      } catch (error) {
        if (!cancelled) setState((previous) => (previous.phase === "ok" ? previous : { phase: "down" }));
      }
    };
    reloadRef.current = read;
    const stop = startPolling(read, CAMCAL_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);
  return { state, reload: () => reloadRef.current() };
}

function WatchLine({ state, run, busy }) {
  const watch = state.watch || {};
  if (!state.saved) return null;
  const when = watch.time ? formatWhen(watch.time) : "";
  // 1.127: moved a little and corrected by itself (from what stays still in the picture: the frame, the bed's edges)
  if (watch.state === "corrected") {
    const correction = (state.saved && state.saved.shift_fix) || {};
    return h(
      "div",
      { className: "cal-watch", "data-watch": "corrected" },
      h("span", null, tx("The camera moved a little ({px} px, {deg}°): corrected by itself from what stays still in the picture (checked {when}).", { px: formatNumber(correction.shift_px || watch.shift_px || 0), deg: formatNumber(correction.rotation_deg || watch.rotation_deg || 0), when })),
      h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", disabled: busy, "data-undo-correction": "1", onClick: () => run("calibration/correction", { undo: true }) }, tx("Do not trust it")),
    );
  }
  if (watch.state === "moved") {
    if (watch.waiting)
      return h(
        "div",
        { className: "cal-watch", "data-watch": "waiting" },
        h("span", null, tx("The camera seems to have moved a little: checking again before correcting it ({n} of {total}).", { n: watch.waiting, total: 3 })),
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", disabled: busy, "data-check": "1", onClick: () => run("check") }, tx("Check now")),
      );
    return h(
      "div",
      { className: "set-status set-status--warn", role: "alert" },
      h("span", { className: "set-status__dot" }),
      h("span", null, tx("The camera has moved since the calibration ({when}): calibrate it again. Until then the monitor does not use the calibration.", { when }), " ", h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: busy, onClick: () => run("check") }, tx("Check again"))),
    );
  }
  return h(
    "div",
    { className: "cal-watch" },
    h("span", null, watch.state === "ok" ? tx("Camera still in place (checked {when}).", { when }) : tx("Not known whether the camera has moved (picture too dark or unclear).")),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", disabled: busy, "data-check": "1", onClick: () => run("check") }, tx("Check now")),
  );
}

function CameraCalibrationPage({ active }) {
  const { settings } = useSettings();
  const camera = settings.camera;
  const { state, reload } = useCameraCalibration(active);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [calibrating, setCalibrating] = useState(false);
  const [askForget, setAskForget] = useState(false);
  /** One step on the backend. `here`: the caller shows the error next to its own button (it gets the whole reply). */
  const run = async (path, body, here) => {
    setBusy(true);
    const reply = await camcalPost(path, body);
    setBusy(false);
    setProblem(reply.ok || here ? "" : reply.message);
    if (reply.ok && path === "calibration/save") setCalibrating(false);
    reload();
    return here ? reply : reply.ok;
  };
  if (state.phase === "old") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The KlippEye service on the Raspberry cannot calibrate the camera yet: update KlippEye (Settings → Updates)."));
  if (state.phase !== "ok") return h(BackendNotice, { phase: state.phase === "loading" ? "loading" : "down" });
  const saved = state.saved;
  const drafting = calibrating || Boolean(state.draft && state.draft.z_moves);
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: cx("set-status", saved && state.usable ? "set-status--ok" : "set-status--warn") },
      h("span", { className: "set-status__dot" }),
      saved
        ? tx("Calibrated on {when} with {points} points: average error {px} px ({quality}).", { when: formatWhen(saved.saved), points: saved.points, px: formatNumber(Math.round(saved.rms_px * 10) / 10), quality: QUALITY_TEXT[saved.quality] })
        : tx("The camera is not calibrated: the monitor cannot tell the toolhead from a problem yet."),
    ),
    h(WatchLine, { state, run, busy }),
    state.has_cv2 === false && h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("OpenCV is missing on the Raspberry")),
    state.printer === null && h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("Klipper does not answer: the printer cannot be moved now.")),
    problem && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), problem),
    drafting
      ? h(React.Fragment, null, h(KindStep, { state, busy, onChange: (body) => run("calibration/options", body) }), state.draft && state.draft.z_moves && h(PointsStep, { state, camera, run, busy }))
      : h(
          React.Fragment,
          null,
          saved &&
            h(
              SettingsGroup,
              { title: tx("Toolhead and gantry on the live picture"), note: tx("What is inside the outlines is left out of the AI monitor's checks (Settings → Monitor thresholds → False alarms). Adjust the sizes until the outlines cover the toolhead and the gantry wherever they are.") },
              h(LiveCheck, { camera, draft: false, editShape: true }),
            ),
          saved && h(BedArea, { state, reload }),
          saved && h(MaskSwitches, { active }),
          h(
            SettingsGroup,
            { note: tx("About ten minutes, once: do it again only if you move the camera.") },
            h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-start": "1", onClick: () => setCalibrating(true) }, h(Icons.Camera, { size: 18 }), saved ? tx("Calibrate again") : tx("Calibrate the camera")),
          ),
          saved &&
            (askForget
              ? h(
                  "div",
                  { className: "set-confirm", role: "alertdialog", "aria-label": tx("Forget the calibration?") },
                  h("span", null, tx("The monitor goes back to working without the calibration. Confirm?")),
                  h("div", { className: "set-confirm__buttons" }, h("button", { type: "button", className: "oui-btn", onClick: () => setAskForget(false) }, tx("No")), h("button", { type: "button", className: "oui-btn oui-btn--danger", onClick: async () => (setAskForget(false), await camcalDelete(), reload()) }, tx("Yes, forget it"))),
                )
              : h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", onClick: () => setAskForget(true) }, h(Icons.Trash, { size: 18 }), tx("Forget the calibration"))),
        ),
  );
}

/**
 * 1.127: the bed the monitor watches (the dashed outline on the live picture). Worked out from Klipper's mesh area (a
 * little wider), else the toolhead's travel, which often goes beyond the plate (a purge bucket, a brush, the frame):
 * changes there are no failures. The person can set it with − and +.
 */
const BED_STEP_MM = 5;
function BedArea({ state, reload }) {
  const bed = state.bed || {};
  const area = bed.area;
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  if (!area) return null;
  const send = async (next) => {
    setBusy(true);
    const reply = await camcalPost("shape", { bed: next });
    setBusy(false);
    setProblem(reply.ok ? "" : reply.message);
    reload();
  };
  const fields = [
    { key: "x0", label: tx("Left edge (X min)"), get: (a) => a[0][0], set: (a, v) => [[v, a[0][1]], a[1]] },
    { key: "x1", label: tx("Right edge (X max)"), get: (a) => a[1][0], set: (a, v) => [a[0], [v, a[1][1]]] },
    { key: "y0", label: tx("Front edge (Y min)"), get: (a) => a[0][1], set: (a, v) => [[a[0][0], v], a[1]] },
    { key: "y1", label: tx("Back edge (Y max)"), get: (a) => a[1][1], set: (a, v) => [a[0], [a[1][0], v]] },
  ];
  const source =
    bed.source === "person" ? tx("Set by you.") : bed.source === "mesh" ? tx("Worked out from the area of the bed mesh (a little wider).") : tx("The toolhead's travel: it may go beyond the plate.");
  return h(
    SettingsGroup,
    { title: tx("Bed area"), note: tx("The dashed outline on the live picture: the AI monitor watches the bed inside it. Leave out what is not the plate (a purge bucket, a brush, the frame): changes there are no failures.") },
    h("p", { className: "set-group__note", "data-bed-source": bed.source }, source),
    fields.map((field) =>
      h(
        "div",
        { key: field.key, className: "cal-size" },
        h("span", { className: "cal-size__label" }, field.label),
        h("button", { type: "button", className: "oui-btn oui-btn--sm", "aria-label": field.label + " −", "data-bed": field.key + ".minus", disabled: busy, onClick: () => send(field.set(area, field.get(area) - BED_STEP_MM)) }, "−"),
        h("span", { className: "cal-size__value", "data-bed-value": field.key }, formatNumber(field.get(area)), " mm"),
        h("button", { type: "button", className: "oui-btn oui-btn--sm", "aria-label": field.label + " +", "data-bed": field.key + ".plus", disabled: busy, onClick: () => send(field.set(area, field.get(area) + BED_STEP_MM)) }, "+"),
      ),
    ),
    bed.source === "person" && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-bed-auto": "1", disabled: busy, onClick: () => send(null) }, h(Icons.RotateCcw, { size: 16 }), tx("Work it out again by itself")),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

async function camcalDelete() {
  try {
    await fetch("/api/camera/calibration", { method: "DELETE" });
  } catch (error) {}
}

/** What the AI monitor does with the calibration (1.19: these two switches were in Monitor thresholds). */
function MaskSwitches({ active }) {
  const config = useBackendConfig(active);
  const data = useMemo(() => (config.data ? localizeBackendSchema(config.data) : null), [config.data]);
  if (config.phase !== "ok" || !data) return null;
  const specs = ["machine_masks", "expected_zone", "inside_parts"].map((key) => data.spec.find((spec) => spec.key === key)).filter(Boolean);
  return h(SettingsGroup, { title: tx("What the AI monitor does with it") }, h("div", { className: "oui-list" }, specs.map((spec) => h(BackendSettingControl, { key: spec.key, spec, config }))));
}

/** One line for the menu list. */
function cameraCalibrationSummary(calibration) {
  if (!calibration || calibration.phase !== "ok") return tx("So that the monitor knows the toolhead");
  if (!calibration.data.saved) return tx("Not calibrated");
  if (calibration.data.watch && calibration.data.watch.state === "moved") return tx("Camera moved: calibrate again");
  return tx("Calibrated • error {px} px", { px: formatNumber(Math.round(calibration.data.saved.rms_px * 10) / 10) });
}
