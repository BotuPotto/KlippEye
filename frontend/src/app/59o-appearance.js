/* ============================================================================
   59o · APPEARANCE (1.50, roadmap 6e)
   Settings → Appearance, what this device shows and how (kept on it):
     · the order of the cards of Home and Control, and the ones hidden there;
       1.66: dragged, in columns, one layout per kind of device (LayoutEditor);
     · the folded cards (every card with a chevron can be folded on its page):
       how many, and "open them all";
     · 1.51: the hints, the small texts that explain how to use a page;
     · 1.52: the accent colour: the logo's violet, a few others, or any colour;
     · 1.53: the look: One UI (the usual), Liquid Glass, Material 3 Expressive, HyperOS 4.
   ========================================================================== */

const LAYOUT_DEVICE_LABELS = () => ({ phone: tx("Phone"), tablet: tx("Tablet"), computer: tx("Computer") });
const LAYOUT_PAGE_LABELS = (device) => (device === "computer" ? { home: tx("Device"), control: tx("Calibration") } : { home: "Home", control: tx("Control") });
const LAYOUT_COLUMN_LABELS = () => ({ main: tx("Main column"), side: tx("Side column"), left: tx("Left"), right: tx("Right") });

/**
 * 1.66: the cards of a page, as a small drawing of it: one column on a phone and a tablet, two on a
 * computer. A card is dragged by its handle (finger or mouse) to its new place, also into the other column; the arrows
 * do the same one step at a time, the switch shows or hides it. Each kind of device keeps its own layout: the one of
 * this screen is chosen at first and marked.
 */
function LayoutEditor() {
  useLayout();
  const here = layoutStore.device();
  const [device, setDevice] = useState(here);
  const [page, setPage] = useState("home");
  const [drag, setDrag] = useState(null); // { id, x, y, dx, dy, target: { column, index } }
  const boardRef = useRef(null);
  const columns = layoutStore.columns(page, device);
  const names = Object.keys(columns);
  const title = (id) => layoutCardTitle(id, device);

  /** Where a drag at (x, y) would drop: the column under the pointer, before the row whose middle is below it. */
  const dropAt = (x, y, id) => {
    const board = boardRef.current;
    if (!board) return null;
    let best = null;
    for (const column of board.querySelectorAll("[data-layout-column]")) {
      const box = column.getBoundingClientRect();
      if (x < box.left - 24 || x > box.right + 24) continue;
      const rows = [...column.querySelectorAll("[data-layout-card]")].filter((row) => row.getAttribute("data-layout-card") !== id);
      let index = rows.length;
      for (let i = 0; i < rows.length; i++) {
        const r = rows[i].getBoundingClientRect();
        if (y < r.top + r.height / 2) {
          index = i;
          break;
        }
      }
      best = { column: column.getAttribute("data-layout-column"), index };
    }
    return best;
  };
  const startDrag = (event, id) => {
    if (event.button !== undefined && event.button !== 0) return;
    event.preventDefault();
    const row = event.currentTarget.closest("[data-layout-card]");
    const box = row.getBoundingClientRect();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch (e) {}
    setDrag({ id, x: event.clientX, y: event.clientY, dx: event.clientX - box.left, dy: event.clientY - box.top, width: box.width, target: dropAt(event.clientX, event.clientY, id) });
  };
  const moveDrag = (event) => {
    if (!drag) return;
    setDrag({ ...drag, x: event.clientX, y: event.clientY, target: dropAt(event.clientX, event.clientY, drag.id) || drag.target });
  };
  const endDrag = () => {
    if (drag && drag.target) layoutStore.place(page, drag.id, drag.target.column, drag.target.index, device);
    setDrag(null);
  };

  const row = (id, column, index, list) => {
    const hidden = layoutStore.isHidden(page, id, device);
    const fixed = LAYOUT_FIXED.includes(id);
    const other = names.find((name) => name !== column);
    const dragging = drag && drag.id === id;
    return h(
      React.Fragment,
      { key: id },
      drag && drag.target && drag.target.column === column && drag.target.index === index && !dragging && h("div", { className: "layout-drop", "aria-hidden": "true" }),
      h(
        "div",
        { className: cx("layout-row", hidden && "is-hidden", dragging && "is-dragging"), "data-layout-card": id, style: dragging ? { position: "fixed", left: drag.x - drag.dx + "px", top: drag.y - drag.dy + "px", width: drag.width + "px", zIndex: 5 } : undefined },
        h(
          "button",
          { type: "button", className: "layout-row__grip", "aria-label": tx("Drag: {name}", { name: title(id) }), title: tx("Drag to move"), onPointerDown: (event) => startDrag(event, id), onPointerMove: moveDrag, onPointerUp: endDrag, onPointerCancel: () => setDrag(null) },
          h(Icons.Menu, { size: 16 }),
        ),
        h("span", { className: "layout-row__name" }, title(id)),
        // in two columns (a narrow drawing) the drag and the arrow to the other column; in one, the arrows up and down too
        !other && h("button", { type: "button", className: "layout-row__btn", "aria-label": tx("Up") + ": " + title(id), disabled: index === 0, onClick: () => layoutStore.move(page, id, -1, device) }, h(Icons.ArrowUp, { size: 16 })),
        !other && h("button", { type: "button", className: "layout-row__btn", "aria-label": tx("Down") + ": " + title(id), disabled: index === list.length - 1, onClick: () => layoutStore.move(page, id, 1, device) }, h(Icons.ArrowDown, { size: 16 })),
        other && h("button", { type: "button", className: "layout-row__btn", "aria-label": tx("To the other column") + ": " + title(id), title: tx("To the other column"), onClick: () => layoutStore.place(page, id, other, 999, device) }, h(names.indexOf(column) === 0 ? Icons.Forward : Icons.Back, { size: 16 })),
        fixed
          ? h("span", { className: "layout-row__fixed" }, tx("always"))
          : h("button", { type: "button", role: "switch", "aria-checked": !hidden, "aria-label": tx("Show «{name}»", { name: title(id) }), className: cx("layout-row__switch", !hidden && "is-on"), onClick: () => layoutStore.setHidden(page, id, !hidden, device) }, h("span", { className: "oui-switch" }, h("span", { className: "oui-switch__knob" }))),
      ),
    );
  };

  const devices = LAYOUT_DEVICE_LABELS();
  const pages = LAYOUT_PAGE_LABELS(device);
  return h(
    SettingsGroup,
    { title: tx("Cards"), note: tx("Drag a card by its handle (or use the arrows) to move it, also into the other column; the switch shows or hides it. Each kind of device keeps its own layout.") },
    h(ChipChoice, { label: tx("Kind of device"), options: LAYOUT_DEVICES.map((id) => ({ id, label: devices[id] + (id === here ? " · " + tx("this one") : "") })), value: device, onChange: (id) => (setDevice(id), setDrag(null)) }),
    h(ChipChoice, { label: tx("Page"), options: Object.keys(pages).map((id) => ({ id, label: pages[id] })), value: page, onChange: (id) => (setPage(id), setDrag(null)) }),
    h(
      "div",
      { ref: boardRef, className: cx("layout-board", names.length > 1 && "layout-board--columns", "layout-board--" + device), "data-layout-page": page, "data-layout-device": device },
      names.map((column) =>
        h(
          "div",
          { key: column, className: "layout-col", "data-layout-column": column },
          names.length > 1 && h("div", { className: "layout-col__title" }, LAYOUT_COLUMN_LABELS()[column]),
          h("div", { className: "oui-list layout-list" }, columns[column].map((id, index, list) => row(id, column, index, list)), drag && drag.target && drag.target.column === column && drag.target.index >= columns[column].filter((id) => id !== drag.id).length && h("div", { className: "layout-drop", "aria-hidden": "true" })),
        ),
      ),
    ),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-layout-reset": device, onClick: () => layoutStore.resetDevice(device) }, h(Icons.RotateCcw, { size: 16 }), tx("Usual layout for: {device}", { device: devices[device] })),
  );
}

function AccentChoice() {
  const layout = useLayout();
  const current = layout.accent || "violet";
  const custom = !ACCENT_PRESETS.some((preset) => preset.id === current);
  const [wheel, setWheel] = useState(custom);
  return h(
    SettingsGroup,
    { title: tx("Colour"), note: tx("The colour of buttons, switches and highlights on this device. A colour that is too dark or too pale is made lighter or deeper, so that it reads on the dark page.") },
    h(
      "div",
      { className: "accent-swatches", role: "radiogroup", "aria-label": tx("Colour") },
      ACCENT_PRESETS.map((preset) =>
        h(
          "button",
          { key: preset.id, type: "button", role: "radio", "aria-checked": current === preset.id, className: cx("accent-swatch", current === preset.id && "is-on"), "data-accent": preset.id, onClick: () => (setWheel(false), layoutStore.setAccent(preset.id === "violet" ? null : preset.id)) },
          h("span", { className: "accent-swatch__dot", style: { background: preset.hex } }),
          h("span", { className: "accent-swatch__name" }, accentLabel(preset.id)),
        ),
      ),
      h(
        "button",
        { type: "button", role: "radio", "aria-checked": custom, className: cx("accent-swatch", custom && "is-on"), "data-accent": "custom", onClick: () => setWheel(true) },
        h("span", { className: "accent-swatch__dot accent-swatch__dot--wheel", style: custom ? { background: (accentTokens(current) || {}).accent } : undefined }),
        h("span", { className: "accent-swatch__name" }, tx("Your own")),
      ),
    ),
    wheel && h("div", { className: "accent-wheel" }, h(ColorWheel, { value: custom ? current : "#7c5cff", brightness: true, onChange: (hex) => layoutStore.setAccent(hex) })),
  );
}

function LookChoice() {
  const layout = useLayout();
  const current = LOOKS.includes(layout.look) ? layout.look : "oneui";
  return h(
    SettingsGroup,
    { title: tx("Look"), note: tx("The same page and colours, dressed after another phone. On this device.") },
    h(
      "div",
      { className: "look-choices", role: "radiogroup", "aria-label": tx("Look") },
      LOOKS.map((id) =>
        h(
          "button",
          { key: id, type: "button", role: "radio", "aria-checked": current === id, className: cx("look-choice", current === id && "is-on"), "data-look-choice": id, onClick: () => layoutStore.setLook(id === "oneui" ? null : id) },
          h("span", { className: "look-choice__preview look-choice__preview--" + id }, h("span", null), h("span", null)),
          h("span", { className: "look-choice__text" }, h("span", { className: "look-choice__name" }, lookLabel(id)), h("span", { className: "look-choice__detail" }, lookDetail(id))),
        ),
      ),
    ),
  );
}

function AppearancePage() {
  const layout = useLayout();
  const folded = Object.values(layout.collapsed).filter(Boolean).length;
  return h(
    React.Fragment,
    null,
    h(AccentChoice),
    h(LookChoice),
    h(
      SettingsGroup,
      { title: tx("Hints") },
      h("div", { className: "oui-list", "data-setting": "hints" }, h(SwitchRow, { title: tx("Show the hints"), detail: tx("The small texts that explain how to use a page: «Tap to change», «Long-press a file…»"), checked: !layout.hideHints, onChange: layoutStore.setHints })),
    ),
    h(LayoutEditor),
    h(
      SettingsGroup,
      { title: tx("Folded cards"), note: tx("The chevron at the top right of a card folds it down to its title; it stays so on this device.") },
      h("p", { className: "set-group__note", "data-folded": folded }, folded === 0 ? tx("No card is folded.") : folded === 1 ? tx("1 card is folded.") : tx("{count} cards are folded.", { count: folded })),
      folded > 0 && h("button", { type: "button", className: "oui-btn oui-btn--sm layout-expand", onClick: layoutStore.expandAll }, tx("Open them all")),
    ),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block layout-reset", onClick: layoutStore.reset }, h(Icons.RotateCcw, { size: 18 }), tx("Usual order, everything shown")),
  );
}

function appearanceSummary() {
  const state = layoutStore.snapshot();
  const look = LOOKS.includes(state.look) && state.look !== "oneui" ? lookLabel(state.look) : "";
  const colour = state.accent ? (ACCENT_PRESETS.some((preset) => preset.id === state.accent) ? accentLabel(state.accent) : tx("Your colour")) : "";
  const device = layoutStore.device();
  const pages = Object.keys(LAYOUT_DEFAULTS[device]);
  const hidden = pages.reduce((sum, page) => sum + layoutStore.order(page, device).filter((id) => layoutStore.isHidden(page, id, device)).length, 0);
  const moved = pages.some((page) => JSON.stringify(layoutStore.columns(page, device)) !== JSON.stringify(LAYOUT_DEFAULTS[device][page]));
  return [look, colour, moved ? tx("Own order") : !hidden && tx("Usual order"), hidden && (hidden === 1 ? tx("1 card hidden") : tx("{count} cards hidden", { count: hidden }))].filter(Boolean).join(" • ");
}
