/* ============================================================================
   59o · APPEARANCE (1.50, roadmap 6e)
   Settings → Appearance, what this device shows and how (kept on it):
     · the order of the cards of Home and Control, and the ones hidden there;
     · the folded cards (every card with a chevron can be folded on its page):
       how many, and "open them all";
     · 1.51: the hints, the small texts that explain how to use a page.
   ========================================================================== */

function LayoutPageEditor({ page, title }) {
  useLayout();
  const order = layoutStore.order(page);
  return h(
    SettingsGroup,
    { title, note: tx("The arrows move a card; the switch shows or hides it on this device.") },
    h(
      "div",
      { className: "oui-list layout-list", "data-layout-page": page },
      order.map((id, index) => {
        const hidden = layoutStore.isHidden(page, id);
        return h(
          "div",
          { key: id, className: cx("layout-row", hidden && "is-hidden"), "data-layout-card": id },
          h("span", { className: "layout-row__name" }, layoutCardTitle(id)),
          h("button", { type: "button", className: "layout-row__btn", "aria-label": tx("Up") + ": " + layoutCardTitle(id), disabled: index === 0, onClick: () => layoutStore.move(page, id, -1) }, h(Icons.ArrowUp, { size: 16 })),
          h("button", { type: "button", className: "layout-row__btn", "aria-label": tx("Down") + ": " + layoutCardTitle(id), disabled: index === order.length - 1, onClick: () => layoutStore.move(page, id, 1) }, h(Icons.ArrowDown, { size: 16 })),
          h("button", { type: "button", role: "switch", "aria-checked": !hidden, "aria-label": tx("Show «{name}»", { name: layoutCardTitle(id) }), className: cx("layout-row__switch", !hidden && "is-on"), onClick: () => layoutStore.setHidden(page, id, !hidden) }, h("span", { className: "oui-switch" }, h("span", { className: "oui-switch__knob" }))),
        );
      }),
    ),
  );
}

function AppearancePage() {
  const layout = useLayout();
  const folded = Object.values(layout.collapsed).filter(Boolean).length;
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Hints") },
      h("div", { className: "oui-list", "data-setting": "hints" }, h(SwitchRow, { title: tx("Show the hints"), detail: tx("The small texts that explain how to use a page: «Tap to change», «Long-press a file…»"), checked: !layout.hideHints, onChange: layoutStore.setHints })),
    ),
    h(LayoutPageEditor, { page: "home", title: tx("Home: the cards") }),
    h(LayoutPageEditor, { page: "control", title: tx("Control: the cards") }),
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
  const hidden = Object.values(state.hidden).reduce((sum, list) => sum + list.length, 0);
  const moved = Object.keys(state.order).some((page) => JSON.stringify(layoutStore.order(page)) !== JSON.stringify(LAYOUT_PAGES[page]));
  if (!hidden && !moved) return tx("Usual order");
  return [moved && tx("Own order"), hidden && (hidden === 1 ? tx("1 card hidden") : tx("{count} cards hidden", { count: hidden }))].filter(Boolean).join(" • ");
}
