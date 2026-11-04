/* ============================================================================
   00 · REACT BINDINGS
   React and ReactDOM are third-party code: they live, unmodified, in the vendor
   block that precedes this file. `Pt()` returns React (CommonJS exports) and
   `af()` returns `react-dom/client`.
   ========================================================================== */
const React = Pt();
const { createRoot } = af();
/** 1.63: layers drawn on document.body (a menu inside the top bar would be held in it by its backdrop-filter). */
const { createPortal } = of();
const { useState, useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore, useContext } = React;
/** Hyperscript helper: h(type, props, ...children) */
const h = React.createElement;
