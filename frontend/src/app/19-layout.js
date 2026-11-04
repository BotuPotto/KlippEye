/* ============================================================================
   19 · LAYOUT OF THE PAGES (1.50, roadmap 6e part 1)
   Kept on this device (a phone and a computer want different things):
     · collapsed cards: a card with an id has a chevron in its header that folds
       it down to the header (Card / CardHeader in 20-ui-primitives.js);
     · the order of the cards of Home and Control, and the ones hidden there
       (Settings → Appearance);
     · 1.51: the small texts that explain how to use a page (.ui-hint: «Tap to
       change»…), shown or not;
     · 1.52: the accent colour (the violet of the logo, or another one);
     · 1.53: the look (One UI, Liquid Glass, Material 3 Expressive, HyperOS 4).
   ========================================================================== */

const LAYOUT_KEY = "ke_layout";
/** The cards of the phone's pages that can be moved or hidden, in their usual order (the print card always stays on top). */
const LAYOUT_PAGES = {
  home: ["camera", "heaters", "temps", "spool", "movement"],
  control: ["console", "extruder", "devices", "macros", "tune", "endstops", "bedmesh"],
};
const layoutCardTitle = (id) =>
  ({
    camera: tx("Camera"),
    heaters: tx("Heaters and fans"),
    temps: tx("Temperatures"),
    spool: tx("Spool"),
    movement: tx("Movement and Z-offset"),
    console: tx("Console"),
    extruder: tx("Extruder"),
    devices: tx("Devices"),
    macros: tx("Macros"),
    tune: tx("Tuning"),
    endstops: tx("Endstops and probe"),
    bedmesh: "Bed mesh",
  })[id] || id;

const layoutStore = (() => {
  const listeners = new Set();
  const empty = () => ({ collapsed: {}, order: {}, hidden: {} });
  let state = empty();
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
    if (saved && typeof saved === "object") state = { ...empty(), ...saved };
  } catch (e) {}
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
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => state,
    toggleCollapsed: (id) => save({ ...state, collapsed: { ...state.collapsed, [id]: !state.collapsed[id] } }),
    expandAll: () => save({ ...state, collapsed: {} }),
    /** The page's cards in the chosen order (new cards of a later release at their usual place, at the end). */
    order(page) {
      const usual = LAYOUT_PAGES[page];
      const chosen = (state.order[page] || []).filter((id) => usual.includes(id));
      return chosen.concat(usual.filter((id) => !chosen.includes(id)));
    },
    move(page, id, step) {
      const list = this.order(page);
      const at = list.indexOf(id);
      const to = at + step;
      if (at < 0 || to < 0 || to >= list.length) return;
      list.splice(at, 1);
      list.splice(to, 0, id);
      save({ ...state, order: { ...state.order, [page]: list } });
    },
    isHidden: (page, id) => (state.hidden[page] || []).includes(id),
    setHidden(page, id, hidden) {
      const list = (state.hidden[page] || []).filter((one) => one !== id);
      save({ ...state, hidden: { ...state.hidden, [page]: hidden ? list.concat(id) : list } });
    },
    setHints: (show) => save({ ...state, hideHints: !show }),
    setAccent: (accent) => save({ ...state, accent }),
    setLook: (look) => save({ ...state, look }),
    reset: () => save({ ...empty(), hideHints: state.hideHints, accent: state.accent, look: state.look }),
  };
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

/** The tokens of an accent colour: { accent, rgb, text, onAccent, backdrop } (null: the logo's violet, the stylesheet's own). */
function accentTokens(accent) {
  const preset = ACCENT_PRESETS.find((one) => one.id === accent);
  const hex = preset ? preset.hex : /^#[0-9a-f]{6}$/i.test(accent || "") ? accent.toLowerCase() : null;
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

function applyAccent() {
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

/** The page's cards in the chosen order, without the hidden ones: `cards` is { id: element }. */
function arrangeCards(page, cards) {
  return layoutStore
    .order(page)
    .filter((id) => !layoutStore.isHidden(page, id))
    .map((id) => cards[id] && h(React.Fragment, { key: id }, cards[id]));
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
