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
