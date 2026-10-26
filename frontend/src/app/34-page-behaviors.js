/* ============================================================================
   34 · PAGE-WIDE BEHAVIOURS
   Things that belong to the page rather than to a single card:
     · pull-to-refresh (drag down from the top to reload),
     · links to other sites open in a new tab,
     · inputs inside modals scroll into view when the keyboard opens.
   ========================================================================== */

/* ---------------------------------------------------------------------------
   Pull to refresh
   Touch drag from the very top of the page (any scroll container at its top);
   a mouse drag starting in the top 70 px works too, for desktop testing.
   ------------------------------------------------------------------------- */
const PULL = {
  THRESHOLD: 78, // px of (damped) pull needed to trigger the reload
  MAX: 130, // px, hard limit of the damped pull
  DAMPING: 0.55, // finger distance → indicator distance
  START_SLOP: 8, // px of finger movement before a pull starts
  BAR_HEIGHT: 68,
  MOUSE_ZONE: 70, // mouse drag must start in the top 70 px
  RELOAD_DELAY_MS: 320,
};

const PULL_HINT = "Trascina giù per aggiornare";

/** Scrollable ancestors of `target`, plus the document and the window. */
function scrollableAncestors(target) {
  const found = [];
  for (let el = target; el && el !== document.body && el !== document.documentElement; el = el.parentElement) {
    const overflowY = window.getComputedStyle(el).overflowY;
    if ((overflowY === "auto" || overflowY === "scroll" || el.scrollHeight > el.clientHeight) && el.scrollTop !== undefined) found.push(el);
  }
  found.push(document.documentElement, window);
  return found;
}

function allAtTop(scrollers) {
  return scrollers.every((scroller) => {
    const top = scroller === window || scroller === document.documentElement ? window.scrollY || document.documentElement.scrollTop || 0 : scroller.scrollTop;
    return top <= 2;
  });
}

function PullToRefresh() {
  const barRef = useRef(null);

  useEffect(() => {
    const bar = barRef.current;
    const text = bar.querySelector(".pull-refresh__text");
    let startY = 0;
    let pulling = false;
    let lastPull = 0;
    let scrollers = [];
    let mouseDown = false;

    const reset = () => {
      pulling = false;
      startY = 0;
      lastPull = 0;
      scrollers = [];
    };

    const showPull = (pull) => {
      bar.style.transform = `translateY(${pull - PULL.BAR_HEIGHT}px)`;
      const ready = pull >= PULL.THRESHOLD;
      bar.classList.toggle("is-ready", ready);
      text.textContent = ready ? "Rilascia per aggiornare" : PULL_HINT;
    };

    const onTouchStart = (e) => {
      if (e.touches.length !== 1) return;
      const target = e.target;
      if (target.closest && target.closest("input, textarea, button, [contenteditable]")) return;
      scrollers = scrollableAncestors(target);
      if (!allAtTop(scrollers)) return;
      startY = e.touches[0].clientY;
      lastPull = 0;
    };

    const onTouchMove = (e) => {
      if (startY === 0) return;
      if (!allAtTop(scrollers)) {
        // the page scrolled during the drag: cancel the pull
        if (pulling) {
          pulling = false;
          bar.style.transform = "translateY(-100%)";
          bar.classList.remove("is-dragging", "is-ready");
          document.body.classList.remove("is-pulling");
        }
        return;
      }
      const diff = e.touches[0].clientY - startY;
      if (diff <= 0 || diff <= PULL.START_SLOP) return;
      pulling = true;
      document.body.classList.add("is-pulling");
      bar.classList.add("is-dragging");
      lastPull = Math.min(diff * PULL.DAMPING, PULL.MAX);
      showPull(lastPull);
      if (lastPull > 10) bar.style.transition = "none";
      if (lastPull > 20) e.preventDefault(); // stop the native bounce
    };

    const finish = () => {
      if (!pulling && lastPull < PULL.THRESHOLD) {
        reset();
        return;
      }
      bar.classList.remove("is-dragging");
      bar.style.transition = "transform var(--oui-dur-base) var(--oui-ease)";
      if (lastPull >= PULL.THRESHOLD) {
        bar.style.transform = "translateY(0)";
        bar.classList.add("is-ready");
        text.textContent = "Aggiorno...";
        setTimeout(() => window.location.reload(), PULL.RELOAD_DELAY_MS);
      } else {
        bar.style.transform = "translateY(-100%)";
        setTimeout(() => {
          bar.classList.remove("is-ready");
          document.body.classList.remove("is-pulling");
        }, 260);
      }
      reset();
    };

    const onMouseDown = (e) => {
      if (e.clientY > PULL.MOUSE_ZONE || (window.scrollY || 0) > 2) return;
      mouseDown = true;
      startY = e.clientY;
      scrollers = [window, document.documentElement];
    };
    const onMouseMove = (e) => {
      if (!mouseDown) return;
      const diff = e.clientY - startY;
      if (diff <= PULL.START_SLOP) return;
      pulling = true;
      lastPull = Math.min(diff * PULL.DAMPING, PULL.MAX);
      showPull(lastPull);
    };
    const onMouseUp = () => {
      if (!mouseDown) return;
      mouseDown = false;
      finish();
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", finish, { passive: true });
    window.addEventListener("touchcancel", finish, { passive: true });
    window.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", finish);
      window.removeEventListener("touchcancel", finish);
      window.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return h(
    "div",
    { className: "pull-refresh", ref: barRef },
    h("span", { className: "pull-refresh__arrow" }, "↓"),
    h("span", { className: "pull-refresh__spinner" }),
    h("span", { className: "pull-refresh__text" }, PULL_HINT),
  );
}

/* ---------------------------------------------------------------------------
   External links open in a new tab
   ------------------------------------------------------------------------- */
function openExternalLinkInNewTab(anchor) {
  const href = anchor.getAttribute("href");
  if (!href) return;
  try {
    const url = new URL(href, document.baseURI);
    if ((url.protocol === "http:" || url.protocol === "https:") && url.host !== location.host) {
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
    }
  } catch (e) {}
}

function useExternalLinksInNewTab() {
  useEffect(() => {
    document.querySelectorAll("a[href]").forEach(openExternalLinkInNewTab);
    const onClick = (e) => {
      const anchor = e.target && e.target.closest && e.target.closest("a[href]");
      if (anchor) openExternalLinkInNewTab(anchor);
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);
}

/* ---------------------------------------------------------------------------
   Keep focused inputs visible
   Inputs inside a modal scroll to the middle of the screen once the on-screen
   keyboard has opened; the console input does the same, slightly sooner.
   ------------------------------------------------------------------------- */
const MODAL_INPUT_SCROLL_DELAY_MS = 350;
const CONSOLE_INPUT_SCROLL_DELAY_MS = 300;

function scrollIntoViewSoon(element, delay) {
  setTimeout(() => {
    try {
      element.scrollIntoView({ block: "center", behavior: "smooth" });
    } catch (e) {}
  }, delay);
}

function useModalInputScroll() {
  useEffect(() => {
    const onFocusIn = (e) => {
      const target = e.target;
      if (target.matches && target.matches(".modal input")) scrollIntoViewSoon(target, MODAL_INPUT_SCROLL_DELAY_MS);
    };
    document.addEventListener("focusin", onFocusIn);
    return () => document.removeEventListener("focusin", onFocusIn);
  }, []);
}
