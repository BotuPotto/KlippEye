/* ============================================================================
   59p · SETTINGS → CAMERA: EVERY CAMERA, ONE PAGE EACH (1.59)
   The Camera page lists:
     · the main camera (KlippEye's own setting: the one the AI monitor watches),
       on its page "camera-main" (method, address, image, snapshot, Mainsail);
     · the webcams kept by Moonraker, the same ones Mainsail and Fluidd show and
       edit (/server/webcams/*): each on its page, as in Mainsail's Webcam
       settings (name, kind, addresses, frames a second, image, on / off),
       saved to Moonraker at once; "Add a camera" makes a new one; a webcam
       written in moonraker.conf can only be read;
     · Timelapse: the settings of moonraker-timelapse (or how to install it).
   ========================================================================== */

const WEBCAM_PAGE_PREFIX = "webcam:";
/** The kinds of webcam this dashboard can show, as Moonraker / Mainsail name them. */
const WEBCAM_SERVICES = [
  { id: "webrtc-camerastreamer", label: "WebRTC (camera-streamer)" },
  { id: "mjpegstreamer", label: "MJPEG" },
  { id: "mjpegstreamer-adaptive", label: tx("MJPEG adaptive") },
  { id: "iframe", label: tx("Web page") },
];
const WEBCAM_ROTATIONS = [0, 90, 180, 270];
/** The name of each webcam's page, for the title bar (filled when the list is read). */
const webcamTitles = {};

const webcamsApi = {
  async list() {
    const json = await fetchJson("/server/webcams/list", { timeout: SETTINGS_DB_TIMEOUT_MS });
    const list = json && json.result && Array.isArray(json.result.webcams) ? json.result.webcams.filter(isPlainObject) : [];
    list.forEach((cam) => cam.uid && (webcamTitles[WEBCAM_PAGE_PREFIX + cam.uid] = String(cam.name || tx("Camera"))));
    return list;
  },
  /** Adds a webcam, or changes the one with the same uid; answers the saved webcam. */
  async save(cam) {
    const response = await fetchFresh("/server/webcams/post_item", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(cam) });
    if (!response.ok) throw new Error(await responseError(response));
    webcamsAsk = null; // the camera picker reads the list again
    const json = await response.json().catch(() => ({}));
    return (json.result && json.result.webcam) || cam;
  },
  async remove(uid) {
    const response = await fetchFresh("/server/webcams/delete_item?uid=" + encodeURIComponent(uid), { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
    webcamsAsk = null;
  },
};

const webcamPageTitle = (page) => webcamTitles[page] || tx("Camera");
const webcamServiceLabel = (service) => (WEBCAM_SERVICES.find((one) => one.id === service) || {}).label || service || "?";

/** The webcams of Moonraker, read when the page opens; `reload` after a change. */
function useWebcams() {
  const [state, setState] = useState({ list: null, error: "" });
  const load = () => {
    webcamsApi
      .list()
      .then((list) => setState({ list, error: "" }))
      .catch((error) => setState({ list: [], error: error.message || tx("Error") }));
  };
  useEffect(() => load(), []);
  return { ...state, reload: load };
}

/** A row that opens a page, with any line under the name (the menu's own rows). */
function CameraRow({ page, title, meta, icon, menu, off }) {
  return h(
    "button",
    { type: "button", className: cx("set-entry", off && "is-off"), "data-page": page, onClick: () => menu.goTo(page) },
    h("span", { className: "oui-row__icon oui-row__icon--accent" }, icon || h(Icons.Camera)),
    h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, title), meta ? h("span", { className: "oui-row__meta set-entry__meta" }, meta) : null),
    h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
  );
}

/** A free name for a new webcam: "Camera 2", "Camera 3"… */
function freeWebcamName(list) {
  const names = new Set(list.map((cam) => String(cam.name || "").toLowerCase()));
  for (let n = list.length + 1; ; n += 1) if (!names.has(("camera " + n).toLowerCase())) return "Camera " + n;
}

function CamerasPage({ menu }) {
  const { settings } = useSettings();
  const camera = settings.camera;
  const webcams = useWebcams();
  const timelapse = useHasTimelapse();
  const [adding, setAdding] = useState(false);
  const add = async () => {
    setAdding(true);
    try {
      const n = (webcams.list || []).length + 2;
      const saved = await webcamsApi.save({ name: freeWebcamName(webcams.list || []), service: "webrtc-camerastreamer", enabled: true, location: "printer", icon: "mdiWebcam", stream_url: "/webcam" + n + "/webrtc", snapshot_url: "/webcam" + n + "/?action=snapshot", target_fps: 15, target_fps_idle: 5, flip_horizontal: false, flip_vertical: false, rotation: 0, aspect_ratio: "16:9" });
      await webcamsApi.list();
      if (saved.uid) menu.goTo(WEBCAM_PAGE_PREFIX + saved.uid);
      else webcams.reload();
    } catch (error) {
      toast.action(tx("The camera was not added: ") + (error.message || error));
    }
    setAdding(false);
  };
  const method = CAMERA_METHODS.find((one) => one.id === camera.method);
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("The camera of KlippEye"), note: tx("The one the AI monitor watches and the camera card shows first.") },
      h("div", { className: "oui-list" }, h(CameraRow, { page: "camera-main", title: tx("Main camera"), meta: method.label + " · " + camera.urls[camera.method], menu })),
    ),
    h(
      SettingsGroup,
      { title: tx("Cameras of the printer"), note: tx("The ones Moonraker keeps for every program of the printer: a change here is a change there too. The camera card can show any of them.") },
      webcams.list === null
        ? h("p", { className: "set-group__note" }, tx("Loading..."))
        : webcams.list.length > 0 &&
            h(
              "div",
              { className: "oui-list", "data-webcams": webcams.list.length },
              webcams.list.map((cam) =>
                h(CameraRow, {
                  key: cam.uid || cam.name,
                  page: WEBCAM_PAGE_PREFIX + (cam.uid || ""),
                  title: String(cam.name || tx("Camera")),
                  meta: [cam.enabled === false ? tx("Off") : "", webcamServiceLabel(cam.service), cam.stream_url].filter(Boolean).join(" · "),
                  off: cam.enabled === false,
                  menu,
                }),
              ),
            ),
      webcams.error && h("p", { className: "set-group__note set-group__note--warn" }, tx("Cannot read the cameras: {error}", { error: webcams.error })),
      h("button", { type: "button", className: "oui-btn oui-btn--block", "data-webcam-add": "1", disabled: adding || webcams.list === null, onClick: add }, h(Icons.Plus, { size: 18 }), adding ? tx("Adding…") : tx("Add a camera")),
    ),
    h(
      SettingsGroup,
      { title: "Timelapse" },
      h("div", { className: "oui-list" }, h(CameraRow, { page: "camera-timelapse", title: tx("Timelapse settings"), meta: timelapse === false ? tx("moonraker-timelapse is not installed: how to") : tx("Videos of the prints: when photos are taken, the video"), icon: h(Icons.Play), menu })),
    ),
    h(SettingsGroup, { title: tx("For the AI monitor") }, h(SubpageRow, { entry: AI_SUBPAGES[0], meta: tx("Where the bed and the nozzle are in the picture: needed to watch the whole bed"), menu })),
    h(SettingsGroup, null, h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: requestCameraReload }, h(Icons.Refresh, { size: 18 }), tx("Reload the camera"))),
  );
}

/** One webcam of Moonraker, as in Mainsail's settings: every change is saved at once. */
function WebcamPage({ uid, menu }) {
  const webcams = useWebcams();
  const [deleting, setDeleting] = useState(false);
  const [problem, setProblem] = useState("");
  const [local, setLocal] = useState(null); // the webcam as last saved here (the list is read once)
  const cam = local || (webcams.list || []).find((one) => one.uid === uid);
  if (webcams.list === null) return h("p", { className: "set-group__note" }, tx("Loading..."));
  if (!cam) return h("p", { className: "set-group__note" }, tx("This camera is not there any more."));
  const readOnly = cam.source === "config";
  const save = async (changes) => {
    const next = { ...cam, ...changes };
    setLocal(next);
    try {
      const saved = await webcamsApi.save(next);
      setLocal({ ...next, ...saved });
      webcamTitles[WEBCAM_PAGE_PREFIX + uid] = String(next.name);
      setProblem("");
    } catch (error) {
      setLocal(cam);
      setProblem(error.message || String(error));
    }
  };
  const remove = async () => {
    setDeleting(false);
    try {
      await webcamsApi.remove(uid);
      toast.notice(tx("Camera removed: {name}", { name: cam.name }));
      menu.back();
    } catch (error) {
      setProblem(error.message || String(error));
    }
  };
  const known = WEBCAM_SERVICES.some((one) => one.id === cam.service);
  const services = known ? WEBCAM_SERVICES : WEBCAM_SERVICES.concat({ id: cam.service, label: String(cam.service) });
  const address = (key, label, hint) =>
    h(TextSetting, {
      key: key + "|" + cam[key],
      label,
      value: String(cam[key] || ""),
      validate: (text) => (typeof text === "string" && text.trim() === "" && key === "snapshot_url" ? "" : cleanCameraAddress(text)),
      error: tx("Write a path that starts with / (like /webcam/webrtc) or a full address http://…"),
      hint,
      inputMode: "url",
      onCommit: (value) => !readOnly && value !== cam[key] && save({ [key]: value }),
    });
  return h(
    React.Fragment,
    null,
    readOnly && h("div", { className: "set-status set-status--warn", "data-webcam-config": "1" }, h("span", { className: "set-status__dot" }), tx("This camera is written in moonraker.conf: it can be changed only there.")),
    problem && h("p", { className: "set-field__error", role: "alert" }, tx("Not saved: {error}", { error: problem })),
    h(
      "fieldset",
      { className: "webcam-fields", disabled: readOnly },
      h(
        SettingsGroup,
        { title: tx("Name") },
        h(TextSetting, {
          key: "name|" + cam.name,
          label: tx("Name of the camera"),
          value: String(cam.name || ""),
          validate: (text) => (typeof text === "string" && text.trim().length > 0 && text.trim().length <= 40 ? text.trim() : null),
          error: tx("From 1 to 40 characters"),
          onCommit: (name) => name !== cam.name && save({ name }),
        }),
        h("div", { className: "oui-list" }, h(SwitchRow, { title: tx("On"), detail: tx("Off: it is not shown, here or in the other programs"), checked: cam.enabled !== false, disabled: readOnly, onChange: (enabled) => save({ enabled }) })),
      ),
      h(SettingsGroup, { title: tx("Kind") }, h(ChoiceRows, { label: tx("Kind"), options: services.map((one) => ({ id: one.id, label: one.label })), value: cam.service, onChange: (service) => !readOnly && save({ service }) })),
      !known && h("p", { className: "set-group__note set-group__note--warn" }, tx("KlippEye cannot show this kind: choose one of the others to see it here.")),
      h(SettingsGroup, { title: tx("Addresses") }, address("stream_url", tx("Address of the video"), tx("A path on the printer (/webcam2/…) or a full address http://…")), address("snapshot_url", tx("Address of the snapshot"), tx("The single photo (the timelapse can use it)."))),
      h(
        SettingsGroup,
        { title: tx("Frames per second"), note: tx("For MJPEG adaptive: how many pictures a second.") },
        h(TextSetting, {
          key: "fps|" + cam.target_fps,
          label: tx("Frames per second"),
          value: String(cam.target_fps || 15),
          inputMode: "numeric",
          validate: (text) => {
            const value = Number(text);
            return Number.isInteger(value) && value >= 1 && value <= 60 ? value : null;
          },
          error: tx("From {min} to {max}", { min: 1, max: 60 }),
          onCommit: (target_fps) => target_fps !== cam.target_fps && save({ target_fps }),
        }),
      ),
      h(
        SettingsGroup,
        { title: tx("Image") },
        h(
          "div",
          { className: "oui-list" },
          h(SwitchRow, { title: tx("Mirror (horizontal)"), detail: tx("Left and right swapped"), checked: cam.flip_horizontal === true, disabled: readOnly, onChange: (value) => save({ flip_horizontal: value }) }),
          h(SwitchRow, { title: tx("Flip (vertical)"), detail: tx("Top and bottom swapped"), checked: cam.flip_vertical === true, disabled: readOnly, onChange: (value) => save({ flip_vertical: value }) }),
        ),
        h("div", { className: "set-field__label" }, tx("Rotation")),
        h(ChipChoice, { label: tx("Rotation"), options: WEBCAM_ROTATIONS.map((degrees) => ({ id: String(degrees), label: degrees + "°" })), value: String(Number(cam.rotation) || 0), onChange: (degrees) => !readOnly && save({ rotation: Number(degrees) }) }),
      ),
    ),
    !readOnly && h("button", { type: "button", className: "oui-btn oui-btn--danger-soft oui-btn--block", "data-webcam-delete": "1", onClick: () => setDeleting(true) }, h(Icons.Trash, { size: 18 }), tx("Remove this camera")),
    h(ConfirmDialog, {
      open: deleting,
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Remove this camera?"),
      subtitle: String(cam.name || ""),
      message: tx("It is removed from Moonraker: the other programs of the printer will not show it either."),
      confirmLabel: tx("Remove"),
      onConfirm: remove,
      onCancel: () => setDeleting(false),
    }),
  );
}

/** Settings → Camera → Timelapse: moonraker-timelapse's settings, or how to install it. */
function CameraTimelapsePage() {
  const has = useHasTimelapse();
  if (has === null) return h("p", { className: "set-group__note" }, tx("Loading..."));
  if (!has) return h(TimelapseMissingContent);
  return h(TimelapseSettingsInDrawer);
}

function TimelapseSettingsInDrawer() {
  const timelapse = useTimelapse();
  if (!timelapse.values) return h("p", { className: "set-group__note" }, timelapse.error || tx("Loading..."));
  return h(SettingsGroup, null, h(TimelapseSettingsFields, { timelapse }));
}

/** 1.67: which camera takes the photos: one of the settings saved with «Save» (in the card of the Files page too). */
function TimelapseCameraChoice({ timelapse }) {
  const webcams = useWebcams();
  const names = (webcams.list || []).filter((cam) => cam.enabled !== false).map((cam) => String(cam.name));
  if (!names.length) return null;
  const current = String(timelapse.values.camera || "");
  return h(
    "div",
    { className: "timelapse-camera", "data-setting": "camera" },
    h("div", { className: "set-field__label timelapse-label" }, tx("Which camera")),
    h(ChoiceRows, { label: tx("Which camera"), options: [{ id: "", label: tx("The default one"), detail: timelapse.values.snapshoturl || "" }].concat(names.map((name) => ({ id: name, label: name }))), value: names.includes(current) ? current : "", onChange: (choice) => timelapse.edit({ camera: choice }) }),
  );
}
