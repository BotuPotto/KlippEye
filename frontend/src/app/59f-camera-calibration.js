/* ============================================================================
   59f · CAMERA CALIBRATION
   The page "Calibra la camera" of the settings menu (roadmap phase 4): the backend learns where every point of the
   printer appears in the camera picture (backend/camera_calibration.py, camera_model.py), so that the AI monitor can
   leave the toolhead out and know where the part is. The person:
     1. says how Z moves (the bed, or the toolhead) and how big the toolhead is;
     2. (Z moves the bed) puts six markers on the bed: six small pyramids printed from the STL made here (KlippEye then
        reads where they ended up in the G-code that printed them), or six quick blobs left by the printer itself;
     3. for each of about twelve points: the printer goes there, the person taps the nozzle tip (or the marker) in the
        picture, then taps again in the magnified view to be precise;
     4. "Calculate": the error in pixels and the points to redo; "Save" when it is good;
     5. checks it live: the toolhead outline and the bed are drawn over the picture while the toolhead moves.
   The calibration is valid until the camera moves: the backend compares the picture with the one taken at calibration
   every ten minutes and, when the camera has moved, says so here and stops using the calibration.
   ========================================================================== */

const CAMCAL_POLL_MS = 3000;
const CAMCAL_LIVE_MS = 1500;
const LOUPE_ZOOM = 4;
const TOOLHEAD_FIELDS = [
  { key: "width", label: tx("Width (X)") },
  { key: "depth", label: tx("Depth (Y)") },
  { key: "height", label: tx("Height above the nozzle") },
];
const QUALITY_TEXT = { good: tx("good"), fair: tx("acceptable"), poor: tx("not good enough") };

/** POST to the calibration API; resolves { ok, data, message } like brainPost, with a longer wait (moves take time). */
async function camcalPost(path, body) {
  try {
    const response = await fetch("/api/camera/" + path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body || {}) });
    let data = null;
    try {
      data = await response.json();
    } catch (error) {}
    return { ok: response.ok && !(data && data.ok === false), data, message: (data && data.error) || (response.ok ? "" : "HTTP " + response.status) };
  } catch (error) {
    return { ok: false, data: null, message: tx("the backend does not answer") };
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
function CameraFrame({ src, camera, onTap, children, label, onAspect }) {
  return h(
    "div",
    { className: cx("cal-frame", onTap && "cal-frame--tap"), style: flipStyle(camera) },
    h("img", {
      className: "cal-frame__img",
      src,
      alt: label || tx("Camera picture"),
      draggable: false,
      onLoad: onAspect ? (event) => event.currentTarget.naturalHeight && onAspect(event.currentTarget.naturalWidth / event.currentTarget.naturalHeight) : undefined,
      onClick: onTap ? (event) => onTap(tapFraction(event, event.currentTarget, camera)) : undefined,
    }),
    h("svg", { className: "cal-frame__draw", viewBox: "0 0 1 1", preserveAspectRatio: "none", "aria-hidden": "true" }, children),
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
function LiveCheck({ camera, draft }) {
  const [stamp, setStamp] = useState(() => Date.now());
  const [overlay, setOverlay] = useState(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const read = async () => {
      try {
        const response = await fetchFresh("/api/camera/overlay" + (draft ? "?draft=1" : ""), { timeout: BRAIN_READ_TIMEOUT_MS });
        const data = await response.json();
        if (cancelled) return;
        if (response.ok && data.ok) {
          setOverlay(data);
          setProblem("");
        } else setProblem(data.error || "HTTP " + response.status);
      } catch (error) {}
      if (!cancelled) setStamp(Date.now());
    };
    return startPolling(read, CAMCAL_LIVE_MS);
  }, [draft]);
  const jog = async (dx, dy, dz) => {
    setBusy(true);
    const reply = await camcalPost("calibration/jog", { dx, dy, dz });
    setBusy(false);
    setProblem(reply.ok ? "" : reply.message);
  };
  const step = (label, dx, dy, dz) => h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: busy, onClick: () => jog(dx, dy, dz) }, label);
  return h(
    React.Fragment,
    null,
    h(
      CameraFrame,
      { src: "/api/print/snapshot?t=" + stamp, camera, label: tx("Live picture with the calibration drawn over it") },
      overlay && overlay.bed.length > 2 && h("polygon", { className: "cal-bed", points: pointsAttr(overlay.bed) }),
      overlay && overlay.toolhead.length > 2 && h("polygon", { className: "cal-toolhead", points: pointsAttr(overlay.toolhead) }),
      overlay && overlay.nozzle && h(Cross, { u: overlay.nozzle[0], v: overlay.nozzle[1], tone: "nozzle" }),
    ),
    h("p", { className: "set-group__note" }, tx("Purple: the toolhead as the monitor will see it; dashed: the bed. Move the toolhead: the drawing must follow it.") + (overlay ? " X " + overlay.position[0] + " • Y " + overlay.position[1] + " • Z " + overlay.position[2] : "")),
    h("div", { className: "cal-jog" }, step("X −20", -20, 0, 0), step("X +20", 20, 0, 0), step("Y −20", 0, -20, 0), step("Y +20", 0, 20, 0), step("Z −10", 0, 0, -10), step("Z +10", 0, 0, 10)),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

/* ---------------------------------------------------------------------------
   The steps
   ------------------------------------------------------------------------- */
function KindStep({ state, onChange, busy }) {
  const draft = state.draft || {};
  const chosen = draft.z_moves || "";
  const tool = draft.toolhead || {};
  const [sizes, setSizes] = useState(() => ({ width: tool.width || 60, depth: tool.depth || 70, height: tool.height || 70 }));
  const options = [
    { id: "bed", label: tx("Z moves the bed"), detail: tx("VzBot, Voron Trident, RatRig V-Core, most CoreXY") },
    { id: "toolhead", label: tx("Z moves the toolhead"), detail: tx("Voron 2.4 and other printers whose gantry goes up and down") },
  ];
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("How does the Z axis move?"), note: (state.guess && !chosen ? tx("From Klipper's configuration it looks like: {kind}.", { kind: options.find((o) => o.id === state.guess).label }) + " " : "") + tx("Printers whose bed moves in Y (Prusa, Ender) are not supported yet.") },
      h(ChoiceRows, { options, value: chosen || state.guess, label: tx("How does the Z axis move?"), onChange: (id) => onChange({ z_moves: id, toolhead: sizes }) }),
    ),
    h(
      SettingsGroup,
      { title: tx("Size of the toolhead"), note: tx("A box around the nozzle, from the tip upwards, in mm: with fan duct and cables. Used for the drawing (and later for leaving the toolhead out).") },
      h(
        "div",
        { className: "set-grid" },
        TOOLHEAD_FIELDS.map((field) =>
          h(
            "label",
            { key: field.key, className: "set-field" },
            h("span", { className: "set-field__label" }, field.label),
            h("input", {
              className: "oui-field oui-field--num set-field__input",
              inputMode: "numeric",
              value: sizes[field.key],
              onChange: (event) => /^\d{0,3}$/.test(event.target.value) && setSizes({ ...sizes, [field.key]: event.target.value }),
              onBlur: () => chosen && onChange({ toolhead: { width: Number(sizes.width) || 60, depth: Number(sizes.depth) || 70, height: Number(sizes.height) || 70 } }),
            }),
          ),
        ),
      ),
      !chosen && h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: busy || !state.guess, onClick: () => onChange({ z_moves: state.guess, toolhead: { width: Number(sizes.width) || 60, depth: Number(sizes.depth) || 70, height: Number(sizes.height) || 70 } }) }, tx("Go on")),
    ),
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
        const response = await fetchFresh("/api/camera/gcode-files", { timeout: BRAIN_READ_TIMEOUT_MS * 2 });
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
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Before starting"), note: tx("Clean bed (only the markers on it); the light as during prints; the printer idle. The printer moves by itself: keep your hands out.") },
      !state.printer || !/x/.test(state.printer.homed) || !/z/.test(state.printer.homed)
        ? h("button", { type: "button", className: "oui-btn oui-btn--block", disabled: busy, onClick: () => run("calibration/home") }, h(Icons.House, { size: 16 }), tx("Home the printer (G28)"))
        : h("p", { className: "set-group__note" }, tx("Printer homed.")),
    ),
    needsMarks && h(MarkersStep, { state, run, busy }),
    target &&
      h(
        SettingsGroup,
        { title: tx("Points: {done} of {total}", { done, total: targets.length }) },
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
                className: cx("cal-target", points[t.id] && "is-done", redo.has(t.id) && "is-redo", t.id === target.id && "is-current"),
                onClick: () => setCurrent(t.id),
                title: errors[t.id] !== undefined ? errors[t.id] + " px" : "",
              },
              index + 1,
            ),
          ),
        ),
        h(
          "p",
          { className: "set-group__note cal-instruction" },
          target.kind === "mark"
            ? tx("Point {n}: the bed goes down and the nozzle moves away. Tap the tip of the marker at X {x}, Y {y} (the centre, for a blob).", { n: targets.indexOf(target) + 1, x: target.x, y: target.y })
            : tx("Point {n}: the nozzle goes to X {x}, Y {y}, Z {z}. Tap the very tip of the nozzle.", { n: targets.indexOf(target) + 1, x: target.x, y: target.y, z: target.z }),
        ),
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-go": target.id, disabled: busy, onClick: go }, at ? tx("Go there again") : tx("Go to point {n}", { n: targets.indexOf(target) + 1 })),
        at &&
          h(
            "div",
            { className: "cal-pick" },
            h(CameraFrame, { src, camera, onTap: setTap, onAspect: setAspect }, tap && h(Cross, tap), points[target.id] && h(Cross, { u: points[target.id].u, v: points[target.id].v, tone: "saved" })),
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
        const response = await fetchFresh("/api/camera/calibration", { timeout: BRAIN_READ_TIMEOUT_MS * 2 });
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
  if (watch.state === "moved") {
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
  if (state.phase === "old") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The backend on the Raspberry cannot calibrate the camera yet: update KlippEye (Settings → Updates)."));
  if (state.phase !== "ok") return h(BrainNotice, { phase: state.phase === "loading" ? "loading" : "down" });
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
          saved && h(SettingsGroup, { title: tx("Check it on the live picture") }, h(LiveCheck, { camera, draft: false })),
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

async function camcalDelete() {
  try {
    await fetch("/api/camera/calibration", { method: "DELETE" });
  } catch (error) {}
}

/** One line for the menu list. */
function cameraCalibrationSummary(calibration) {
  if (!calibration || calibration.phase !== "ok") return tx("So that the monitor knows the toolhead");
  if (!calibration.data.saved) return tx("Not calibrated");
  if (calibration.data.watch && calibration.data.watch.state === "moved") return tx("Camera moved: calibrate again");
  return tx("Calibrated • error {px} px", { px: formatNumber(Math.round(calibration.data.saved.rms_px * 10) / 10) });
}
