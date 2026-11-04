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
const MESH_TILT_RANGE = [8, 85]; // the eye's height above the bed, degrees
const MESH_DEFAULT_VIEW = { tilt: 30, rotation: -28, zoom: 1 };
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

/** Mainsail's colours (blue low → yellow → red high), the scale running over the mesh's own range (1.36.1). */
const MESH_COLORS = ["#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8", "#ffffbf", "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"];
const MESH_RGB = MESH_COLORS.map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));
/** White writing on the dark ends of the scale, black in the light middle. */
const meshTextColor = (value, { min, range }) => {
  const t = (value - min) / (range || 0.001);
  return t < 0.22 || t > 0.8 ? "rgba(255,255,255,0.92)" : "rgba(0,0,0,0.72)";
};

function heightColor(value, { min, range }) {
  const t = clamp((value - min) / (range || 0.001), 0, 1) * (MESH_RGB.length - 1);
  const i = Math.min(MESH_RGB.length - 2, Math.floor(t));
  const f = t - i;
  const [a, b] = [MESH_RGB[i], MESH_RGB[i + 1]];
  return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * f) + "," + Math.round(a[1] + (b[1] - a[1]) * f) + "," + Math.round(a[2] + (b[2] - a[2]) * f) + ")";
}

/* ---------------------------------------------------------------------------
   3D drawing (1.36.1: like Mainsail's) — a smooth surface (each cell split in
   small pieces, each coloured by its own height: the colour runs across the
   cell instead of one colour a square), the mesh lines on it, and a box with a
   grid and the X / Y / Z values on its edges. Seen from the front, above.
   ------------------------------------------------------------------------- */
const degrees = (value) => (value * Math.PI) / 180;
const MESH_SURFACE_PIECES = 2600; // about how many small quads the surface is split in

/** Maps (column, row from the front, height) to canvas pixels for a view: { rotation (around the vertical), tilt (height of the eye, degrees) }. */
function createProjector(canvasSize, stats, view) {
  const { width, height } = canvasSize;
  const spanX = stats.area ? stats.area.max[0] - stats.area.min[0] : stats.cols - 1;
  const spanY = stats.area ? stats.area.max[1] - stats.area.min[1] : stats.rows - 1;
  const longest = Math.max(spanX, spanY) || 1;
  const size = Math.min(width * 0.9, height * 1.25) * 0.58 * view.zoom; // the longer side of the bed, in pixels
  const half = { x: (spanX / longest) * size * 0.5, y: (spanY / longest) * size * 0.5 };
  const boxHeight = size * 0.42;
  const mid = (stats.min + stats.max) / 2;
  const heightScale = (boxHeight * 0.55) / (stats.range || 0.05);
  const [sinZ, cosZ] = [Math.sin(degrees(view.rotation)), Math.cos(degrees(view.rotation))];
  const [sinE, cosE] = [Math.sin(degrees(view.tilt)), Math.cos(degrees(view.tilt))];
  const centre = { x: width / 2, y: height / 2 + boxHeight * 0.05 };

  /** u, v from -1 (front left) to 1; `up` in pixels. */
  const place = (u, v, up) => {
    const x0 = u * half.x;
    const y0 = v * half.y;
    const x = x0 * cosZ - y0 * sinZ;
    const y = x0 * sinZ + y0 * cosZ;
    return { x: centre.x + x, y: centre.y - (up * cosE + y * sinE), depth: y * cosE - up * sinE };
  };
  const u = (column) => (stats.cols > 1 ? (column / (stats.cols - 1)) * 2 - 1 : 0);
  const v = (row) => (stats.rows > 1 ? (row / (stats.rows - 1)) * 2 - 1 : 0);
  const project = (column, row, z, flatUp) => place(u(column), v(row), flatUp !== undefined ? flatUp : (z - mid) * heightScale);
  return { project, place, boxHeight, heightScale, mid };
}

function drawPath(ctx, points) {
  ctx.beginPath();
  points.forEach((point, index) => (index === 0 ? ctx.moveTo(point.x, point.y) : ctx.lineTo(point.x, point.y)));
}

/** The box: floor and the two walls at the back (as the view turns), each with a grid, and the values on the edges. */
function drawBuildVolume(ctx, { place, boxHeight, heightScale, mid }, stats) {
  const low = -boxHeight / 2;
  const top = boxHeight / 2;
  const line = (a, b, color, widthPx) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = widthPx || 0.8;
    drawPath(ctx, [a, b]);
    ctx.stroke();
  };
  const STEPS = 4;
  const grid = "rgba(255,255,255,0.10)";
  const edge = "rgba(255,255,255,0.28)";
  // floor
  ctx.fillStyle = "rgba(255,255,255,0.035)";
  drawPath(ctx, [place(-1, -1, low), place(1, -1, low), place(1, 1, low), place(-1, 1, low)]);
  ctx.closePath();
  ctx.fill();
  for (let i = 0; i <= STEPS; i++) {
    const t = (i / STEPS) * 2 - 1;
    line(place(t, -1, low), place(t, 1, low), i % STEPS ? grid : edge);
    line(place(-1, t, low), place(1, t, low), i % STEPS ? grid : edge);
  }
  // the walls at the back: the side (x = ±1) and the end (y = ±1) farther from the eye
  const sideX = place(1, 0, 0).depth > place(-1, 0, 0).depth ? 1 : -1;
  const endY = place(0, 1, 0).depth > place(0, -1, 0).depth ? 1 : -1;
  for (let i = 0; i <= STEPS; i++) {
    const t = (i / STEPS) * 2 - 1;
    const z = low + ((top - low) * i) / STEPS;
    line(place(sideX, t, low), place(sideX, t, top), i % STEPS ? grid : edge);
    line(place(sideX, -1, z), place(sideX, 1, z), grid);
    line(place(t, endY, low), place(t, endY, top), i % STEPS ? grid : edge);
    line(place(-1, endY, z), place(1, endY, z), grid);
  }
  // values: X along the front edge, Y along the near side, Z up the corner between the walls
  ctx.fillStyle = "rgba(255,255,255,0.62)";
  ctx.font = "500 10px system-ui, sans-serif";
  ctx.textAlign = "center";
  const area = stats.area;
  const nearY = -endY;
  const nearX = -sideX;
  for (let i = 0; i <= STEPS; i += 2) {
    const t = (i / STEPS) * 2 - 1;
    const xValue = area ? area.min[0] + ((area.max[0] - area.min[0]) * i) / STEPS : null;
    const yValue = area ? area.min[1] + ((area.max[1] - area.min[1]) * i) / STEPS : null;
    const px = place(t, nearY * 1.14, low);
    const py = place(nearX * 1.14, t, low);
    if (xValue !== null) ctx.fillText(Math.round(xValue), px.x, px.y + 4);
    if (yValue !== null) ctx.fillText(Math.round(yValue), py.x, py.y + 4);
  }
  const xLabel = place(0, nearY * 1.32, low);
  const yLabel = place(nearX * 1.32, 0, low);
  ctx.font = "700 11px system-ui, sans-serif";
  ctx.fillStyle = "#ff8a8a";
  ctx.fillText("X", xLabel.x, xLabel.y + 4);
  ctx.fillStyle = "#7ee2a0";
  ctx.fillText("Y", yLabel.x, yLabel.y + 4);
  ctx.textAlign = "start";
}

/** The Z values on the back corner, written after the surface so it cannot cover them. */
function drawZValues(ctx, { place, heightScale, mid }, stats) {
  const sideX = place(1, 0, 0).depth > place(-1, 0, 0).depth ? 1 : -1;
  const endY = place(0, 1, 0).depth > place(0, -1, 0).depth ? 1 : -1;
  ctx.font = "500 10px system-ui, sans-serif";
  ctx.fillStyle = "rgba(255,255,255,0.7)";
  ctx.textAlign = "right";
  for (const value of [stats.min, stats.max]) {
    const p = place(sideX, endY, (value - mid) * heightScale);
    ctx.fillText((value > 0 ? "+" : "") + value.toFixed(3), p.x - 6, p.y + 3);
  }
  ctx.textAlign = "start";
}

/** The surface: every cell split in small quads, each in the colour of its own height (bilinear), far ones first. */
function drawSurface(ctx, { project }, stats, heightAt) {
  const cells = Math.max(1, (stats.cols - 1) * (stats.rows - 1));
  const split = clamp(Math.round(Math.sqrt(MESH_SURFACE_PIECES / cells)), 1, 10);
  const pieces = [];
  for (let row = 0; row < stats.rows - 1; row++) {
    for (let column = 0; column < stats.cols - 1; column++) {
      const [z00, z10, z01, z11] = [heightAt(row, column), heightAt(row, column + 1), heightAt(row + 1, column), heightAt(row + 1, column + 1)];
      const at = (a, b) => z00 * (1 - a) * (1 - b) + z10 * a * (1 - b) + z01 * (1 - a) * b + z11 * a * b;
      for (let j = 0; j < split; j++) {
        for (let i = 0; i < split; i++) {
          const [a0, a1, b0, b1] = [i / split, (i + 1) / split, j / split, (j + 1) / split];
          const corners = [project(column + a0, row + b0, at(a0, b0)), project(column + a1, row + b0, at(a1, b0)), project(column + a1, row + b1, at(a1, b1)), project(column + a0, row + b1, at(a0, b1))];
          pieces.push({ corners, value: at((a0 + a1) / 2, (b0 + b1) / 2), depth: (corners[0].depth + corners[1].depth + corners[2].depth + corners[3].depth) / 4 });
        }
      }
    }
  }
  pieces.sort((a, b) => b.depth - a.depth);
  ctx.lineWidth = 0.6;
  ctx.lineJoin = "round";
  for (const piece of pieces) {
    const color = heightColor(piece.value, stats);
    drawPath(ctx, piece.corners);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = color; // closes the hairline seams between the pieces
    ctx.stroke();
  }
  // the mesh lines, faint, along the rows and columns Klipper measured
  ctx.strokeStyle = "rgba(0,0,0,0.22)";
  ctx.lineWidth = 0.7;
  for (let row = 0; row < stats.rows; row++) {
    drawPath(ctx, Array.from({ length: stats.cols }, (_, column) => project(column, row, heightAt(row, column))));
    ctx.stroke();
  }
  for (let column = 0; column < stats.cols; column++) {
    drawPath(ctx, Array.from({ length: stats.rows }, (_, row) => project(column, row, heightAt(row, column))));
    ctx.stroke();
  }
}

/** A white dot at the front-left point (0,0 of the mesh). */
function drawOrigin(ctx, { project }, stats, heightAt) {
  const origin = project(0, 0, heightAt(0, 0));
  [
    ["#ffffff", 4.5],
    ["#000000", 1.8],
  ].forEach(([color, radius]) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(origin.x, origin.y, radius, 0, Math.PI * 2);
    ctx.fill();
  });
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
  drawZValues(ctx, projector, stats);
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
              style: { background: heightColor(value, stats), color: meshTextColor(value, stats) },
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
    { cardId: "bedmesh", className: "mesh-card" },
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
