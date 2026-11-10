/* ============================================================================
   57b · INPUT SHAPER GRAPHS (1.80, redrawn in 1.89)
   What Klipper's resonance measurement (SHAPER_CALIBRATE, with an accelerometer)
   found, drawn as an axis frequency profile: the vibrations at each frequency
   (all axes together and each one), what is left with the two recommended
   shapers, the two bands (below the green one the vibrations do not matter,
   above the orange one they show in the prints), the peaks, and each shaper's
   response (dotted, 0 to 100 % on the right). Under it the recommendations and
   a table with each shaper's frequency, vibrations, smoothing and highest
   acceleration (backend/shaper_data.py computes them as Klipper does).
   «Measure X/Y» each have their settings (empty: Klipper's own); «Save» writes
   the chosen shaper in the printer's config and applies it at once.
   The files are the ones Klipper leaves in /tmp: they go away when the
   Raspberry restarts.
   ========================================================================== */

const SHAPER_CHART_HEIGHT = 260;
const SHAPER_PAD = { left: 40, right: 40, top: 14, bottom: 24 };
const SHAPER_POLL_MS = 15000;
const SHAPER_COLORS = { zv: "#3987e5", mzv: "#c98500", zvd: "#9085e9", ei: "#d55181", "2hump_ei": "#199e70", "3hump_ei": "#d95926" };
const SHAPER_PSD_COLORS = { sum: "#8a5cd1", x: "#e5484d", y: "#2f9e44", z: "#3b82f6" };
const SHAPER_AFTER_COLORS = ["#22c55e", "#06b6d4"];
const SHAPER_NAMES = { zv: "ZV", mzv: "MZV", zvd: "ZVD", ei: "EI", "2hump_ei": "2HUMP_EI", "3hump_ei": "3HUMP_EI" };
const SHAPER_PARAMS_KEY = "ke_shaper_params";
const SHAPER_CONFIG_FILE = "printer.cfg";
const SHAPER_AUTOSAVE_MARK = /^#\*#\s*<-+\s*SAVE_CONFIG\s*-+>/;

const shaperName = (name) => SHAPER_NAMES[name] || String(name || "").toUpperCase();
const shaperColor = (name) => SHAPER_COLORS[name] || "#7c8594";
const formatHz = (value) => (Math.round(value * 10) / 10).toLocaleString(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " Hz";
const shaperNumber = (value, digits) => Number(value).toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });
const SUPERSCRIPT = { "-": "⁻", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" };
const superscript = (n) => String(n).split("").map((c) => SUPERSCRIPT[c] || c).join("");

/** The settings of a measurement, Klipper's names: empty ones are not sent (Klipper uses [resonance_tester]'s or its own). */
const SHAPER_MEASURE_FIELDS = [
  { key: "FREQ_START", label: () => tx("Start frequency"), unit: "Hz", fallback: (d) => d.freq_start },
  { key: "FREQ_END", label: () => tx("End frequency"), unit: "Hz", fallback: (d) => d.freq_end },
  { key: "HZ_PER_SEC", label: () => tx("Sweep speed"), unit: "Hz/s", fallback: (d) => d.hz_per_sec },
  { key: "ACCEL_PER_HZ", label: () => tx("Acceleration per Hz"), unit: "mm/s²/Hz", fallback: (d) => d.accel_per_hz },
  { key: "MAX_SMOOTHING", label: () => tx("Max smoothing"), unit: "", fallback: (d) => d.max_smoothing },
];

/** A setting's value as typed: a number above zero, the end above the start; null when empty, false when not valid. */
function shaperParamValue(params, key, defaults) {
  const raw = String((params || {})[key] || "")
    .trim()
    .replace(",", ".");
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) return false;
  if (key === "FREQ_END" || key === "FREQ_START") {
    const start = key === "FREQ_START" ? value : Number(String((params || {}).FREQ_START || "").replace(",", ".")) || defaults.freq_start;
    const end = key === "FREQ_END" ? value : Number(String((params || {}).FREQ_END || "").replace(",", ".")) || defaults.freq_end;
    if (start && end && end <= start) return false;
  }
  return value;
}

/** The command for a measurement of `axis` with the settings typed (the valid ones). */
function shaperMeasureCommand(axis, params, defaults) {
  const extra = SHAPER_MEASURE_FIELDS.map((field) => [field.key, shaperParamValue(params, field.key, defaults)])
    .filter(([, value]) => typeof value === "number")
    .map(([key, value]) => key + "=" + value);
  return ["SHAPER_CALIBRATE AXIS=" + axis.toUpperCase()].concat(extra).join(" ");
}

/** The measurement files, newest first; null while not read yet. */
function useShaperFiles() {
  const [files, setFiles] = useState(null);
  const [error, setError] = useState(null);
  const load = async () => {
    try {
      const response = await fetchFresh("/api/shaper/files");
      if (!response.ok) throw new Error(await responseError(response));
      const list = (await response.json()).files || [];
      setFiles((previous) => (JSON.stringify(previous) === JSON.stringify(list) ? previous : list));
      setError(null);
    } catch (problem) {
      setError(problem.message || String(problem));
      setFiles((previous) => previous || []);
    }
  };
  useEffect(() => startPolling(load, SHAPER_POLL_MS), []);
  return { files, error, reload: load };
}

function useShaperData(name, query) {
  const key = name ? name + query : null;
  const [state, setState] = useState({ key: null, data: null, error: null });
  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetchFresh("/api/shaper/data?name=" + encodeURIComponent(name) + query);
        if (!response.ok) throw new Error(await responseError(response));
        const data = await response.json();
        if (!cancelled) setState({ key, data, error: null });
      } catch (problem) {
        if (!cancelled) setState({ key, data: null, error: problem.message || String(problem) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [key]);
  return state.key === key ? state : { key, data: null, error: null };
}

/** The measurement's date, from the file's own name (calibration_data_x_20261109_221500.csv) or its time. */
function shaperFileDate(file) {
  const match = /_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.csv$/i.exec(file.name || "");
  const date = match ? new Date(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +match[6]) : new Date((file.modified || 0) * 1000);
  return date.toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/* ---- writing the shaper in the config ------------------------------------------------------------------------ */

/**
 * Writes `values` in the [input_shaper] found between lines `from` and `to` (Klipper's own block, the lines after
 * SAVE_CONFIG's mark, when `autosave`): a setting already there gets its new value, the others are added at the end
 * of the section. False when the section is not there.
 */
function writeShaperSection(lines, from, to, values, autosave) {
  const read = (line) => (autosave ? line.replace(/^#\*#\s?/, "") : line);
  const header = /^\s*\[\s*input_shaper\s*\]\s*([#;].*)?$/i;
  let start = -1;
  for (let index = from; index < to; index += 1)
    if (header.test(read(lines[index]))) {
      start = index;
      break;
    }
  if (start < 0) return false;
  let end = start + 1;
  while (end < to && !isSectionHeader(read(lines[end]))) end += 1;
  let last = end - 1;
  while (last > start && !read(lines[last]).trim()) last -= 1;
  const left = { ...values };
  const line = (key) => (autosave ? "#*# " + key + " = " : key + ": ") + left[key];
  for (let index = start + 1; index <= last; index += 1) {
    const key = configLineKey(read(lines[index]));
    if (key && Object.prototype.hasOwnProperty.call(left, key)) {
      lines[index] = line(key);
      delete left[key];
    }
  }
  lines.splice(last + 1, 0, ...Object.keys(left).map(line));
  return true;
}

/** A config file as it is now (not the copy the dashboard keeps: Klipper or someone else may have changed it). */
async function readConfigFresh(path) {
  configFileCache.delete(path);
  return configFilesApi.read(path);
}

/** The files an [include …] line names (a * or ? in the name: the matching files of that folder, in order). */
async function includedConfigFiles(folder, pattern) {
  const path = joinPath(folder, pattern.replace(/^\.\//, ""));
  const name = path.split("/").pop();
  if (!/[*?[]/.test(name)) return [path];
  const match = new RegExp("^" + name.replace(/[.+^${}()|\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$");
  try {
    const { files } = await configFilesApi.listDirectory(parentPath(path));
    return files
      .map((file) => file.path)
      .filter((one) => match.test(one.split("/").pop()))
      .sort();
  } catch (error) {
    return [];
  }
}

/** The first file printer.cfg includes (or includes in turn) with an [input_shaper], with `values` written in it. */
async function findIncludedShaper(lines, folder, values, seen, depth) {
  if (depth > 5) return null;
  for (const one of lines) {
    const match = /^\s*\[\s*include\s+([^\]]+?)\s*\]/i.exec(one);
    if (!match) continue;
    for (const path of await includedConfigFiles(folder, match[1])) {
      if (seen.has(path)) continue;
      seen.add(path);
      let text;
      try {
        text = await readConfigFresh(path);
      } catch (error) {
        continue;
      }
      const own = text.split("\n");
      if (writeShaperSection(own, 0, own.length, values, false)) return { path, text, next: own.join("\n") };
      const deeper = await findIncludedShaper(own, parentPath(path), values, seen, depth + 1);
      if (deeper) return deeper;
    }
  }
  return null;
}

/**
 * 1.89: writes the shaper of `axis` (type and frequency) where Klipper reads it, so it does not refuse to start over a
 * clash: Klipper's own block at the end of printer.cfg when it has an [input_shaper] (SAVE_CONFIG wrote it); else the
 * [input_shaper] of printer.cfg; else the included file that has one; else a new [input_shaper] in printer.cfg, before
 * Klipper's block. The file's version before is kept (Config › versions). Resolves to the file written.
 */
async function saveShaperSetting(axis, type, freq) {
  const values = { ["shaper_type_" + axis]: type, ["shaper_freq_" + axis]: Number(freq).toFixed(1) };
  const write = async (path, before, next) => {
    if (next !== before) {
      await configVersionsApi.keep(path, before);
      await configFilesApi.save(path, next);
    }
    return path;
  };
  const text = await readConfigFresh(SHAPER_CONFIG_FILE);
  const lines = text.split("\n");
  const found = lines.findIndex((line) => SHAPER_AUTOSAVE_MARK.test(line));
  const mark = found < 0 ? lines.length : found;
  if (found >= 0 && writeShaperSection(lines, mark + 1, lines.length, values, true)) return write(SHAPER_CONFIG_FILE, text, lines.join("\n"));
  if (writeShaperSection(lines, 0, mark, values, false)) return write(SHAPER_CONFIG_FILE, text, lines.join("\n"));
  const included = await findIncludedShaper(lines.slice(0, mark), "", values, new Set([SHAPER_CONFIG_FILE]), 0);
  if (included) return write(included.path, included.text, included.next);
  const head = lines.slice(0, mark);
  while (head.length && !head[head.length - 1].trim()) head.pop();
  const section = ["[input_shaper]"].concat(Object.keys(values).map((key) => key + ": " + values[key]));
  const tail = found >= 0 ? [""].concat(lines.slice(mark)) : [""];
  return write(SHAPER_CONFIG_FILE, text, (head.length ? head.concat([""]) : []).concat(section, tail).join("\n"));
}

/* ---- the chart ------------------------------------------------------------------------------------------------- */

/** Round steps for the vibrations' scale: { ticks, exponent } (the numbers shown are the ticks / 10^exponent). */
function psdTicks(top) {
  const exponent = top > 0 ? Math.floor(Math.log10(top)) : 0;
  const scaled = top / Math.pow(10, exponent);
  const step = scaled > 5 ? 2 : scaled > 2.5 ? 1 : scaled > 1.2 ? 0.5 : 0.25;
  const ticks = [];
  for (let value = 0; value <= scaled + 1e-9; value += step) ticks.push(value);
  return { ticks, exponent, digits: step === 0.25 ? 2 : step === 0.5 ? 1 : 0 };
}

/** The series the legend can hide or show. */
function shaperSeries(data, recommended) {
  const series = [];
  if (data.psd.sum) series.push({ id: "sum", label: "X+Y+Z", color: SHAPER_PSD_COLORS.sum, kind: "psd", values: data.psd.sum });
  ["x", "y", "z"].forEach((name) => data.psd[name] && series.push({ id: name, label: name.toUpperCase(), color: SHAPER_PSD_COLORS[name], kind: "psd-axis", values: data.psd[name] }));
  const total = data.psd.sum || data.psd[data.axis] || [];
  recommended.forEach((shaper, index) =>
    series.push({ id: "after-" + shaper.name, label: tx("With {shaper} applied", { shaper: shaperName(shaper.name) }), color: SHAPER_AFTER_COLORS[index], kind: "after", values: total.map((value, i) => value * (shaper.response[i] || 0)) }),
  );
  data.shapers.forEach((shaper) => series.push({ id: "shaper-" + shaper.name, label: shaperName(shaper.name), color: shaperColor(shaper.name), kind: "response", values: shaper.response, shaper: shaper.name }));
  return series;
}

function ShaperChart({ data, selected, recommended, onSelect }) {
  const [boxRef, width] = useWidth();
  const [pointer, setPointer] = useState(null); // index of the frequency under the pointer
  const [hidden, setHidden] = useState(() => new Set(["z"]));
  const freq = data.freq;
  const series = shaperSeries(data, recommended);
  const psdSeries = series.filter((one) => one.kind !== "response");
  const top = Math.max(1e-9, ...psdSeries.filter((one) => !hidden.has(one.id)).flatMap((one) => one.values), data.bands ? data.bands.warning : 0);
  const { ticks, exponent, digits } = psdTicks(top * 1.12);
  const scaleTop = Math.max(ticks[ticks.length - 1], 1e-9) * Math.pow(10, exponent);
  const fMax = Math.min(200, Math.ceil(freq[freq.length - 1] / 25) * 25);
  const plotW = Math.max(0, width - SHAPER_PAD.left - SHAPER_PAD.right);
  const plotH = SHAPER_CHART_HEIGHT - SHAPER_PAD.top - SHAPER_PAD.bottom;
  const bottom = SHAPER_PAD.top + plotH;
  const x = (f) => SHAPER_PAD.left + (f / fMax) * plotW;
  const yPsd = (value) => SHAPER_PAD.top + (1 - value / scaleTop) * plotH;
  const yResponse = (value) => SHAPER_PAD.top + (1 - Math.min(1, value)) * plotH;
  const line = (values, y) => values.map((value, i) => (i ? "L" : "M") + x(freq[i]).toFixed(1) + " " + y(value).toFixed(1)).join("");
  const freqTicks = [];
  const tickStep = plotW / (fMax / 25) < 44 ? 50 : 25;
  for (let f = 0; f <= fMax; f += tickStep) freqTicks.push(f);
  const move = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const f = ((event.clientX - rect.left - SHAPER_PAD.left) / plotW) * fMax;
    if (f < freq[0] - 1 || f > freq[freq.length - 1] + 1) return setPointer(null);
    let best = 0;
    for (let i = 1; i < freq.length; i++) if (Math.abs(freq[i] - f) < Math.abs(freq[best] - f)) best = i;
    setPointer(best);
  };
  const toggle = (id) =>
    setHidden((was) => {
      const next = new Set(was);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const chosen = data.shapers.find((shaper) => shaper.name === selected);
  const cursorX = pointer !== null ? x(freq[pointer]) : 0;
  const total = data.psd.sum || data.psd[data.axis] || [];
  const bands = data.bands || null;
  const psdText = (value) => shaperNumber(value / Math.pow(10, exponent), 2) + (exponent ? "×10" + superscript(exponent) : "");
  const resonance = data.resonance || {};
  const title =
    tx("Axis frequency profile") +
    (resonance.freq ? " (ω0=" + formatHz(resonance.freq) + (resonance.damping ? ", ζ=" + shaperNumber(resonance.damping, 3) : "") + ")" : "");
  const shown = (one) => !hidden.has(one.id);
  return h(
    "div",
    { className: "shaper-chart", "data-axis": data.axis },
    h("div", { className: "shaper-chart__title", "data-shaper-title": "1" }, title),
    h(
      "div",
      { className: "shaper-chart__plot", ref: boxRef },
      width > 0 &&
        h(
          "svg",
          {
            className: "shaper-chart__svg",
            width,
            height: SHAPER_CHART_HEIGHT,
            role: "img",
            "aria-label": tx("Vibrations of the {axis} axis by frequency", { axis: String(data.axis || "").toUpperCase() }),
            onPointerMove: move,
            onPointerDown: move,
            onPointerLeave: () => setPointer(null),
          },
          bands && h("rect", { className: "shaper-chart__band is-relax", x: SHAPER_PAD.left, width: plotW, y: yPsd(bands.relax), height: Math.max(0, bottom - yPsd(bands.relax)) }),
          bands && h("rect", { className: "shaper-chart__band is-warning", x: SHAPER_PAD.left, width: plotW, y: yPsd(bands.warning), height: Math.max(0, yPsd(bands.relax) - yPsd(bands.warning)) }),
          ticks.map((value) =>
            h(
              "g",
              { key: "p" + value },
              h("line", { className: "shaper-chart__grid", x1: SHAPER_PAD.left, x2: width - SHAPER_PAD.right, y1: yPsd(value * Math.pow(10, exponent)), y2: yPsd(value * Math.pow(10, exponent)) }),
              h("text", { className: "shaper-chart__tick", x: SHAPER_PAD.left - 6, y: yPsd(value * Math.pow(10, exponent)) + 4, textAnchor: "end" }, shaperNumber(value, digits)),
            ),
          ),
          exponent !== 0 && h("text", { className: "shaper-chart__tick", x: SHAPER_PAD.left - 6, y: SHAPER_PAD.top - 4, textAnchor: "end", "data-shaper-exponent": exponent }, "×10" + superscript(exponent)),
          [0, 0.25, 0.5, 0.75, 1].map((value) => h("text", { key: "r" + value, className: "shaper-chart__tick", x: width - SHAPER_PAD.right + 6, y: yResponse(value) + 4 }, Math.round(value * 100) + "%")),
          freqTicks.map((f) => h("line", { key: "fg" + f, className: "shaper-chart__grid is-vertical", x1: x(f), x2: x(f), y1: SHAPER_PAD.top, y2: bottom })),
          freqTicks.map((f) => h("text", { key: "f" + f, className: "shaper-chart__tick", x: x(f), y: SHAPER_CHART_HEIGHT - 6, textAnchor: f === 0 ? "start" : f === fMax ? "end" : "middle" }, f + (f === fMax ? " Hz" : ""))),
          bands && h("line", { className: "shaper-chart__band-line is-relax", x1: SHAPER_PAD.left, x2: width - SHAPER_PAD.right, y1: yPsd(bands.relax), y2: yPsd(bands.relax), "data-shaper-band": "relax" }),
          bands && h("line", { className: "shaper-chart__band-line is-warning", x1: SHAPER_PAD.left, x2: width - SHAPER_PAD.right, y1: yPsd(bands.warning), y2: yPsd(bands.warning), "data-shaper-band": "warning" }),
          series
            .filter((one) => one.kind === "response" && shown(one))
            .map((one) =>
              h("path", {
                key: one.id,
                className: cx("shaper-chart__shaper", selected === one.shaper && "is-selected"),
                d: line(one.values, yResponse),
                stroke: one.color,
                "data-shaper": one.shaper,
                onClick: () => onSelect(one.shaper),
              }),
            ),
          series
            .filter((one) => one.kind !== "response" && shown(one))
            .map((one) => h("path", { key: one.id, className: cx("shaper-chart__line", "is-" + one.kind), d: line(one.values, yPsd), stroke: one.color, "data-series": one.id })),
          shown(series[0] || {}) &&
            (data.peaks || []).map((one, index) =>
              h(
                "g",
                { key: "k" + index, className: "shaper-chart__peak", "data-shaper-peak": index + 1 },
                h("path", { d: "M" + (x(one.freq) - 4) + " " + (yPsd(one.value) - 4) + "l8 8m0 -8l-8 8" }),
                h("text", { x: x(one.freq) + 7, y: yPsd(one.value) - 5, textAnchor: "start" }, index + 1),
              ),
            ),
          pointer !== null && h("line", { className: "shaper-chart__cursor", x1: cursorX, x2: cursorX, y1: SHAPER_PAD.top, y2: bottom }),
        ),
      pointer !== null &&
        h(
          "div",
          { className: cx("shaper-chart__tip", cursorX > width / 2 && "is-left"), style: { left: cursorX + "px" } },
          h("div", { className: "shaper-chart__tip-freq" }, formatHz(freq[pointer])),
          h("div", null, tx("Vibrations: {value}", { value: psdText(total[pointer] || 0) })),
          chosen && h("div", null, tx("{shaper} lets through {percent}", { shaper: shaperName(chosen.name), percent: Math.round((chosen.response[pointer] || 0) * 100) + "%" })),
        ),
    ),
    h(
      "div",
      { className: "shaper-legend", role: "group", "aria-label": tx("Lines shown") },
      series.map((one) =>
        h(
          "button",
          { key: one.id, type: "button", className: cx("shaper-legend__item", "is-" + one.kind, hidden.has(one.id) && "is-off"), "aria-pressed": !hidden.has(one.id), "data-shaper-legend": one.id, onClick: () => toggle(one.id) },
          h("span", { className: "shaper-legend__key", style: { "--key": one.color } }),
          one.label,
        ),
      ),
    ),
  );
}

/* ---- the card -------------------------------------------------------------------------------------------------- */

function ShaperParams({ axis, params, defaults, onChange }) {
  const values = params || {};
  return h(
    "div",
    { id: "shaper-params-" + axis, className: "oui-well shaper-params", "data-shaper-params-panel": axis },
    h("div", { className: "shaper-params__title" }, tx("Measurement settings for {axis}", { axis: axis.toUpperCase() })),
    h(
      "div",
      { className: "shaper-params__grid" },
      SHAPER_MEASURE_FIELDS.map((field) => {
        const fallback = field.fallback(defaults);
        const value = shaperParamValue(values, field.key, defaults);
        const id = "shaper-" + axis + "-" + field.key.toLowerCase();
        return h(
          "label",
          { key: field.key, className: "shaper-params__field", htmlFor: id },
          h("span", { className: "shaper-params__label" }, field.label() + (field.unit ? " (" + field.unit + ")" : "")),
          h("input", {
            id,
            className: "oui-field",
            type: "text",
            inputMode: "decimal",
            autoComplete: "off",
            value: values[field.key] || "",
            placeholder: fallback === null || fallback === undefined ? tx("none") : String(fallback),
            "aria-invalid": value === false ? "true" : undefined,
            "data-shaper-param": field.key,
            onChange: (event) => onChange({ ...values, [field.key]: event.target.value }),
          }),
          h("span", { className: "shaper-params__key" }, field.key + (value === false ? " · " + tx("not valid: the default is used") : "")),
        );
      }),
    ),
    h(
      "div",
      { className: "shaper-params__foot" },
      h("span", { className: "oui-caption" }, tx("Empty: Klipper's default (shown in grey).")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-shaper-params-reset": axis, disabled: !Object.values(values).some((one) => String(one || "").trim()), onClick: () => onChange({}) }, tx("Defaults")),
    ),
  );
}

function ShaperCard({ capabilities, lockReason, homedAxes, onGcode }) {
  const { files, error: listError, reload } = useShaperFiles();
  const axes = files ? Array.from(new Set(files.map((file) => file.axis))).sort() : [];
  const [axis, setAxis] = useState(null);
  const [fileName, setFileName] = useState(null);
  const [selected, setSelected] = useState(null);
  const [confirm, setConfirm] = useState(null); // the axis to measure, while asking
  const [asking, setAsking] = useState(false); // «Save»: asking first
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState({}); // what this page wrote, until Klipper restarts and says it
  const [openParams, setOpenParams] = useState(null);
  const [params, setParams] = useState(() => storage.getJson(SHAPER_PARAMS_KEY) || {});
  const shownAxis = axis && axes.includes(axis) ? axis : axes[0] || null;
  const axisFiles = (files || []).filter((file) => file.axis === shownAxis);
  const file = axisFiles.find((one) => one.name === fileName) || axisFiles[0] || null;
  const shaper = (capabilities && capabilities.shaper) || { canMeasure: true, current: null };
  const defaults = shaper.defaults || { freq_start: 5, freq_end: 133.33, hz_per_sec: 1, accel_per_hz: 60, max_smoothing: null };
  const scv = (capabilities && capabilities.tune && capabilities.tune.scv) || 5;
  const damping = shownAxis && shaper.damping ? shaper.damping[shownAxis] : null;
  const { data, error } = useShaperData(file && file.name, "&scv=" + scv + (damping ? "&damping=" + damping : ""));
  const current = shownAxis ? saved[shownAxis] || (shaper.current ? shaper.current[shownAxis] : null) : null;
  const recommendedNames = data && data.recommended ? [data.recommended.performance, data.recommended.low_vibrations] : [];
  const recommended = data ? recommendedNames.filter((name, index) => name && recommendedNames.indexOf(name) === index).map((name) => data.shapers.find((one) => one.name === name)).filter(Boolean) : [];
  const chosenName = selected || (data && data.recommended && data.recommended.performance) || (data && data.shapers[0] && data.shapers[0].name) || null;
  const chosen = data && data.shapers.find((one) => one.name === chosenName);
  const homed = ["x", "y", "z"].every((name) => (homedAxes || "").includes(name));
  const inUse = (one) => current && current.type === one.name && Math.abs(current.freq - one.freq) < 0.05 + one.freq * 0.02;

  useEffect(() => setSelected(null), [file && file.name]);

  const changeParams = (which, values) =>
    setParams((was) => {
      const next = { ...was, [which]: values };
      storage.set(SHAPER_PARAMS_KEY, JSON.stringify(next));
      return next;
    });
  const measure = (which) => {
    setConfirm(null);
    setOpenParams(null);
    onGcode((homed ? "" : "G28\n") + shaperMeasureCommand(which, params[which], defaults));
    toast.notice(tx("Measuring the {axis} axis: the printer shakes for a minute or two, then the graph appears here.", { axis: which.toUpperCase() }), 8000);
    window.setTimeout(reload, 60000);
  };
  const save = async () => {
    setAsking(false);
    if (!chosen || !shownAxis) return;
    setSaving(true);
    try {
      const path = await saveShaperSetting(shownAxis, chosen.name, chosen.freq);
      const name = shownAxis.toUpperCase();
      onGcode("SET_INPUT_SHAPER SHAPER_TYPE_" + name + "=" + chosen.name + " SHAPER_FREQ_" + name + "=" + Number(chosen.freq).toFixed(1));
      setSaved((was) => ({ ...was, [shownAxis]: { type: chosen.name, freq: chosen.freq } }));
      toast.notice(tx("{shaper} at {freq} for {axis} saved in {file}, and in use already.", { shaper: shaperName(chosen.name), freq: formatHz(chosen.freq), axis: name, file: path }), 6000);
    } catch (problem) {
      toast.notice(tx("Could not save: ") + (problem.message || String(problem)), 6000);
    } finally {
      setSaving(false);
    }
  };
  const confirmParams = confirm ? shaperMeasureCommand(confirm, params[confirm], defaults).split(" ").slice(2).join(" ") : "";

  return h(
    Card,
    { cardId: "shaper", className: "shaper-card" },
    h(
      CardHeader,
      { title: tx("Input shaper") },
      (shaper.current || Object.keys(saved).length > 0) &&
        h(
          "span",
          { className: "oui-badge shaper-current", "data-shaper-current": "1" },
          ["x", "y"]
            .map((name) => [name, saved[name] || (shaper.current ? shaper.current[name] : null)])
            .filter(([, one]) => one)
            .map(([name, one]) => name.toUpperCase() + " " + shaperName(one.type) + " " + formatHz(one.freq))
            .join(" · "),
        ),
    ),
    axes.length > 0 &&
      h(
        "div",
        { className: "shaper-toolbar" },
        h(
          "div",
          { className: "oui-segmented oui-segmented--sm", role: "group", "aria-label": tx("Axis") },
          axes.map((name) => h("button", { key: name, type: "button", className: cx(shownAxis === name && "is-selected"), "aria-pressed": shownAxis === name, "data-shaper-axis": name, onClick: () => setAxis(name) }, name.toUpperCase())),
        ),
        axisFiles.length > 1
          ? h(
              "select",
              { className: "oui-field shaper-file", "aria-label": tx("Measurement"), value: file ? file.name : "", onChange: (event) => setFileName(event.target.value) },
              axisFiles.map((one) => h("option", { key: one.name, value: one.name }, shaperFileDate(one))),
            )
          : file && h("span", { className: "oui-caption shaper-date" }, shaperFileDate(file)),
      ),
    files === null && h("div", { className: "oui-well shaper-empty" }, tx("Loading...")),
    files !== null &&
      axes.length === 0 &&
      h(
        "div",
        { className: "oui-well shaper-empty", "data-shaper-empty": "1" },
        listError ? listError : shaper.canMeasure ? tx("No measurement yet: measure an axis below. Klipper keeps the results until the Raspberry restarts.") : tx("No measurement: it needs an accelerometer and the [resonance_tester] section in printer.cfg."),
      ),
    error && h("div", { className: "oui-well shaper-empty" }, error),
    data && h(ShaperChart, { data, selected: chosenName, recommended, onSelect: setSelected }),
    data &&
      data.recommended &&
      h(
        "div",
        { className: "shaper-advice", "data-shaper-advice": "1" },
        h("div", { className: "shaper-advice__title" }, tx("Recommended shapers")),
        recommended[0] && h("div", { "data-shaper-advice-for": "performance" }, tx("For performance: {shaper} at {freq}", { shaper: shaperName(recommended[0].name), freq: formatHz(recommended[0].freq) })),
        data.recommended.low_vibrations &&
          (() => {
            const calm = data.shapers.find((one) => one.name === data.recommended.low_vibrations);
            return calm && h("div", { "data-shaper-advice-for": "low_vibrations" }, tx("For low vibrations: {shaper} at {freq}", { shaper: shaperName(calm.name), freq: formatHz(calm.freq) }));
          })(),
        data.resonance && data.resonance.damping && h("div", { "data-shaper-advice-for": "damping" }, tx("Estimated damping ratio ζ = {value}", { value: shaperNumber(data.resonance.damping, 3) })),
      ),
    data &&
      h(
        "div",
        { className: "shaper-table-box" },
        h(
          "table",
          { className: "shaper-table" },
          h("caption", { className: "shaper-table__caption" }, tx("The shapers Klipper tried: choose one to save it")),
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", { scope: "col" }, tx("Type")),
              h("th", { scope: "col" }, tx("Frequency"), h("span", { className: "shaper-table__unit" }, "Hz")),
              h("th", { scope: "col" }, tx("Vibrations"), h("span", { className: "shaper-table__unit" }, "%")),
              h("th", { scope: "col" }, tx("Smoothing")),
              h("th", { scope: "col" }, tx("Max accel"), h("span", { className: "shaper-table__unit" }, "mm/s²")),
            ),
          ),
          h(
            "tbody",
            null,
            data.shapers.map((one) =>
              h(
                "tr",
                { key: one.name, className: cx("shaper-row", chosenName === one.name && "is-selected"), "data-shaper-row": one.name, onClick: () => setSelected(one.name) },
                h(
                  "th",
                  { scope: "row" },
                  h(
                    "button",
                    { type: "button", className: "shaper-row__pick", "aria-pressed": chosenName === one.name, onClick: (event) => (event.stopPropagation(), setSelected(one.name)) },
                    h("span", { className: "shaper-row__key", style: { background: shaperColor(one.name) } }),
                    shaperName(one.name),
                  ),
                  inUse(one) && h("span", { className: "oui-badge shaper-row__tag" }, tx("in use")),
                ),
                h("td", { className: "shaper-row__freq" }, shaperNumber(one.freq, 1)),
                h("td", { "data-vibrations": one.vibrations }, shaperNumber(one.vibrations, 1)),
                h("td", { "data-smoothing": one.smoothing }, one.smoothing === null || one.smoothing === undefined ? "—" : shaperNumber(one.smoothing, 3)),
                h("td", { "data-max-accel": one.max_accel }, one.max_accel === null || one.max_accel === undefined ? "—" : Math.round(one.max_accel).toLocaleString(LOCALE)),
              ),
            ),
          ),
        ),
      ),
    data &&
      h(
        "div",
        { className: "oui-caption shaper-note" },
        tx("Vibrations: what a shaper leaves (fewer is better). Smoothing: how much it rounds the corners (less is better). Max accel: the highest acceleration that keeps the smoothing low. Below the green line the vibrations do not matter; above the orange one they show in the prints."),
      ),
    h(
      "div",
      { className: "shaper-actions" },
      shaper.canMeasure &&
        ["x", "y"].map((name) => {
          const custom = SHAPER_MEASURE_FIELDS.some((field) => typeof shaperParamValue(params[name], field.key, defaults) === "number");
          return h(
            "div",
            { key: name, className: "shaper-measure" },
            h(
              "button",
              { type: "button", className: "oui-btn oui-btn--sm shaper-measure__main", "data-shaper-measure": name, disabled: Boolean(lockReason), title: lockReason || undefined, onClick: () => setConfirm(name) },
              h(Icons.Refresh, { size: 16 }),
              tx("Measure {axis}", { axis: name.toUpperCase() }),
              custom && h("span", { className: "shaper-measure__dot", "aria-hidden": "true" }),
            ),
            h(
              "button",
              {
                type: "button",
                className: cx("oui-btn oui-btn--sm shaper-measure__more", openParams === name && "is-open"),
                "aria-expanded": openParams === name,
                "aria-controls": "shaper-params-" + name,
                "aria-label": tx("Measurement settings for {axis}", { axis: name.toUpperCase() }) + (custom ? " · " + tx("changed") : ""),
                "data-shaper-params": name,
                onClick: () => setOpenParams((was) => (was === name ? null : name)),
              },
              h(Icons.Chevron, { size: 16 }),
            ),
          );
        }),
      chosen &&
        h(
          "button",
          { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", "data-shaper-save": chosen.name, disabled: Boolean(lockReason) || saving || !shownAxis, title: lockReason || undefined, onClick: () => setAsking(true) },
          h(Icons.Save, { size: 16 }),
          tx("Save {shaper} at {freq} in printer.cfg", { shaper: shaperName(chosen.name), freq: formatHz(chosen.freq) }),
        ),
    ),
    openParams && shaper.canMeasure && h(ShaperParams, { axis: openParams, params: params[openParams], defaults, onChange: (values) => changeParams(openParams, values) }),
    createPortal(
      h(ConfirmDialog, {
        open: Boolean(confirm),
        icon: h(Icons.Refresh),
        title: confirm ? tx("Measure the {axis} axis?", { axis: confirm.toUpperCase() }) : "",
        subtitle: tx("Resonance measurement"),
        message:
          (homed ? "" : tx("The printer first homes its axes. ")) +
          tx("The toolhead goes to the middle of the bed and the printer shakes loudly for a minute or two: keep the bed clear. Then choose a shaper below and save it.") +
          (confirmParams ? " " + tx("With: {settings}", { settings: confirmParams }) : ""),
        confirmLabel: tx("Measure"),
        onConfirm: () => measure(confirm),
        onCancel: () => setConfirm(null),
      }),
      document.body,
    ),
    createPortal(
      h(ConfirmDialog, {
        open: asking && Boolean(chosen),
        icon: h(Icons.Save),
        title: chosen && shownAxis ? tx("Save {shaper} at {freq} for {axis}?", { shaper: shaperName(chosen.name), freq: formatHz(chosen.freq), axis: shownAxis.toUpperCase() }) : "",
        subtitle: tx("Input shaper"),
        message: tx("KlippEye writes it in [input_shaper] where Klipper reads it (printer.cfg, or the file it includes with that section), keeping a copy of the file first. It is applied at once: no restart needed."),
        confirmLabel: tx("Save"),
        onConfirm: save,
        onCancel: () => setAsking(false),
      }),
      document.body,
    ),
  );
}
