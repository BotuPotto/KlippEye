/* ============================================================================
   22 · MOTION
   Two small helpers that give the interface its movement; the curves, times and
   keyframes are in css/00-tokens.css and css/22-motion.css.

   · Presence  keeps a layer (dialog, sheet, menu, full-screen editor) on screen
               for one exit animation after the code that shows it has let go.
   · Collapse  opens and closes a section with a height transition.

   Both render nothing extra while closed, so a page at rest has the same DOM as
   before. With "reduce motion" on, the times in the stylesheet drop to 1 ms.
   ========================================================================== */

/** How long a layer needs to leave. Keep in step with --oui-dur-exit (css/00-tokens.css). */
const LAYER_EXIT_MS = 150;
/** How long a section needs to fold. Keep in step with --oui-dur-slow. */
const COLLAPSE_MS = 350;

/**
 * Use:  h(Presence, null, open && h(Dialog, ...))
 * While `children` is falsy the last thing that was shown stays for LAYER_EXIT_MS, inside a wrapper without a
 * box of its own that is marked data-presence="leaving"; css/22-motion.css plays the exit and ignores the taps.
 */
function Presence({ children, exitMs = LAYER_EXIT_MS }) {
  const present = Boolean(children);
  const last = useRef(children);
  const [alive, setAlive] = useState(present);
  if (present) last.current = children;

  useEffect(() => {
    if (present) {
      setAlive(true);
      return undefined;
    }
    const timer = setTimeout(() => setAlive(false), exitMs);
    return () => clearTimeout(timer);
  }, [present]);

  if (!present && !alive) return null;
  return h("div", { className: "oui-presence", "data-presence": present ? "present" : "leaving" }, last.current);
}

/**
 * Use:  h(Collapse, { open }, content)
 * The wrapper is always there (that is what lets the height move); the content is mounted while open and for
 * the time it takes to fold. A section that starts open does not animate.
 */
function Collapse({ open, children }) {
  const [alive, setAlive] = useState(open);
  const last = useRef(children);
  if (open) last.current = children;

  useEffect(() => {
    if (open) {
      setAlive(true);
      return undefined;
    }
    const timer = setTimeout(() => setAlive(false), COLLAPSE_MS);
    return () => clearTimeout(timer);
  }, [open]);

  return h("div", { className: cx("oui-collapse", open && "is-open") }, h("div", { className: "oui-collapse__inner" }, (open || alive) && last.current));
}

/* ---------------------------------------------------------------------------
   1.134: things come from where they were touched, and move instead of jumping
   ------------------------------------------------------------------------- */

/** The spring of css/00-tokens.css (curve and length), for the motions made here in code. */
function springTiming() {
  const css = getComputedStyle(document.documentElement);
  return { easing: css.getPropertyValue("--oui-spring").trim() || "ease-out", duration: parseFloat(css.getPropertyValue("--oui-dur-spring")) || 550 };
}

/* A dialog grows out of the point that was tapped: its transform-origin goes there as it is added (css/22-motion.css,
   oui-pop). The box is read with the animation switched off for a moment, or the half-grown size would be read. */
let lastTap = null;
document.addEventListener("pointerdown", (event) => (lastTap = { x: event.clientX, y: event.clientY, at: Date.now() }), true);
if (typeof MutationObserver === "function") {
  new MutationObserver((records) => {
    if (!lastTap || Date.now() - lastTap.at > 1000) return;
    for (const record of records)
      for (const node of record.addedNodes) {
        if (node.nodeType !== 1) continue;
        const cards = node.matches(".modal-card, .confirm-card, .sheet-card") ? [node] : node.querySelectorAll(".modal-card, .confirm-card, .sheet-card");
        for (const card of cards) {
          card.style.animation = "none";
          const box = card.getBoundingClientRect();
          card.style.transformOrigin = lastTap.x - box.left + "px " + (lastTap.y - box.top) + "px";
          card.style.animation = "";
        }
      }
  }).observe(document.body, { childList: true, subtree: true });
}

/**
 * The cards of a page slide to their new places when `moment` changes (the ones that arrive rise by themselves:
 * css/22-motion.css). A card is known by the data-slot of its wrapper; places are taken after every
 * render with offsetTop, which neither scrolling nor a running animation changes.
 */
function useCardMorph(listRef, moment) {
  const places = useRef(new Map());
  const keyOf = (el) => el.getAttribute("data-slot");
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list || !places.current.size) return;
    const timing = springTiming();
    for (const el of list.children) {
      const was = places.current.get(keyOf(el));
      const shift = was === undefined ? 0 : was - el.offsetTop;
      if (Math.abs(shift) > 1 && el.animate) el.animate([{ transform: "translateY(" + shift + "px)" }, { transform: "none" }], timing);
    }
  }, [moment]);
  useLayoutEffect(() => {
    const list = listRef.current;
    if (list) places.current = new Map([...list.children].map((el) => [keyOf(el), el.offsetTop]));
  });
}
