/* ============================================================================
   49a · G-CODE VIEWER (1.49, roadmap 6d part 8)
   A file seen layer by layer, from above, in 2D:
     · the file is read in pieces (a bar says how far), every move parsed:
       absolute / relative moves and extrusion, G92, arcs (G2 / G3) as short
       lines, the slicer's ;TYPE: comments for what each line is;
     · the layer chosen with a slider (or ‹ ›): its lines coloured by what they
       are (outer and inner walls, infill, top / bottom, support, skirt…), the
       layer under it in grey, the travels on request; a tap on a kind in the
       legend hides it; pinch / wheel to zoom, drag to move;
     · while that file prints, "Follow the print" shows the layer at the
       nozzle, what is printed of it and what is still to print, and the nozzle.
   ========================================================================== */

const GCODE_VIEW_MAX_BYTES = 120 * 1024 * 1024;
const GCODE_VIEW_YIELD_LINES = 40000; // lines parsed between two breaths of the page
const GCODE_VIEW_FOLLOW_MS = 1500;
const GCODE_ARC_SEGMENT_MM = 1;

/** What a line is, from the slicer's comments (PrusaSlicer / OrcaSlicer / SuperSlicer ;TYPE:, Cura ;TYPE: too). */
const GCODE_KINDS = [
  { id: "outer", color: "#d95926", match: /outer|external perimeter|wall-outer/i },
  { id: "inner", color: "#c98500", match: /inner|perimeter|wall/i },
  { id: "solid", color: "#d55181", match: /solid|top|bottom|skin|ironing/i },
  { id: "infill", color: "#e66767", match: /infill|fill|gap/i },
  { id: "bridge", color: "#3987e5", match: /bridge/i },
  { id: "support", color: "#199e70", match: /support/i },
  { id: "skirt", color: "#9085e9", match: /skirt|brim|prime|purge|wipe/i },
  { id: "other", color: "#8e94a3", match: /./ },
];
const GCODE_KIND_INDEX = Object.fromEntries(GCODE_KINDS.map((kind, index) => [kind.id, index]));
const TRAVEL = 255;

const gcodeKindLabel = (id) =>
  ({
    outer: tx("Outer wall"),
    inner: tx("Inner wall"),
    solid: tx("Top / bottom"),
    infill: tx("Infill"),
    bridge: tx("Bridge"),
    support: tx("Support"),
    skirt: tx("Skirt / brim"),
    other: tx("Other"),
  })[id];

function gcodeKindOf(text) {
  const order = ["bridge", "support", "skirt", "outer", "solid", "infill", "inner", "other"]; // the specific ones first
  for (const id of order) if (GCODE_KINDS[GCODE_KIND_INDEX[id]].match.test(text)) return GCODE_KIND_INDEX[id];
  return GCODE_KIND_INDEX.other;
}

/* ---------------------------------------------------------------------------
   Parsing
   ------------------------------------------------------------------------- */
/** Growing typed arrays for the segments: x1 y1 x2 y2, kind, file offset. */
function segmentStore() {
  let size = 0;
  let capacity = 65536;
  let coords = new Float32Array(capacity * 4);
  let kinds = new Uint8Array(capacity);
  let offsets = new Uint32Array(capacity);
  return {
    get size() {
      return size;
    },
    push(x1, y1, x2, y2, kind, offset) {
      if (size === capacity) {
        capacity *= 2;
        const grow = (old, Type, per) => {
          const next = new Type(capacity * per);
          next.set(old);
          return next;
        };
        coords = grow(coords, Float32Array, 4);
        kinds = grow(kinds, Uint8Array, 1);
        offsets = grow(offsets, Uint32Array, 1);
      }
      const at = size * 4;
      coords[at] = x1;
      coords[at + 1] = y1;
      coords[at + 2] = x2;
      coords[at + 3] = y2;
      kinds[size] = kind;
      offsets[size] = offset;
      size++;
    },
    finish: () => ({ coords: coords.subarray(0, size * 4), kinds: kinds.subarray(0, size), offsets: offsets.subarray(0, size), size }),
  };
}

/**
 * The parser: feed it lines (with the byte offset where each starts), read the result at the end:
 * { segments, layers: [{ z, start, end, offset }], bounds: { minX, minY, maxX, maxY } }.
 * A layer starts at the first extrusion at a new height; the travels before it belong to it.
 * 1.63: when the slicer marks its layers (;LAYER_CHANGE of PrusaSlicer / OrcaSlicer / SuperSlicer, ;LAYER:n of Cura) a
 * layer starts only there: in vase mode (and with a lift in spiral) the height rises a little at every move, and every
 * move became a "layer" (thousands of them, each with a few millimetres of line). Without marks, a new layer needs the
 * height to rise by more than LAYER_MIN_RISE, or to come down.
 */
const GCODE_LAYER_MIN_RISE = 0.02;
function gcodeParser() {
  const segments = segmentStore();
  const layers = [];
  const state = { x: 0, y: 0, z: 0, e: 0, absolute: true, absoluteE: true, kind: GCODE_KIND_INDEX.other };
  const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  let layer = null;
  let marked = false; // the slicer marks its layers
  let markPending = false; // a mark was met: the next extrusion starts a layer
  let pendingTravels = []; // travels since the last extrusion, given to the layer of the next one
  const extend = (x, y) => {
    if (x < bounds.minX) bounds.minX = x;
    if (x > bounds.maxX) bounds.maxX = x;
    if (y < bounds.minY) bounds.minY = y;
    if (y > bounds.maxY) bounds.maxY = y;
  };
  const line = (x1, y1, x2, y2, extruding, offset) => {
    if (!extruding) return pendingTravels.push([x1, y1, x2, y2, offset]);
    const newLayer = !layer || (marked ? markPending : state.z > layer.z + GCODE_LAYER_MIN_RISE || state.z < layer.z - 0.0001);
    if (newLayer) {
      markPending = false;
      if (layer) layer.end = segments.size;
      layer = { z: state.z, start: segments.size, end: segments.size, offset };
      layers.push(layer);
    }
    for (const travel of pendingTravels) segments.push(travel[0], travel[1], travel[2], travel[3], TRAVEL, travel[4]);
    pendingTravels = [];
    segments.push(x1, y1, x2, y2, state.kind, offset);
    extend(x1, y1);
    extend(x2, y2);
  };
  const number = (words, letter) => {
    const word = words[letter];
    return word === undefined ? undefined : parseFloat(word);
  };
  const move = (words, offset, arc) => {
    const at = (letter, current) => {
      const value = number(words, letter);
      return value === undefined || isNaN(value) ? current : state.absolute ? value : current + value;
    };
    const x = at("X", state.x);
    const y = at("Y", state.y);
    const z = at("Z", state.z);
    let extruding = false;
    const e = number(words, "E");
    if (e !== undefined && !isNaN(e)) {
      extruding = state.absoluteE ? e > state.e + 1e-6 : e > 1e-6;
      state.e = state.absoluteE ? e : state.e + e;
    }
    state.z = z;
    if (x === state.x && y === state.y) return;
    if (arc) {
      const i = number(words, "I") || 0;
      const j = number(words, "J") || 0;
      const cx = state.x + i;
      const cy = state.y + j;
      const radius = Math.hypot(i, j);
      let start = Math.atan2(state.y - cy, state.x - cx);
      let end = Math.atan2(y - cy, x - cx);
      if (arc === "G2" && end >= start) end -= 2 * Math.PI;
      if (arc === "G3" && end <= start) end += 2 * Math.PI;
      const steps = Math.max(2, Math.min(64, Math.ceil((Math.abs(end - start) * radius) / GCODE_ARC_SEGMENT_MM)));
      let px = state.x;
      let py = state.y;
      for (let step = 1; step <= steps; step++) {
        const angle = start + ((end - start) * step) / steps;
        const nx = step === steps ? x : cx + radius * Math.cos(angle);
        const ny = step === steps ? y : cy + radius * Math.sin(angle);
        line(px, py, nx, ny, extruding, offset);
        px = nx;
        py = ny;
      }
    } else line(state.x, state.y, x, y, extruding, offset);
    state.x = x;
    state.y = y;
  };
  return {
    feed(text, offset) {
      const semicolon = text.indexOf(";");
      if (semicolon !== -1) {
        const comment = text.slice(semicolon + 1).trim();
        if (/^TYPE:/i.test(comment)) state.kind = gcodeKindOf(comment.slice(5));
        else if (/^LAYER_CHANGE\b/i.test(comment) || /^LAYER:\s*-?\d+/i.test(comment)) {
          marked = true;
          markPending = true;
        }
        else if (/^FEATURE:/i.test(comment)) state.kind = gcodeKindOf(comment.slice(8));
        text = text.slice(0, semicolon);
      }
      const parts = text.trim().split(/\s+/);
      const command = parts[0] ? parts[0].toUpperCase() : "";
      if (!command) return;
      const words = {};
      for (let index = 1; index < parts.length; index++) {
        const part = parts[index];
        if (part) words[part.charAt(0).toUpperCase()] = part.slice(1);
      }
      if (command === "G1" || command === "G0") move(words, offset, null);
      else if (command === "G2" || command === "G3") move(words, offset, command);
      else if (command === "G90") state.absolute = true;
      else if (command === "G91") state.absolute = false;
      else if (command === "M82") state.absoluteE = true;
      else if (command === "M83") state.absoluteE = false;
      else if (command === "G92") {
        if (words.E !== undefined) state.e = parseFloat(words.E) || 0;
        if (words.X !== undefined) state.x = parseFloat(words.X) || 0;
        if (words.Y !== undefined) state.y = parseFloat(words.Y) || 0;
        if (words.Z !== undefined) state.z = parseFloat(words.Z) || 0;
      } else if (command === "G28") {
        state.x = 0;
        state.y = 0;
      }
    },
    result() {
      if (layer) layer.end = segments.size;
      return { segments: segments.finish(), layers, bounds: isFinite(bounds.minX) ? bounds : { minX: 0, minY: 0, maxX: 100, maxY: 100 } };
    },
  };
}

/** Reads `path` and parses it, a piece at a time: `onProgress(fraction)`; resolves the parser's result. `signal` stops it. */
async function loadGcodeModel(path, onProgress, signal) {
  const response = await fetchFresh("/server/files/" + GCODES_ROOT + "/" + encodeRemotePath(path), { timeout: 0, signal });
  if (!response.ok) throw new Error(await responseError(response));
  const total = Number(response.headers.get("Content-Length")) || 0;
  if (total > GCODE_VIEW_MAX_BYTES) throw new Error(tx("The file is too big to be drawn here ({size}).", { size: formatBytes(total) }));
  const parser = gcodeParser();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let rest = "";
  let restOffset = 0;
  let received = 0;
  let lines = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (signal && signal.aborted) throw new DOMException("aborted", "AbortError");
    if (value) received += value.length;
    const text = rest + (value ? decoder.decode(value, { stream: !done }) : "");
    let start = 0;
    let offset = restOffset;
    for (let end = text.indexOf("\n", start); end !== -1; end = text.indexOf("\n", start)) {
      const piece = text.slice(start, end);
      parser.feed(piece, offset);
      offset += piece.length + 1; // close enough to the byte offset for G-code (ASCII)
      start = end + 1;
      if (++lines % GCODE_VIEW_YIELD_LINES === 0) {
        onProgress(total ? received / total : 0);
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    }
    rest = text.slice(start);
    restOffset = offset;
    if (done) break;
  }
  if (rest) parser.feed(rest, restOffset);
  onProgress(1);
  return parser.result();
}

/* ---------------------------------------------------------------------------
   Drawing
   ------------------------------------------------------------------------- */
function drawGcodeLayer(canvas, model, view) {
  const context = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  const { bounds, layers, segments } = model;
  const spanX = Math.max(1, bounds.maxX - bounds.minX);
  const spanY = Math.max(1, bounds.maxY - bounds.minY);
  const fit = Math.min((width - 32) / spanX, (height - 32) / spanY);
  const scale = fit * view.zoom;
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  // Y up, as the printer sees it
  const px = (x) => width / 2 + (x - cx) * scale + view.panX;
  const py = (y) => height / 2 - (y - cy) * scale + view.panY;

  // a 10 mm grid, recessive
  context.strokeStyle = "rgba(255,255,255,0.05)";
  context.lineWidth = 1;
  const step = scale * 10 < 12 ? 50 : 10;
  const firstX = Math.floor((cx - width / 2 / scale - view.panX / scale) / step) * step;
  const firstY = Math.floor((cy - height / 2 / scale + view.panY / scale) / step) * step;
  context.beginPath();
  for (let x = firstX; px(x) < width; x += step) {
    context.moveTo(Math.round(px(x)) + 0.5, 0);
    context.lineTo(Math.round(px(x)) + 0.5, height);
  }
  for (let y = firstY; py(y) > 0; y += step) {
    context.moveTo(0, Math.round(py(y)) + 0.5);
    context.lineTo(width, Math.round(py(y)) + 0.5);
  }
  context.stroke();

  const layer = layers[view.layer];
  if (!layer) return;
  const { coords, kinds, offsets } = segments;
  const width2 = Math.max(1, Math.min(4, scale * 0.42)); // about a 0.4 mm line
  const stroke = (from, to, test, color, lineWidth, alpha) => {
    context.globalAlpha = alpha;
    context.strokeStyle = color;
    context.lineWidth = lineWidth;
    context.beginPath();
    for (let i = from; i < to; i++) {
      if (!test(i)) continue;
      context.moveTo(px(coords[i * 4]), py(coords[i * 4 + 1]));
      context.lineTo(px(coords[i * 4 + 2]), py(coords[i * 4 + 3]));
    }
    context.stroke();
  };
  context.lineCap = "round";
  context.lineJoin = "round";
  // the layer under it, grey
  const below = layers[view.layer - 1];
  if (below && view.showBelow) stroke(below.start, below.end, (i) => kinds[i] !== TRAVEL, "#5d6371", width2, 0.45);
  // what is still to print (following a print): dim
  const printedUpTo = view.followOffset !== null && view.followOffset !== undefined ? view.followOffset : Infinity;
  for (let kind = 0; kind < GCODE_KINDS.length; kind++) {
    if (view.hidden.includes(GCODE_KINDS[kind].id)) continue;
    stroke(layer.start, layer.end, (i) => kinds[i] === kind && offsets[i] <= printedUpTo, GCODE_KINDS[kind].color, width2, 1);
    if (printedUpTo !== Infinity) stroke(layer.start, layer.end, (i) => kinds[i] === kind && offsets[i] > printedUpTo, GCODE_KINDS[kind].color, width2, 0.18);
  }
  if (view.showTravels) {
    context.setLineDash([3, 3]);
    stroke(layer.start, layer.end, (i) => kinds[i] === TRAVEL, "#9aa0ad", 1, 0.6);
    context.setLineDash([]);
  }
  context.globalAlpha = 1;
  // the nozzle
  if (view.nozzle) {
    context.fillStyle = "#ffffff";
    context.strokeStyle = "#000000";
    context.lineWidth = 2;
    context.beginPath();
    context.arc(px(view.nozzle[0]), py(view.nozzle[1]), 6, 0, Math.PI * 2);
    context.fill();
    context.stroke();
  }
}

/** The layer and the point of the file at `offset` (the printer's file_position). */
function gcodeAtOffset(model, offset) {
  const { layers, segments } = model;
  let index = 0;
  for (let i = 0; i < layers.length; i++) if (layers[i].offset <= offset) index = i;
  const layer = layers[index];
  let last = null;
  for (let i = layer ? layer.start : 0; layer && i < layer.end; i++) if (segments.offsets[i] <= offset) last = i;
  return { layer: index, nozzle: last === null ? null : [segments.coords[last * 4 + 2], segments.coords[last * 4 + 3]] };
}

/* ---------------------------------------------------------------------------
   The viewer
   ------------------------------------------------------------------------- */
function GcodeViewer({ path, onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const [model, setModel] = useState(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [layer, setLayer] = useState(0);
  const [hidden, setHidden] = useState([]);
  const [showTravels, setShowTravels] = useState(false);
  const [showBelow, setShowBelow] = useState(true);
  const [follow, setFollow] = useState(false);
  const [printing, setPrinting] = useState(null); // { offset } while this very file prints
  const [zoom, setZoom] = useState({ zoom: 1, panX: 0, panY: 0 });
  const canvasRef = useRef(null);
  const pointers = useRef(new Map());
  const gesture = useRef(null);
  const name = path.split("/").pop();

  useEffect(() => {
    const onKey = (event) => {
      if (event.target && event.target.type === "range" && event.key !== "Escape") return; // the slider moves by itself
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowUp" || event.key === "ArrowRight") setLayer((value) => value + 1);
      else if (event.key === "ArrowDown" || event.key === "ArrowLeft") setLayer((value) => Math.max(0, value - 1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadGcodeModel(path, setProgress, controller.signal)
      .then((result) => {
        setModel(result);
        setLayer(Math.max(0, result.layers.length - 1));
      })
      .catch((failure) => failure.name !== "AbortError" && setError(failure.message || tx("Error")));
    return () => controller.abort();
  }, [path]);

  // is this file printing? then the viewer can follow it
  useEffect(() => {
    if (!model) return undefined;
    let first = true;
    const read = async () => {
      const status = await moonraker.queryObjects("print_stats=state,filename&virtual_sdcard=file_position,file_path");
      const stats = status.print_stats || {};
      const mine = ["printing", "paused"].includes(stats.state) && stats.filename === path;
      setPrinting(mine ? { offset: Number((status.virtual_sdcard || {}).file_position) || 0 } : null);
      if (first && mine) setFollow(true);
      first = false;
    };
    return startPolling(read, GCODE_VIEW_FOLLOW_MS);
  }, [model]);

  const count = model ? model.layers.length : 0;
  const shownLayer = Math.min(layer, Math.max(0, count - 1));
  const at = model && follow && printing ? gcodeAtOffset(model, printing.offset) : null;
  const current = at ? at.layer : shownLayer;
  useEffect(() => {
    if (at && at.layer !== layer) setLayer(at.layer);
  }, [at && at.layer]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !model) return undefined;
    const draw = () => drawGcodeLayer(canvas, model, { layer: current, hidden, showTravels, showBelow, followOffset: at ? printing.offset : null, nozzle: at ? at.nozzle : null, ...zoom });
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  });

  /* zoom and move: the wheel, a drag, two fingers */
  const onWheel = (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
    setZoom((value) => ({ ...value, zoom: Math.max(0.5, Math.min(40, value.zoom * factor)) }));
  };
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [model]);
  const onPointerDown = (event) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, [event.clientX, event.clientY]);
    gesture.current = null;
  };
  const onPointerMove = (event) => {
    const previous = pointers.current.get(event.pointerId);
    if (!previous) return;
    pointers.current.set(event.pointerId, [event.clientX, event.clientY]);
    const points = [...pointers.current.values()];
    if (points.length === 2) {
      const distance = Math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1]);
      if (gesture.current) setZoom((value) => ({ ...value, zoom: Math.max(0.5, Math.min(40, value.zoom * (distance / gesture.current))) }));
      gesture.current = distance;
    } else setZoom((value) => ({ ...value, panX: value.panX + event.clientX - previous[0], panY: value.panY + event.clientY - previous[1] }));
  };
  const onPointerUp = (event) => {
    pointers.current.delete(event.pointerId);
    gesture.current = null;
  };

  const layerInfo = model && model.layers[current];
  const toggleKind = (id) => setHidden((list) => (list.includes(id) ? list.filter((one) => one !== id) : list.concat(id)));
  const present = model ? GCODE_KINDS.filter((kind, index) => model.segments.kinds.some((value) => value === index)) : [];
  return h(
    "div",
    { className: "screen screen--viewer gcode-viewer", role: "dialog", "aria-label": tx("Layers of {name}", { name }) },
    h(
      "div",
      { className: "screen-bar viewer-bar" },
      h("span", { className: "viewer-title" }, name),
      printing && h("button", { type: "button", className: cx("oui-chip gcode-follow", follow && "is-selected"), "aria-pressed": follow, onClick: () => setFollow(!follow) }, h("span", { className: "oui-dot gcode-follow__dot" }), tx("Follow the print")),
      h("button", { className: "oui-btn oui-btn--icon", "aria-label": tx("Close"), onClick: onClose }, "✕"),
    ),
    h(
      "div",
      { className: "gcode-stage" },
      !model && !error && h("div", { className: "gcode-loading" }, h("div", { className: "oui-caption" }, tx("Reading the file… {percent}%", { percent: Math.round(progress * 100) })), h("div", { className: "gcode-loading__bar" }, h("span", { style: { width: progress * 100 + "%" } }))),
      error && h("div", { className: "oui-tile oui-tile--danger gcode-error" }, error),
      model && count === 0 && h("div", { className: "oui-caption gcode-error" }, tx("No extrusion in this file: nothing to draw.")),
      model && count > 0 && h("canvas", { ref: canvasRef, className: "gcode-canvas", "data-layer": current, "data-layers": count, onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp, onDoubleClick: () => setZoom({ zoom: 1, panX: 0, panY: 0 }) }),
    ),
    model &&
      count > 0 &&
      h(
        "div",
        { className: "screen-bar gcode-controls" },
        h(
          "div",
          { className: "gcode-layer" },
          h("button", { type: "button", className: "oui-btn oui-btn--icon", "aria-label": tx("Layer below"), disabled: current === 0, onClick: () => (setFollow(false), setLayer(Math.max(0, current - 1))) }, "‹"),
          h("input", { type: "range", className: "gcode-layer__range", min: 0, max: count - 1, step: 1, value: current, "aria-label": tx("Layer"), onChange: (event) => (setFollow(false), setLayer(Number(event.target.value))) }),
          h("button", { type: "button", className: "oui-btn oui-btn--icon", "aria-label": tx("Layer above"), disabled: current >= count - 1, onClick: () => (setFollow(false), setLayer(Math.min(count - 1, current + 1))) }, "›"),
          h("span", { className: "gcode-layer__label" }, tx("Layer {layer} / {count}", { layer: current + 1, count }), layerInfo ? " · Z " + Number(layerInfo.z.toFixed(2)) + " mm" : ""),
        ),
        h(
          "div",
          { className: "gcode-legend" },
          present.map((kind) =>
            h("button", { key: kind.id, type: "button", className: cx("gcode-legend__item", hidden.includes(kind.id) && "is-off"), "aria-pressed": !hidden.includes(kind.id), "data-kind": kind.id, onClick: () => toggleKind(kind.id) }, h("span", { className: "gcode-legend__key", style: { background: kind.color } }), gcodeKindLabel(kind.id)),
          ),
          h("button", { type: "button", className: cx("gcode-legend__item gcode-travels", !showTravels && "is-off"), "aria-pressed": showTravels, onClick: () => setShowTravels(!showTravels) }, h("span", { className: "gcode-legend__key gcode-legend__key--dash" }), tx("Travels")),
          h("button", { type: "button", className: cx("gcode-legend__item gcode-below", !showBelow && "is-off"), "aria-pressed": showBelow, onClick: () => setShowBelow(!showBelow) }, h("span", { className: "gcode-legend__key", style: { background: "#5d6371" } }), tx("Layer below")),
        ),
      ),
  );
}

/** The viewer's layer: one file at a time, opened from anywhere (the file menu, the computer's file panel, the print card). */
const gcodeViewerStore = (() => {
  const listeners = new Set();
  let path = null;
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => path,
    open(next) {
      path = next;
      listeners.forEach((fn) => fn());
    },
    close() {
      path = null;
      listeners.forEach((fn) => fn());
    },
  };
})();

function GcodeViewerLayer() {
  const path = useSyncExternalStore(gcodeViewerStore.subscribe, gcodeViewerStore.snapshot);
  return h(Presence, null, path && h(GcodeViewer, { key: path, path, onClose: gcodeViewerStore.close }));
}

/** On the print card: the layers of the file printing, following the nozzle. */
function GcodeViewButton({ status }) {
  const path = status.filePath || status.filename;
  if (!path || path === "-") return null;
  return h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--block gcode-view-btn", onClick: () => gcodeViewerStore.open(path) }, h(Icons.Layers, { size: 16 }), tx("See the layers"));
}
