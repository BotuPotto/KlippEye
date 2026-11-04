/* ============================================================================
   19 · LAYOUT OF THE PAGES (1.50, roadmap 6e part 1)
   Kept on this device (a phone and a computer want different things):
     · collapsed cards: a card with an id has a chevron in its header that folds
       it down to the header (Card / CardHeader in 20-ui-primitives.js);
     · the order of the cards of Home and Control, and the ones hidden there
       (Settings → Appearance).
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
    reset: () => save(empty()),
  };
})();

const useLayout = () => useSyncExternalStore(layoutStore.subscribe, layoutStore.snapshot);

/** The page's cards in the chosen order, without the hidden ones: `cards` is { id: element }. */
function arrangeCards(page, cards) {
  return layoutStore
    .order(page)
    .filter((id) => !layoutStore.isHidden(page, id))
    .map((id) => cards[id] && h(React.Fragment, { key: id }, cards[id]));
}
