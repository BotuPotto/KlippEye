/* ============================================================================
   43a · TEMPERATURES: EVERY SENSOR AND THE CHART (1.43, roadmap 6d part 2)
   Every heater and sensor Klipper has
   (nozzles, bed, heater_generic, temperature_sensor, temperature_fan; a name
   starting with _ stays hidden), each with its temperature, target and power,
   and a chart of the last minutes: the temperature as a line, the target as a
   dashed line of the same colour. A tap on a name hides or shows its lines (kept
   on this device); a tap on a target changes it. The history starts with what
   Moonraker kept (/server/temperature_store, a sample a second for 20 minutes)
   and goes on with a reading every TEMP_POLL_MS while the card is on screen.
   ========================================================================== */

const TEMP_TICK_MIN_PX = 52; // room a clock time (12:34) needs under the chart
const TEMP_POLL_MS = 2000;
const TEMP_KEEP_MS = 20 * 60 * 1000; // what is kept (Moonraker keeps 20 minutes too)
const TEMP_GAP_MS = 10000; // back on screen after longer than this: Moonraker's history is read again
const TEMP_RANGES = [5, 10, 20]; // minutes the chart can show
const TEMP_HIDDEN_KEY = "ke_temp_hidden";
const TEMP_RANGE_KEY = "ke_temp_range";
/** The series colours, in a fixed order (the dark steps of a palette checked for colour blindness): a sensor keeps its colour. */
const TEMP_COLORS = ["#e66767", "#3987e5", "#199e70", "#c98500", "#d55181", "#9085e9", "#d95926", "#008300"];

/* ---------------------------------------------------------------------------
   Which objects, and their names
   ------------------------------------------------------------------------- */
const TEMP_OBJECT = /^(extruder\d*|heater_bed|heater_generic \S+|temperature_sensor \S+|temperature_fan \S+)$/;
const isTempObject = (name) => TEMP_OBJECT.test(name) && !/^\S+ _/.test(name);
/** Has a target (and a power): the heaters and the temperature fans. */
const hasTarget = (name) => /^(extruder\d*|heater_bed|heater_generic |temperature_fan )/.test(name);
const hasPower = (name) => /^(extruder\d*|heater_bed|heater_generic )/.test(name);

/** "Nozzle", "Nozzle 2", "Bed", "Chamber" (from "temperature_sensor chamber"). */
function tempLabel(name) {
  if (name === "extruder") return tx("Nozzle");
  const nozzle = name.match(/^extruder(\d+)$/);
  if (nozzle) return tx("Nozzle") + " " + (Number(nozzle[1]) + 1);
  if (name === "heater_bed") return tx("Bed");
  const own = name.split(" ").slice(1).join(" ").replace(/_/g, " ");
  return own.charAt(0).toUpperCase() + own.slice(1);
}

/** The order of the list and of the colours: nozzles, bed, other heaters, fans, sensors (each by name). */
function tempOrder(names) {
  const rank = (name) => (/^extruder/.test(name) ? 0 : name === "heater_bed" ? 1 : /^heater_generic/.test(name) ? 2 : /^temperature_fan/.test(name) ? 3 : 4);
  return names.slice().sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** The G-code that sets the target of `name` to `value` °C (0 switches it off). */
function tempTargetGcode(name, value) {
  const target = Math.max(0, Math.round(Number(value) || 0));
  if (name === "extruder") return "M104 S" + target;
  if (name === "heater_bed") return "M140 S" + target;
  if (/^temperature_fan /.test(name)) return "SET_TEMPERATURE_FAN_TARGET TEMPERATURE_FAN=" + name.split(" ")[1] + " TARGET=" + target;
  return "SET_HEATER_TEMPERATURE HEATER=" + name.replace(/^heater_generic /, "") + " TARGET=" + target;
}

/* ---------------------------------------------------------------------------
   The history: one store for the whole page (the chart keeps it when the
   card leaves the screen and comes back)
   { names, times: [ms], data: { name: { temp: [], target: [], power: [] } }, latest: { name: { temp, target, power } }, maxTemp: { name } }
   ------------------------------------------------------------------------- */
const tempHistory = (() => {
  const listeners = new Set();
  let state = { names: [], times: [], data: {}, latest: {}, maxTemp: {}, ready: false, error: null };
  let users = 0;
  let stopPolling = null;
  let lastSample = 0;
  const emit = () => listeners.forEach((fn) => fn());
  const set = (next) => {
    state = next;
    emit();
  };

  const trim = (times, data) => {
    const first = times.findIndex((time) => time >= times[times.length - 1] - TEMP_KEEP_MS);
    if (first <= 0) return;
    times.splice(0, first);
    Object.values(data).forEach((series) => ["temp", "target", "power"].forEach((key) => series[key].splice(0, first)));
  };

  /** Moonraker's own history (a sample a second), ending now. */
  async function load() {
    const names = tempOrder((await moonraker.objectsList()).filter(isTempObject));
    let stored = {};
    try {
      const response = await fetchFresh("/server/temperature_store?include_monitors=false");
      if (response.ok) stored = (await response.json()).result || {};
    } catch (error) {}
    const length = Math.max(0, ...names.map((name) => ((stored[name] || {}).temperatures || []).length));
    const now = Date.now();
    const times = Array.from({ length }, (_, index) => now - (length - 1 - index) * 1000);
    const data = {};
    for (const name of names) {
      const entry = stored[name] || {};
      const pad = (list) => {
        const values = Array.isArray(list) ? list.slice(-length) : [];
        return Array(length - values.length).fill(null).concat(values);
      };
      data[name] = { temp: pad(entry.temperatures), target: pad(entry.targets), power: pad(entry.powers) };
    }
    let maxTemp = state.maxTemp;
    try {
      const settings = (await moonraker.configfile("settings")).settings || {};
      maxTemp = {};
      for (const name of names) if (settings[name] && settings[name].max_temp) maxTemp[name] = Number(settings[name].max_temp);
    } catch (error) {}
    set({ ...state, names, times, data, maxTemp, ready: true, error: null });
  }

  async function sample() {
    const { names } = state;
    if (!names.length) return;
    const query = names.map((name) => encodeURIComponent(name) + "=" + (hasTarget(name) ? "temperature,target" + (hasPower(name) ? ",power" : "") : "temperature")).join("&");
    const status = await moonraker.queryObjects(query);
    const now = Date.now();
    if (now - lastSample > TEMP_GAP_MS && lastSample) return load().then(() => (lastSample = Date.now()));
    lastSample = now;
    const times = state.times.concat(now);
    const data = {};
    const latest = {};
    for (const name of names) {
      const reading = status[name] || {};
      const series = state.data[name] || { temp: Array(state.times.length).fill(null), target: Array(state.times.length).fill(null), power: Array(state.times.length).fill(null) };
      const pick = (value) => (typeof value === "number" && isFinite(value) ? value : null);
      latest[name] = { temp: pick(reading.temperature), target: pick(reading.target), power: pick(reading.power) };
      data[name] = { temp: series.temp.concat(latest[name].temp), target: series.target.concat(latest[name].target), power: series.power.concat(latest[name].power) };
    }
    trim(times, data);
    set({ ...state, times, data, latest });
  }

  return {
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    snapshot: () => state,
    /** A card on screen: reading starts (and stops when the last one leaves). */
    use() {
      users++;
      if (users === 1) {
        const start = async () => {
          try {
            if (!state.ready || Date.now() - lastSample > TEMP_GAP_MS) await load();
            lastSample = Date.now();
          } catch (error) {
            set({ ...state, error: error.message || tx("Error") });
          }
        };
        let started = start();
        stopPolling = startPolling(() => started.then(() => (state.ready ? sample() : (started = start()))), TEMP_POLL_MS);
      }
      return () => {
        users--;
        if (users === 0 && stopPolling) {
          stopPolling();
          stopPolling = null;
        }
      };
    },
  };
})();

function useTempHistory() {
  useEffect(() => tempHistory.use(), []);
  return useSyncExternalStore(tempHistory.subscribe, tempHistory.snapshot);
}

/** A small per-device store: the hidden series and the minutes shown. */
function useTempView() {
  const [hidden, setHidden] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(TEMP_HIDDEN_KEY) || "[]");
    } catch (e) {
      return [];
    }
  });
  const [range, setRange] = useState(() => {
    try {
      const minutes = Number(localStorage.getItem(TEMP_RANGE_KEY));
      return TEMP_RANGES.includes(minutes) ? minutes : 10;
    } catch (e) {
      return 10;
    }
  });
  const remember = (key, value) => {
    try {
      localStorage.setItem(key, typeof value === "string" ? value : JSON.stringify(value));
    } catch (e) {}
  };
  return {
    hidden,
    range,
    toggle(name) {
      const next = hidden.includes(name) ? hidden.filter((one) => one !== name) : hidden.concat(name);
      setHidden(next);
      remember(TEMP_HIDDEN_KEY, next);
    },
    setRange(minutes) {
      setRange(minutes);
      remember(TEMP_RANGE_KEY, String(minutes));
    },
  };
}

/* ---------------------------------------------------------------------------
   The chart
   ------------------------------------------------------------------------- */
const TEMP_CHART_HEIGHT = 210;
const TEMP_PAD = { left: 34, right: 10, top: 10, bottom: 22 };

/** The width of an element, followed as it changes. */
function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    setWidth(element.clientWidth);
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** The index of the last time at or before `time` (times sorted). */
function indexAt(times, time) {
  let low = 0;
  let high = times.length - 1;
  if (high < 0) return -1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (times[middle] <= time) low = middle;
    else high = middle - 1;
  }
  return low;
}

function TemperatureChart({ history, view, colors }) {
  const [boxRef, width] = useWidth();
  const [pointer, setPointer] = useState(null); // the time under the pointer, or null
  const { times, data } = history;
  const shown = history.names.filter((name) => !view.hidden.includes(name));
  const end = times.length ? times[times.length - 1] : Date.now();
  const start = end - view.range * 60000;
  const first = Math.max(0, indexAt(times, start));
  let top = 0;
  for (const name of shown) {
    const series = data[name];
    if (!series) continue;
    for (let i = first; i < times.length; i++) {
      if (series.temp[i] > top) top = series.temp[i];
      if (series.target[i] > top) top = series.target[i];
    }
  }
  const step = top + 10 > 150 ? 50 : 25;
  const yMax = Math.max(step * 2, Math.ceil((top + 10) / step) * step);
  const plotW = Math.max(0, width - TEMP_PAD.left - TEMP_PAD.right);
  const plotH = TEMP_CHART_HEIGHT - TEMP_PAD.top - TEMP_PAD.bottom;
  // 1.69: back to time running left to right (now on the right), with the clock time under each mark
  const x = (time) => TEMP_PAD.left + ((time - start) / (end - start)) * plotW;
  const y = (value) => TEMP_PAD.top + (1 - value / yMax) * plotH;
  const path = (values) => {
    if (!values) return "";
    let d = "";
    let pen = false;
    for (let i = first; i < times.length; i++) {
      const value = values[i];
      if (value === null || value === undefined) {
        pen = false;
        continue;
      }
      d += (pen ? "L" : "M") + x(times[i]).toFixed(1) + " " + y(value).toFixed(1);
      pen = true;
    }
    return d;
  };
  const ticks = [];
  for (let value = 0; value <= yMax; value += step) ticks.push(value);
  const minutes = [];
  for (let m = view.range; m >= 0; m -= view.range / 5) minutes.push(m);
  const at = pointer !== null ? indexAt(times, pointer) : -1;
  const move = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    if (px < TEMP_PAD.left || !times.length) return setPointer(null);
    setPointer(Math.min(end, start + ((px - TEMP_PAD.left) / plotW) * (end - start)));
  };
  const tooltipLeft = at >= 0 ? x(times[at]) : 0;
  return h(
    "div",
    { className: "temp-chart", ref: boxRef, "data-samples": times.length, "data-end": end },
    width > 0 &&
      h(
        "svg",
        {
          className: "temp-chart__svg",
          width,
          height: TEMP_CHART_HEIGHT,
          role: "img",
          "aria-label": tx("Temperatures of the last {count} minutes", { count: view.range }),
          onPointerMove: move,
          onPointerDown: move,
          onPointerLeave: () => setPointer(null),
        },
        ticks.map((value) =>
          h(
            "g",
            { key: "y" + value },
            h("line", { className: "temp-chart__grid", x1: TEMP_PAD.left, x2: width - TEMP_PAD.right, y1: y(value), y2: y(value) }),
            h("text", { className: "temp-chart__tick", x: TEMP_PAD.left - 6, y: y(value) + 4, textAnchor: "end" }, value + "°"),
          ),
        ),
        // 1.70: on a narrow chart every other time only (the newest kept), so they never run into each other
        minutes.map((m, index) => (plotW / (minutes.length - 1) >= TEMP_TICK_MIN_PX || (minutes.length - 1 - index) % 2 === 0) && h("text", { key: "x" + m, className: "temp-chart__tick", x: x(end - m * 60000), y: TEMP_CHART_HEIGHT - 6, textAnchor: m === view.range ? "start" : m === 0 ? "end" : "middle" }, new Date(end - m * 60000).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }))),
        shown.map((name) =>
          data[name] && hasTarget(name)
            ? h("path", { key: "t" + name, className: "temp-chart__target", d: path(data[name].target), stroke: colors[name], "data-series-target": name })
            : null,
        ),
        shown.map((name) => (data[name] ? h("path", { key: "v" + name, className: "temp-chart__line", d: path(data[name].temp), stroke: colors[name], "data-series": name }) : null)),
        at >= 0 && h("line", { className: "temp-chart__cursor", x1: tooltipLeft, x2: tooltipLeft, y1: TEMP_PAD.top, y2: TEMP_PAD.top + plotH }),
        at >= 0 &&
          shown.map((name) =>
            data[name] && data[name].temp[at] !== null && data[name].temp[at] !== undefined ? h("circle", { key: "c" + name, className: "temp-chart__dot", cx: tooltipLeft, cy: y(data[name].temp[at]), r: 4, fill: colors[name] }) : null,
          ),
      ),
    at >= 0 &&
      h(
        "div",
        { className: cx("temp-chart__tip", tooltipLeft > width / 2 && "is-left"), style: { left: tooltipLeft + "px" } },
        h("div", { className: "temp-chart__tip-time" }, new Date(times[at]).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", second: "2-digit" })),
        shown.map((name) => {
          const series = data[name];
          if (!series || series.temp[at] === null || series.temp[at] === undefined) return null;
          const target = series.target[at];
          return h(
            "div",
            { key: name, className: "temp-chart__tip-row" },
            h("span", { className: "temp-key", style: { background: colors[name] } }),
            h("span", { className: "temp-chart__tip-name" }, tempLabel(name)),
            h("b", null, series.temp[at].toFixed(1) + "°"),
            hasTarget(name) && target > 0 ? h("span", { className: "temp-chart__tip-target" }, "/ " + Math.round(target) + "°") : null,
          );
        }),
      ),
  );
}

/* ---------------------------------------------------------------------------
   The list and the target editor
   ------------------------------------------------------------------------- */
function TempTargetDialog({ name, value, max, onClose }) {
  useBackHandler(onClose, true);
  const [text, setText] = useState(value > 0 ? String(Math.round(value)) : "");
  const number = Number(String(text).replace(",", "."));
  const valid = text !== "" && isFinite(number) && number >= 0 && (!max || number <= max);
  const send = (target) => {
    fireGcode(tempTargetGcode(name, target));
    onClose();
  };
  return h(
    "div",
    { className: "confirm-overlay", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "confirm-card temp-target", role: "dialog", "aria-label": tempLabel(name), onClick: (e) => e.stopPropagation() },
      h("div", { className: "dialog-title" }, tempLabel(name)),
      h("div", { className: "dialog-sub" }, max ? tx("Target, up to {max} °C", { max }) : tx("Target")),
      h(
        "form",
        {
          className: "temp-target__form",
          onSubmit: (event) => {
            event.preventDefault();
            if (valid) send(number);
          },
        },
        h("input", { className: "oui-field temp-target__input", type: "number", inputMode: "decimal", min: 0, max: max || undefined, value: text, autoFocus: true, "aria-label": tx("Target"), onChange: (event) => setText(event.target.value) }),
        h("span", { className: "temp-target__unit" }, "°C"),
      ),
      max && !valid && text !== "" && h("div", { className: "oui-caption temp-target__error" }, tx("From {min} to {max}", { min: 0, max })),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { type: "button", className: "oui-btn", onClick: () => send(0) }, tx("Switch off")),
        h("button", { type: "button", className: "oui-btn oui-btn--primary", disabled: !valid, onClick: () => send(number) }, tx("Set")),
      ),
    ),
  );
}

function TemperatureRow({ name, reading, color, hidden, onToggle, onEdit }) {
  const fmt = (value) => (value === null || value === undefined ? "--" : value.toFixed(1) + "°");
  return h(
    "div",
    { className: cx("temp-row", hidden && "is-hidden"), "data-temp": name },
    h(
      "button",
      { type: "button", className: "temp-row__name", "aria-pressed": !hidden, title: hidden ? tx("Show in the chart") : tx("Hide from the chart"), onClick: onToggle },
      h("span", { className: "temp-key", style: { background: hidden ? "transparent" : color, borderColor: color } }),
      h("span", { className: "temp-row__label" }, tempLabel(name)),
    ),
    h("span", { className: "temp-row__power" }, hasPower(name) && reading.power !== null && reading.power !== undefined ? Math.round(reading.power * 100) + "%" : ""),
    h("span", { className: "temp-row__value" }, fmt(reading.temp)),
    hasTarget(name)
      ? h("button", { type: "button", className: "temp-row__target", "aria-label": tx("Change the target of {name}", { name: tempLabel(name) }), onClick: onEdit }, reading.target > 0 ? Math.round(reading.target) + "°" : tx("off"))
      : h("span", { className: "temp-row__target temp-row__target--none" }),
  );
}

function TemperatureCard({ onEditTemperature }) {
  const history = useTempHistory();
  const view = useTempView();
  const [editing, setEditing] = useState(null);
  const colors = {};
  history.names.forEach((name, index) => (colors[name] = TEMP_COLORS[index % TEMP_COLORS.length]));
  const latest = (name) => {
    if (history.latest[name]) return history.latest[name];
    const series = history.data[name];
    const last = history.times.length - 1;
    return series && last >= 0 ? { temp: series.temp[last], target: series.target[last], power: series.power[last] } : {};
  };
  const edit = (name) => {
    // the nozzle and the bed keep the dialog of the heater tiles (with its presets)
    if (name === "extruder" && onEditTemperature) return onEditTemperature("hotend", Math.round(latest(name).target || 0));
    if (name === "heater_bed" && onEditTemperature) return onEditTemperature("bed", Math.round(latest(name).target || 0));
    setEditing(name);
  };
  // the dialog sits next to the card, not in it: a card's glass (backdrop-filter) would hold a fixed overlay inside it
  return h(
    React.Fragment,
    null,
    h(
    Card,
    { cardId: "temps", className: "temp-card" },
    h(
      CardHeader,
      { title: tx("Temperatures") },
      h(
        "div",
        { className: "oui-segmented oui-segmented--sm temp-ranges", role: "group", "aria-label": tx("Minutes shown") },
        TEMP_RANGES.map((minutes) => h("button", { key: minutes, type: "button", className: cx(view.range === minutes && "is-selected"), "aria-pressed": view.range === minutes, "data-range": minutes, onClick: () => view.setRange(minutes) }, minutes + " min")),
      ),
    ),
    history.error && !history.ready
      ? h("div", { className: "oui-caption" }, history.error)
      : !history.ready
        ? h("div", { className: "oui-caption" }, tx("Loading..."))
        : h(
            React.Fragment,
            null,
            h(TemperatureChart, { history, view, colors }),
            h(
              "div",
              { className: "temp-list" },
              h("div", { className: "temp-row temp-row--head", "aria-hidden": "true" }, h("span", null, tx("Sensor")), h("span", null, tx("Power")), h("span", null, tx("Now")), h("span", null, tx("Target"))),
              history.names.map((name) => h(TemperatureRow, { key: name, name, reading: latest(name), color: colors[name], hidden: view.hidden.includes(name), onToggle: () => view.toggle(name), onEdit: () => edit(name) })),
            ),
            h("div", { className: "oui-caption temp-hint ui-hint" }, tx("Tap a name to hide or show its lines; tap a target to change it. Dashed: the target.")),
          ),
    ),
    h(Presence, null, editing && h(TempTargetDialog, { name: editing, value: latest(editing).target, max: history.maxTemp[editing], onClose: () => setEditing(null) })),
  );
}
