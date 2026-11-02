/* ============================================================================
   15a · BACK (1.24)
   One "back" for the whole dashboard: the phone's back button (the KlippEye app calls window.klippeyeBack(), app 7+) and
   the Escape key. The layers open on top of each other register what "back" means for them; the top one answers:
     · the guide ("?") closes;
     · the guided set-up goes to the previous step (the first step: it closes);
     · the settings menu goes to the page it came from (the menu's history), then closes;
     · any other dialog, sheet or full-screen layer gets an Escape, which they all already handle.
   Nothing open: false, and the app does its own back (the WebView's history, then leaves).
   ========================================================================== */

const backHandlers = []; // [{ fn }], the last one is the layer on top

/** While `active`, `fn()` is what "back" does (it returns false when it had nothing to do). */
function useBackHandler(fn, active = true) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!active) return undefined;
    const entry = { fn: () => ref.current() };
    backHandlers.push(entry);
    return () => {
      const index = backHandlers.indexOf(entry);
      if (index >= 0) backHandlers.splice(index, 1);
    };
  }, [active]);
}

const OTHER_LAYERS = ".modal, .confirm-overlay, .sheet-overlay, .screen, .editor-overlay";

/** Does "back" once. True when something was closed or went back. */
function goBack() {
  for (let index = backHandlers.length - 1; index >= 0; index -= 1) {
    if (backHandlers[index].fn() !== false) return true;
  }
  if (document.querySelector(OTHER_LAYERS)) {
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    (document.activeElement || document.body).dispatchEvent(event);
    return true;
  }
  return false;
}

window.klippeyeBack = goBack; // called by the KlippEye app when the phone's back button is pressed

/* ---------------------------------------------------------------------------
   Sliders that do not move by themselves (1.24)
   On a phone a finger that lands on a slider's track while scrolling the menu used to change the value: now a touch moves
   a slider only when it starts on (or right next to) its knob; anywhere else on the track it is ignored (the page can be
   scrolled from there with the next touch, and the number field next to each slider is there for exact values).
   ------------------------------------------------------------------------- */
const SLIDER_KNOB_REACH_PX = 26;

function sliderKnobX(input) {
  const rect = input.getBoundingClientRect();
  const min = Number(input.min || 0);
  const max = Number(input.max || 100);
  const fraction = max > min ? (Number(input.value) - min) / (max - min) : 0;
  const knob = 22; // the knob's width: its centre runs from knob/2 to width - knob/2
  return rect.left + knob / 2 + fraction * (rect.width - knob);
}

document.addEventListener(
  "touchstart",
  (event) => {
    const input = event.target;
    if (!input || input.tagName !== "INPUT" || input.type !== "range" || event.touches.length !== 1) return;
    if (Math.abs(event.touches[0].clientX - sliderKnobX(input)) > SLIDER_KNOB_REACH_PX) event.preventDefault();
  },
  { capture: true, passive: false },
);
