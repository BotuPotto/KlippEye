/* ============================================================================
   20 · UI PRIMITIVES
   Building blocks shared by every page: cards, section titles, icons, toasts,
   dialogs. Class strings are Tailwind utilities (pre-compiled in <style>).
   ========================================================================== */

/** Joins truthy class names. */
const cx = (...parts) => parts.filter(Boolean).join(" ");

/* ---------------------------------------------------------------------------
   Layout primitives (look: css/15-surfaces.css and css/16-controls.css)
   ------------------------------------------------------------------------- */

/** Glass pill button shared by the macro, extrusion and filament buttons (each adds size and layout). */
const PILL_BUTTON_CLASS = "oui-btn";

/** Rounded glass panel used for every dashboard section. `flush` lets the body run edge to edge. */
function Card({ className, flush, children, ...rest }) {
  return h("div", { className: cx("oui-card", flush && "oui-card--flush", className), ...rest }, children);
}

/** Large page title under the top bar (One UI "viewing area"); it scrolls away with the page. */
function PageTitle({ children }) {
  return h("h1", { className: "oui-page-title" }, children);
}

/** Card heading: sentence-case title, optionally with actions on the right. */
function SectionTitle({ children, className }) {
  return h("span", { className: cx("oui-card-title", className) }, children);
}

/** Card header: title on the left, optional actions on the right. */
function CardHeader({ title, children }) {
  return h("div", { className: "oui-card__head" }, h(SectionTitle, null, title), children);
}

/* ---------------------------------------------------------------------------
   Icons — thin wrappers so every SVG shares the same stroke attributes
   ------------------------------------------------------------------------- */
function Svg({ size, viewBox = "0 0 24 24", strokeWidth, stroke = "currentColor", children, ...rest }) {
  return h(
    "svg",
    {
      width: size,
      height: size,
      viewBox,
      fill: "none",
      stroke,
      strokeWidth,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      ...rest,
    },
    children,
  );
}

const HOUSE_PATH = "M3 10.5L12 3L21 10.5V20C21 20.5523 20.5523 21 20 21H15V14H9V21H4C3.44772 21 3 20.5523 3 20V10.5Z";

const Icons = {
  House: ({ size = 14, strokeWidth = "2", stroke }) => h(Svg, { size, strokeWidth, stroke }, h("path", { d: HOUSE_PATH })),
  Save: ({ size = 18 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.7" },
      h("path", { d: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" }),
      h("path", { d: "M17 21v-8H7v8" }),
      h("path", { d: "M7 3v5h8" }),
    ),
  CancelCircle: ({ size = 18 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.7" },
      h("circle", { cx: "12", cy: "12", r: "10" }),
      h("line", { x1: "15", y1: "9", x2: "9", y2: "15" }),
      h("line", { x1: "9", y1: "9", x2: "15", y2: "15" }),
    ),
  Clock: ({ size = 14 }) => h(Svg, { size, strokeWidth: "2" }, h("circle", { cx: "12", cy: "12", r: "9" }), h("path", { d: "M12 7v5l3 2" })),
  Spool: ({ size = 14 }) => h(Svg, { size, strokeWidth: "2" }, h("circle", { cx: "12", cy: "12", r: "9" }), h("circle", { cx: "12", cy: "12", r: "3" })),
  Sort: ({ size = 16 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M7 4v16M7 20l-3-3M7 20l3-3" }), h("path", { d: "M17 20V4M17 4l-3 3M17 4l3 3" })),
  Gear: ({ size = 20 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.8" },
      h("circle", { cx: "12", cy: "12", r: "3" }),
      h("path", { d: "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" }),
    ),
  Download: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M12 4v11M12 15l-4.5-4.5M12 15l4.5-4.5" }), h("path", { d: "M5 19h14" })),
  Refresh: ({ size = 16 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M20 11a8 8 0 1 0-2.3 6.1" }), h("path", { d: "M20 4v7h-7" })),
  Warning: ({ size = 22 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M12 3.5 2.8 19.5h18.4L12 3.5z" }), h("path", { d: "M12 10v4.5" }), h("path", { d: "M12 17.4v.1" })),
  Search: ({ size = 20 }) => h(Svg, { size, strokeWidth: "2" }, h("circle", { cx: "11", cy: "11", r: "7" }), h("path", { d: "M20 20l-4-4" })),
  Code: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M16 18l6-6-6-6" }), h("path", { d: "M8 6l-6 6 6 6" })),
  Trash: ({ size = 20 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.9" },
      h("path", { d: "M3 6h18" }),
      h("path", { d: "M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" }),
      h("path", { d: "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" }),
      h("path", { d: "M10 11v6M14 11v6" }),
    ),
  Chevron: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M6 9l6 6 6-6" })),
  Power: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M12 3v8" }), h("path", { d: "M6.4 6.6a8 8 0 1 0 11.2 0" })),
  /** Bubble level: the calibration menu of the movement card. */
  Level: ({ size = 18 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("rect", { x: "2.5", y: "8", width: "19", height: "8", rx: "3" }), h("circle", { cx: "12", cy: "12", r: "1.6" }), h("path", { d: "M8 8v2.4M16 8v2.4M8 16v-2.4M16 16v-2.4" })),
  /** A screw seen from the side: head, shaft, thread. */
  Screw: ({ size = 20 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("rect", { x: "6.5", y: "2.5", width: "11", height: "3.5", rx: "1.2" }), h("path", { d: "M9.5 6v12.5l2.5 3 2.5-3V6" }), h("path", { d: "M9.5 10h5M9.5 13.5h5M9.5 17h5" })),
  /** Z probe: a pin touching a surface. */
  Probe: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M12 3v12" }), h("path", { d: "M9 15l3 4 3-4" }), h("path", { d: "M5 21h14" })),
  Endstop: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("rect", { x: "3", y: "7", width: "13", height: "10", rx: "2.5" }), h("path", { d: "M16 12h5" }), h("circle", { cx: "8.5", cy: "12", r: "1.4" })),
  /** A line that bends: the twist of an axis. */
  Wave: ({ size = 20 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M3 12c2.5-6.5 5-6.5 7.5 0s5 6.5 7.5 0" }), h("path", { d: "M18 6l3 3-3 3" })),
  RotateCw: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M21 12a9 9 0 1 1-3-6.7" }), h("path", { d: "M21 4v5h-5" })),
  RotateCcw: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M3 12a9 9 0 1 0 3-6.7" }), h("path", { d: "M3 4v5h5" })),
  ArrowUp: ({ size = 20 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M12 19V5" }), h("path", { d: "M5 12l7-7 7 7" })),
  ArrowDown: ({ size = 20 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M12 5v14" }), h("path", { d: "M19 12l-7 7-7-7" })),
  Check: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2.4" }, h("path", { d: "M5 12.5l4.5 4.5L19 7.5" })),
  /** File manager (config files): folder, new folder, new file, upload, rename, move, picture, row menu, plus. */
  Folder: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M3 7.5a2 2 0 0 1 2-2h4.2l2 2.5H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5z" })),
  FolderPlus: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M3 7.5a2 2 0 0 1 2-2h4.2l2 2.5H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5z" }), h("path", { d: "M12 11v5M9.5 13.5h5" })),
  FilePlus: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" }), h("path", { d: "M14 3v5h5" }), h("path", { d: "M12 12v5M9.5 14.5h5" })),
  Upload: ({ size = 20 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M12 16V5M12 5l-4.5 4.5M12 5l4.5 4.5" }), h("path", { d: "M5 19h14" })),
  Pencil: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M4 20h4L19.2 8.8a2.1 2.1 0 0 0-3-3L5 17v3z" }), h("path", { d: "M14.5 7.5l3 3" })),
  Move: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M3 7.5a2 2 0 0 1 2-2h4.2l2 2.5H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5z" }), h("path", { d: "M8.5 13h7M13 10.5l2.5 2.5-2.5 2.5" })),
  Image: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("rect", { x: "3", y: "4", width: "18", height: "16", rx: "3" }), h("circle", { cx: "9", cy: "10", r: "1.6" }), h("path", { d: "M4 18l5-5 4 4 3-3 4 4" })),
  Dots: ({ size = 20 }) => h(Svg, { size, strokeWidth: "0" }, [5, 12, 19].map((cy) => h("circle", { key: cy, cx: "12", cy, r: "1.7", fill: "currentColor" }))),
  Plus: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M12 5v14M5 12h14" })),
  /** The filled paper plane of chat apps (WhatsApp's send button): Material Design "send" glyph. */
  Send: ({ size = 24 }) => h(Svg, { size, strokeWidth: "0" }, h("path", { d: "M2.01 21 23 12 2.01 3 2 10l15 2-15 2z", fill: "currentColor" })),
  Play: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M7 4.5v15l12-7.5z" })),
  Stop: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2" }, h("rect", { x: "6", y: "6", width: "12", height: "12", rx: "2.5" })),
  Rocket: ({ size = 22 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.9" },
      h("path", { d: "M12 2.8c3.1 2.1 4.8 5.2 4.8 8.7v3.6H7.2v-3.6c0-3.5 1.7-6.6 4.8-8.7z" }),
      h("circle", { cx: "12", cy: "9.4", r: "1.7" }),
      h("path", { d: "M7.2 11.8 4.6 14.4v3.7l2.6-1.5M16.8 11.8l2.6 2.6v3.7l-2.6-1.5" }),
      h("path", { d: "M10 17.3 12 21l2-3.7" }),
    ),
  Plug: ({ size = 22 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.9" },
      h("path", { d: "M9 3v4M15 3v4" }),
      h("path", { d: "M6.5 7h11v3.8a5.5 5.5 0 0 1-11 0V7z" }),
      h("path", { d: "M12 16.3V21" }),
    ),
  Chip: ({ size = 20 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.9" },
      h("rect", { x: "6", y: "6", width: "12", height: "12", rx: "2.5" }),
      h("rect", { x: "9.6", y: "9.6", width: "4.8", height: "4.8", rx: "1" }),
      h("path", { d: "M9.5 2.8V6M14.5 2.8V6M9.5 18v3.2M14.5 18v3.2M2.8 9.5H6M2.8 14.5H6M18 9.5h3.2M18 14.5h3.2" }),
    ),
  /* ---- the kinds of file (see app/20a-file-icons.js): the same 24-unit grid and 1.9 stroke as the rest ---- */
  // a printed object: a cube with one layer line across its faces
  Cube: ({ size = 20 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.9" },
      h("path", { d: "M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" }),
      h("path", { d: "M4 7.5l8 4.5 8-4.5M12 12v9" }),
      h("path", { d: "M4 12l8 4.5 8-4.5", strokeOpacity: "0.55" }),
    ),
  // a page with a folded corner and two lines of text: the plain file
  Doc: ({ size = 20 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z" }), h("path", { d: "M14 3v5h5" }), h("path", { d: "M9 13h6M9 17h4" })),
  Sliders: ({ size = 20 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1" }), h("circle", { cx: "15", cy: "7", r: "2" }), h("circle", { cx: "9", cy: "12", r: "2" }), h("circle", { cx: "17", cy: "17", r: "2" })),
  Terminal: ({ size = 20 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("rect", { x: "3", y: "4", width: "18", height: "16", rx: "3.5" }), h("path", { d: "M7.5 9.5l3 2.5-3 2.5" }), h("path", { d: "M13 15h3.5" })),
  Braces: ({ size = 20 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M8.5 4C6.5 4 5.5 5 5.5 7v2c0 1.5-.8 3-2.5 3 1.7 0 2.5 1.5 2.5 3v2c0 2 1 3 3 3" }), h("path", { d: "M15.5 4c2 0 3 1 3 3v2c0 1.5.8 3 2.5 3-1.7 0-2.5 1.5-2.5 3v2c0 2-1 3-3 3" })),
  // take back / do again: a curved arrow turning left / right
  Undo: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M9 14 4 9l5-5" }), h("path", { d: "M4 9h10.5a5.5 5.5 0 0 1 0 11H11" })),
  Redo: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "m15 14 5-5-5-5" }), h("path", { d: "M20 9H9.5a5.5 5.5 0 0 0 0 11H13" })),
  // the hash mark of a comment, and the same crossed out
  Hash: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M9.5 4 8 20M16 4l-1.5 16" }), h("path", { d: "M4.5 9h15M4 15h15" })),
  HashOff: ({ size = 20 }) =>
    h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M9.5 4 8 20M16 4l-1.5 16", strokeOpacity: "0.5" }), h("path", { d: "M4.5 9h15M4 15h15", strokeOpacity: "0.5" }), h("path", { d: "M4 20 20 4" })),
  // a copy kept for safety: the arrow of "go back" around a clock hand
  Backup: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M3 12a9 9 0 1 0 3-6.7" }), h("path", { d: "M3 4v5h5" }), h("path", { d: "M12 8v4.5l3 1.8" })),
  Bulb: ({ size = 20 }) =>
    h(
      Svg,
      { size, strokeWidth: "1.8" },
      h("path", { d: "M9 18h6" }),
      h("path", { d: "M10 21.5h4" }),
      h("path", { d: "M12 2.5a6.5 6.5 0 0 0-3.9 11.7c.6.5.9 1.1.9 1.8V16h6v-.01c0-.7.3-1.3.9-1.8A6.5 6.5 0 0 0 12 2.5Z" }),
    ),
  Emergency: () =>
    h(
      Svg,
      { size: "22", strokeWidth: "2", stroke: "white" },
      h("path", { d: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z", strokeOpacity: "0.2" }),
      h("path", { d: "M12 8v4" }),
      h("path", { d: "M9 13a3 3 0 0 0 6 0" }),
      h("path", { d: "M8 5.5A8.5 8.5 0 0 1 16 5.5" }),
    ),
  /** Settings menu: the menu button, close, back, forward, and one icon per section. */
  Menu: ({ size = 22 }) => h(Svg, { size, strokeWidth: "2" }, h("path", { d: "M4 7h16M4 12h16M4 17h16" })),
  Close: ({ size = 22 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M6 6l12 12M18 6L6 18" })),
  Back: ({ size = 22 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M15 5l-7 7 7 7" })),
  Forward: ({ size = 18 }) => h(Svg, { size, strokeWidth: "2.2" }, h("path", { d: "M9 5l7 7-7 7" })),
  Camera: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M3 8.5a2 2 0 0 1 2-2h2.2l1.4-2h6.8l1.4 2H19a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8.5z" }), h("circle", { cx: "12", cy: "12.5", r: "3.6" })),
  Network: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("circle", { cx: "12", cy: "12", r: "9" }), h("path", { d: "M3 12h18" }), h("path", { d: "M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9S9.4 5.6 12 3z" })),
  Bell: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M6 16.5V11a6 6 0 0 1 12 0v5.5l1.6 2H4.4L6 16.5z" }), h("path", { d: "M10 21a2.2 2.2 0 0 0 4 0" })),
  Language: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M3.5 5.5h10M8.5 3.5v2M6 5.5c.7 3.2 2.8 5.8 6 7.3M11 5.5c-.8 3.5-3.2 6.4-7 8" }), h("path", { d: "M13 20.5l4-9 4 9M14.4 17.5h5.2" })),
  Lock: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("rect", { x: "5", y: "10.5", width: "14", height: "10", rx: "2.2" }), h("path", { d: "M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3" }), h("path", { d: "M12 14.5v2.5" })),
  Sparkle: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" }), h("path", { d: "M19 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8z" })),
  Info: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("circle", { cx: "12", cy: "12", r: "9" }), h("path", { d: "M12 11v5" }), h("circle", { cx: "12", cy: "7.8", r: "0.6", fill: "currentColor" })),
  Layers: ({ size = 20 }) => h(Svg, { size, strokeWidth: "1.9" }, h("path", { d: "M12 3 3 8l9 5 9-5-9-5z" }), h("path", { d: "M3 12.5l9 5 9-5" }), h("path", { d: "M3 17l9 5 9-5" })),
};

/* ---------------------------------------------------------------------------
   Toasts
   Two looks exist in the dashboard and both are kept:
     · "action"  — pill above the bottom bar, confirms taps ("Hotend → 200°")
     · "notice"  — small uppercase pill at the very bottom (fans, save, cancel)
   Anything can call toast.action(...) / toast.notice(...); <ToastHost/> shows them.
   ------------------------------------------------------------------------- */
const toastListeners = new Set();
const toast = {
  action: (message) => toastListeners.forEach((listener) => listener({ kind: "action", message })),
  notice: (message, ms = 2000) => toastListeners.forEach((listener) => listener({ kind: "notice", message, ms })),
};

const ACTION_TOAST_MS = 2200;

function ToastHost() {
  const [actionMessage, setActionMessage] = useState(null);
  const [notice, setNotice] = useState({ message: "", visible: false, created: false });
  const noticeTimer = useRef(null);

  useEffect(() => {
    const listener = (event) => {
      if (event.kind === "action") {
        setActionMessage(event.message);
        return;
      }
      clearTimeout(noticeTimer.current);
      setNotice({ message: event.message, visible: true, created: true });
      noticeTimer.current = setTimeout(() => setNotice((n) => ({ ...n, visible: false })), event.ms);
    };
    toastListeners.add(listener);
    return () => toastListeners.delete(listener);
  }, []);

  useEffect(() => {
    if (!actionMessage) return;
    const timer = setTimeout(() => setActionMessage(null), ACTION_TOAST_MS);
    return () => clearTimeout(timer);
  }, [actionMessage]);

  return h(
    React.Fragment,
    null,
    actionMessage &&
      h(
        "div",
        { className: "toast toast--action" },
        actionMessage,
      ),
    notice.created && h("div", { className: cx("toast toast--notice", notice.visible && "is-visible") }, notice.message),
  );
}

/* ---------------------------------------------------------------------------
   Dialogs
   ------------------------------------------------------------------------- */

/**
 * Locks page scrolling while an overlay is open. Several overlays can be open
 * at once (a confirmation above the editor, say): the page unlocks only when
 * the last one lets go. `acquireScrollLock()` returns the function that lets go.
 */
let scrollLockCount = 0;
function applyScrollLock() {
  const value = scrollLockCount > 0 ? "hidden" : "";
  document.body.style.overflow = value;
  document.documentElement.style.overflow = value;
}
function acquireScrollLock() {
  let held = true;
  scrollLockCount++;
  applyScrollLock();
  return () => {
    if (!held) return;
    held = false;
    scrollLockCount--;
    applyScrollLock();
  };
}
function useBodyScrollLock(active) {
  useEffect(() => (active ? acquireScrollLock() : undefined), [active]);
}

/**
 * Yes/no confirmation card used by SAVE_CONFIG and CANCEL PRINT.
 * `tone` picks the colour set: "neutral" (blue confirm) or "danger" (red confirm).
 */
function ConfirmDialog({ open, tone = "neutral", icon, title, subtitle, message, confirmLabel, cancelLabel = tx("Cancel"), onConfirm, onCancel, zIndex }) {
  useBodyScrollLock(open);
  return h(
    Presence,
    null,
    open &&
      h(
        "div",
        { className: "confirm-overlay", style: zIndex ? { zIndex } : undefined, onClick: (e) => e.target === e.currentTarget && onCancel() },
        h(
          "div",
          { className: cx("confirm-card", tone === "danger" && "confirm-card--danger"), onClick: (e) => e.stopPropagation() },
          h(
            "div",
            { className: "dialog-head" },
            h("div", { className: "dialog-head__icon" }, icon),
            h("div", null, h("div", { className: "dialog-title" }, title), h("div", { className: "dialog-sub" }, subtitle)),
          ),
          h("div", { className: "dialog-text" }, message),
          h(
            "div",
            { className: "oui-btn-row" },
            h("button", { className: "oui-btn", onClick: onCancel }, cancelLabel),
            h("button", { className: cx("oui-btn", tone === "danger" ? "oui-btn--danger" : "oui-btn--primary"), onClick: onConfirm }, confirmLabel),
          ),
        ),
      ),
  );
}
