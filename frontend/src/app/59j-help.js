/* ============================================================================
   59j · HELP (1.22, phase 5e)
   The small "?" buttons: in the title bar of every settings page (the guide of that page) and next to the groups that need
   a word more (the guide opened at that part). The guide is a sheet over the menu: short paragraphs, the steps to follow and,
   where a picture says it better, a small drawing. Everything in English here, translated by the dictionaries.
   ========================================================================== */

/* ---------------------------------------------------------------------------
   Drawings (inline SVG, they follow the theme: currentColor and the accent)
   ------------------------------------------------------------------------- */
const FIG_ACCENT = "var(--oui-accent, #b79cff)";
const FIG_OK = "var(--oui-ok, #3ddc8a)";
const FIG_WARN = "var(--oui-warn, #ffb740)";

const figText = (x, y, text, extra) => h("text", { x, y, fontSize: 11, fill: "currentColor", textAnchor: "middle", ...(extra || {}) }, text);

/** Z-offset: the nozzle, the bed and the gap the steps change. */
function FigZOffset() {
  return h(
    "svg",
    { viewBox: "0 0 260 130", className: "help-fig", role: "img", "aria-label": tx("The nozzle above the bed: the Z-offset is the gap between them") },
    h("rect", { x: 30, y: 98, width: 200, height: 10, rx: 2, fill: "currentColor", opacity: 0.35 }),
    figText(130, 124, tx("bed")),
    h("path", { d: "M110 20h40v34l-12 18h-16l-12-18z", fill: "currentColor", opacity: 0.55 }),
    figText(130, 14, tx("nozzle")),
    h("path", { d: "M122 72h16l-8 8z", fill: FIG_ACCENT }),
    h("path", { d: "M170 80v18M166 84l4-4 4 4M166 94l4 4 4-4", stroke: FIG_ACCENT, strokeWidth: 2, fill: "none" }),
    figText(206, 93, tx("Raise / Lower"), { fill: FIG_ACCENT }),
    figText(206, 78, tx("gap"), { fill: FIG_ACCENT }),
  );
}

/** Addresses: the phone at home reaches the local address, away from home the ZeroTier / VPN one. */
function FigAddresses() {
  const box = (x, label, sub, color) =>
    h("g", null, h("rect", { x, y: 46, width: 64, height: 40, rx: 8, fill: "none", stroke: color, strokeWidth: 2 }), figText(x + 32, 64, label), figText(x + 32, 78, sub, { fontSize: 9, opacity: 0.75 }));
  return h(
    "svg",
    { viewBox: "0 0 300 130", className: "help-fig", role: "img", "aria-label": tx("At home the local address, away from home the external one") },
    box(118, "Raspberry", "KlippEye", FIG_ACCENT),
    box(10, tx("phone"), tx("at home"), FIG_OK),
    box(226, tx("phone"), tx("away"), FIG_WARN),
    h("path", { d: "M74 66h44", stroke: FIG_OK, strokeWidth: 2 }),
    h("path", { d: "M182 66h44", stroke: FIG_WARN, strokeWidth: 2, strokeDasharray: "4 3" }),
    figText(96, 38, tx("local IP"), { fill: FIG_OK, fontSize: 10 }),
    figText(204, 38, tx("external IP"), { fill: FIG_WARN, fontSize: 10 }),
    figText(204, 106, "ZeroTier / VPN", { fill: FIG_WARN, fontSize: 10 }),
  );
}

/** Camera calibration: where to tap (the very tip of the nozzle, not the toolhead). */
function FigCalibrationTap() {
  return h(
    "svg",
    { viewBox: "0 0 260 140", className: "help-fig", role: "img", "aria-label": tx("Tap the very tip of the nozzle") },
    h("rect", { x: 70, y: 10, width: 120, height: 56, rx: 6, fill: "currentColor", opacity: 0.25 }),
    figText(130, 42, tx("toolhead: no")),
    h("path", { d: "M114 66h32v18l-10 14h-12l-10-14z", fill: "currentColor", opacity: 0.55 }),
    h("circle", { cx: 130, cy: 100, r: 7, fill: "none", stroke: FIG_OK, strokeWidth: 2.5 }),
    h("circle", { cx: 130, cy: 100, r: 2, fill: FIG_OK }),
    h("path", { d: "M180 116l-42-14", stroke: FIG_OK, strokeWidth: 1.6 }),
    figText(200, 128, tx("the tip: yes"), { fill: FIG_OK }),
    h("rect", { x: 20, y: 110, width: 90, height: 8, rx: 2, fill: "currentColor", opacity: 0.35 }),
    figText(64, 132, tx("bed"), { fontSize: 10 }),
  );
}

/** What the AI monitor watches: the bed around the parts, without the toolhead and the gantry. */
function FigWatched() {
  return h(
    "svg",
    { viewBox: "0 0 260 150", className: "help-fig", role: "img", "aria-label": tx("Watched: the bed around the parts. Left out: toolhead and gantry") },
    h("path", { d: "M30 120L70 40h120l40 80z", fill: FIG_OK, opacity: 0.18, stroke: FIG_OK, strokeWidth: 1.5 }),
    h("rect", { x: 104, y: 78, width: 50, height: 26, rx: 3, fill: FIG_ACCENT, opacity: 0.35, stroke: FIG_ACCENT }),
    figText(129, 95, tx("part"), { fontSize: 10 }),
    h("rect", { x: 46, y: 18, width: 168, height: 12, rx: 3, fill: "currentColor", opacity: 0.25 }),
    h("rect", { x: 148, y: 30, width: 30, height: 30, rx: 4, fill: "currentColor", opacity: 0.4 }),
    figText(130, 13, tx("gantry and toolhead: left out"), { fontSize: 10 }),
    figText(130, 140, tx("watched: the bed around the parts"), { fill: FIG_OK, fontSize: 10 }),
  );
}

/** Notifications: the Raspberry sends, ntfy carries, the phone receives (the KlippEye app or the ntfy app). */
function FigNotifications() {
  const node = (x, label, color) => h("g", null, h("rect", { x, y: 40, width: 72, height: 36, rx: 8, fill: "none", stroke: color, strokeWidth: 2 }), figText(x + 36, 62, label));
  return h(
    "svg",
    { viewBox: "0 0 300 110", className: "help-fig", role: "img", "aria-label": tx("The Raspberry sends, ntfy carries, the phone receives") },
    node(6, "Raspberry", FIG_ACCENT),
    node(114, "ntfy", "currentColor"),
    node(222, tx("phone"), FIG_OK),
    h("path", { d: "M78 58h36M186 58h36", stroke: "currentColor", strokeWidth: 2 }),
    h("path", { d: "M108 54l6 4-6 4M216 54l6 4-6 4", stroke: "currentColor", strokeWidth: 2, fill: "none" }),
    figText(150, 96, tx("a private address that only your phones know"), { fontSize: 10, opacity: 0.8 }),
  );
}

const HELP_FIGURES = { zoffset: FigZOffset, addresses: FigAddresses, tap: FigCalibrationTap, watched: FigWatched, notifications: FigNotifications };

/* ---------------------------------------------------------------------------
   The guides, one per page. A section: { id, title, text: [paragraphs], steps: [...], figure }.
   ------------------------------------------------------------------------- */
const HELP = {
  home: {
    title: tx("How the settings work"),
    sections: [
      { id: "where", title: tx("Saved on the Raspberry"), text: [tx("The settings are saved on the Raspberry: every phone and computer that opens the dashboard sees the same ones (only the language is chosen on each device). The line under the list says whether the last change has reached the Raspberry.")] },
      { id: "groups", title: tx("What is where"), text: [tx("The printer: name, logo, the buttons that use your macros, the Z-offset steps. Camera and AI monitor: the picture and the failure detection. Phone and network: notifications and addresses. System: password, updates, language.")] },
      { id: "guide", title: tx("The guided set-up"), text: [tx("«Guided set-up», at the top of the menu, goes through everything KlippEye needs, one step at a time. It can be repeated whenever you want; every step can be skipped.")] },
      { id: "help", title: tx("The «?» buttons"), text: [tx("Every page has a «?» in its title bar: it opens the guide of that page. Some groups have their own small «?» for the part that needs a word more.")] },
    ],
  },
  printer: {
    title: tx("Name and logo"),
    sections: [
      { id: "logo", title: "Logo", text: [tx("The logo in the top bar. Choose the brand of your printer, or KlippEye. A brand whose logo file is not in the repository yet shows only the name.")] },
      { id: "name", title: tx("Name"), text: [tx("A name of your own (example: Voron.287): shown in the top bar and in the browser tab, useful with more than one printer. Empty: the name of the brand.")] },
    ],
  },
  functions: {
    title: tx("Printer functions"),
    sections: [
      { id: "what", title: tx("What it is"), text: [tx("Some buttons of the dashboard run something of your printer: park the toolhead, wipe the nozzle, load and unload the filament, switch the light. Every printer does them with its own macros, or cannot: here you say what each button does.")] },
      {
        id: "modes",
        title: tx("The four choices"),
        steps: [
          tx("Automatic: KlippEye looks for the usual macro names in Klipper (PARK, CLEAN_NOZZLE, LOAD_FILAMENT, M701…) and says what it found."),
          tx("Macro: one of your macros, by name."),
          tx("G-code: a few lines written in the editor that opens over the page."),
          tx("Not used: the button is hidden."),
        ],
      },
      { id: "create", title: tx("Create a macro for this"), text: [tx("KlippEye proposes a macro, you check it in the editor and it is saved in klippeye_macros.cfg next to printer.cfg. Klipper reads it after a restart: the page offers to restart it (never during a print).")] },
      { id: "light", title: tx("The light"), text: [tx("The light button always shows the real state of the light, read from its Klipper output (and from the led_effect effects), whoever switched it: Mainsail, KlipperScreen, a macro.")] },
      { id: "filament", title: tx("Filament change notification"), text: [tx("The phone is told «Filament run out» by a filament sensor, by a macro you choose (M600, your runout macro: KlippEye adds a small wrapper that announces it and then runs it exactly as before) or by a line of the console.")] },
      { id: "check", title: tx("«All right»"), text: [tx("The entry is marked «To check» until you look at it once and press «All right».")] },
    ],
  },
  zoffset: {
    title: "Z-offset",
    sections: [
      { id: "what", title: tx("The steps of the Z-offset card"), figure: "zoffset", text: [tx("The Z-offset card raises or lowers the nozzle during the first layer. These are the sizes of each tap, in millimetres: small for fine tuning (0.01), bigger to correct quickly (0.1). Up to four; a field left empty is not shown.")] },
    ],
  },
  camera: {
    title: "Camera",
    sections: [
      { id: "mainsail", title: tx("The quickest way"), text: [tx("If the camera already works in Mainsail, press «Import from Mainsail» at the bottom and pick it: method and address are taken from there.")] },
      {
        id: "method",
        title: tx("Which method"),
        steps: [
          tx("WebRTC: smooth and light, with camera-streamer (crowsnest «webrtc»). The best when it works."),
          tx("MJPEG: the classic stream (ustreamer, mjpg-streamer). Works everywhere."),
          tx("MJPEG adaptive: one photo at a time, as many per second as you choose. For slow networks."),
          tx("Web page: any page that shows the camera."),
        ],
      },
      { id: "address", title: tx("The address"), text: [tx("Usually a path on the Raspberry, like /webcam/webrtc or /webcam/?action=stream: the right address of the Raspberry is added by itself (see Addresses). A full address http://… is used as it is.")] },
      {
        id: "snapshot",
        title: tx("The snapshot"),
        text: [
          tx("A single photo of the camera, taken by the Raspberry itself: the AI monitor and the camera calibration use it, and later the timelapse. Leave it empty: KlippEye works it out from the address above (/webcam/?action=snapshot for crowsnest)."),
          tx("Write it only if «Try» gives no photo, or to use another camera: the same «Snapshot URL» you see in Mainsail's webcam settings."),
        ],
      },
      { id: "image", title: tx("Upside down or mirrored?"), text: [tx("Use the two switches of «Image»: they turn the picture of the dashboard, not the camera.")] },
      { id: "ai", title: tx("For the AI monitor"), text: [tx("To watch the whole bed the AI monitor needs the camera calibrated: Settings → AI monitor → Camera calibration.")] },
    ],
  },
  network: {
    title: tx("Addresses"),
    sections: [
      { id: "what", title: tx("Do I need them?"), figure: "addresses", text: [tx("Only if you open the dashboard from outside your home through ZeroTier, Tailscale or another VPN. Empty, the camera uses the address you opened the dashboard at, which is right in most homes.")] },
      {
        id: "how",
        title: tx("How to fill them in"),
        steps: [tx("Local IP: the address of the Raspberry on your home network (the one you use for Mainsail, without http:// and without :8085)."), tx("External IP: the address of the Raspberry in ZeroTier / the VPN."), tx("«For the camera use»: Automatic picks the one of the network you are on.")],
      },
      { id: "app", title: tx("The Android app"), text: [tx("The KlippEye app uses the same addresses to find the Raspberry: at home the local one, away the external one.")] },
    ],
  },
  notifications: {
    title: tx("Notifications"),
    sections: [
      { id: "how", title: tx("How they arrive"), figure: "notifications", text: [tx("The Raspberry sends the notifications through ntfy, a free service, to a private address that only your phones know. No account, no key.")] },
      { id: "app", title: tx("On Android: the KlippEye app"), text: [tx("Open this page in the KlippEye app and follow «This phone»: five steps, and the app receives the notifications by itself, also when closed. A small fixed notification «KlippEye in ascolto» keeps the connection open: hold it to hide it.")] },
      { id: "ntfy", title: tx("iPhone and other phones: the ntfy app"), text: [tx("Install the free ntfy app, scan the QR code with the camera and send a test notification. Several phones can scan the same code.")] },
      { id: "which", title: tx("Which notifications"), text: [tx("Choose which events to be told about and in which language: the same for every phone.")] },
      { id: "privacy", title: tx("Keep the address private"), text: [tx("Whoever knows the address can read the notifications. «New address» makes another one: the phones with the ntfy app must scan the new code; the KlippEye app takes it by itself.")] },
    ],
  },
  ai: {
    title: tx("AI monitor"),
    sections: [
      { id: "what", title: tx("What it does"), figure: "watched", text: [tx("During a print KlippEye compares the pictures of the camera with each other. When something changes where it should not (spaghetti, a part that came off), it asks an AI service to look at the picture and tells you; if you want, it pauses the print by itself.")] },
      {
        id: "start",
        title: tx("To start"),
        steps: [tx("A free AI key: Groq gives one at console.groq.com → API Keys. Paste it in «The AI service»."), tx("Calibrate the camera (Camera calibration): then the whole bed is watched, not only a band around the picture."), tx("Leave the other values as they are: they are the usual ones.")],
      },
      { id: "confidence", title: tx("Minimum AI confidence"), text: [tx("How sure the AI must be to propose a pause. 70% is the usual value; above 85% a failed print may not be stopped, because the AI is rarely that sure.")] },
      { id: "actions", title: tx("Automatic actions"), text: [tx("Off by default: you are told and you decide. «Pause by itself» stops the print when the AI is sure; a cancelled print cannot be recovered, so «Cancel by itself» is for when you really trust it.")] },
    ],
  },
  camcal: {
    title: tx("Camera calibration"),
    sections: [
      { id: "why", title: tx("Why"), text: [tx("KlippEye learns where the bed, the nozzle and the gantry are in the picture. Then the AI monitor watches the whole bed around the parts and leaves out the moving toolhead and gantry, without false alarms.")] },
      { id: "tap", title: tx("Where to tap"), figure: "tap", text: [tx("The printer moves the nozzle to a few points; at each one tap the very tip of the nozzle on the picture, where it would touch the bed. Not the toolhead, not the green marker. Zoom in with two fingers to be precise.")] },
      { id: "before", title: tx("Before starting"), steps: [tx("The bed empty and clean, the light on."), tx("The printer homed (the page does it if needed)."), tx("The camera still: if it moves later, calibrate again.")] },
      { id: "shape", title: tx("Toolhead and gantry"), text: [tx("After the calibration the live picture shows what is left out: purple the toolhead, orange the gantry. If they do not cover them, change their size with − and + under «Toolhead» and «Gantry», then move the toolhead to check.")] },
    ],
  },
  detector: {
    title: tx("Monitor thresholds"),
    sections: [
      { id: "what", title: tx("The fine numbers"), text: [tx("How sensitive the monitor is, how many checks in a row are needed before asking the AI, the pause between two analyses, when it starts during a print. The usual values work for most printers: change one at a time and watch the result in Recordings.")] },
      { id: "fallback", title: tx("Without camera calibration"), text: [tx("Only then the rectangle and its outer band are used: the middle, where the part is, is not watched. Calibrate the camera to watch the whole bed.")] },
    ],
  },
  recordings: {
    title: tx("Recordings"),
    sections: [
      { id: "what", title: tx("What they are"), text: [tx("Every print can be recorded (a picture every few seconds and what the monitor thought). Mark the alarms as right or wrong: «Measure now» replays them with the current thresholds and shows how many false alarms and missed failures they would give.")] },
    ],
  },
  access: {
    title: tx("Access"),
    sections: [
      { id: "password", title: tx("The password"), text: [tx("Optional. With the password on, a device must enter it once (it is remembered for 6 months) before it can change anything. This device stays logged in.")] },
      { id: "forgot", title: tx("Forgot it?"), text: [tx("On the Raspberry: klippeye password remove.")] },
      { id: "outside", title: tx("From outside your home"), text: [tx("Never open port 8085 to the internet: use a VPN such as ZeroTier, Tailscale or WireGuard.")] },
    ],
  },
  software: {
    title: tx("Updates"),
    sections: [
      { id: "how", title: tx("Updating"), text: [tx("«Check» asks GitHub for a new release; «Update KlippEye» installs it and restarts the services (not during a print). If something goes wrong you can go back to the previous release.")] },
      { id: "channel", title: tx("Update channel"), text: [tx("«Stable releases»: only the tested releases (recommended). «Every change»: every change as soon as it is on GitHub, for those who test.")] },
      { id: "app", title: tx("Android app"), text: [tx("«Download the app» on the phone installs it the first time; later «Update the app» updates it (Android always asks to confirm).")] },
    ],
  },
  language: {
    title: tx("Language"),
    sections: [{ id: "what", title: tx("Language"), text: [tx("The language of this device only. «Automatic» follows the language of the phone or computer. The language of the notifications is chosen in Notifications.")] }],
  },
};

/* ---------------------------------------------------------------------------
   Opening and showing
   ------------------------------------------------------------------------- */
const helpListeners = new Set();
let helpOpen = null; // { page, section } or null

function openHelp(page, section) {
  if (!HELP[page]) return;
  helpOpen = { page, section: section || "" };
  helpListeners.forEach((listener) => listener(helpOpen));
}

function closeHelp() {
  helpOpen = null;
  helpListeners.forEach((listener) => listener(null));
}

function useHelpState() {
  const [state, setState] = useState(helpOpen);
  useEffect(() => {
    helpListeners.add(setState);
    return () => helpListeners.delete(setState);
  }, []);
  return state;
}

/** The small round "?" that opens the guide of `page` (at `section`). */
function HelpButton({ page, section, className }) {
  if (!HELP[page]) return null;
  return h(
    "button",
    { type: "button", className: cx("help-btn", className), "aria-label": tx("Help"), title: tx("Help"), "data-help": page + (section ? "#" + section : ""), onClick: (event) => (event.stopPropagation(), openHelp(page, section)) },
    "?",
  );
}

function HelpSection({ section, highlight }) {
  const ref = useRef(null);
  useEffect(() => {
    if (highlight && ref.current && ref.current.scrollIntoView) ref.current.scrollIntoView({ block: "start" });
  }, [highlight]);
  const Figure = section.figure ? HELP_FIGURES[section.figure] : null;
  return h(
    "section",
    { ref, className: cx("help-section", highlight && "is-highlight"), "data-help-section": section.id },
    h("h3", null, section.title),
    Figure && h(Figure),
    (section.text || []).map((paragraph, index) => h("p", { key: index }, paragraph)),
    section.steps && h("ol", { className: "help-steps" }, section.steps.map((step, index) => h("li", { key: index }, step))),
  );
}

/** The guide over everything (also over the settings menu). */
function HelpLayer() {
  const state = useHelpState();
  useEffect(() => {
    if (!state) return undefined;
    const onKey = (event) => event.key === "Escape" && (event.stopPropagation(), closeHelp());
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [state]);
  const guide = state && HELP[state.page];
  return h(
    Presence,
    null,
    guide &&
      h(
        "div",
        { className: "help-overlay", onClick: (event) => event.target === event.currentTarget && closeHelp() },
        h(
          "div",
          { className: "help-sheet", role: "dialog", "aria-modal": "true", "aria-label": guide.title, "data-help-open": state.page },
          h("div", { className: "help-sheet__head" }, h("span", { className: "help-sheet__mark", "aria-hidden": "true" }, "?"), h("div", { className: "help-sheet__title" }, guide.title), h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": tx("Close"), onClick: closeHelp }, h(Icons.Close))),
          h("div", { className: "help-sheet__body" }, guide.sections.map((section) => h(HelpSection, { key: section.id, section, highlight: state.section === section.id }))),
        ),
      ),
  );
}
