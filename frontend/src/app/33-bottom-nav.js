/* ============================================================================
   33 · BOTTOM NAVIGATION
   Five tabs in a floating glass pill. The icons are drawn here (24 px) and
   styled by the .bottom-nav rules in the stylesheet (css/20-layout.css).
   ========================================================================== */

/** Inline SVG icon for each tab. */
const NAV_ICONS = {
  home: [h("path", { key: 1, d: "M3 10 L12 2 L21 10 V20 H3 V10 Z" }), h("path", { key: 2, d: "M9 20 V14 H15 V20" })],
  controllo: [
    h("circle", { key: 1, cx: "12", cy: "12", r: "6" }),
    h("circle", { key: 2, cx: "12", cy: "12", r: "1.5", fill: "currentColor", stroke: "none" }),
    h("path", { key: 3, d: "M12 2 V5" }),
    h("path", { key: 4, d: "M12 19 V22" }),
    h("path", { key: 5, d: "M2 12 H5" }),
    h("path", { key: 6, d: "M19 12 H22" }),
  ],
  files: [h("path", { key: 1, d: "M3 7 C3 5.5 4 5 5 5 H9 L11 8 H19 C20.5 8 21 8.5 21 10 V18 C21 19.5 20.5 20 19 20 H5 C3.5 20 3 19.5 3 18 V7 Z" })],
  // three sliders: each line is broken around its knob so the icon stays transparent
  config: [
    h("path", { key: 1, d: "M3 7 H5 M9 7 H21" }),
    h("circle", { key: 2, cx: "7", cy: "7", r: "2" }),
    h("path", { key: 3, d: "M3 12 H13 M17 12 H21" }),
    h("circle", { key: 4, cx: "15", cy: "12", r: "2" }),
    h("path", { key: 5, d: "M3 17 H7 M11 17 H21" }),
    h("circle", { key: 6, cx: "9", cy: "17", r: "2" }),
  ],
  sistema: [
    h("rect", { key: 1, x: "3", y: "4", width: "18", height: "5", rx: "2" }),
    h("circle", { key: 2, cx: "7", cy: "6.5", r: "1", fill: "currentColor", stroke: "none" }),
    h("rect", { key: 3, x: "3", y: "9.5", width: "18", height: "5", rx: "2" }),
    h("circle", { key: 4, cx: "7", cy: "12", r: "1", fill: "currentColor", stroke: "none" }),
    h("rect", { key: 5, x: "3", y: "15", width: "18", height: "5", rx: "2" }),
    h("circle", { key: 6, cx: "7", cy: "17.5", r: "1", fill: "currentColor", stroke: "none" }),
  ],
};

const NAV_TABS = [
  { id: "home", label: "Home" },
  { id: "controllo", label: tx("Control") },
  { id: "files", label: "Files" },
  { id: "config", label: "Config" },
  { id: "sistema", label: tx("System") },
];

function BottomNav({ active, onSelect }) {
  return h(
    "nav",
    { className: "bottom-nav", "aria-label": tx("Pages"), style: { "--tabs": NAV_TABS.length, "--at": Math.max(0, NAV_TABS.findIndex((tab) => tab.id === active)) } },
    h("span", { className: "bottom-nav__pill", "aria-hidden": "true" }),
    NAV_TABS.map((tab) =>
      h(
        "button",
        { key: tab.id, className: cx("bottom-nav__tab", active === tab.id && "is-active"), "data-tab": tab.id, onClick: () => onSelect(tab.id) },
        h("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeLinecap: "round", strokeLinejoin: "round" }, NAV_ICONS[tab.id]),
        h("span", { className: "bottom-nav__label" }, tab.label),
      ),
    ),
  );
}
