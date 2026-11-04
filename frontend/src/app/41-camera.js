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
    /** What the switch shows now (the wish while one is pending). */
    current: () => (wish !== null ? wish : real === true),
    /** On or off (1.37: the round button sets every light it switches to the same state). */
    set(target) {
      if (wish === null && real === target) return;
      wish = target;
      generation += 1; // readings that left before this tap are out of date
      confirmFrom = 0;
      clearTimeout(giveUpTimer);
      emit();
      restartReading(LIGHT_CONFIRM_POLL_MS);
      pump();
    },
    toggle() {
      this.set(!(wish !== null ? wish : real === true));
    },
    /** Ask Klipper now (after a brightness or colour sent around the switch). */
    refresh: () => restartReading(150),
  };
}

/**
 * The lights (1.37): one engine each, and the round button over the ones it switches (`main`, or all when none is):
 * on when any of them is on; a tap switches them all off when any is on, else all on.
 * -> { lights, views: { id: { on, waiting, failures } }, available, on, waiting, failures, toggle, set(id, on), sendLevel(light, level, color) }
 */
function useCaseLight() {
  const functions = usePrinterFunctions();
  const lights = functions.lights;
  const lightsRef = useRef(lights);
  lightsRef.current = lights;
  const engines = useRef(new Map());
  const [views, setViews] = useState({});
  const capabilities = usePrinterCapabilities();
  const key = lights.map((light) => [light.id, light.mode, light.object ? light.object.object : "", light.on, light.off].join("|")).join(";");
  useEffect(() => {
    const made = lights.map((light) => {
      const engine = createLightEngine(
        (view) => setViews((previous) => ({ ...previous, [light.id]: view })),
        () => lightsRef.current.find((one) => one.id === light.id) || light,
      );
      engine.start();
      return [light.id, engine];
    });
    engines.current = new Map(made);
    return () => made.forEach(([, engine]) => engine.stop());
  }, [key]);

  const chosen = lights.filter((light) => light.main);
  const group = chosen.length ? chosen : lights;
  const viewOf = (light) => views[light.id] || { on: false, waiting: false, failures: 0 };
  const toggle = () => {
    const now = group.some((light) => {
      const engine = engines.current.get(light.id);
      return engine ? engine.current() : viewOf(light).on;
    });
    group.forEach((light) => engines.current.get(light.id) && engines.current.get(light.id).set(!now));
  };
  return {
    lights,
    views,
    available: lights.length > 0,
    on: group.some((light) => viewOf(light).on),
    waiting: group.some((light) => viewOf(light).waiting),
    failures: group.reduce((sum, light) => sum + viewOf(light).failures, 0),
    toggle,
    set: (id, on) => engines.current.get(id) && engines.current.get(id).set(on),
    /** Brightness 0-100 and colour of a light switched on its output; true when Klipper took it. */
    async sendLevel(light, level, color) {
      const response = await sendBrainGcode(lightLevelCommand(light, level, color, capabilities.commands)).catch(() => null);
      const engine = engines.current.get(light.id);
      if (engine) engine.refresh();
      if (!response || !response.ok) toast.notice(tx("Cannot switch the light"), 2600);
      return Boolean(response && response.ok);
    },
  };
}

/* ---------------------------------------------------------------------------
   The lights panel (1.37): every light with its switch, its brightness and its
   colour where the output has them, and the scenes (saved combinations).
   ------------------------------------------------------------------------- */
const LIGHT_DETAILS_POLL_MS = 1200;
const LIGHT_LEVEL_SEND_MS = 300;
/** Settings → Printer functions, opened from the panel (99-main.js sets it). */
const lightSettingsLink = { open: noop };

/** Brightness and colour of the lights switched on their outputs, read while the panel is open. */
function useLightDetails(lights) {
  const [details, setDetails] = useState({});
  const direct = lights.filter((light) => light.object);
  const query = [...new Set(direct.flatMap((light) => [light.object.object, ...light.object.effects]))].map(encodeURIComponent).join("&");
  useEffect(() => {
    if (!query) return undefined;
    let cancelled = false;
    const read = async () => {
      const status = await moonraker.queryObjects(query).catch(() => null);
      if (cancelled || !status) return;
      setDetails(Object.fromEntries(direct.map((light) => [light.id, lightDetails(status, light)]).filter(([, value]) => value)));
    };
    read();
    const timer = setInterval(read, LIGHT_DETAILS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [query]);
  return details;
}

/** One light: name, switch, brightness bar, colour. */
function LightRow({ light, view, detail, controller }) {
  // what was asked last, shown until Klipper reports it (a reading may still carry the old value for a moment)
  const [asked, setAsked] = useState(null); // { level, color, at }
  const [wheel, setWheel] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (asked && detail && detail.level === asked.level && (!light.color || detail.color === asked.color || asked.level === 0)) setAsked(null);
    else if (asked && Date.now() - asked.at > 6000) setAsked(null);
  }, [detail]);
  const shownLevel = asked ? asked.level : detail ? detail.level : view.on ? 100 : 0;
  const color = (asked && asked.color) || (detail && detail.color) || "#ffffff";
  const sendSoon = (next, nextColor) => {
    setAsked({ level: next, color: nextColor, at: Date.now() });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => controller.sendLevel(light, next, nextColor), LIGHT_LEVEL_SEND_MS);
  };
  return h(
    "div",
    { className: "light-row", "data-light": light.id },
    h(
      "div",
      { className: "light-row__head" },
      light.color && h("button", { type: "button", className: cx("light-row__swatch", wheel && "is-open"), style: { background: view.on ? color : "transparent" }, "aria-label": tx("Colour of {name}", { name: light.name }), onClick: () => setWheel(!wheel) }),
      h("span", { className: "light-row__name" }, light.name),
      h(
        "button",
        { type: "button", role: "switch", "aria-checked": view.on, "aria-label": light.name, className: cx("light-row__switch", view.on && "is-on"), onClick: () => controller.set(light.id, !view.on) },
        h("span", { className: "oui-switch" }, h("span", { className: "oui-switch__knob" })),
      ),
    ),
    light.dim &&
      h("input", {
        type: "range",
        className: "light-row__level",
        min: 0,
        max: 100,
        step: 1,
        value: shownLevel,
        "aria-label": tx("Brightness of {name}", { name: light.name }),
        style: { "--level-color": light.color ? color : "var(--oui-accent)" },
        onChange: (event) => sendSoon(Number(event.target.value), color),
      }),
    wheel && light.color && h(ColorWheel, { value: color, brightness: false, onChange: (next) => sendSoon(shownLevel > 0 ? shownLevel : 100, next) }),
  );
}

function LightsPanel({ controller, onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const { settings, update } = useSettings();
  const details = useLightDetails(controller.lights);
  const scenes = settings.functions.lights.scenes;
  const [naming, setNaming] = useState(false);
  const [sceneName, setSceneName] = useState("");
  const viewOf = (light) => controller.views[light.id] || { on: false, waiting: false, failures: 0 };

  const applyScene = (scene) => {
    for (const light of controller.lights) {
      const want = scene.set[light.id];
      if (!want) continue;
      if (!want.on) controller.set(light.id, false);
      else if (light.dim || light.color) controller.sendLevel(light, want.level || 100, want.color || "#ffffff");
      else controller.set(light.id, true);
    }
    toast.action(tx("Scene «{name}»", { name: scene.name }));
  };
  const saveScene = async () => {
    const name = sceneName.trim().slice(0, LIGHT_NAME_MAX);
    if (!name) return;
    // read the outputs now: the panel's own reading may be a moment old
    const direct = controller.lights.filter((light) => light.object);
    const query = [...new Set(direct.flatMap((light) => [light.object.object, ...light.object.effects]))].map(encodeURIComponent).join("&");
    const status = query ? await moonraker.queryObjects(query).catch(() => null) : null;
    const fresh = status ? Object.fromEntries(direct.map((light) => [light.id, lightDetails(status, light)])) : {};
    const set = Object.fromEntries(
      controller.lights.map((light) => {
        const detail = fresh[light.id] || details[light.id];
        return [light.id, { on: detail ? detail.on : viewOf(light).on, level: detail ? detail.level : 100, color: detail ? detail.color : "" }];
      }),
    );
    update((draft) => {
      const list = draft.functions.lights.scenes.filter((scene) => scene.name.toLowerCase() !== name.toLowerCase());
      draft.functions.lights.scenes = [...list, { id: "s" + Date.now().toString(36), name, set }].slice(-LIGHT_SCENES_MAX);
    });
    setNaming(false);
    setSceneName("");
    toast.action(tx("Scene «{name}» saved", { name }));
  };

  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--lights", onClick: (event) => event.target === event.currentTarget && onClose() },
    h(
      "div",
      { className: "sheet-card sheet-card--column lights-panel", role: "dialog", "aria-label": tx("Lights") },
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title" }, tx("Lights")), h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕")),
      h(
        "div",
        { className: "lights-panel__body" },
        h(
          "div",
          { className: "lights-scenes", role: "group", "aria-label": tx("Scenes") },
          scenes.map((scene) => h("button", { key: scene.id, type: "button", className: "oui-chip lights-scene", "data-scene": scene.id, onClick: () => applyScene(scene) }, scene.name)),
          naming
            ? h(
                "span",
                { className: "lights-scene-new" },
                h("input", {
                  className: "oui-field lights-scene-new__input",
                  value: sceneName,
                  autoFocus: true,
                  maxLength: LIGHT_NAME_MAX,
                  placeholder: tx("Name of the scene"),
                  "aria-label": tx("Name of the scene"),
                  onChange: (event) => setSceneName(event.target.value),
                  onKeyDown: (event) => (event.key === "Enter" ? saveScene() : event.key === "Escape" && setNaming(false)),
                }),
                h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", disabled: !sceneName.trim(), onClick: saveScene }, tx("Save")),
              )
            : h("button", { type: "button", className: "oui-chip lights-scene lights-scene--add", onClick: () => setNaming(true) }, h(Icons.Plus, { size: 14 }), tx("Save as a scene")),
        ),
        h(
          "div",
          { className: "lights-list" },
          controller.lights.map((light) => h(LightRow, { key: light.id, light, view: viewOf(light), detail: details[light.id], controller })),
        ),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        h(
          "button",
          {
            type: "button",
            className: "oui-btn",
            onClick: () => {
              onClose();
              lightSettingsLink.open("functions");
            },
          },
          h(Icons.Gear, { size: 16 }),
          tx("Light settings"),
        ),
        h("button", { type: "button", className: "oui-btn oui-btn--primary", onClick: onClose }, tx("Done")),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Button + card
   ------------------------------------------------------------------------- */
/**
 * The round bulb button (css/41-camera.css): amber when on. It is a switch for screen readers; while a command
 * waits for Klipper it carries aria-busy / .is-waiting (no visible change: the button simply shows what was asked).
 */
/** The round button and, next to it, the arrow that opens every light (`controller`: useCaseLight()). */
function LightButton(controller) {
  const { on, waiting, failures, toggle } = controller;
  const [panel, setPanel] = useState(false);
  return h(
    "span",
    { className: "light-group" },
    h(LightMainButton, { on, waiting, failures, toggle }),
    controller.lights && h("button", { type: "button", className: "light-more", "aria-label": tx("All the lights"), title: tx("All the lights"), "aria-haspopup": "dialog", onClick: () => setPanel(true) }, h(Icons.Chevron, { size: 14 })),
    h(Presence, null, panel && h(LightsPanel, { controller, onClose: () => setPanel(false) })),
  );
}

function LightMainButton({ on, waiting, failures, toggle }) {
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

/** The camera being watched (the settings' one, or another picked in 41a-cameras.js). `reloads` (useCameraReloads) loads everything afresh. */
function CameraMedia({ className, reloads }) {
  const { settings } = useSettings();
  const camera = useCurrentCamera().current;
  const url = cameraAddress(settings, camera.address);
  const style = flipStyle(camera);
  if (camera.method === "mjpeg") return h(CameraStream, { key: "mjpeg" + reloads + url, className, url, style });
  if (camera.method === "adaptive") return h(CameraSnapshots, { key: "adaptive" + reloads + url, className, url, fps: camera.fps, style });
  return h("iframe", { key: camera.method + reloads + url, className, src: url, style, allow: "autoplay; fullscreen", loading: "eager", title: camera.name });
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
      { cardId: "camera" },
      h(CardHeader, { title: "Camera" }, h("div", { className: "camera-head-actions" }, h(CameraPicker), light.available && h(LightButton, light), h(CameraFullscreenButton, { onOpen: () => setFull(true) }))),
      h("div", { className: "camera-frame" }, !full && h(CameraMedia, { className: "camera-frame__video", reloads })),
    ),
    h(Presence, null, full && h(CameraFullscreen, { onClose: () => setFull(false) })),
  );
}
