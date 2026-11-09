/* ============================================================================
   47c · TIMELAPSE (1.46, roadmap 6d part 5)
   moonraker-timelapse, as Mainsail shows it, as the third part of the Files
   page (only when Moonraker has the component):
     · the videos: preview, date, size; play here, download, delete; the frames
       of the last print and "Make the video" when they are not one yet;
     · the settings: on / off, a frame per layer or every few seconds
       (hyperlapse), park the head for the photo, make the video at the end,
       frames a second (or a length to aim at), repeat the last frame, keep the
       frames, the quality. A setting fixed in moonraker.conf is shown locked.
   The photo itself is taken by the TIMELAPSE_TAKE_FRAME macro (timelapse.cfg):
   without it the page says so.
   ========================================================================== */

const TIMELAPSE_ROOT = "timelapse";
const TIMELAPSE_POLL_MS = 5000;
const TIMELAPSE_RENDER_WAIT_MS = 5 * 60 * 1000; // after "Make the video": how long the page waits for it
const VIDEO_FILE = /\.(mp4|mkv|webm|mov|avi|gif)$/i;
const TIMELAPSE_PARK_POSITIONS = ["back_left", "back_right", "front_left", "front_right", "center", "x_only", "y_only", "custom"];
const TIMELAPSE_CONFIG_FILE = "moonraker.conf";
const TIMELAPSE_RESTART_WAIT_MS = 60000;

/**
 * 1.67: moonraker-timelapse's own defaults (timelapse.py). The card saves its settings in moonraker.conf, section
 * [timelapse]: a setting is written there when it differs from these, or when the section already has it. What is in
 * moonraker.conf wins over what the add-on keeps in its database (and Mainsail cannot change it any more: it shows it
 * locked), so the file is where they stay.
 */
const TIMELAPSE_DEFAULTS = {
  enabled: true, mode: "layermacro", camera: "", snapshoturl: "http://localhost:8080/?action=snapshot", stream_delay_compensation: 0.05,
  gcode_verbose: false, parkhead: false, parkpos: "back_left", park_custom_pos_x: 10, park_custom_pos_y: 10, park_custom_pos_dz: 0,
  park_travel_speed: 100, park_retract_speed: 15, park_extrude_speed: 15, park_retract_distance: 1, park_extrude_distance: 1, park_time: 0.1,
  fw_retract: false, hyperlapse_cycle: 30, autorender: true, constant_rate_factor: 23, output_framerate: 30, pixelformat: "yuv420p",
  time_format_code: "%Y%m%d_%H%M", extraoutputparams: "", variable_fps: false, targetlength: 10, variable_fps_min: 5, variable_fps_max: 60,
  rotation: 0, flip_x: false, flip_y: false, duplicatelastframe: 0, previewimage: true, saveframes: false, wait_for_snapshot: false,
};

const configLineKey = (line) => {
  const match = /^([A-Za-z_][\w]*)\s*[:=]/.exec(line); // indented lines continue the value above
  return match ? match[1].toLowerCase() : null;
};
const isSectionHeader = (line) => /^\s*\[[^\]]+\]/.test(line);

/** Where `[section]` is in `text`'s lines: { start, last } (its header, its last line not blank), or null. */
function findConfigSection(lines, section) {
  const header = new RegExp("^\\s*\\[\\s*" + section + "\\s*\\]\\s*([#;].*)?$", "i");
  const start = lines.findIndex((line) => header.test(line));
  if (start < 0) return null;
  let end = start + 1;
  while (end < lines.length && !isSectionHeader(lines[end])) end += 1;
  let last = end - 1;
  while (last > start && !lines[last].trim()) last -= 1;
  return { start, last };
}

/** The settings `[section]` of `text` already has (lower case). */
function configSectionKeys(text, section) {
  const lines = String(text).split("\n");
  const found = findConfigSection(lines, section);
  if (!found) return [];
  return lines.slice(found.start + 1, found.last + 1).map(configLineKey).filter(Boolean);
}

/**
 * `text` with `values` written in `[section]`: a setting already there gets its new value on its own line (its comment
 * is lost), the others are added at the end of the section; the rest of the file stays as it is. Without the section,
 * it is added at the end of the file.
 */
function setConfigSection(text, section, values) {
  const line = (key, value) => key + ": " + value;
  const lines = String(text).split("\n");
  const found = findConfigSection(lines, section);
  const left = { ...values };
  if (!found) {
    const body = Object.keys(left).map((key) => line(key, left[key]));
    const head = String(text).replace(/\s*$/, "");
    return (head ? head + "\n\n" : "") + ["[" + section + "]"].concat(body).join("\n") + "\n";
  }
  for (let index = found.start + 1; index <= found.last; index += 1) {
    const key = configLineKey(lines[index]);
    if (key && Object.prototype.hasOwnProperty.call(left, key)) {
      lines[index] = line(key, left[key]);
      delete left[key];
    }
  }
  const added = Object.keys(left).map((key) => line(key, left[key]));
  lines.splice(found.last + 1, 0, ...added);
  return lines.join("\n");
}

/** A value as moonraker.conf writes it. */
const configValue = (value) => (value === true ? "True" : value === false ? "False" : String(value));

/** Moonraker back after a restart, with its components: resolves to them, or null after `waitMs`. */
async function waitForMoonrakerBack(waitMs) {
  const end = Date.now() + waitMs;
  await new Promise((resolve) => setTimeout(resolve, 3000));
  while (Date.now() < end) {
    try {
      const json = await fetchJson("/server/info", { timeout: 3000 });
      if (json && json.result) return json.result.components || [];
    } catch (error) {}
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  return null;
}

/**
 * Writes the timelapse settings `values` (all of them, as the card shows them) in moonraker.conf and restarts Moonraker.
 * Refused while printing (the add-on is taking the photos). Resolves when Moonraker is back with the timelapse.
 */
async function saveTimelapseConfig(values) {
  const stats = await moonraker.queryObjects("print_stats").catch(() => ({}));
  const state = ((stats && stats.print_stats) || {}).state;
  if (state === "printing" || state === "paused") throw new Error(tx("Not while printing: the timelapse is taking its photos. Save when the print is over."));
  configFileCache.delete(TIMELAPSE_CONFIG_FILE); // read it as it is now: it may have been changed elsewhere
  const text = await configFilesApi.read(TIMELAPSE_CONFIG_FILE).catch(() => {
    throw new Error(tx("Cannot read moonraker.conf"));
  });
  const present = configSectionKeys(text, "timelapse");
  const written = {};
  Object.keys(values).forEach((key) => {
    if (!Object.prototype.hasOwnProperty.call(TIMELAPSE_DEFAULTS, key)) return;
    if (present.includes(key) || values[key] !== TIMELAPSE_DEFAULTS[key]) written[key] = configValue(values[key]);
  });
  const next = setConfigSection(text, "timelapse", written);
  if (next !== text) await configFilesApi.save(TIMELAPSE_CONFIG_FILE, next);
  try {
    await moonraker.serviceAction("restart", "moonraker");
  } catch (error) {} // the answer may not arrive: Moonraker is restarting
  const components = await waitForMoonrakerBack(TIMELAPSE_RESTART_WAIT_MS);
  if (components === null) throw new Error(tx("Moonraker did not come back: try again in a moment."));
  if (!components.includes("timelapse")) throw new Error(tx("Moonraker restarted without the timelapse: open moonraker.conf in Config and check the [timelapse] section."));
}

const timelapseApi = {
  async settings() {
    const json = await fetchJson("/machine/timelapse/settings");
    return (json && json.result) || {};
  },
  async set(changes) {
    const response = await fetchFresh("/machine/timelapse/settings", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(changes) });
    if (!response.ok) throw new Error(await responseError(response));
    return ((await response.json()).result || {});
  },
  async frames() {
    const json = await fetchJson("/machine/timelapse/lastframeinfo");
    return (json && json.result) || {};
  },
  async render() {
    const response = await fetchFresh("/machine/timelapse/render", { method: "POST" });
    if (!response.ok) throw new Error(await responseError(response));
  },
  async files() {
    const json = await fetchJson("/server/files/list?root=" + TIMELAPSE_ROOT);
    return Array.isArray(json && json.result) ? json.result : [];
  },
  async remove(path) {
    const response = await fetchFresh("/server/files/" + TIMELAPSE_ROOT + "/" + encodeRemotePath(path), { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
  },
};
const timelapseUrl = (path) => "/server/files/" + TIMELAPSE_ROOT + "/" + encodeRemotePath(path);

/** The videos, newest first, each with its preview (the .jpg of the same name, written by the component). */
function timelapseVideos(files) {
  const byName = new Map(files.map((file) => [file.path, file]));
  return files
    .filter((file) => VIDEO_FILE.test(file.path))
    .map((file) => {
      const base = file.path.replace(/\.[^.]+$/, "");
      const preview = [".jpg", ".png"].map((ext) => base + ext).find((name) => byName.has(name));
      return { ...file, preview: preview ? timelapseUrl(preview) : null, previewPath: preview || null };
    })
    .sort((a, b) => (b.modified || 0) - (a.modified || 0));
}

function useTimelapse() {
  const [state, setState] = useState({ settings: null, videos: [], frames: 0, hasMacro: null, error: null });
  const [rendering, setRendering] = useState(0); // when "Make the video" was asked (0: not waiting)
  const [draft, setDraft] = useState({}); // 1.67: changed, not yet saved in moonraker.conf
  const [saving, setSaving] = useState(false);
  const refreshRef = useRef(null);
  useEffect(() => {
    let cancelled = false;
    let macroChecked = false;
    const refresh = async () => {
      try {
        const [settings, files, frames] = await Promise.all([timelapseApi.settings(), timelapseApi.files(), timelapseApi.frames().catch(() => ({}))]);
        let hasMacro = null;
        if (!macroChecked) {
          macroChecked = true;
          try {
            hasMacro = (await moonraker.objectsList()).some((name) => name.toLowerCase() === "gcode_macro timelapse_take_frame");
          } catch (error) {}
        }
        if (cancelled) return;
        setState((previous) => ({ settings, videos: timelapseVideos(files), frames: Number(frames.count) || 0, hasMacro: hasMacro === null ? previous.hasMacro : hasMacro, error: null }));
      } catch (error) {
        if (!cancelled) setState((previous) => ({ ...previous, error: error.message || tx("Error") }));
      }
    };
    refreshRef.current = refresh;
    const stop = startPolling(refresh, TIMELAPSE_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, []);
  // a new video while waiting for one: the wait is over
  const newest = state.videos[0] ? state.videos[0].modified * 1000 : 0;
  useEffect(() => {
    if (rendering && (newest > rendering - 2000 || Date.now() - rendering > TIMELAPSE_RENDER_WAIT_MS)) setRendering(0);
  }, [newest, rendering, state.frames]);
  // what the card shows: the settings, with the changes not saved yet over them
  const values = state.settings ? { ...state.settings, ...draft } : null;
  const dirty = Object.keys(draft).some((key) => !state.settings || draft[key] !== state.settings[key]);
  return {
    ...state,
    values,
    dirty,
    saving,
    rendering: rendering > 0,
    reload: () => refreshRef.current && refreshRef.current(),
    /** 1.67: a change waits for «Save» (moonraker.conf and a restart of Moonraker), it is not sent at once any more. */
    edit(changes) {
      setDraft((previous) => ({ ...previous, ...changes }));
    },
    discard: () => setDraft({}),
    async save() {
      if (!values || saving) return;
      setSaving(true);
      try {
        await saveTimelapseConfig(values);
        const settings = await timelapseApi.settings();
        setState((previous) => ({ ...previous, settings }));
        setDraft({});
        toast.notice(tx("Timelapse settings saved in moonraker.conf"));
      } catch (error) {
        toast.action("Timelapse: " + (error.message || error));
      } finally {
        setSaving(false);
      }
    },
    async render() {
      try {
        await timelapseApi.render();
        setRendering(Date.now());
        toast.notice(tx("Making the video…"));
      } catch (error) {
        toast.action("Timelapse: " + (error.message || error));
      }
    },
    forget: (path) => setState((previous) => ({ ...previous, videos: previous.videos.filter((video) => video.path !== path) })),
  };
}

/* ---------------------------------------------------------------------------
   The videos
   ------------------------------------------------------------------------- */
function TimelapseVideoViewer({ video, onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return h(
    "div",
    { className: "screen screen--viewer timelapse-viewer", role: "dialog", "aria-label": video.path },
    h("div", { className: "screen-bar viewer-bar" }, h("span", { className: "viewer-title" }, video.path), h("button", { className: "oui-btn oui-btn--icon", "aria-label": tx("Close"), onClick: onClose }, "✕")),
    h("div", { className: "viewer-stage" }, h("video", { className: "timelapse-video", src: timelapseUrl(video.path), poster: video.preview || undefined, controls: true, autoPlay: true, playsInline: true })),
  );
}

function TimelapseVideoRow({ video, onPlay, onDelete }) {
  return h(
    "div",
    { className: "timelapse-row", "data-video": video.path },
    h("button", { type: "button", className: "timelapse-row__preview oui-well", "aria-label": tx("Play {name}", { name: video.path }), onClick: () => onPlay(video) }, video.preview ? h("img", { src: video.preview, alt: "", loading: "lazy", draggable: false }) : null, h("span", { className: "timelapse-row__play" }, h(Icons.Play, { size: 18 }))),
    h(
      "div",
      { className: "timelapse-row__body" },
      h("div", { className: "timelapse-row__name" }, video.path),
      h("div", { className: "timelapse-row__meta" }, [formatFileDate(video.modified), formatBytes(video.size)].filter(Boolean).join(" · ")),
      h(
        "div",
        { className: "timelapse-row__actions" },
        h("button", { type: "button", className: "oui-btn oui-btn--sm", onClick: () => downloadFile(timelapseUrl(video.path), video.path) }, h(Icons.Download, { size: 15 }), tx("Download")),
        h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--danger-soft timelapse-delete", "aria-label": tx("Delete {name}", { name: video.path }), onClick: () => onDelete(video) }, h(Icons.Trash, { size: 15 })),
      ),
    ),
  );
}

function TimelapseVideosCard({ timelapse, onPlay, onDelete }) {
  const { videos, frames, settings } = timelapse;
  const waitingFrames = frames > 0 && !(settings && settings.autorender && timelapse.rendering);
  return h(
    Card,
    { className: "timelapse-videos" },
    h(CardHeader, { title: tx("Videos") }, h("span", { className: "oui-badge" }, videos.length)),
    timelapse.hasMacro === false && h("div", { className: "oui-tile oui-tile--warn timelapse-macro" }, tx("Klipper has no TIMELAPSE_TAKE_FRAME: add [include timelapse.cfg] to printer.cfg (moonraker-timelapse's macros), or no photo is taken.")),
    (waitingFrames || timelapse.rendering) &&
      h(
        "div",
        { className: "timelapse-frames" },
        h("span", { className: "timelapse-frames__text" }, timelapse.rendering ? tx("Making the video… it appears here when ready.") : frames === 1 ? tx("1 frame of the last print, not a video yet") : tx("{count} frames of the last print, not a video yet", { count: frames })),
        !timelapse.rendering && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary timelapse-render", onClick: timelapse.render }, tx("Make the video")),
      ),
    timelapse.error && !settings ? h("div", { className: "oui-caption" }, timelapse.error) : !settings ? h("div", { className: "oui-caption" }, tx("Loading...")) : videos.length === 0 ? h("div", { className: "oui-caption timelapse-empty" }, tx("No video yet: with the timelapse on, each print makes one.")) : h("div", { className: "timelapse-list" }, videos.map((video) => h(TimelapseVideoRow, { key: video.path, video, onPlay, onDelete }))),
  );
}

/* ---------------------------------------------------------------------------
   The settings
   ------------------------------------------------------------------------- */
function TimelapseSettingsCard({ timelapse }) {
  if (!timelapse.values) return null;
  return h(Card, { className: "timelapse-settings" }, h(CardHeader, { title: tx("Timelapse settings") }), h(TimelapseSettingsFields, { timelapse }));
}

/**
 * The settings themselves: on the Files page's card and in Settings → Camera → Timelapse (1.59). 1.67: the most used
 * ones, then «Advanced» for the others (parking, the photo's timing, the video's encoding); only those the installed
 * moonraker-timelapse knows are shown. Nothing is sent until «Save»: they are written in moonraker.conf, section
 * [timelapse], and Moonraker restarts to read them.
 */
function TimelapseSettingsFields({ timelapse }) {
  const settings = timelapse.values;
  const [advanced, setAdvanced] = useState(false);
  if (!settings) return null;
  const has = (key) => Object.prototype.hasOwnProperty.call(settings, key);
  const change = (key, value) => timelapse.edit({ [key]: value });
  const switchRow = (key, title, detail) => has(key) && h("div", { "data-setting": key }, h(SwitchRow, { title, detail, checked: Boolean(settings[key]), disabled: timelapse.saving, onChange: (value) => change(key, value) }));
  const number = (key, label, min, max, hint, decimals) =>
    has(key) &&
    h(
      "div",
      { "data-setting": key },
      h(TextSetting, {
        label,
        value: String(settings[key] === undefined ? "" : settings[key]),
        inputMode: decimals ? "decimal" : "numeric",
        hint,
        validate: (text) => {
          const value = Number(String(text).replace(",", "."));
          return isFinite(value) && value >= min && value <= max && (decimals || Number.isInteger(value)) ? value : null;
        },
        error: tx("From {min} to {max}", { min, max }),
        onCommit: (value) => change(key, value),
      }),
    );
  // a word for the file: one line, no comment marks (they would cut it in moonraker.conf)
  const text = (key, label, hint) =>
    has(key) &&
    h(
      "div",
      { "data-setting": key },
      h(TextSetting, {
        label,
        value: String(settings[key] === undefined || settings[key] === null ? "" : settings[key]),
        hint,
        validate: (value) => (/[\n\r]|\s[#;]/.test(value) ? null : value.trim()),
        error: tx("One line, without # or ;"),
        onCommit: (value) => change(key, value),
      }),
    );
  const chips = (key, label, options) =>
    has(key) && h("div", { "data-setting": key }, h("div", { className: "set-field__label timelapse-label" }, label), h(ChipChoice, { label, value: settings[key], options, onChange: (value) => change(key, value) }));
  const parkLabels = {
    back_left: tx("Back left"),
    back_right: tx("Back right"),
    front_left: tx("Front left"),
    front_right: tx("Front right"),
    center: tx("Centre"),
    x_only: tx("X only"),
    y_only: tx("Y only"),
    custom: tx("Custom"),
  };
  const group = (title, ...children) => h("div", { className: "timelapse-group" }, h("div", { className: "timelapse-group__title" }, title), ...children);
  return h(
    "div",
    { className: "timelapse-settings__fields", "data-dirty": timelapse.dirty ? "1" : "0" },
    h("div", { className: "oui-list" }, switchRow("enabled", tx("Timelapse on"), tx("Every print makes a video"))),
    settings.enabled &&
      h(
        React.Fragment,
        null,
        h(TimelapseCameraChoice, { timelapse }),
        chips("mode", tx("When a photo is taken"), [
          { id: "layermacro", label: tx("Every layer") },
          { id: "hyperlapse", label: tx("Every few seconds") },
        ]),
        settings.mode === "hyperlapse" && number("hyperlapse_cycle", tx("Seconds between photos"), 1, 3600),
        h("div", { className: "oui-list timelapse-switches" }, switchRow("parkhead", tx("Park the head for the photo"), tx("The object is not hidden by the nozzle (layer mode)"))),
        settings.parkhead && chips("parkpos", tx("Where"), TIMELAPSE_PARK_POSITIONS.map((id) => ({ id, label: parkLabels[id] }))),
        h("div", { className: "oui-list timelapse-switches" }, switchRow("autorender", tx("Make the video at the end of the print"), settings.autorender ? null : tx("Off: «Make the video» does it when you want")), switchRow("variable_fps", tx("Frames a second from the length"), tx("Aims at a video length instead of a fixed rate"))),
        settings.variable_fps ? number("targetlength", tx("Video length (s)"), 1, 600) : number("output_framerate", tx("Frames a second"), 1, 120),
        number("duplicatelastframe", tx("Repeat the last frame (times)"), 0, 600, tx("The finished object stays on screen at the end")),
        number("constant_rate_factor", tx("Quality (CRF)"), 0, 51, tx("Lower: better and bigger; 23 is the usual")),
        h("div", { className: "oui-list timelapse-switches" }, switchRow("previewimage", tx("Preview picture"), tx("The last frame, shown in the list")), switchRow("saveframes", tx("Keep the frames"), tx("A .zip next to the video"))),
        h(
          "button",
          { type: "button", className: cx("timelapse-advanced-toggle", advanced && "is-open"), "aria-expanded": advanced, "data-timelapse-advanced": "1", onClick: () => setAdvanced(!advanced) },
          h("span", null, tx("Advanced")),
          h("span", { className: "timelapse-advanced-toggle__hint" }, tx("Parking, photo timing, video encoding")),
          h(Icons.Chevron, { size: 16 }),
        ),
        advanced &&
          h(
            "div",
            { className: "timelapse-advanced" },
            settings.parkhead &&
              group(
                tx("Parking the head"),
                settings.parkpos === "custom" && number("park_custom_pos_x", tx("X position (mm)"), -1000, 1000, null, true),
                settings.parkpos === "custom" && number("park_custom_pos_y", tx("Y position (mm)"), -1000, 1000, null, true),
                number("park_custom_pos_dz", tx("Raise Z by (mm)"), 0, 50, tx("Lifts the nozzle off the print while parked"), true),
                number("park_travel_speed", tx("Travel speed (mm/s)"), 1, 1000),
                number("park_time", tx("Wait while parked (s)"), 0, 30, tx("Time for the camera to take a sharp photo"), true),
                h("div", { className: "oui-list timelapse-switches" }, switchRow("fw_retract", tx("Firmware retraction"), tx("G10/G11 instead of the distances below"))),
                !settings.fw_retract && number("park_retract_distance", tx("Retract (mm)"), 0, 20, tx("Against oozing while the head is away"), true),
                !settings.fw_retract && number("park_retract_speed", tx("Retract speed (mm/s)"), 1, 200),
                !settings.fw_retract && number("park_extrude_distance", tx("Extrude back (mm)"), 0, 20, null, true),
                !settings.fw_retract && number("park_extrude_speed", tx("Extrude speed (mm/s)"), 1, 200),
              ),
            group(
              tx("The photo"),
              !settings.camera && text("snapshoturl", tx("Snapshot address"), tx("Used when no camera is chosen")),
              number("stream_delay_compensation", tx("Delay of the camera (s)"), 0, 10, tx("Waits this long before the photo, for a stream that lags behind"), true),
              h("div", { className: "oui-list timelapse-switches" }, switchRow("wait_for_snapshot", tx("Wait for the photo"), tx("The print waits until the photo is taken")), switchRow("gcode_verbose", tx("Messages in the console"), tx("A line for every photo"))),
            ),
            group(
              tx("The video"),
              settings.variable_fps && number("variable_fps_min", tx("At least (frames a second)"), 1, 120),
              settings.variable_fps && number("variable_fps_max", tx("At most (frames a second)"), 1, 120),
              chips("rotation", tx("Turn the video"), [0, 90, 180, 270].map((degrees) => ({ id: degrees, label: degrees + "°" }))),
              h("div", { className: "oui-list timelapse-switches" }, switchRow("flip_x", tx("Mirror left-right")), switchRow("flip_y", tx("Mirror up-down"))),
              text("pixelformat", tx("Pixel format"), tx("yuv420p plays everywhere")),
              text("time_format_code", tx("Date in the file name"), tx("Like %Y%m%d_%H%M (year, month, day, hour, minute)")),
              text("extraoutputparams", tx("More ffmpeg options"), tx("For those who know ffmpeg; empty is fine")),
            ),
          ),
      ),
    h(TimelapseSaveBar, { timelapse }),
  );
}

/** 1.67: «Save»: in moonraker.conf, section [timelapse], then Moonraker restarts to read it. */
function TimelapseSaveBar({ timelapse }) {
  return h(
    "div",
    { className: cx("timelapse-save", timelapse.dirty && "is-dirty"), "data-timelapse-save": timelapse.saving ? "saving" : timelapse.dirty ? "dirty" : "clean" },
    h("p", { className: "oui-caption timelapse-where" }, timelapse.saving ? tx("Saving in moonraker.conf and restarting Moonraker…") : timelapse.dirty ? tx("Changes not saved yet. «Save» writes them in moonraker.conf (section [timelapse]) and restarts Moonraker, which takes a few seconds.") : tx("Saved in moonraker.conf, section [timelapse]. Changes are written there with «Save», and Moonraker restarts to read them.")),
    (timelapse.dirty || timelapse.saving) &&
      h(
        "div",
        { className: "oui-btn-row timelapse-save__buttons" },
        h("button", { type: "button", className: "oui-btn", disabled: timelapse.saving, onClick: timelapse.discard }, tx("Undo changes")),
        h("button", { type: "button", className: "oui-btn oui-btn--primary", "data-timelapse-save-btn": "1", disabled: timelapse.saving, onClick: timelapse.save }, timelapse.saving ? tx("Restarting Moonraker…") : tx("Save and restart Moonraker")),
      ),
  );
}

/* ---------------------------------------------------------------------------
   Without moonraker-timelapse (1.56): what it is and how to install it
   ------------------------------------------------------------------------- */
const TIMELAPSE_INSTALL = "cd ~\ngit clone https://github.com/mainsail-crew/moonraker-timelapse.git\ncd ~/moonraker-timelapse\nmake install";
const TIMELAPSE_MOONRAKER_CONF = "[timelapse]\n\n[update_manager timelapse]\ntype: git_repo\nprimary_branch: main\npath: ~/moonraker-timelapse\norigin: https://github.com/mainsail-crew/moonraker-timelapse.git\nmanaged_services: klipper moonraker";

function TimelapseStep({ number, title, children }) {
  return h("li", { className: "timelapse-step" }, h("span", { className: "timelapse-step__number", "aria-hidden": "true" }, number), h("div", { className: "timelapse-step__body" }, h("div", { className: "timelapse-step__title" }, title), children));
}

function TimelapseMissingCard() {
  return h(Card, { className: "timelapse-missing" }, h(CardHeader, { title: "Timelapse" }), h(TimelapseMissingContent));
}

/** What moonraker-timelapse is and how to install it: on the Files page and in Settings → Camera → Timelapse (1.59). */
function TimelapseMissingContent() {
  return h(
    "div",
    { className: "timelapse-missing__body" },
    h("p", { className: "timelapse-missing__intro" }, tx("To record a video of every print, Moonraker needs moonraker-timelapse: a free add-on by the Mainsail team. Once it is installed, the videos and their settings appear here.")),
    h(
      "ol",
      { className: "timelapse-steps" },
      h(TimelapseStep, { number: 1, title: tx("Install it") }, h("p", { className: "oui-caption" }, tx("On the Raspberry, in a terminal (SSH). With KIAUH you can install it from its menu instead.")), h(CodeBlock, { code: TIMELAPSE_INSTALL, lang: "bash" })),
      h(
        TimelapseStep,
        { number: 2, title: tx("Check the configuration") },
        h("p", { className: "oui-caption" }, tx("The installer usually adds these lines by itself. If they are missing, add them in Config: in moonraker.conf (the second section keeps it updated)…")),
        h(CodeBlock, { code: TIMELAPSE_MOONRAKER_CONF, lang: "conf" }),
        h("p", { className: "oui-caption" }, tx("…and in printer.cfg:")),
        h(CodeBlock, { code: "[include timelapse.cfg]", lang: "cfg" }),
      ),
      h(TimelapseStep, { number: 3, title: tx("Restart") }, h("p", { className: "oui-caption" }, tx("Restart Moonraker and Klipper (the power button at the top), then come back here."))),
      h(TimelapseStep, { number: 4, title: tx("In the slicer") }, h("p", { className: "oui-caption" }, tx("To take a picture at every layer, add TIMELAPSE_TAKE_FRAME to the slicer's layer change G-code. Without it, choose «Every few seconds» in the settings."))),
    ),
    h(TimelapseRecheck),
  );
}

/**
 * «Installed: check again» (1.63): Moonraker loads its components when it starts, so it is restarted first (a print
 * going on does not stop), then asked again; found, the page reloads with the timelapse.
 */
function TimelapseRecheck() {
  const [phase, setPhase] = useState("idle"); // idle | restarting | missing | failed
  const recheck = async () => {
    setPhase("restarting");
    try {
      await moonraker.serviceAction("restart", "moonraker");
    } catch (error) {}
    const end = Date.now() + 45000;
    let answered = 0;
    await new Promise((resolve) => setTimeout(resolve, 3000));
    while (Date.now() < end) {
      try {
        const json = await fetchJson("/server/info", { timeout: 3000 });
        const components = ((json && json.result) || {}).components || [];
        if (components.includes("timelapse")) return window.location.reload();
        if (json && json.result && ++answered >= 3) return setPhase("missing"); // Moonraker is back, without it
      } catch (error) {}
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    setPhase("failed");
  };
  return h(
    React.Fragment,
    null,
    h("button", { type: "button", className: "oui-btn oui-btn--block timelapse-recheck", disabled: phase === "restarting", onClick: recheck }, h(Icons.Refresh, { size: 16 }), phase === "restarting" ? tx("Restarting Moonraker…") : tx("Installed: check again")),
    h("p", { className: "oui-caption timelapse-recheck__note", "data-recheck": phase }, phase === "missing" ? tx("Moonraker restarted but has no timelapse yet: check that moonraker.conf has the [timelapse] section (step 2).") : phase === "failed" ? tx("Moonraker did not come back: try again in a moment.") : tx("Moonraker restarts to find it (a print going on does not stop).")),
  );
}

/* ---------------------------------------------------------------------------
   The page
   ------------------------------------------------------------------------- */
function TimelapsePage({ desktop }) {
  const timelapse = useTimelapse();
  const [playing, setPlaying] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const remove = async () => {
    const video = deleting;
    setDeleting(null);
    try {
      await timelapseApi.remove(video.path);
      if (video.previewPath) timelapseApi.remove(video.previewPath).catch(noop); // the preview picture goes with its video
      timelapse.forget(video.path);
      toast.notice(tx("Deleted: ") + video.path);
    } catch (error) {
      toast.action(tx("Delete failed: ") + (error.message || error));
    }
  };
  const videos = h(TimelapseVideosCard, { timelapse, onPlay: setPlaying, onDelete: setDeleting });
  const settings = h(TimelapseSettingsCard, { timelapse });
  return h(
    React.Fragment,
    null,
    desktop ? h("div", { className: "desk-split desk-split--timelapse" }, h("div", { className: "desk-col" }, videos), h("div", { className: "desk-col" }, settings)) : h("div", { className: "timelapse-page" }, videos, settings),
    h(Presence, null, playing && h(TimelapseVideoViewer, { video: playing, onClose: () => setPlaying(null) })),
    h(ConfirmDialog, {
      open: Boolean(deleting),
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Delete the video?"),
      subtitle: deleting ? deleting.path : "",
      message: tx("It is deleted from the Raspberry for good."),
      confirmLabel: tx("Delete"),
      onConfirm: remove,
      onCancel: () => setDeleting(null),
    }),
  );
}
