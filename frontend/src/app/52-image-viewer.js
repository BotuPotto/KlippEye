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
