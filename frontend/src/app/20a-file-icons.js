/* ============================================================================
   20a · FILE ICONS
   One place decides how a file or a folder looks: a soft tinted tile with a line icon in it, the way
   One UI draws the type of a file. Used by the config files, the system logs, the move-to chooser and
   (as the placeholder of a print without preview) by every thumbnail.
     fileKind(name, options)   what a file is: { icon, tone }
     FileGlyph                 the tile of that kind
     PrintPlaceholder          the tile standing where the preview of a G-code file would be
   The tiles are styled in css/21a-file-icons.css (the tones are named there).
   ========================================================================== */

/**
 * The kinds by extension (the last one of the name: "moonraker.conf.bkp" is a .bkp). Every file of an extension looks the
 * same, whatever its name: printer.cfg, macros.cfg and moonraker.conf all wear the sliders.
 */
const FILE_KIND_BY_EXTENSION = {
  cfg: { icon: "Sliders", tone: "accent" },
  conf: { icon: "Sliders", tone: "accent" },
  bkp: { icon: "Doc", tone: "neutral" },
  log: { icon: "Terminal", tone: "neutral" },
  gcode: { icon: "Cube", tone: "accent" },
  gco: { icon: "Cube", tone: "accent" },
  g: { icon: "Cube", tone: "accent" },
  json: { icon: "Braces", tone: "neutral" },
  yaml: { icon: "Braces", tone: "neutral" },
  yml: { icon: "Braces", tone: "neutral" },
  toml: { icon: "Braces", tone: "neutral" },
  py: { icon: "Code", tone: "cool" },
  sh: { icon: "Code", tone: "cool" },
  bash: { icon: "Code", tone: "cool" },
  js: { icon: "Code", tone: "cool" },
  service: { icon: "Code", tone: "cool" },
  bak: { icon: "Backup", tone: "neutral" },
  old: { icon: "Backup", tone: "neutral" },
  orig: { icon: "Backup", tone: "neutral" },
  backup: { icon: "Backup", tone: "neutral" },
};

const FILE_KIND_FOLDER = { icon: "Folder", tone: "warn" };
const FILE_KIND_IMAGE = { icon: "Image", tone: "ok" };
const FILE_KIND_OTHER = { icon: "Doc", tone: "neutral" };

/**
 * The kind of a file as { icon, tone } (`icon` is a component of Icons, `tone` a colour of the tile).
 * `folder` / `image` are for the caller to say when it already knows (the config files decide what an image is).
 */
function fileKind(name, { folder = false, image = false } = {}) {
  const spec = folder ? FILE_KIND_FOLDER : image ? FILE_KIND_IMAGE : fileKindSpec(name || "");
  return { icon: Icons[spec.icon], tone: spec.tone };
}

function fileKindSpec(name) {
  // "moonraker.log.1", "klippy.log.2024-01-01": a rotated log is still a log; a name ending in ~ is a copy
  const extension = /\.log(\.[^.]+)?$/i.test(name) ? "log" : /~$/.test(name) ? "bak" : name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  return FILE_KIND_BY_EXTENSION[extension] || FILE_KIND_OTHER;
}

/** The tile of a kind: 40 px in a list, `large` (64 px) at the top of a menu. */
function FileGlyph({ kind, large = false }) {
  const Icon = kind.icon;
  return h("span", { className: cx("fi", "fi--" + kind.tone, large && "fi--lg"), "aria-hidden": "true" }, h(Icon, { size: large ? 30 : 20 }));
}

/** Where the preview of a print would be and there is none: it fills the middle of its (round or square) frame. */
function PrintPlaceholder() {
  return h("span", { className: "fi fi--accent fi--placeholder", "aria-hidden": "true" }, h(Icons.Cube, { size: 28 }));
}
