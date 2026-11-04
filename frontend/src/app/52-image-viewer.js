/* ============================================================================
   52 · IMAGE VIEWER
   Full-screen preview for pictures stored in the config folder, with the
   resolution in the footer, a download button and "open in a new tab".
   ========================================================================== */

function ImageViewer({ path, onClose }) {
  const [info, setInfo] = useState(null);
  const url = path ? configFileUrl(path) : "";
  useBodyScrollLock(!!path);

  useEffect(() => {
    setInfo(path ? path + tx(" • loading...") : null);
  }, [path]);

  useEffect(() => {
    if (!path) return;
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [path, onClose]);

  if (!path) return null;

  const download = () => downloadFile(url, baseName(path) || "image");

  return h(
    "div",
    { className: "screen screen--viewer", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "screen-bar viewer-bar" },
      h("button", { className: "oui-btn oui-btn--icon", title: tx("Close"), "aria-label": tx("Close"), onClick: onClose }, "✕"),
      h("span", { className: "viewer-title" }, baseName(path) || path),
    ),
    h(
      "div",
      { className: "viewer-stage", onClick: (e) => e.target === e.currentTarget && onClose() },
      h("img", {
        src: url,
        alt: "preview",
        onLoad: (e) => setInfo(path + " • " + e.currentTarget.naturalWidth + "x" + e.currentTarget.naturalHeight),
        onError: () => setInfo(path + tx(" • loading error")),
      }),
    ),
    h(
      "div",
      { className: "screen-bar viewer-footer" },
      h("div", { className: "viewer-info" }, info),
      h("div", { className: "oui-btn-row viewer-actions" }, h("button", { className: "oui-btn oui-btn--sm", onClick: download }, tx("Download")), h("button", { className: "oui-btn oui-btn--sm oui-btn--primary", onClick: () => window.open(url, "_blank") }, tx("Open in a new tab"))),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Photo viewer (1.25): a picture of the AI monitor (an alarm, a recording) over the whole screen, to look at it closely.
   Fit to the screen; a tap (or the button) shows it at its real size, to scroll around; pinch zoom works too.
   openPhoto(src, title) from anywhere; PhotoViewerLayer is mounted once by the application.
   ------------------------------------------------------------------------- */
const photoListeners = new Set();
let photoOpen = null; // { src, title }

function openPhoto(src, title) {
  if (!src) return;
  photoOpen = { src, title: title || "" };
  photoListeners.forEach((listener) => listener(photoOpen));
}

function closePhoto() {
  photoOpen = null;
  photoListeners.forEach((listener) => listener(null));
}

/** A picture that opens in the photo viewer when tapped. */
function ZoomablePhoto({ src, title, className, alt }) {
  return h(
    "button",
    { type: "button", className: cx("zoom-photo", className), "aria-label": tx("Enlarge the picture"), title: tx("Enlarge the picture"), "data-zoom": src, onClick: (event) => (event.stopPropagation(), openPhoto(src, title)) },
    h("img", { src, alt: alt || title || "", loading: "lazy" }),
    h("span", { className: "zoom-photo__hint", "aria-hidden": "true" }, h(Icons.Search, { size: 14 })),
  );
}

function PhotoViewerLayer() {
  const [photo, setPhoto] = useState(photoOpen);
  useEffect(() => {
    photoListeners.add(setPhoto);
    return () => photoListeners.delete(setPhoto);
  }, []);
  return photo ? h(PhotoViewer, { key: photo.src, photo }) : null;
}

/**
 * 1.67: the picture over the whole screen, like the camera's full screen: black, edge to edge, the app's bars hidden
 * (the browser's own full screen elsewhere), turned to fit a screen that stays upright. A tap shows or hides the
 * buttons; «Real size» shows it pixel for pixel, to scroll around.
 */
function PhotoViewer({ photo }) {
  const [real, setReal] = useState(false);
  const [controls, setControls] = useState(true);
  const box = useRef(null);
  const hideTimer = useRef(null);
  const viewport = useViewportSize();
  const [landscape, setLandscape] = useState(null); // the picture's own shape, once loaded
  const picture = useRef(null);
  const measure = () => {
    const img = picture.current;
    if (img && img.naturalWidth) setLandscape(img.naturalWidth > img.naturalHeight);
  };
  useEffect(measure, []); // a picture already in the cache may have loaded before onLoad was listened to
  useBodyScrollLock(true);
  useBackHandler(() => {
    closePhoto();
    return true;
  }, true);
  useScreenTakeover(box, closePhoto);
  const showControls = () => {
    setControls(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setControls(false), CAMERA_CONTROLS_HIDE_MS);
  };
  useEffect(() => {
    showControls();
    const onKey = (event) => event.key === "Escape" && (event.stopPropagation(), closePhoto());
    window.addEventListener("keydown", onKey, true);
    return () => {
      clearTimeout(hideTimer.current);
      window.removeEventListener("keydown", onKey, true);
    };
  }, []);
  // a wide picture on a screen that stays upright (a browser that cannot turn it) is turned 90°, as the camera is
  const rotated = !real && landscape === true && viewport.h > viewport.w;
  const stage = rotated ? { width: viewport.h + "px", height: viewport.w + "px" } : undefined;
  return h(
    "div",
    {
      ref: box,
      className: cx("photo-viewer", controls && "is-controls"),
      role: "dialog",
      "aria-modal": "true",
      "aria-label": photo.title || tx("Picture"),
      "data-photo-open": "1",
      "data-rotated": rotated ? "true" : "false",
      onClick: () => (controls ? setControls(false) : showControls()),
      onPointerMove: (event) => event.pointerType === "mouse" && showControls(),
    },
    h(
      "div",
      { className: cx("photo-viewer__stage", real && "is-real", rotated && "is-rotated"), style: stage },
      h("img", { ref: picture, src: photo.src, alt: photo.title, onLoad: measure }),
    ),
    h(
      "div",
      { className: "photo-viewer__bar", onClick: (event) => event.stopPropagation() },
      h("button", { type: "button", className: "camera-full__btn", title: tx("Close"), "aria-label": tx("Close"), onClick: closePhoto }, h(Icons.Close)),
      h("span", { className: "photo-viewer__title" }, photo.title),
      h("button", { type: "button", className: "oui-btn oui-btn--sm photo-viewer__size", "data-photo-size": real ? "real" : "fit", onClick: () => (setReal(!real), showControls()) }, real ? tx("Fit to the screen") : tx("Real size")),
    ),
  );
}
