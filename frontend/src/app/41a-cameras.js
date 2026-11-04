/* ============================================================================
   41a · MORE CAMERAS (1.48, roadmap 6d part 7)
   Besides the camera of the settings (the one the AI monitor watches), the
   webcams set up in Mainsail or Fluidd (Moonraker keeps them: /server/webcams/
   list) that this dashboard can show: when there is more than one, the camera
   card (and the computer's camera panel, and the full screen) has a menu to
   pick which one to watch. The choice is kept on this device; the settings'
   camera is always the first.
   ========================================================================== */

const CAMERA_CHOICE_KEY = "ke_camera";
const CAMERAS_REFRESH_MS = 60000;

const cameraChoiceStore = (() => {
  const listeners = new Set();
  let current = "main";
  try {
    current = localStorage.getItem(CAMERA_CHOICE_KEY) || "main";
  } catch (e) {}
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => current,
    set(id) {
      current = id;
      try {
        localStorage.setItem(CAMERA_CHOICE_KEY, id);
      } catch (e) {}
      listeners.forEach((fn) => fn());
    },
  };
})();

/** Moonraker's webcams that can be shown here, read once a minute at most (a shared promise). */
let webcamsAsk = null;
let webcamsAskedAt = 0;
function sharedWebcams() {
  if (!webcamsAsk || Date.now() - webcamsAskedAt > CAMERAS_REFRESH_MS) {
    webcamsAskedAt = Date.now();
    webcamsAsk = loadMainsailWebcams().catch(() => []);
  }
  return webcamsAsk;
}

/**
 * The cameras to choose from: { id, name, method, address, fps, flipH, flipV }. "main" is the settings' camera; a webcam
 * that is the same camera (same method and address) is left out, and so are the kinds this dashboard cannot show.
 */
function useCameraList() {
  const { settings } = useSettings();
  const [webcams, setWebcams] = useState([]);
  useEffect(() => {
    let cancelled = false;
    sharedWebcams().then((list) => !cancelled && setWebcams(list));
    return () => {
      cancelled = true;
    };
  }, []);
  const camera = settings.camera;
  const main = { id: "main", name: tx("Camera"), method: camera.method, address: camera.urls[camera.method], fps: camera.fps, flipH: camera.flipH, flipV: camera.flipV };
  const others = webcams
    .filter((cam) => cam.method && !(cam.method === main.method && cam.address === main.address))
    .map((cam) => ({ id: "w:" + cam.name, name: cam.name, method: cam.method, address: cam.address, fps: cam.fps || camera.fps, flipH: cam.flipH, flipV: cam.flipV, rotation: cam.rotation }));
  return [main].concat(others);
}

/** The camera being watched (the settings' one when the choice is gone). */
function useCurrentCamera() {
  const list = useCameraList();
  const chosen = useSyncExternalStore(cameraChoiceStore.subscribe, cameraChoiceStore.snapshot);
  return { list, current: list.find((cam) => cam.id === chosen) || list[0] };
}

/** The menu that picks the camera: nothing when there is only one. */
function CameraPicker({ className }) {
  const { list, current } = useCurrentCamera();
  const menu = useDropdown();
  if (list.length < 2) return null;
  return h(
    React.Fragment,
    null,
    h(
      "button",
      { type: "button", ref: menu.anchorRef, className: cx("camera-picker", menu.open && "is-open", className), "aria-haspopup": "menu", "aria-expanded": menu.open, "aria-label": tx("Choose the camera") + ": " + current.name, title: tx("Choose the camera") + ": " + current.name, "data-camera-now": current.id, onClick: menu.toggle },
      h(Icons.Camera, { size: 15 }),
      h("span", { className: "camera-picker__name" }, current.name),
      h(Icons.Chevron, { size: 14 }),
    ),
    h(
      DropdownMenu,
      { menu },
      h(MenuLabel, null, tx("Cameras")),
      list.map((cam) =>
        h(
          "button",
          { key: cam.id, type: "button", className: "oui-menu__item console-option", role: "menuitemradio", "aria-checked": cam.id === current.id, "data-camera": cam.id, onClick: () => (cameraChoiceStore.set(cam.id), menu.close()) },
          h("span", { className: "oui-menu__icon" }, cam.id === current.id ? h(Icons.Check, { size: 18 }) : null),
          h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, cam.name), h("span", { className: "oui-menu__sub" }, cam.id === "main" ? tx("The one of the settings (the AI monitor watches it)") : (CAMERA_METHODS.find((one) => one.id === cam.method) || {}).label + " · " + cam.address)),
        ),
      ),
    ),
  );
}
