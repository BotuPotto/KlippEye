/* ============================================================================
   57b · INPUT SHAPER GRAPHS (1.80)
   What Klipper's resonance measurement (SHAPER_CALIBRATE, with an accelerometer)
   found: the vibrations of the axis at each frequency (the filled curve, with
   its peak) and, for each shaper Klipper tried, how much of them it lets
   through (the lines, 0 to 100 % on the right) and the vibrations it leaves.
   The files are the ones Klipper leaves in /tmp (backend/shaper_data.py): they
   go away when the Raspberry restarts. The shaper printer.cfg sets is marked;
   another one can be tried until Klipper restarts (SET_INPUT_SHAPER).
   ========================================================================== */

const SHAPER_CHART_HEIGHT = 220;
const SHAPER_PAD = { left: 10, right: 38, top: 12, bottom: 24 };
const SHAPER_POLL_MS = 15000;
const SHAPER_COLORS = ["#3987e5", "#199e70", "#c98500", "#d55181", "#9085e9", "#d95926"];
const SHAPER_NAMES = { zv: "ZV", mzv: "MZV", zvd: "ZVD", ei: "EI", "2hump_ei": "2HUMP_EI", "3hump_ei": "3HUMP_EI" };

const shaperName = (name) => SHAPER_NAMES[name] || String(name || "").toUpperCase();
const formatHz = (value) => (Math.round(value * 10) / 10).toLocaleString(LOCALE) + " Hz";

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

function useShaperData(name) {
  const [state, setState] = useState({ name: null, data: null, error: null });
  useEffect(() => {
    if (!name) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetchFresh("/api/shaper/data?name=" + encodeURIComponent(name));
        if (!response.ok) throw new Error(await responseError(response));
        const data = await response.json();
        if (!cancelled) setState({ name, data, error: null });
      } catch (problem) {
        if (!cancelled) setState({ name, data: null, error: problem.message || String(problem) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [name]);
  return state.name === name ? state : { name, data: null, error: null };
}

/** The measurement's date, from the file's own name (calibration_data_x_20261109_221500.csv) or its time. */
function shaperFileDate(file) {
  const match = /_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.csv$/i.exec(file.name || "");
  const date = match ? new Date(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +match[6]) : new Date((file.modified || 0) * 1000);
  return date.toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** The chart: the vibrations (filled, left scale without numbers: only their shape counts) and the shapers' lines. */
function ShaperChart({ data, axis, selected, current, onSelect }) {
  const [boxRef, width] = useWidth();
  const [pointer, setPointer] = useState(null); // index of the frequency under the pointer
  const freq = data.freq;
  const total = data.psd.sum || data.psd[axis] || [];
  const own = data.psd[axis];
  const top = Math.max(1e-9, ...total, ...(own || []));
  const fMax = Math.min(200, Math.ceil(freq[freq.length - 1] / 25) * 25);
  const plotW = Math.max(0, width - SHAPER_PAD.left - SHAPER_PAD.right);
  const plotH = SHAPER_CHART_HEIGHT - SHAPER_PAD.top - SHAPER_PAD.bottom;
  const x = (f) => SHAPER_PAD.left + (f / fMax) * plotW;
  const yPsd = (value) => SHAPER_PAD.top + (1 - value / (top * 1.08)) * plotH;
  const yResponse = (value) => SHAPER_PAD.top + (1 - Math.min(1, value)) * plotH;
  const line = (values, y) => values.map((value, i) => (i ? "L" : "M") + x(freq[i]).toFixed(1) + " " + y(value).toFixed(1)).join("");
  const area = total.length ? line(total, yPsd) + "L" + x(freq[freq.length - 1]).toFixed(1) + " " + (SHAPER_PAD.top + plotH) + "L" + x(freq[0]).toFixed(1) + " " + (SHAPER_PAD.top + plotH) + "Z" : "";
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
  const chosen = data.shapers.find((shaper) => shaper.name === selected);
  const cursorX = pointer !== null ? x(freq[pointer]) : 0;
  return h(
    "div",
    { className: "shaper-chart", ref: boxRef, "data-axis": axis },
    width > 0 &&
      h(
        "svg",
        {
          className: "shaper-chart__svg",
          width,
          height: SHAPER_CHART_HEIGHT,
          role: "img",
          "aria-label": tx("Vibrations of the {axis} axis by frequency", { axis: axis.toUpperCase() }),
          onPointerMove: move,
          onPointerDown: move,
          onPointerLeave: () => setPointer(null),
        },
        [0, 0.25, 0.5, 0.75, 1].map((value) =>
          h(
            "g",
            { key: "r" + value },
            h("line", { className: "shaper-chart__grid", x1: SHAPER_PAD.left, x2: width - SHAPER_PAD.right, y1: yResponse(value), y2: yResponse(value) }),
            h("text", { className: "shaper-chart__tick", x: width - SHAPER_PAD.right + 6, y: yResponse(value) + 4 }, Math.round(value * 100) + "%"),
          ),
        ),
        freqTicks.map((f) => h("text", { key: "f" + f, className: "shaper-chart__tick", x: x(f), y: SHAPER_CHART_HEIGHT - 6, textAnchor: f === 0 ? "start" : "middle" }, f + (f === fMax ? " Hz" : ""))),
        h("path", { className: "shaper-chart__area", d: area }),
        own && data.psd.sum && h("path", { className: "shaper-chart__own", d: line(own, yPsd), "data-series": "psd-" + axis }),
        h("path", { className: "shaper-chart__psd", d: line(total, yPsd), "data-series": "psd" }),
        h("line", { className: "shaper-chart__peak", x1: x(data.peak.freq), x2: x(data.peak.freq), y1: SHAPER_PAD.top, y2: SHAPER_PAD.top + plotH }),
        h("text", { className: "shaper-chart__peak-label", x: x(data.peak.freq) + 4, y: SHAPER_PAD.top + 10 }, formatHz(data.peak.freq)),
        data.shapers.map((shaper, index) =>
          h("path", {
            key: shaper.name,
            className: cx("shaper-chart__shaper", selected && selected !== shaper.name && "is-dim", selected === shaper.name && "is-selected"),
            d: line(shaper.response, yResponse),
            stroke: SHAPER_COLORS[index % SHAPER_COLORS.length],
            "data-shaper": shaper.name,
            onClick: () => onSelect(shaper.name),
          }),
        ),
        pointer !== null && h("line", { className: "shaper-chart__cursor", x1: cursorX, x2: cursorX, y1: SHAPER_PAD.top, y2: SHAPER_PAD.top + plotH }),
      ),
    pointer !== null &&
      h(
        "div",
        { className: cx("shaper-chart__tip", cursorX > width / 2 && "is-left"), style: { left: cursorX + "px" } },
        h("div", { className: "shaper-chart__tip-freq" }, formatHz(freq[pointer])),
        h("div", null, tx("Vibrations: {percent} of the peak", { percent: Math.round((total[pointer] / top) * 100) + "%" })),
        chosen && h("div", null, tx("{shaper} lets through {percent}", { shaper: shaperName(chosen.name), percent: Math.round(chosen.response[pointer] * 100) + "%" })),
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
  const shownAxis = axis && axes.includes(axis) ? axis : axes[0] || null;
  const axisFiles = (files || []).filter((file) => file.axis === shownAxis);
  const file = axisFiles.find((one) => one.name === fileName) || axisFiles[0] || null;
  const { data, error } = useShaperData(file && file.name);
  const shaper = (capabilities && capabilities.shaper) || { canMeasure: true, current: null };
  const current = shaper.current && shownAxis ? shaper.current[shownAxis] : null;
  const best = data && data.shapers.length ? data.shapers.reduce((low, one) => (one.vibrations < low.vibrations ? one : low)) : null;
  const chosen = data && data.shapers.find((one) => one.name === selected);
  const homed = ["x", "y", "z"].every((name) => (homedAxes || "").includes(name));

  useEffect(() => setSelected(null), [file && file.name]);

  const measure = (which) => {
    setConfirm(null);
    const script = (homed ? "" : "G28\n") + "SHAPER_CALIBRATE AXIS=" + which.toUpperCase();
    onGcode(script);
    toast.notice(tx("Measuring the {axis} axis: the printer shakes for a minute or two, then the graph appears here.", { axis: which.toUpperCase() }), 8000);
    window.setTimeout(reload, 60000);
  };
  const apply = () => {
    if (!chosen || !shownAxis) return;
    const name = shownAxis.toUpperCase();
    onGcode("SET_INPUT_SHAPER SHAPER_TYPE_" + name + "=" + chosen.name + " SHAPER_FREQ_" + name + "=" + chosen.freq);
    toast.action(tx("{shaper} at {freq} on {axis} until Klipper restarts", { shaper: shaperName(chosen.name), freq: formatHz(chosen.freq), axis: name }));
  };

  return h(
    Card,
    { cardId: "shaper", className: "shaper-card" },
    h(
      CardHeader,
      { title: tx("Input shaper") },
      shaper.current &&
        h(
          "span",
          { className: "oui-badge shaper-current", "data-shaper-current": "1" },
          ["x", "y"]
            .filter((name) => shaper.current[name])
            .map((name) => name.toUpperCase() + " " + shaperName(shaper.current[name].type) + " " + formatHz(shaper.current[name].freq))
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
    data && h(ShaperChart, { data, axis: shownAxis, selected, current, onSelect: (name) => setSelected((was) => (was === name ? null : name)) }),
    data &&
      h(
        "div",
        { className: "shaper-list", role: "list" },
        data.shapers.map((one, index) =>
          h(
            "button",
            {
              key: one.name,
              type: "button",
              role: "listitem",
              className: cx("shaper-row", selected === one.name && "is-selected"),
              "aria-pressed": selected === one.name,
              "data-shaper-row": one.name,
              onClick: () => setSelected((was) => (was === one.name ? null : one.name)),
            },
            h("span", { className: "shaper-row__key", style: { background: SHAPER_COLORS[index % SHAPER_COLORS.length] } }),
            h("span", { className: "shaper-row__name" }, shaperName(one.name)),
            h("span", { className: "shaper-row__freq" }, formatHz(one.freq)),
            h("span", { className: "shaper-row__vib", "data-vibrations": one.vibrations }, tx("{percent} left", { percent: one.vibrations.toLocaleString(LOCALE) + "%" })),
            current && current.type === one.name && Math.abs(current.freq - one.freq) < 0.05 + one.freq * 0.02 ? h("span", { className: "oui-badge shaper-row__tag" }, tx("in use")) : best === one ? h("span", { className: "oui-badge shaper-row__tag is-best" }, tx("fewest vibrations")) : null,
          ),
        ),
      ),
    data &&
      h(
        "div",
        { className: "oui-caption shaper-note" },
        tx("The filled curve: how much the axis shakes at each frequency (peak at {freq}). Each line: how much a shaper lets through. Fewer vibrations left is better, but the shapers that remove more also round the corners more: Klipper weighs both when it recommends one.", { freq: formatHz(data.peak.freq) }),
      ),
    h(
      "div",
      { className: "shaper-actions" },
      shaper.canMeasure &&
        ["x", "y"].map((name) =>
          h("button", { key: name, type: "button", className: "oui-btn oui-btn--sm", "data-shaper-measure": name, disabled: Boolean(lockReason), title: lockReason || undefined, onClick: () => setConfirm(name) }, h(Icons.Refresh, { size: 16 }), tx("Measure {axis}", { axis: name.toUpperCase() })),
        ),
      chosen && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", "data-shaper-apply": chosen.name, disabled: Boolean(lockReason), onClick: apply }, tx("Try {shaper}", { shaper: shaperName(chosen.name) })),
    ),
    createPortal(
      h(ConfirmDialog, {
        open: Boolean(confirm),
        icon: h(Icons.Refresh),
        title: confirm ? tx("Measure the {axis} axis?", { axis: confirm.toUpperCase() }) : "",
        subtitle: tx("Resonance measurement"),
        message: (homed ? "" : tx("The printer first homes its axes. ")) + tx("The toolhead goes to the middle of the bed and the printer shakes loudly for a minute or two: keep the bed clear. At the end Klipper proposes the best shaper: «Save configuration» writes it in printer.cfg."),
        confirmLabel: tx("Measure"),
        onConfirm: () => measure(confirm),
        onCancel: () => setConfirm(null),
      }),
      document.body,
    ),
  );
}
