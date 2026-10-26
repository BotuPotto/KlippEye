/* ============================================================================
   58 · BED MESH
   Shows Klipper's bed-leveling map (`bed_mesh` object) either as a coloured
   2D grid or as a 3D surface drawn on a canvas that can be rotated (drag) and
   zoomed (wheel or pinch). Buttons: Homing (G28) and CALIBRA MESH.
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

/** The probed heights and their statistics, or null while there is no mesh. */
function analyzeMesh(mesh) {
  const matrix = mesh && (mesh.probed_matrix || mesh.mesh_matrix);
  if (!matrix || matrix.length === 0 || matrix[0].length === 0) return null;
  const values = matrix.flat();
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { matrix, rows: matrix.length, cols: matrix[0].length, min, max, range: max - min, mean: values.reduce((sum, value) => sum + value, 0) / values.length };
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
  const baseScale = Math.min(width, height) * 0.135 * view.zoom;
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
  ctx.fillText("Origine (0,0)", origin.x - 10, origin.y + 20);
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
  // The matrix lists the back row first; the view works from the front (row 0 = Y min).
  const heightAt = (row, column) => stats.matrix[stats.rows - 1 - row][column];
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
function ViewToggle({ mode, onChange }) {
  const button = (id, label) => h("button", { onClick: () => onChange(id), className: mode === id ? "is-selected" : "" }, label);
  return h("div", { className: "oui-segmented" }, button("2d", "2D"), button("3d", "3D"));
}

/** Colour scale legend (low → high) + height variation shown under both views. */
function MeshLegend({ stats }) {
  return h(
    "div",
    { className: "mesh-legend" },
    h("span", null, stats.min.toFixed(3)),
    h("span", { className: "mesh-legend__scale" }),
    h("span", null, stats.max.toFixed(3)),
    h("span", { className: "mesh-legend__var" }, "var " + stats.range.toFixed(4) + " mm"),
  );
}

function MeshGrid({ stats }) {
  return h(
    "div",
    { className: "mesh-well oui-well" },
    h(
      "div",
      { className: "mesh-grid", style: { gridTemplateColumns: "repeat(" + stats.cols + ", minmax(0,1fr))" } },
      stats.matrix.map((row, rowIndex) => row.map((value, columnIndex) => h("div", { key: rowIndex + "-" + columnIndex, className: "mesh-cell", style: { background: heightColor(value, stats) } }))),
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

  return h("div", { className: "mesh-well oui-well" }, h("canvas", { ref: canvasRef, className: "mesh-canvas" }), h(MeshLegend, { stats }));
}

/** `onGcode(script)` sends G-code; confirmations are shown as toasts. */
function BedMeshCard({ onGcode }) {
  const { mesh, loading } = useBedMesh();
  const [viewMode, setViewMode] = useState("3d");
  const stats = useMemo(() => analyzeMesh(mesh), [mesh]);
  const send = (script, message) => {
    onGcode(script);
    toast.action(message);
  };

  return h(
    Card,
    null,
    h(CardHeader, { title: "Mappa dell'altezza / mesh" }),
    h(
      "div",
      { className: "mesh-toolbar" },
      h(ViewToggle, { mode: viewMode, onChange: setViewMode }),
      h("span", { className: "oui-badge mesh-profile" }, (mesh && mesh.profile_name) || "nessuna"),
      h(
        "button",
        { onClick: () => send("G28", "Homing G28"), className: "icon-btn", title: "Homing G28", "aria-label": "Homing G28" },
        h("svg", { viewBox: "0 0 24 24", width: 16, height: 16, fill: "currentColor" }, h("path", { d: "M12 2L2 12h3v8h6v-6h2v6h6v-8h3L12 2z" })),
      ),
    ),
    !stats
      ? h("div", { className: "mesh-well oui-well mesh-empty" }, loading ? "Caricamento..." : "Nessuna mesh")
      : viewMode === "2d"
        ? h(MeshGrid, { stats })
        : h(MeshSurface, { stats }),
    h("div", { className: "mt-4" }, h("button", { onClick: () => send("BED_MESH_CALIBRATE", "CALIBRA"), className: "oui-btn oui-btn--primary oui-btn--block" }, "Calibra mesh")),
  );
}
