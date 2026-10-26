/* ============================================================================
   42 · FANS
   Fan discovery and speed polling (useFans), the anti-touch lock
   (useFanLock) and the fan controls shown in the "Riscaldatori e ventole" card.
   ========================================================================== */

const FAN_CONFIG_REFRESH_MS = 30000;
/** The list of fans is read again this often (the speeds are read at every poll). */
const FAN_NAMES_REFRESH_MS = 30000;
/** After the user sets a speed, polled values are ignored for this long. */
const FAN_USER_VALUE_HOLD_MS = 8000;
const FAN_UNLOCK_MS = 10000;

/* ---------------------------------------------------------------------------
   Names
   ------------------------------------------------------------------------- */
const FAN_PREFIXES = ["fan_generic ", "heater_fan ", "controller_fan "];
const isFanObject = (name) => name === "fan" || FAN_PREFIXES.some((prefix) => name.indexOf(prefix.trim()) === 0);
const stripFanPrefix = (name) => FAN_PREFIXES.reduce((result, prefix) => result.replace(prefix, ""), name);

/** Klipper object names that map straight to a friendly label. */
const FAN_LABELS = {
  fan: "Part Fan",
  "fan_generic Part Cooling": "Part Fan",
  "Part Cooling": "Part Fan",
  part_cooling: "Part Fan",
  "part cooling": "Part Fan",
  "fan_generic Aux_Fan": "Aux Fan",
  Aux_Fan: "Aux Fan",
  aux_fan: "Aux Fan",
  "fan_generic hotend_fan": "Hotend Fan",
  "heater_fan hotend_fan": "Hotend Fan",
  hotend_fan: "Hotend Fan",
  "controller_fan hotend_fan": "Hotend Fan",
  "fan_generic drivers_fan": "Drivers Fan",
  "controller_fan drivers_fan": "Drivers Fan",
  drivers_fan: "Drivers Fan",
  driver_fan: "Drivers Fan",
};
const FAN_ORDER = ["Part Fan", "Aux Fan", "Hotend Fan", "Drivers Fan"];
/** Only these two fans may be changed from the dashboard. */
const CONTROLLABLE_FANS = ["Part Fan", "Aux Fan"];

function fanLabel(fan) {
  const displayName = fan.displayName || "";
  if (FAN_LABELS[fan.name]) return FAN_LABELS[fan.name];
  if (FAN_LABELS[displayName]) return FAN_LABELS[displayName];
  const text = (fan.name + " " + displayName).toLowerCase();
  const has = (word) => text.indexOf(word) !== -1;
  if (has("part") && has("cool")) return "Part Fan";
  if (has("part") && has("fan") && !has("aux") && !has("hotend") && !has("driver")) return "Part Fan";
  if (has("aux")) return "Aux Fan";
  if (has("hotend")) return "Hotend Fan";
  if (has("driver")) return "Drivers Fan";
  return displayName || stripFanPrefix(fan.name);
}

/* ---------------------------------------------------------------------------
   Klipper queries
   ------------------------------------------------------------------------- */
async function fetchObjectNames() {
  try {
    const response = await fetchFresh("/printer/objects/list");
    if (!response.ok) return null;
    const json = await response.json();
    return (json.result && json.result.objects) || [];
  } catch (e) {
    return null;
  }
}

/** Printer configuration (for each fan's max_power), or null when unavailable. */
async function fetchPrinterConfig() {
  for (const url of ["/printer/objects/query?configfile=config", "/printer/config"]) {
    try {
      const response = await fetchFresh(url);
      if (!response.ok) continue;
      const result = (await response.json()).result || {};
      const configfile = (result.status && result.status.configfile) || {};
      const config = configfile.config || configfile.settings || result.config || result.status;
      if (config) return config;
    } catch (e) {}
  }
  return null;
}

function maxPowerFromConfig(fanName, config) {
  if (!config) return 1.0;
  const positive = (value) => {
    const number = parseFloat(value);
    return !isNaN(number) && number > 0 ? number : null;
  };
  const entry = config[fanName];
  if (entry && entry.max_power !== undefined && positive(entry.max_power)) return positive(entry.max_power);
  const generic = config["fan_generic " + stripFanPrefix(fanName)];
  if (generic && generic.max_power !== undefined && positive(generic.max_power)) return positive(generic.max_power);
  return 1.0;
}

/** G-code that sets a fan to `fraction` (0..1). */
function fanGcode(fanName, fraction) {
  if (fanName === "fan") return "M106 S" + Math.round(fraction * 255);
  const usesFullName = fanName.indexOf("heater_fan ") === 0 || fanName.indexOf("controller_fan ") === 0;
  return "SET_FAN_SPEED FAN=" + (usesFullName ? fanName : stripFanPrefix(fanName)) + " SPEED=" + fraction;
}

/* ---------------------------------------------------------------------------
   useFans — list, speeds and what the user is doing right now
   Each fan is { name, displayName, speed, maxPower, pct } where `pct` is the
   value to show (0..100): what the user just set, else speed / max_power.
   ------------------------------------------------------------------------- */
function useFans() {
  const [fans, setFans] = useState([]);
  const fansRef = useRef([]);
  const userValue = useRef({}); // fan name -> { pct, time }
  const interacting = useRef({}); // fan name -> true while dragging / typing
  const config = useRef({ value: null, fetchedAt: 0 });
  const knownNames = useRef(null);
  const namesReadAt = useRef(0);

  const percentFor = (fan) => {
    const set = userValue.current[fan.name];
    if (set && Date.now() - set.time < FAN_USER_VALUE_HOLD_MS) return set.pct;
    return clamp(Math.round(fan.speed / (fan.maxPower > 0 ? fan.maxPower : 1.0) * 100), 0, 100);
  };
  const publish = (list) => {
    fansRef.current = list;
    setFans(list.map((fan) => ({ ...fan, pct: percentFor(fan) })));
  };

  const getConfig = async () => {
    const now = Date.now();
    if (!config.current.value || now - config.current.fetchedAt > FAN_CONFIG_REFRESH_MS) {
      const fresh = await fetchPrinterConfig();
      if (fresh) config.current = { value: fresh, fetchedAt: now };
    }
    return config.current.value;
  };

  /** Re-reads each fan's speed, leaving alone fans the user is controlling. */
  const refreshSpeeds = async (list) => {
    if (list.length === 0) return list;
    try {
      const params = new URLSearchParams();
      list.forEach((fan) => params.append(fan.name, "speed"));
      const status = await moonraker.queryObjects(params.toString());
      const cfg = await getConfig();
      return list.map((fan) => {
        const set = userValue.current[fan.name];
        if ((set && Date.now() - set.time < FAN_USER_VALUE_HOLD_MS) || interacting.current[fan.name]) return fan;
        const object = status[fan.name];
        if (!object || object.speed === undefined) return fan;
        return { name: fan.name, displayName: fan.displayName, speed: object.speed, maxPower: maxPowerFromConfig(fan.name, cfg) };
      });
    } catch (e) {
      return list;
    }
  };

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (fansRef.current.length > 0 && Date.now() - namesReadAt.current < FAN_NAMES_REFRESH_MS) {
        const refreshed = await refreshSpeeds(fansRef.current); // the usual poll: just the speeds
        if (!cancelled) publish(refreshed);
        return;
      }
      const objects = await fetchObjectNames();
      if (objects !== null) namesReadAt.current = Date.now();
      const cfg = await getConfig();
      if (cancelled) return;
      const current = fansRef.current;
      if (objects === null) {
        if (current.length > 0) publish(await refreshSpeeds(current));
        return;
      }
      let names = objects.filter(isFanObject);
      if (names.length === 0) {
        if (knownNames.current && knownNames.current.length > 0) names = knownNames.current;
        else {
          if (current.length > 0) publish(await refreshSpeeds(current));
          return;
        }
      }
      knownNames.current = names.slice();
      const sameFans = current.length === names.length && names.every((name) => current.some((fan) => fan.name === name));
      const list = sameFans
        ? current
        : names.map((name) => ({
            name,
            displayName: name === "fan" ? "Part Cooling" : stripFanPrefix(name),
            speed: 0,
            maxPower: maxPowerFromConfig(name, cfg),
          }));
      const refreshed = await refreshSpeeds(list);
      if (!cancelled) publish(refreshed);
    };
    const stopPolling = startPolling(poll, POLL_MS.fans);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  /** The user chose `pct` (0..100) for a fan: show it now and tell Klipper. */
  const setSpeed = (name, pct) => {
    const value = clamp(pct, 0, 100);
    userValue.current[name] = { pct: value, time: Date.now() };
    publish(fansRef.current.map((fan) => (fan.name === name ? { ...fan, speed: value / 100 } : fan)));
    fireGcode(fanGcode(name, value / 100));
  };
  const setInteracting = (name, active) => {
    interacting.current[name] = active;
  };

  const labelled = fans
    .map((fan) => ({ ...fan, label: fanLabel(fan) }))
    .sort((a, b) => {
      const rank = (label) => (FAN_ORDER.indexOf(label) === -1 ? 99 : FAN_ORDER.indexOf(label));
      return rank(a.label) - rank(b.label);
    });
  return { fans: labelled, setSpeed, setInteracting };
}

/* ---------------------------------------------------------------------------
   useFanLock — fans are locked by default; unlocking lasts 10 s
   ------------------------------------------------------------------------- */
function useFanLock() {
  const [locked, setLocked] = useState(true);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const toggle = () => {
    clearTimeout(timer.current);
    if (locked) {
      setLocked(false);
      toast.notice("Ventole sbloccate per 10s");
      timer.current = setTimeout(() => {
        setLocked(true);
        toast.notice("Ventole bloccate - anti-tocco");
      }, FAN_UNLOCK_MS);
    } else {
      setLocked(true);
      toast.notice("Ventole bloccate");
    }
  };
  return { locked, toggle };
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */
const FAN_BUTTON_CLASS = "fan-step";
const FAN_NAME_CLASS = "fan-name";

/** Horizontal slider driven by pointer events (works for touch and mouse). */
function FanSlider({ name, pct, onDrag, onCommit }) {
  const ref = useRef(null);
  const percentAt = (clientX) => {
    const rect = ref.current.getBoundingClientRect();
    return clamp(Math.round(((clientX - rect.left) / rect.width) * 100), 0, 100);
  };

  const onPointerDown = (event) => {
    const slider = ref.current;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch (e) {}
    onDrag(percentAt(event.clientX));
    const onMove = (e) => onDrag(percentAt(e.clientX));
    const onUp = (e) => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      try {
        slider.releasePointerCapture(e.pointerId);
      } catch (err) {}
      onCommit(percentAt(e.clientX));
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  };

  return h(
    "div",
    { ref, className: "slider flex-1", style: { "--p": pct / 100 }, onPointerDown },
    h("div", { className: "slider__fill" }),
    h("div", { className: "slider__handle" }),
  );
}

/** Slider + − / + buttons + number box for one controllable fan. */
function FanControl({ fan, locked, onSet, onInteract }) {
  const [draft, setDraft] = useState(null); // value shown while the user drags / types
  const [typed, setTyped] = useState(null); // raw text of the number box while editing
  const pct = draft !== null ? draft : fan.pct;

  const commit = (value) => {
    setDraft(null);
    setTyped(null);
    onInteract(false);
    onSet(value);
  };
  const nudge = (step) => commit(clamp(pct + step, 0, 100));
  const parse = (text) => clamp(parseInt(text) || 0, 0, 100);

  return h(
    "div",
    { className: cx("fan-row fan-card", locked && "is-locked") },
    h(
      "div",
      { className: "fan-row__head" },
      h("span", { className: FAN_NAME_CLASS }, fan.label),
      h(
        "div",
        { className: "flex items-center gap-2" },
        h("button", { className: FAN_BUTTON_CLASS, onClick: () => nudge(-1), "aria-label": "Meno" }, "−"),
        h("button", { className: FAN_BUTTON_CLASS, onClick: () => nudge(1), "aria-label": "Più" }, "+"),
      ),
    ),
    h(
      "div",
      { className: "flex items-center gap-3" },
      h(FanSlider, {
        name: fan.name,
        pct,
        onDrag: (value) => {
          onInteract(true);
          setDraft(value);
          setTyped(null);
        },
        onCommit: commit,
      }),
      h(
        "div",
        { className: "fan-value" },
        h("input", {
          type: "number",
          min: "0",
          max: "100",
          value: typed !== null ? typed : pct,
          className: "fan-value__input",
          onFocus: (e) => {
            onInteract(true);
            e.target.select();
          },
          // Like the original, every change in the box is sent at once (typing "42" sends 4, then 42).
          onChange: (e) => {
            setTyped(e.target.value); // keep exactly what is typed, even an empty box
            setDraft(null);
            onInteract(false);
            onSet(parse(e.target.value));
          },
          onBlur: () => {
            setTyped(null);
            onInteract(false);
          },
          onKeyDown: (e) => {
            if (e.key !== "Enter") return;
            commit(parse(e.target.value));
            e.target.blur();
          },
        }),
        h("span", { className: "fan-value__unit" }, "%"),
      ),
    ),
  );
}

/** Read-only fan (hotend / drivers): label + level bar + percentage. */
function FanReadout({ fan }) {
  return h(
    "div",
    { className: "fan-row fan-row--readout" },
    h("span", { className: FAN_NAME_CLASS }, fan.label),
    h(
      "div",
      { className: "flex items-center gap-3" },
      h("div", { className: "oui-progress fan-level" }, h("div", { className: "oui-progress__bar", style: { width: fan.pct + "%" } })),
      h("span", { className: "oui-badge fan-pct" }, fan.pct + "%"),
    ),
  );
}

/** The padlock row above the fans: a switch that reads "unlocked" when on (see css/42-fans.css). */
function FanLockBar({ locked, onToggle }) {
  const lockPath = locked ? "M7 11V7a5 5 0 0 1 10 0v4" : "M7 11V7a5 5 0 0 1 9.9-1";
  return h(
    "div",
    {
      className: cx("fan-lock", !locked && "is-unlocked"),
      role: "switch",
      "aria-checked": !locked,
      title: locked ? "Tocca per sbloccare ventole" : "Tocca per bloccare - auto tra 10s",
      onClick: onToggle,
    },
    h(
      "span",
      { className: "fan-lock__icon" },
      h(Svg, { size: 20, strokeWidth: "1.8" }, h("rect", { x: "3", y: "11", width: "18", height: "11", rx: "2", ry: "2" }), h("path", { d: lockPath })),
    ),
    h(
      "span",
      { className: "fan-lock__text" },
      h("span", { className: "fan-lock__label" }, locked ? "Ventole bloccate" : "Ventole sbloccate"),
      h("span", { className: "fan-lock__hint" }, locked ? "Tocca per sbloccare" : "Modifica abilitata"),
    ),
    h("span", { className: "oui-switch" }, h("span", { className: "oui-switch__knob" })),
  );
}

function FanList() {
  const { fans, setSpeed, setInteracting } = useFans();
  const lock = useFanLock();
  return h(
    React.Fragment,
    null,
    h(FanLockBar, { locked: lock.locked, onToggle: lock.toggle }),
    fans.length > 0
      ? h(
          "div",
          { className: "oui-list fan-list" },
          fans.map((fan) =>
            CONTROLLABLE_FANS.includes(fan.label)
              ? h(FanControl, {
                  key: fan.name,
                  fan,
                  locked: lock.locked,
                  onSet: (pct) => setSpeed(fan.name, pct),
                  onInteract: (active) => setInteracting(fan.name, active),
                })
              : h(FanReadout, { key: fan.name, fan }),
          ),
        )
      : h("div", { className: "oui-caption py-4" }, "Nessuna ventola rilevata - in attesa dati Klipper..."),
  );
}
