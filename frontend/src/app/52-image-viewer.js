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
  const [real, setReal] = useState(false);
  useEffect(() => {
    photoListeners.add(setPhoto);
    return () => photoListeners.delete(setPhoto);
  }, []);
  useEffect(() => setReal(false), [photo]);
  useBodyScrollLock(Boolean(photo));
  useBackHandler(() => {
    closePhoto();
    return true;
  }, Boolean(photo));
  useEffect(() => {
    if (!photo) return undefined;
    const onKey = (event) => event.key === "Escape" && (event.stopPropagation(), closePhoto());
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [photo]);
  if (!photo) return null;
  return h(
    "div",
    { className: "screen screen--viewer photo-viewer", role: "dialog", "aria-modal": "true", "aria-label": photo.title || tx("Picture"), "data-photo-open": "1" },
    h(
      "div",
      { className: "screen-bar viewer-bar" },
      h("button", { className: "oui-btn oui-btn--icon", title: tx("Close"), "aria-label": tx("Close"), onClick: closePhoto }, "✕"),
      h("span", { className: "viewer-title" }, photo.title),
      h("button", { className: "oui-btn oui-btn--sm", "data-photo-size": real ? "real" : "fit", onClick: () => setReal(!real) }, real ? tx("Fit to the screen") : tx("Real size")),
    ),
    h(
      "div",
      { className: cx("viewer-stage", "photo-viewer__stage", real && "is-real"), onClick: (event) => event.target === event.currentTarget && closePhoto() },
      h("img", { src: photo.src, alt: photo.title, onClick: () => setReal(!real) }),
    ),
  );
}
