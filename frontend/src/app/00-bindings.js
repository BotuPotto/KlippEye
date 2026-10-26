/* ============================================================================
   00 · REACT BINDINGS
   React and ReactDOM are third-party code: they live, unmodified, in the vendor
   block that precedes this file. `Pt()` returns React (CommonJS exports) and
   `af()` returns `react-dom/client`.
   ========================================================================== */
const React = Pt();
const { createRoot } = af();
const { useState, useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore } = React;
/** Hyperscript helper: h(type, props, ...children) */
const h = React.createElement;
