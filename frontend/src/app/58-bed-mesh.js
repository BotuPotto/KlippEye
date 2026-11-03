/* ============================================================================
   58 · BED MESH (redone like Mainsail's height map in 1.36, roadmap 6b part 7)
   Klipper's bed-leveling map (`bed_mesh` object) as a coloured 2D grid (the
   values, a tap on a point says where it is) or a 3D surface on a canvas that
   can be rotated (drag) and zoomed (wheel or pinch); the probed points or the
   interpolated mesh; minimum, maximum and range. The profiles Klipper keeps:
   load, rename, remove, save the current mesh under a name; clear the mesh;
   calibrate (a profile name, adaptive or not).
   Klipper's matrices list the front row (Y min) first.
   ========================================================================== */

const MESH_POLL_MS = 2500;
const MESH_ZOOM_RANGE = [0.5, 1.6];
const MESH_TILT_RANGE = [-85, -15];
const MESH_DEFAULT_VIEW = { tilt: -62, rotation: -30, zoom: 0.7 };
const MESH_WHEEL_UNLOCK_MS = 300;

/* ---------------------------------------------------------------------------
   Data
   ------------------------------------------------------------------------- */
function useBedMesh() {
  const [mesh, setMesh] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const status = await moonraker.queryObjects("bed_mesh");
        // keep the previous object when nothing changed, so the canvas is not redrawn for nothing
        if (!cancelled && status.bed_mesh) setMesh((previous) => (JSON.stringify(previous) === JSON.stringify(status.bed_mesh) ? previous : status.bed_mesh));
      } catch (error) {}
      if (!cancelled) setLoading(false);
    };
    const stopPolling = startPolling(load, MESH_POLL_MS);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  return { mesh, loading };
}

/**
 * The heights and their statistics, or null while there is no mesh. `which`: "probed" (the points Klipper measured) or
 * "mesh" (the interpolated mesh Klipper uses). x / y: the place of each column / row in mm (from mesh_min to mesh_max).
 */
function analyzeMesh(mesh, which = "probed") {
  const matrix = mesh && (which === "mesh" ? mesh.mesh_matrix || mesh.probed_matrix : mesh.probed_matrix || mesh.mesh_matrix);
  if (!matrix || matrix.length === 0 || !matrix[0] || matrix[0].length === 0) return null;
  const values = matrix.flat();
  const min = Math.min(...values);
  const max = Math.max(...values);
  const rows = matrix.length;
  const cols = matrix[0].length;
  const low = Array.isArray(mesh.mesh_min) ? mesh.mesh_min : null;
  const high = Array.isArray(mesh.mesh_max) ? mesh.mesh_max : null;
  const place = (index, count, axis) => (low && high ? low[axis] + (count > 1 ? ((high[axis] - low[axis]) * index) / (count - 1) : 0) : null);
  return {
    matrix,
    rows,
    cols,
    min,
    max,
    range: max - min,
    mean: values.reduce((sum, value) => sum + value, 0) / values.length,
    x: Array.from({ length: cols }, (_, i) => place(i, cols, 0)),
    y: Array.from({ length: rows }, (_, i) => place(i, rows, 1)),
    area: low && high ? { min: low, max: high } : null,
  };
}

/** The range (max − min) of a saved profile's points, or null. */
function profileRange(profile) {
  const values = profile && Array.isArray(profile.points) ? profile.points.flat().filter((value) => typeof value === "number") : [];
  return values.length ? Math.max(...values) - Math.min(...values) : null;
}

/** Blue (low) → light blue/green → orange/red (high). */
function heightColor(value, { min, range }) {
  const t = (value - min) / (range || 0.001);
  if (t < 0.5) {
    const g = t * 2;
    return "rgb(" + Math.round(60 + g * 140) + "," + Math.round(120 + g * 100) + "," + Math.round(220 - g * 40) + ")";
  }
  const g = (t - 0.5) * 2;
  return "rgb(" + Math.round(200 + g * 55) + "," + Math.round(220 - g * 140) + "," + Math.round(180 - g * 140) + ")";
}

/* ---------------------------------------------------------------------------
   3D drawing
   ------------------------------------------------------------------------- */
const degrees = (value) => (value * Math.PI) / 180;

/** Maps mesh coordinates (column, row from the front, height) to canvas pixels for a given view. */
function createProjector(canvasSize, stats, view) {
  const { width, height } = canvasSize;
  const baseScale = Math.min(width, height * 1.6) * 0.135 * view.zoom; // a taller canvas (phone, 4:3) gets a bigger map
  const heightScale = (baseScale * 0.6 * 0.22) / (stats.range || 0.1); // heights are exaggerated
  const boxHeight = baseScale;
  const [sinZ, cosZ] = [Math.sin(degrees(view.rotation)), Math.cos(degrees(view.rotation))];
  const [sinX, cosX] = [Math.sin(degrees(view.tilt)), Math.cos(degrees(view.tilt))];

  const project = (column, row, z, flatZ) => {
    let x = column - (stats.cols - 1) / 2;
    let y = (stats.rows - 1) / 2 - row;
    let up = flatZ !== undefined ? flatZ : (stats.mean - z) * heightScale;
    [x, y] = [x * cosZ - y * sinZ, x * sinZ + y * cosZ];
    [y, up] = [y * cosX - up * sinX, y * sinX + up * cosX];
    return { x: width * 0.5 + x * baseScale, y: height * 0.5 + y * baseScale * 0.6 - up, depth: y };
  };
  return { project, boxHeight };
}

function drawPath(ctx, points) {
  ctx.beginPath();
  points.forEach((point, index) => (index === 0 ? ctx.moveTo(point.x, point.y) : ctx.lineTo(point.x, point.y)));
}

/** The translucent build volume: floor, ceiling, pillars and a quarter-step grid on both. */
function drawBuildVolume(ctx, { project, boxHeight }, stats) {
  const { cols, rows } = stats;
  const floor = [project(0, 0, 0, -boxHeight / 2), project(cols - 1, 0, 0, -boxHeight / 2), project(cols - 1, rows - 1, 0, -boxHeight / 2), project(0, rows - 1, 0, -boxHeight / 2)];
  const ceiling = [project(0, 0, 0, boxHeight / 2), project(cols - 1, 0, 0, boxHeight / 2), project(cols - 1, rows - 1, 0, boxHeight / 2), project(0, rows - 1, 0, boxHeight / 2)];
  const between = (a, b, t) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
  const line = (a, b) => {
    drawPath(ctx, [a, b]);
    ctx.stroke();
  };

  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 0.7;
  [floor, ceiling].forEach((ring) => {
    drawPath(ctx, ring);
    ctx.closePath();
    ctx.stroke();
  });
  floor.forEach((corner, index) => line(corner, ceiling[index]));
  for (let step = 1; step < 4; step++) {
    const t = step / 4;
    [floor, ceiling].forEach((ring) => line(between(ring[0], ring[1], t), between(ring[3], ring[2], t)));
    line(between(floor[0], floor[3], t), between(ceiling[0], ceiling[3], t));
    line(between(floor[1], floor[2], t), between(ceiling[1], ceiling[2], t));
  }

  ctx.fillStyle = "rgba(255,255,255,0.05)";
  drawPath(ctx, floor);
  ctx.closePath();
  ctx.fill();
}

/** The mesh as depth-sorted triangles (painter's algorithm). */
function drawSurface(ctx, { project }, stats, heightAt) {
  const triangles = [];
  for (let row = 0; row < stats.rows - 1; row++) {
    for (let column = 0; column < stats.cols - 1; column++) {
      const [v00, v10, v01, v11] = [heightAt(row, column), heightAt(row, column + 1), heightAt(row + 1, column), heightAt(row + 1, column + 1)];
      const [p00, p10, p01, p11] = [project(column, row, v00), project(column + 1, row, v10), project(column, row + 1, v01), project(column + 1, row + 1, v11)];
      triangles.push({ points: [p00, p10, p11], value: (v00 + v10 + v11) / 3, depth: (p00.depth + p10.depth + p11.depth) / 3 });
      triangles.push({ points: [p00, p11, p01], value: (v00 + v11 + v01) / 3, depth: (p00.depth + p11.depth + p01.depth) / 3 });
    }
  }
  triangles.sort((a, b) => a.depth - b.depth);
  ctx.lineWidth = 0.35;
  triangles.forEach((triangle) => {
    drawPath(ctx, triangle.points);
    ctx.closePath();
    ctx.fillStyle = heightColor(triangle.value, stats);
    ctx.globalAlpha = 0.92;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = "rgba(0,0,0,0.18)";
    ctx.stroke();
  });
}

/** Red X axis, green Y axis and a white dot at the front-left probe point (0,0). */
function drawOrigin(ctx, { project }, stats, heightAt) {
  const origin = project(0, 0, heightAt(0, 0));
  const xEnd = Math.min(3, stats.cols - 1);
  const yEnd = Math.min(3, stats.rows - 1);
  const xAxis = project(xEnd, 0, heightAt(0, xEnd));
  const yAxis = project(0, yEnd, heightAt(yEnd, 0));

  ctx.lineWidth = 2.2;
  [
    ["#ff6b6b", xAxis],
    ["#4ade80", yAxis],
  ].forEach(([color, end]) => {
    ctx.strokeStyle = color;
    drawPath(ctx, [origin, end]);
    ctx.stroke();
  });
  [
    ["#ffffff", 5],
    ["#000000", 2],
  ].forEach(([color, radius]) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(origin.x, origin.y, radius, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.fillStyle = "rgba(255,255,255,0.95)";
  ctx.font = "600 12px system-ui, sans-serif";
  ctx.fillText(tx("Origin (0,0)"), origin.x - 10, origin.y + 20);
}

function drawMesh3D(canvas, stats, view) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return; // hidden, or in the middle of a resize: keep the last drawing
  const size = { width: rect.width, height: rect.height };
  canvas.width = size.width * dpr;
  canvas.height = size.height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, size.width, size.height); // the card's well shows through

  const projector = createProjector(size, stats, view);
  // Klipper lists the front row (Y min) first, as the view counts them (1.36: before, the map was drawn front to back)
  const heightAt = (row, column) => stats.matrix[row][column];
  drawBuildVolume(ctx, projector, stats);
  drawSurface(ctx, projector, stats, heightAt);
  drawOrigin(ctx, projector, stats, heightAt);
}

/* ---------------------------------------------------------------------------
   Orbit controls: drag to rotate, wheel / pinch to zoom. The page does not
   scroll while the canvas is being manipulated.
   ------------------------------------------------------------------------- */
function useOrbitControls(canvasRef, viewRef, redraw, enabled) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!enabled || !canvas) return;
    const view = viewRef.current;
    const drag = { active: false, x: 0, y: 0, pinchDistance: 0 };
    let releaseScroll = null;
    const lockScroll = () => {
      if (!releaseScroll) releaseScroll = acquireScrollLock();
    };
    const unlockScroll = () => {
      if (releaseScroll) releaseScroll();
      releaseScroll = null;
    };
    const point = (event) => (event.touches ? event.touches[0] : event);
    const pinchDistance = (event) => Math.hypot(event.touches[0].clientX - event.touches[1].clientX, event.touches[0].clientY - event.touches[1].clientY);
    const zoomBy = (factor) => (view.zoom = clamp(view.zoom * factor, MESH_ZOOM_RANGE[0], MESH_ZOOM_RANGE[1]));

    const onDown = (event) => {
      drag.active = true;
      lockScroll();
      drag.x = point(event).clientX;
      drag.y = point(event).clientY;
      if (event.touches && event.touches.length === 2) drag.pinchDistance = pinchDistance(event);
      if (event.cancelable) event.preventDefault();
    };
    const onMove = (event) => {
      if (!drag.active) return;
      if (event.cancelable) event.preventDefault();
      if (event.touches && event.touches.length === 2) {
        const distance = pinchDistance(event);
        if (drag.pinchDistance > 0) zoomBy(distance / drag.pinchDistance);
        drag.pinchDistance = distance;
      } else {
        const { clientX, clientY } = point(event);
        view.rotation += (clientX - drag.x) * 0.35;
        view.tilt = clamp(view.tilt + (clientY - drag.y) * 0.35, MESH_TILT_RANGE[0], MESH_TILT_RANGE[1]);
        drag.x = clientX;
        drag.y = clientY;
      }
      redraw();
    };
    const onUp = () => {
      drag.active = false;
      drag.pinchDistance = 0;
      unlockScroll();
    };
    const onWheel = (event) => {
      event.preventDefault();
      lockScroll();
      zoomBy(event.deltaY < 0 ? 1.08 : 0.92);
      redraw();
      setTimeout(unlockScroll, MESH_WHEEL_UNLOCK_MS);
    };

    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("touchstart", onDown, { passive: false });
    window.addEventListener("mousemove", onMove, { passive: false });
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchend", onUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      canvas.removeEventListener("mousedown", onDown);
      canvas.removeEventListener("touchstart", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchend", onUp);
      canvas.removeEventListener("wheel", onWheel);
      unlockScroll();
    };
  }, [enabled]);
}

/* ---------------------------------------------------------------------------
   Card
   ------------------------------------------------------------------------- */
const MESH_PROFILE_NAME = /^[A-Za-z0-9_-]{1,40}$/;
const MESH_VALUES_MAX_COLS = 9; // more columns than this: the 2D grid has no room for the numbers
const meshSigned = (value, digits = 3) => (value > 0 ? "+" : "") + value.toFixed(digits);

function ViewToggle({ mode, onChange }) {
  const button = (id, label) => h("button", { type: "button", onClick: () => onChange(id), className: mode === id ? "is-selected" : "", "aria-pressed": mode === id }, label);
  return h("div", { className: "oui-segmented", role: "group", "aria-label": tx("View") }, button("2d", "2D"), button("3d", "3D"));
}

/** Colour scale legend (low → high). */
function MeshLegend({ stats }) {
  return h("div", { className: "mesh-legend" }, h("span", null, meshSigned(stats.min)), h("span", { className: "mesh-legend__scale" }), h("span", null, meshSigned(stats.max)));
}

/** Minimum, maximum, range, and the size of the grid. */
function MeshStats({ stats }) {
  const tile = (label, value, extra) => h("div", { className: cx("oui-tile mesh-stat", extra) }, h("div", { className: "oui-caption" }, label), h("div", { className: "mesh-stat__value" }, value));
  return h(
    "div",
    { className: "mesh-stats" },
    tile(tx("Minimum"), meshSigned(stats.min) + " mm"),
    tile(tx("Maximum"), meshSigned(stats.max) + " mm"),
    tile(tx("Range"), stats.range.toFixed(3) + " mm", stats.range > 0.3 ? "mesh-stat--warn" : null),
    tile(tx("Points"), stats.cols + " × " + stats.rows),
  );
}

/** The grid as seen from above, the back of the bed at the top; the numbers when there is room; a tap tells where a point is. */
function MeshGrid({ stats }) {
  const [picked, setPicked] = useState(null); // { row, col }
  const values = stats.cols <= MESH_VALUES_MAX_COLS;
  const rowsTopDown = stats.matrix.map((row, index) => ({ row, index })).reverse();
  const at = picked && stats.matrix[picked.row] ? stats.matrix[picked.row][picked.col] : null;
  return h(
    "div",
    { className: "mesh-well oui-well" },
    h(
      "div",
      { className: "mesh-grid", style: { gridTemplateColumns: "repeat(" + stats.cols + ", minmax(0,1fr))" } },
      rowsTopDown.map(({ row, index }) =>
        row.map((value, column) =>
          h(
            "button",
            {
              key: index + "-" + column,
              type: "button",
              className: cx("mesh-cell", picked && picked.row === index && picked.col === column && "is-picked"),
              style: { background: heightColor(value, stats) },
              "data-row": index,
              "data-col": column,
              "aria-label": "X " + (stats.x[column] !== null ? Math.round(stats.x[column]) : column) + " Y " + (stats.y[index] !== null ? Math.round(stats.y[index]) : index) + ": " + meshSigned(value),
              onClick: () => setPicked(picked && picked.row === index && picked.col === column ? null : { row: index, col: column }),
            },
            values && h("span", { className: "mesh-cell__value" }, value.toFixed(2)),
          ),
        ),
      ),
    ),
    h(
      "div",
      { className: "mesh-grid__foot" },
      at !== null
        ? h("span", { className: "mesh-pick", "data-pick": "" }, (stats.x[picked.col] !== null ? "X " + stats.x[picked.col].toFixed(1) + " · Y " + stats.y[picked.row].toFixed(1) : tx("Point") + " " + (picked.col + 1) + "," + (picked.row + 1)) + ": ", h("b", null, meshSigned(at) + " mm"))
        : h("span", { className: "oui-caption" }, tx("Back of the bed at the top. Tap a point to see where it is.")),
    ),
    h(MeshLegend, { stats }),
  );
}

function MeshSurface({ stats }) {
  const canvasRef = useRef(null);
  const viewRef = useRef({ ...MESH_DEFAULT_VIEW }); // rotation / tilt / zoom survive new data
  const redrawRef = useRef(noop);
  redrawRef.current = () => canvasRef.current && drawMesh3D(canvasRef.current, stats, viewRef.current);
  const redraw = () => redrawRef.current();

  useEffect(() => {
    redraw();
    window.addEventListener("resize", redraw);
    return () => window.removeEventListener("resize", redraw);
  }, [stats]);
  useOrbitControls(canvasRef, viewRef, redraw, true);

  const reset = () => {
    Object.assign(viewRef.current, MESH_DEFAULT_VIEW);
    redraw();
  };
  return h(
    "div",
    { className: "mesh-well oui-well mesh-surface" },
    h("canvas", { ref: canvasRef, className: "mesh-canvas" }),
    h("button", { type: "button", className: "icon-btn mesh-surface__reset", "aria-label": tx("Reset the view"), title: tx("Reset the view"), onClick: reset }, h(Icons.Refresh, { size: 16 })),
    h(MeshLegend, { stats }),
  );
}

/** A profile name typed by the person (Klipper takes letters, digits, _ and -). */
function MeshNameDialog({ open, title, initial, confirmLabel, onConfirm, onCancel, extra }) {
  const [name, setName] = useState(initial || "");
  useEffect(() => {
    if (open) setName(initial || "");
  }, [open]);
  const valid = MESH_PROFILE_NAME.test(name.trim());
  return h(ConfirmDialog, {
    open,
    tone: "neutral",
    icon: h(Icons.Layers),
    title,
    message: h(
      "div",
      { className: "mesh-name" },
      h("input", {
        className: cx("oui-field mesh-name__input", !valid && name && "is-invalid"),
        value: name,
        autoFocus: true,
        "aria-label": tx("Profile name"),
        placeholder: tx("Profile name"),
        onChange: (event) => setName(event.target.value),
        onKeyDown: (event) => event.key === "Enter" && valid && onConfirm(name.trim()),
      }),
      h("span", { className: "oui-caption" }, valid || !name ? tx("Letters, digits, _ and - (no spaces).") : tx("Only letters, digits, _ and -, no spaces.")),
      extra,
    ),
    confirmLabel,
    onConfirm: () => valid && onConfirm(name.trim()),
    onCancel,
  });
}

/** The profiles Klipper keeps in printer.cfg: the one in use, their range, load / rename / remove. */
function MeshProfiles({ mesh, locked, run }) {
  const [renaming, setRenaming] = useState(null);
  const [removing, setRemoving] = useState(null);
  const profiles = Object.keys((mesh && mesh.profiles) || {}).sort((a, b) => (a === "default" ? -1 : b === "default" ? 1 : a.localeCompare(b)));
  const active = mesh && mesh.profile_name;
  return h(
    "div",
    { className: "mesh-profiles" },
    h("div", { className: "oui-label mesh-profiles__title" }, tx("Profiles")),
    profiles.length === 0
      ? h("p", { className: "oui-caption" }, tx("No profile saved yet: calibrate, or save the current mesh."))
      : h(
          "div",
          { className: "oui-list" },
          profiles.map((name) => {
            const range = profileRange(mesh.profiles[name]);
            return h(
              "div",
              { key: name, className: cx("oui-row mesh-profile-row", name === active && "is-active"), "data-profile": name },
              h(
                "span",
                { className: "oui-row__text" },
                h("span", { className: "oui-row__name" }, name, name === active && h("span", { className: "oui-badge oui-badge--ok mesh-profile-row__badge" }, tx("In use"))),
                h("span", { className: "oui-row__meta" }, range !== null ? tx("Range {value} mm", { value: range.toFixed(3) }) : ""),
              ),
              name !== active && h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: Boolean(locked), onClick: () => run("BED_MESH_PROFILE LOAD=" + name, tx("Profile {name} loaded", { name })) }, tx("Load")),
              h("button", { type: "button", className: "macro-edit-btn", "aria-label": tx("Rename") + " " + name, title: tx("Rename"), disabled: Boolean(locked), onClick: () => setRenaming(name) }, h(Icons.Pencil, { size: 16 })),
              h("button", { type: "button", className: "macro-edit-btn macro-edit-btn--danger", "aria-label": tx("Remove") + " " + name, title: tx("Remove"), onClick: () => setRemoving(name) }, h(Icons.Trash, { size: 16 })),
            );
          }),
        ),
    h(MeshNameDialog, {
      open: Boolean(renaming),
      title: tx("Rename the profile"),
      initial: renaming,
      confirmLabel: tx("Rename"),
      onCancel: () => setRenaming(null),
      onConfirm: (name) => {
        const old = renaming;
        setRenaming(null);
        if (name !== old) run(["BED_MESH_PROFILE LOAD=" + old, "BED_MESH_PROFILE SAVE=" + name, "BED_MESH_PROFILE REMOVE=" + old].join("\n"), tx("Profile renamed: save the configuration to keep it"));
      },
      extra: h("span", { className: "oui-caption" }, tx("Klipper has no renaming: the profile is loaded, saved with the new name and the old one removed.")),
    }),
    h(ConfirmDialog, {
      open: Boolean(removing),
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Remove the profile?"),
      subtitle: removing,
      message: tx("It leaves printer.cfg at the next SAVE_CONFIG (the save button at the top)."),
      confirmLabel: tx("Remove"),
      onConfirm: () => {
        const name = removing;
        setRemoving(null);
        run("BED_MESH_PROFILE REMOVE=" + name, tx("Profile removed: save the configuration to confirm"));
      },
      onCancel: () => setRemoving(null),
    }),
  );
}

/** `onGcode(script)` sends G-code; `lockReason` (a print, or no status yet) stops what moves the machine or changes the mesh in use. */
function BedMeshCard({ onGcode, lockReason, homedAxes }) {
  const { mesh, loading } = useBedMesh();
  const [viewMode, setViewMode] = useState("3d");
  const [which, setWhich] = useState("probed");
  const [calibrating, setCalibrating] = useState(false);
  const [adaptive, setAdaptive] = useState(false);
  const [saving, setSaving] = useState(false);
  const stats = useMemo(() => analyzeMesh(mesh, which), [mesh, which]);
  const homed = ["x", "y", "z"].every((axis) => (homedAxes || "").includes(axis));
  const run = (script, message) => {
    onGcode(script);
    toast.action(message);
  };
  const hasMesh = Boolean(stats);

  return h(
    Card,
    { className: "mesh-card" },
    h(
      CardHeader,
      { title: tx("Height map / mesh") },
      h("span", { className: "oui-badge mesh-profile", "data-active-profile": (mesh && mesh.profile_name) || "" }, (mesh && mesh.profile_name) || tx("no mesh")),
    ),
    h(
      "div",
      { className: "mesh-toolbar" },
      h(ViewToggle, { mode: viewMode, onChange: setViewMode }),
      h(
        "div",
        { className: "oui-segmented mesh-which", role: "group", "aria-label": tx("Data") },
        h("button", { type: "button", className: which === "probed" ? "is-selected" : "", "aria-pressed": which === "probed", onClick: () => setWhich("probed") }, tx("Probed")),
        h("button", { type: "button", className: which === "mesh" ? "is-selected" : "", "aria-pressed": which === "mesh", onClick: () => setWhich("mesh") }, tx("Interpolated")),
      ),
      !homed && h("button", { type: "button", onClick: () => run("G28", "Homing G28"), disabled: Boolean(lockReason), className: "icon-btn", title: "Homing G28", "aria-label": "Homing G28" }, h(Icons.House, { size: 16 })),
    ),
    !stats
      ? h("div", { className: "mesh-well oui-well mesh-empty" }, loading ? tx("Loading...") : tx("No mesh loaded: calibrate, or load a profile."))
      : h(React.Fragment, null, viewMode === "2d" ? h(MeshGrid, { stats }) : h(MeshSurface, { stats }), h(MeshStats, { stats })),
    h(
      "div",
      { className: "mesh-actions" },
      h("button", { type: "button", onClick: () => setCalibrating(true), disabled: Boolean(lockReason), className: "oui-btn oui-btn--primary" }, tx("Calibrate mesh")),
      h("button", { type: "button", onClick: () => setSaving(true), disabled: !hasMesh, className: "oui-btn" }, tx("Save as…")),
      h("button", { type: "button", onClick: () => run("BED_MESH_CLEAR", tx("Mesh cleared")), disabled: !hasMesh || Boolean(lockReason), className: "oui-btn oui-btn--quiet" }, tx("Clear")),
    ),
    lockReason && h("p", { className: "oui-caption mesh-lock" }, lockReason),
    h(MeshProfiles, { mesh, locked: lockReason, run }),
    h(MeshNameDialog, {
      open: calibrating,
      title: tx("Calibrate the mesh"),
      initial: "default",
      confirmLabel: tx("Calibrate"),
      onCancel: () => setCalibrating(false),
      onConfirm: (name) => {
        setCalibrating(false);
        run("BED_MESH_CALIBRATE PROFILE=" + name + (adaptive ? " ADAPTIVE=1" : ""), tx("Mesh calibration started ({name})", { name }));
      },
      extra: h(
        "label",
        { className: "mesh-adaptive" },
        h("input", { type: "checkbox", className: "oui-check", checked: adaptive, onChange: (event) => setAdaptive(event.target.checked) }),
        h("span", null, h("b", null, tx("Adaptive")), " — ", tx("only where the objects of the print are (needs [exclude_object] and a sliced file)")),
      ),
    }),
    h(MeshNameDialog, {
      open: saving,
      title: tx("Save the mesh as a profile"),
      initial: (mesh && mesh.profile_name) || "default",
      confirmLabel: tx("Save"),
      onCancel: () => setSaving(false),
      onConfirm: (name) => {
        setSaving(false);
        run("BED_MESH_PROFILE SAVE=" + name, tx("Saved as {name}: save the configuration to keep it", { name }));
      },
    }),
  );
}
