/* ============================================================================
   19 · LAYOUT OF THE PAGES (1.50, roadmap 6e part 1)
   Kept on this device (a phone and a computer want different things):
     · collapsed cards: a card with an id has a chevron in its header that folds
       it down to the header (Card / CardHeader in 20-ui-primitives.js);
     · the order of the cards of Home and Control, and the ones hidden there
       (Settings → Appearance); 1.66: one layout per kind of device, in columns;
     · 1.51: the small texts that explain how to use a page (.ui-hint: «Tap to
       change»…), shown or not;
     · 1.52: the accent colour (the violet of the logo, or another one);
     · 1.53: the look (One UI, Liquid Glass, Material 3 Expressive, HyperOS 4);
     · 1.108: dark, light, or as the device is set (css/05-light.css).
   ========================================================================== */

const LAYOUT_KEY = "ke_layout";
/**
 * 1.66: a layout for each kind of device: a phone, a tablet (two columns of cards) and a
 * computer (the wide layout, 70-desktop-shell.js) each keep their own order and hidden cards. A page is made of columns:
 * one on a phone and a tablet; on a computer the main column and the side one (Dispositivo), the left and the right one
 * (Calibrazione). The defaults are the usual layout; a card missing from a saved layout (a card of a later release)
 * joins its usual column, at the end.
 */
const LAYOUT_DEVICES = ["phone", "tablet", "computer"];
const LAYOUT_DEFAULTS = {
  phone: { home: { main: ["camera", "heaters", "temps", "spool", "movement", "mmu"] }, control: { main: ["console", "extruder", "devices", "macros", "tune", "endstops", "bedmesh", "shaper"] } },
  computer: {
    home: { main: ["camera", "print", "temps"], side: ["heaters", "motion", "fans", "spool", "mmu", "devices", "extruder", "tune"] },
    control: { left: ["bedmesh", "shaper"], right: ["macros", "endstops"] },
  },
};
LAYOUT_DEFAULTS.tablet = LAYOUT_DEFAULTS.phone;
/** Cards that always stay (the print card: the page's reason to be). */
const LAYOUT_FIXED = ["print"];
/** The cards of the phone's pages (1.50), as before: Settings → Appearance and the tests still name them so. */
const LAYOUT_PAGES = { home: LAYOUT_DEFAULTS.phone.home.main, control: LAYOUT_DEFAULTS.phone.control.main };

/** The kind of device this screen is: the computer's layout from 1100 px (70-desktop-shell.js), a tablet from 700. */
function layoutDeviceNow() {
  const width = window.innerWidth || 0;
  return width >= 1100 ? "computer" : width >= 700 ? "tablet" : "phone";
}

const layoutCardTitle = (id, device) =>
  ({
    camera: tx("Camera"),
    heaters: device === "computer" ? tx("Heaters") : tx("Heaters and fans"),
    temps: tx("Temperatures"),
    spool: tx("Spool"),
    mmu: tx("Multi-material unit"),
    movement: tx("Movement and Z-offset"),
    motion: tx("Movement and Z-offset"),
    fans: tx("Fans"),
    print: tx("Printing"),
    console: tx("Console"),
    extruder: tx("Extruder"),
    devices: tx("Devices"),
    macros: tx("Macros"),
    tune: tx("Tuning"),
    endstops: tx("Endstops and probe"),
    bedmesh: tx("Height map / mesh"),
    shaper: tx("Input shaper"),
  })[id] || id;

const layoutStore = (() => {
  const listeners = new Set();
  const empty = () => ({ collapsed: {}, devices: {} });
  let state = empty();
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
    if (saved && typeof saved === "object") state = { ...empty(), ...saved };
  } catch (e) {}
  // 1.66: the order and the hidden cards of 1.50 (one layout) become the phone's and the tablet's
  if ((state.order || state.hidden) && !Object.keys(state.devices || {}).length) {
    const old = {};
    for (const page of Object.keys(LAYOUT_DEFAULTS.phone)) {
      const usual = LAYOUT_DEFAULTS.phone[page].main;
      const chosen = ((state.order || {})[page] || []).filter((id) => usual.includes(id));
      old[page] = { columns: { main: chosen.concat(usual.filter((id) => !chosen.includes(id))) }, hidden: ((state.hidden || {})[page] || []).filter((id) => usual.includes(id)) };
    }
    state = { ...state, devices: { phone: old, tablet: JSON.parse(JSON.stringify(old)) } };
    delete state.order;
    delete state.hidden;
  }
  // 1.56: the endstops card folds like the others (open unless it was folded again with its own old fold)
  try {
    if (localStorage.getItem("ke_endstops_open") === "0" && !("endstops" in state.collapsed)) {
      state = { ...state, collapsed: { ...state.collapsed, endstops: true } };
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(state));
    }
    localStorage.removeItem("ke_endstops_open");
  } catch (e) {}
  const save = (next) => {
    state = next;
    try {
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(state));
    } catch (e) {}
    listeners.forEach((fn) => fn());
  };
  // the kind of device changes with the window (a tablet turned, a browser made wider): the pages follow
  let device = layoutDeviceNow();
  window.addEventListener("resize", () => {
    const now = layoutDeviceNow();
    if (now === device) return;
    device = now;
    state = { ...state };
    listeners.forEach((fn) => fn());
  });
  const saved = (page, dev) => ((state.devices[dev] || {})[page]) || {};
  const store = {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => state,
    device: () => device,
    toggleCollapsed: (id) => save({ ...state, collapsed: { ...state.collapsed, [id]: !state.collapsed[id] } }),
    expandAll: () => save({ ...state, collapsed: {} }),
    /** { column: [card ids] } of a page on a kind of device: the saved layout, fixed up with the usual one. */
    columns(page, dev = device) {
      const usual = LAYOUT_DEFAULTS[dev][page];
      const known = Object.values(usual).flat();
      const chosen = saved(page, dev).columns || {};
      const out = {};
      const placed = new Set();
      for (const column of Object.keys(usual)) {
        out[column] = (Array.isArray(chosen[column]) ? chosen[column] : usual[column]).filter((id) => known.includes(id) && !placed.has(id) && (placed.add(id), true));
      }
      for (const column of Object.keys(usual)) for (const id of usual[column]) if (!placed.has(id)) (out[column].push(id), placed.add(id));
      return out;
    },
    /** The cards of a page's column in order, the hidden ones left out. */
    shown(page, column = "main", dev = device) {
      return (this.columns(page, dev)[column] || []).filter((id) => !this.isHidden(page, id, dev));
    },
    /** The phone's single list (1.50): the page's columns one after the other. */
    order(page, dev = device) {
      return Object.values(this.columns(page, dev)).flat();
    },
    /** Puts a card in a column at a place (a drag in Settings → Appearance). */
    place(page, id, column, index, dev = device) {
      const columns = this.columns(page, dev);
      if (!columns[column]) return;
      for (const name of Object.keys(columns)) columns[name] = columns[name].filter((one) => one !== id);
      columns[column].splice(Math.max(0, Math.min(index, columns[column].length)), 0, id);
      const pages = { ...(state.devices[dev] || {}), [page]: { ...saved(page, dev), columns } };
      save({ ...state, devices: { ...state.devices, [dev]: pages } });
    },
    move(page, id, step, dev = device) {
      const columns = this.columns(page, dev);
      const column = Object.keys(columns).find((name) => columns[name].includes(id));
      if (!column) return;
      const at = columns[column].indexOf(id);
      const to = at + step;
      if (to < 0 || to >= columns[column].length) return;
      this.place(page, id, column, to, dev);
    },
    isHidden: (page, id, dev = device) => !LAYOUT_FIXED.includes(id) && (saved(page, dev).hidden || []).includes(id),
    setHidden(page, id, hidden, dev = device) {
      if (LAYOUT_FIXED.includes(id)) return;
      const list = (saved(page, dev).hidden || []).filter((one) => one !== id);
      const pages = { ...(state.devices[dev] || {}), [page]: { ...saved(page, dev), hidden: hidden ? list.concat(id) : list } };
      save({ ...state, devices: { ...state.devices, [dev]: pages } });
    },
    /** The usual layout again for one kind of device (or every one). */
    resetDevice: (dev) => save({ ...state, devices: dev ? { ...state.devices, [dev]: {} } : {} }),
    setHints: (show) => save({ ...state, hideHints: !show }),
    setAccent: (accent) => save({ ...state, accent }),
    setLook: (look) => save({ ...state, look }),
    setMode: (mode) => save({ ...state, mode }),
    reset: () => save({ ...empty(), hideHints: state.hideHints, accent: state.accent, look: state.look, mode: state.mode }),
  };
  return store;
})();

const useLayout = () => useSyncExternalStore(layoutStore.subscribe, layoutStore.snapshot);

/** The hints hidden or not: a class on the page, read by css/15-surfaces.css. */
function applyHints() {
  document.documentElement.classList.toggle("hide-hints", Boolean(layoutStore.snapshot().hideHints));
}
applyHints();
layoutStore.subscribe(applyHints);

/* ---------------------------------------------------------------------------
   The accent colour (1.52)
   A preset or any colour from the wheel. The page is dark, so a colour is made light enough for dark text on it (a
   filled button) and to stand out on the glass: its lightness is kept between 62 % and 82 %. The other accent tokens of
   css/00-tokens.css (text, soft, on-accent, the backdrop's glow) are worked out from it.
   ------------------------------------------------------------------------- */
const ACCENT_PRESETS = [
  { id: "violet", hex: "#b79cff" },
  { id: "blue", hex: "#8ab4ff" },
  { id: "teal", hex: "#5fd4c4" },
  { id: "green", hex: "#8fdc7a" },
  { id: "amber", hex: "#ffc06b" },
  { id: "pink", hex: "#ff9ccf" },
];
const accentLabel = (id) => ({ violet: tx("Violet"), blue: tx("Blue"), teal: tx("Teal"), green: tx("Green"), amber: tx("Amber"), pink: tx("Pink") })[id] || id;

function hexToHsl(hex) {
  const value = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map((x) => x / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const hue = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [hue * 60, s, l];
}
function hslToRgb(h, s, l) {
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)].map((x) => Math.round(x * 255));
}
const rgbHex = (rgb) => "#" + rgb.map((x) => x.toString(16).padStart(2, "0")).join("");

/**
 * The tokens of an accent colour: { accent, rgb, text, onAccent, backdrop } (null: the logo's violet, the stylesheet's
 * own). 1.108: on the light page the colour is made deeper instead (white text on it, and it must stand out on white).
 */
function accentTokens(accent, light = modeIsLight()) {
  const preset = ACCENT_PRESETS.find((one) => one.id === accent);
  const hex = preset ? preset.hex : /^#[0-9a-f]{6}$/i.test(accent || "") ? accent.toLowerCase() : light ? ACCENT_PRESETS[0].hex : null;
  if (light) {
    const [h, s0] = hexToHsl(hex);
    const s = Math.max(0.5, Math.min(0.85, s0));
    const rgb = hslToRgb(h, s, 0.5);
    return {
      accent: rgbHex(rgb),
      rgb: rgb.join(", "),
      text: rgbHex(hslToRgb(h, s, 0.4)),
      onAccent: "#ffffff",
      backdrop: hslToRgb(h, Math.min(1, s + 0.1), 0.72).join(", "),
    };
  }
  if (!hex || hex === ACCENT_PRESETS[0].hex) return null;
  const [h, s0, l0] = hexToHsl(hex);
  const s = Math.max(0.45, s0);
  const l = Math.max(0.62, Math.min(0.82, l0));
  const rgb = hslToRgb(h, s, l);
  return {
    accent: rgbHex(rgb),
    rgb: rgb.join(", "),
    text: rgbHex(hslToRgb(h, s, Math.min(0.9, l + 0.08))),
    onAccent: rgbHex(hslToRgb(h, Math.min(s, 0.6), 0.14)),
    backdrop: hslToRgb(h, Math.min(1, s + 0.1), Math.max(0.4, l - 0.14)).join(", "),
  };
}

/* ---------------------------------------------------------------------------
   Dark or light (1.108): "dark" (the usual), "light", or "auto" (as the device is set, following it when it changes).
   <html data-mode="light"> switches the tokens (css/05-light.css); the browser's bar takes the page's colour.
   ------------------------------------------------------------------------- */
const MODES = ["dark", "light", "auto"];
const modeLabel = (id) => ({ dark: txc("theme", "Dark"), light: txc("theme", "Light"), auto: tx("As the device") })[id];
const MODE_QUERY = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: light)") : null;
function modeIsLight() {
  const mode = MODES.includes(layoutStore.snapshot().mode) ? layoutStore.snapshot().mode : "dark";
  return mode === "light" || (mode === "auto" && Boolean(MODE_QUERY && MODE_QUERY.matches));
}
function applyMode() {
  const light = modeIsLight();
  const root = document.documentElement;
  if (light) root.setAttribute("data-mode", "light");
  else root.removeAttribute("data-mode");
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", light ? "#eef0f5" : "#040507");
}

function applyAccent() {
  applyMode();
  const tokens = accentTokens(layoutStore.snapshot().accent);
  const style = document.documentElement.style;
  const set = (name, value) => (value ? style.setProperty(name, value) : style.removeProperty(name));
  set("--oui-accent", tokens && tokens.accent);
  set("--oui-accent-strong", tokens && tokens.accent);
  set("--oui-accent-rgb", tokens && tokens.rgb);
  set("--oui-accent-text", tokens && tokens.text);
  set("--oui-on-accent", tokens && tokens.onAccent);
  set("--oui-backdrop-rgb", tokens && tokens.backdrop);
}
applyAccent();
layoutStore.subscribe(applyAccent);
if (MODE_QUERY) {
  const follow = () => applyAccent();   // the device switched between dark and light (only "auto" changes)
  if (typeof MODE_QUERY.addEventListener === "function") MODE_QUERY.addEventListener("change", follow);
  else if (typeof MODE_QUERY.addListener === "function") MODE_QUERY.addListener(follow);
}

/** A column of the page's cards in the chosen order, without the hidden ones: `cards` is { id: element }. */
function arrangeCards(page, cards, column = "main") {
  return layoutStore.shown(page, column).map((id) => cards[id] && h(React.Fragment, { key: id }, cards[id]));
}

/* ---------------------------------------------------------------------------
   The look (1.53): css/90-looks.css dresses the page after another phone
   ------------------------------------------------------------------------- */
const LOOKS = ["oneui", "glass", "material", "hyperos"];
const lookLabel = (id) => ({ oneui: "One UI", glass: "Liquid Glass", material: "Material 3 Expressive", hyperos: "HyperOS 4" })[id];
const lookDetail = (id) =>
  ({
    oneui: tx("Glass cards on the logo's glow (the usual one)"),
    glass: tx("Clearer glass, a light edge, rounder corners"),
    material: tx("Solid surfaces tinted by the colour, bolder titles"),
    hyperos: tx("Black page, flat grey cards"),
  })[id];
function applyLook() {
  const look = layoutStore.snapshot().look;
  if (LOOKS.includes(look) && look !== "oneui") document.documentElement.setAttribute("data-look", look);
  else document.documentElement.removeAttribute("data-look");
}
applyLook();
layoutStore.subscribe(applyLook);
