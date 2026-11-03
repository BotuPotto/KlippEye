/* ============================================================================
   41 · CAMERA & CASE LIGHT
   The camera is shown the way the settings say (app/16-settings.js, "Camera" in the settings menu), like the service
   of Mainsail's webcam page: the WebRTC page served by the printer's nginx (the default), an MJPEG stream, MJPEG
   "adaptive" (one photo after the other) or any web page. Which of the two addresses of the Raspberry (home network
   or ZeroTier) is used depends on how the dashboard itself was reached. The light switch mirrors the real LED, which
   Klipper exposes: the output that drives it (and the klipper-led_effect effects drawn on it), as chosen in
   Settings → Printer functions (16a-printer-functions.js). Whoever switches the light (this page, Mainsail, KlipperScreen,
   a macro, the console), the switch shows what the output really does. Without an output to read (a light switched only
   by macros or G-code) the switch shows what was last asked.
   ========================================================================== */

/** Away at least this long (ms) and the camera page is loaded again on coming back. */
const CAMERA_RELOAD_AFTER_AWAY_MS = 8000;

/* ---------------------------------------------------------------------------
   Light state
   The switch must go where the finger sent it and stay there until Klipper has really followed. Two things
   used to spoil that: a reading that left BEFORE the tap and came back after it put the old state back, and
   Klipper needs a moment (the macro runs, the variable changes) during which readings still show the old state.
   So:
     · every tap starts a new "generation"; readings of an older generation are thrown away (and cancelled);
     · while a wish is pending, readings that disagree are ignored; the first one that agrees settles it;
     · commands go out one at a time and only when needed (on, off, on in a second sends one command);
     · if Klipper has not followed after LIGHT_CONFIRM_MS the switch goes back and says so.
   ------------------------------------------------------------------------- */
/** Reading rhythm while a wish waits to show up in Klipper (the normal rhythm is POLL_MS.light). */
const LIGHT_CONFIRM_POLL_MS = 250;
/** How long after Klipper has answered the command it may still take to show the new state, before we ask once more and give up. */
const LIGHT_CONFIRM_MS = 3500;
/** Absolute limit, from the command's answer: the switch goes back even if no reading comes through. */
const LIGHT_GIVE_UP_MS = 12000;
const LIGHT_SEND_TIMEOUT_MS = 10000;

async function fetchLightState(signal, light) {
  if (!light || !light.object) return null;
  const status = await moonraker.queryObjects(lightQuery(light.object), { signal });
  return lightIsOn(status, light.object);
}

/** Sends the light's "on" or "off" G-code; true when Klipper answered (the backend waits for a macro to finish). */
async function sendLightCommand(turnOn, light) {
  let timer = 0;
  try {
    const timeout = new Promise((_, reject) => (timer = setTimeout(() => reject(new Error("timeout")), LIGHT_SEND_TIMEOUT_MS)));
    const response = await Promise.race([sendBrainGcode(turnOn ? light.on : light.off), timeout]);
    return Boolean(response && response.ok);
  } catch (e) {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * The state machine behind the switch, kept out of React so that it reads top to bottom.
 * `publish({ on, waiting, failures })` is called whenever what the switch shows changes.
 */
function createLightEngine(publish, getLight) {
  let alive = false;
  let real = null; // what Klipper said last (null until the first answer)
  let wish = null; // what the person asked for and Klipper has not shown yet (null: nothing pending)
  let commanded = null; // what the last finished command asked for (null: none since the wish was settled)
  let sending = false; // a command is on its way
  let generation = 0; // grows with every tap
  let loop = 0; // identifies the current reading loop, so that a cancelled one does not reschedule
  let confirmFrom = 0; // time after which a disagreeing reading means "Klipper did not follow"
  let failures = 0;
  let timer = 0;
  let giveUpTimer = 0;
  let reading = null; // AbortController of the reading in flight
  let stopListening = noop; // unsubscribes from "the page is back" (app/15-live.js)
  let shown = null;

  const emit = () => {
    const next = { on: wish !== null ? wish : real === true, waiting: wish !== null, failures };
    if (shown && Object.keys(next).every((key) => next[key] === shown[key])) return;
    shown = next;
    publish(next);
  };

  const settle = () => {
    wish = null;
    commanded = null;
    confirmFrom = 0;
    clearTimeout(giveUpTimer);
    emit();
  };

  /** The switch goes back to what Klipper really has and says so. */
  const giveUp = (message) => {
    if (!alive || wish === null) return;
    settle();
    failures += 1;
    toast.notice(message, 2600);
    emit();
    restartReading(0);
  };

  const readOnce = async () => {
    const startedAt = Date.now();
    const myGeneration = generation;
    const controller = new AbortController(); // fetchFresh also gives every reading a time limit
    reading = controller;
    try {
      const state = await fetchLightState(controller.signal, getLight());
      if (!alive || myGeneration !== generation || state === null) return; // out of date: a tap came after it left
      real = state;
      if (wish === null) return emit();
      if (state === wish && !sending) return settle(); // Klipper has followed
      if (!sending && confirmFrom && startedAt >= confirmFrom) giveUp(tx("The light did not respond")); // asked again after the grace time: still no
    } catch (e) {
      /* cancelled or failed: the next one will do */
    } finally {
      if (reading === controller) reading = null;
    }
  };

  const tick = async () => {
    const mine = loop;
    if (!pageIsHidden()) await readOnce(); // nobody is looking: no need to ask
    if (mine === loop && alive) timer = setTimeout(tick, wish !== null ? LIGHT_CONFIRM_POLL_MS : POLL_MS.light);
  };

  function restartReading(delay) {
    loop += 1;
    clearTimeout(timer);
    if (reading) reading.abort();
    if (alive) timer = setTimeout(tick, delay);
  }

  /** Sends what the person wants, one command at a time, and only if Klipper does not already have it. */
  const pump = async () => {
    if (sending) return;
    sending = true;
    try {
      while (alive && wish !== null) {
        const target = wish;
        if ((commanded !== null ? commanded : real) === target) break;
        if (!(await sendLightCommand(target, getLight()))) {
          sending = false;
          return giveUp(tx("Cannot switch the light"));
        }
        commanded = target;
        if (!getLight().confirmable) real = target; // nothing to read: what was asked is what the switch shows
      }
    } finally {
      sending = false;
    }
    if (!alive || wish === null) return;
    if (real === wish) return settle(); // a reading had already seen it
    confirmFrom = Date.now() + LIGHT_CONFIRM_MS;
    clearTimeout(giveUpTimer);
    giveUpTimer = setTimeout(() => giveUp(tx("The light did not respond")), LIGHT_GIVE_UP_MS);
  };

  return {
    start() {
      alive = true;
      stopListening = onResume(() => restartReading(0)); // back from a sleep: ask at once
      restartReading(0);
    },
    stop() {
      alive = false;
      stopListening();
      clearTimeout(timer);
      clearTimeout(giveUpTimer);
      if (reading) reading.abort();
    },
    toggle() {
      wish = !(wish !== null ? wish : real === true);
      generation += 1; // readings that left before this tap are out of date
      confirmFrom = 0;
      clearTimeout(giveUpTimer);
      emit();
      restartReading(LIGHT_CONFIRM_POLL_MS);
      pump();
    },
  };
}

/** The case light as the button shows it ({ on, waiting, failures }) plus toggle(). */
function useCaseLight() {
  const light = usePrinterFunctions().light;
  const lightRef = useRef(light);
  lightRef.current = light;
  const [view, setView] = useState({ on: false, waiting: false, failures: 0 });
  const engine = useRef(null);
  if (!engine.current) engine.current = createLightEngine(setView, () => lightRef.current);
  const available = light.mode !== "off";
  const key = light.mode + "|" + (light.object ? light.object.object : "") + "|" + light.on + "|" + light.off;
  useEffect(() => {
    if (!available) return undefined;
    engine.current.start();
    return () => engine.current.stop();
  }, [key]);
  return { ...view, available, toggle: engine.current.toggle };
}

/* ---------------------------------------------------------------------------
   Button + card
   ------------------------------------------------------------------------- */
/**
 * The round bulb button (css/41-camera.css): amber when on. It is a switch for screen readers; while a command
 * waits for Klipper it carries aria-busy / .is-waiting (no visible change: the button simply shows what was asked).
 */
function LightButton({ on, waiting, failures, toggle }) {
  return h(
    "button",
    {
      type: "button",
      role: "switch",
      "aria-checked": on,
      "aria-busy": waiting,
      "aria-label": tx("Light"),
      "data-fail": failures ? (failures % 2 ? "odd" : "even") : undefined, // flips on every failure, so the shake plays again
      className: cx("light-btn", on && "is-on", waiting && "is-waiting"),
      onClick: () => toggle(),
    },
    h(Icons.Bulb),
  );
}

/**
 * The camera is a WebRTC page; its stream stops when the phone sleeps and the page does not start it again.
 * This counts the times the dashboard came back after a long absence: used as the iframe's `key`, each one
 * loads the camera page afresh.
 */
function useCameraReloads() {
  const [reloads, setReloads] = useState(0);
  useEffect(() => {
    const reload = () => setReloads((count) => count + 1);
    cameraReloadListeners.add(reload);
    const stopListening = onResume((info) => wasAwayLong(info, CAMERA_RELOAD_AFTER_AWAY_MS) && reload());
    return () => {
      cameraReloadListeners.delete(reload);
      stopListening();
    };
  }, []);
  return reloads;
}

const cameraReloadListeners = new Set();
/** Every camera view loads its page afresh: the camera service was restarted and the old stream is gone. */
function requestCameraReload() {
  cameraReloadListeners.forEach((reload) => reload());
}

/* ---------------------------------------------------------------------------
   The picture
   `className` is the class of the box the picture fills (css/41-camera.css or css/70-desktop.css).
   ------------------------------------------------------------------------- */
const CAMERA_RETRY_MS = 3000;
const withCacheBuster = (url) => url + (url.indexOf("?") >= 0 ? "&" : "?") + "_=" + Date.now();
const flipStyle = (camera) => (camera.flipH || camera.flipV ? { transform: ((camera.flipH ? "scaleX(-1) " : "") + (camera.flipV ? "scaleY(-1)" : "")).trim() } : undefined);

/** Says that the picture is not coming; the camera is tried again by itself. */
const CameraNote = () => h("div", { className: "camera-note", role: "status" }, tx("Camera not reachable…"));

/** MJPEG: the browser keeps the stream open. A stream that breaks is asked for again after a moment. */
function CameraStream({ className, url, style }) {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!failed) return undefined;
    const timer = setTimeout(() => {
      setFailed(false);
      setAttempt((count) => count + 1);
    }, CAMERA_RETRY_MS);
    return () => clearTimeout(timer);
  }, [failed]);
  return h(
    React.Fragment,
    null,
    h("img", { key: attempt, className: cx(className, "camera-img"), src: url, alt: "Camera", style, onLoad: () => setFailed(false), onError: () => setFailed(true) }),
    failed && h(CameraNote),
  );
}

/**
 * MJPEG "adaptive": one photo, then the next, `fps` times a second at most. Two pictures lie on top of each other: the
 * next one loads behind and comes to the front only when it is complete, so the picture never flickers or tears.
 * Nothing is asked while the page is in the background.
 */
function CameraSnapshots({ className, url, fps, style }) {
  const [front, setFront] = useState(0);
  const [failed, setFailed] = useState(false);
  const images = [useRef(null), useRef(null)];
  useEffect(() => {
    let stopped = false;
    let timer = 0;
    let shown = 0;
    const next = (startedAt, wait) => {
      if (stopped) return;
      timer = setTimeout(load, Math.max(0, wait !== undefined ? wait : 1000 / fps - (Date.now() - startedAt)));
    };
    function load() {
      if (stopped) return;
      if (pageIsHidden()) return next(Date.now(), 1000);
      const startedAt = Date.now();
      const back = 1 - shown;
      const image = images[back].current;
      if (!image) return;
      image.onload = () => {
        if (stopped) return;
        shown = back;
        setFront(back);
        setFailed(false);
        next(startedAt);
      };
      image.onerror = () => {
        if (stopped) return;
        setFailed(true);
        next(startedAt, CAMERA_RETRY_MS);
      };
      image.src = withCacheBuster(url);
    }
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
      images.forEach((ref) => {
        if (ref.current) {
          ref.current.onload = null;
          ref.current.onerror = null;
        }
      });
    };
  }, [url, fps]);
  return h(
    React.Fragment,
    null,
    h("div", { className: cx(className, "camera-snaps") }, [0, 1].map((index) => h("img", { key: index, ref: images[index], className: cx("camera-snaps__img", front === index && "is-front"), alt: index === front ? "Camera" : "", style }))),
    failed && h(CameraNote),
  );
}

/** The camera as the settings describe it. `reloads` (useCameraReloads) loads everything afresh. */
function CameraMedia({ className, reloads }) {
  const { settings } = useSettings();
  const camera = settings.camera;
  const url = cameraUrl(settings);
  const style = flipStyle(camera);
  if (camera.method === "mjpeg") return h(CameraStream, { key: "mjpeg" + reloads + url, className, url, style });
  if (camera.method === "adaptive") return h(CameraSnapshots, { key: "adaptive" + reloads, className, url, fps: camera.fps, style });
  return h("iframe", { key: camera.method + reloads, className, src: url, style, allow: "autoplay; fullscreen", loading: "eager", title: "Camera" });
}

/* ---------------------------------------------------------------------------
   Full screen (1.35, roadmap 6b part 6)
   The picture over the whole screen, turned to fit it: the app (1.5.0) hides
   Android's bars and turns the screen to landscape; a browser enters its own
   full screen and locks landscape where it can. When the screen stays upright
   anyway (iPhone, a browser that cannot lock), the picture itself is turned 90°
   ("automatic"); the turn button switches that off and on.
   ------------------------------------------------------------------------- */
const CAMERA_CONTROLS_HIDE_MS = 3500;

/** The size of the window, kept up to date. */
function useViewportSize() {
  const read = () => ({ w: window.innerWidth, h: window.innerHeight });
  const [size, setSize] = useState(read);
  useEffect(() => {
    const update = () => setSize(read());
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);
  return size;
}

/** Enters the full screen of the app or of the browser (and landscape where it can); `onLeft` when the browser leaves it by itself. */
function useScreenTakeover(box, onLeft) {
  useEffect(() => {
    const bridge = nativeBridge();
    if (APP_CAN_FULLSCREEN && bridge && bridge.setFullscreen) {
      try {
        bridge.setFullscreen(true, true);
      } catch (e) {}
      return () => {
        try {
          bridge.setFullscreen(false, false);
        } catch (e) {}
      };
    }
    let entered = false;
    const element = box.current;
    if (element && element.requestFullscreen && !IN_APP_WEBVIEW) {
      element
        .requestFullscreen({ navigationUI: "hide" })
        .then(() => {
          entered = true;
          if (screen.orientation && screen.orientation.lock) return screen.orientation.lock("landscape").catch(noop);
        })
        .catch(noop);
    }
    const onChange = () => entered && !document.fullscreenElement && onLeft(); // Esc or the phone's back in the browser's full screen
    document.addEventListener("fullscreenchange", onChange);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      try {
        if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock();
      } catch (e) {}
      if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(noop);
    };
  }, []);
}

function CameraFullscreen({ onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const box = useRef(null);
  const light = useCaseLight();
  const reloads = useCameraReloads();
  const viewport = useViewportSize();
  const [turn, setTurn] = useState(true); // turn the picture when the screen stays upright
  const [controls, setControls] = useState(true);
  const hideTimer = useRef(null);
  useScreenTakeover(box, onClose);

  const showControls = () => {
    setControls(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setControls(false), CAMERA_CONTROLS_HIDE_MS);
  };
  useEffect(() => {
    showControls();
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(hideTimer.current);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const rotated = turn && viewport.h > viewport.w;
  const stage = rotated ? { width: viewport.h + "px", height: viewport.w + "px" } : undefined;
  const control = (label, icon, onClick, extra) =>
    h("button", { type: "button", className: cx("camera-full__btn", extra), "aria-label": label, title: label, onClick: (event) => (event.stopPropagation(), showControls(), onClick()) }, icon);

  return h(
    "div",
    { ref: box, className: "camera-full", role: "dialog", "aria-label": "Camera", "data-rotated": rotated ? "true" : "false", onClick: showControls, onPointerMove: (event) => event.pointerType === "mouse" && showControls() },
    h(
      "div",
      { className: cx("camera-full__stage", rotated && "is-rotated"), style: stage },
      h(CameraMedia, { className: "camera-full__video", reloads }),
      // over the picture: a tap on the camera page (an iframe) would not reach this page
      h("div", { className: "camera-full__tap", "aria-hidden": "true" }),
      h(
        "div",
        { className: cx("camera-full__controls", controls && "is-shown") },
        light.available && h("div", { className: "camera-full__light", onClick: (event) => event.stopPropagation() }, h(LightButton, light)),
        viewport.h > viewport.w && control(turn ? tx("Do not turn the picture") : tx("Turn the picture"), h(Icons.RotateCw, { size: 20 }), () => setTurn(!turn), turn && "is-on"),
        control(tx("Leave full screen"), h(Icons.Shrink, { size: 20 }), onClose),
      ),
    ),
  );
}

/** The button that opens the full screen. */
const CameraFullscreenButton = ({ onOpen, className }) =>
  h("button", { type: "button", className: cx("icon-btn camera-full-open", className), "aria-label": tx("Full screen"), title: tx("Full screen"), onClick: onOpen }, h(Icons.Expand, { size: 18 }));

function CameraCard() {
  const light = useCaseLight();
  const reloads = useCameraReloads();
  const [full, setFull] = useState(false);
  // the full screen next to the card, not in it (a card that moves would carry a fixed layer with it)
  return h(
    React.Fragment,
    null,
    h(
      Card,
      null,
      h(CardHeader, { title: "Camera" }, h("div", { className: "camera-head-actions" }, light.available && h(LightButton, light), h(CameraFullscreenButton, { onOpen: () => setFull(true) }))),
      h("div", { className: "camera-frame" }, !full && h(CameraMedia, { className: "camera-frame__video", reloads })),
    ),
    h(Presence, null, full && h(CameraFullscreen, { onClose: () => setFull(false) })),
  );
}
