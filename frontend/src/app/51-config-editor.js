/* ============================================================================
   51 · TEXT EDITOR (1.41: CodeMirror 6)
   Full-screen editor for Klipper/Moonraker config files and G-code files (also
   used to read the system logs), built on CodeMirror 6 (vendor/codemirror-6.js,
   the global CM): line numbers, colours, the [sections] folded and unfolded,
   undo / redo, search and replace, brackets matched, the active line marked.
   Around it: the sections of the file (jump to one, fold them all), the page of
   Klipper's (or Moonraker's) reference for the section under the caret, and the
   comment bar, which puts a # (; in G-code) in front of the selected lines or
   takes one off.
   ========================================================================== */

const EDITOR_INDENT = "  ";
const EDITOR_LONG_DOC_CHARS = 512 * 1024; // 1.58: beyond this the text is copied out of the editor after a pause
const EDITOR_LONG_DOC_PAUSE_MS = 400;
const EDITOR_SAVE_SETTLE_MS = 300;
const EDITOR_AFTER_SAVE_CONFIG_MS = 1000;
const EDITOR_SAVE_CONFIG_FAILED_MS = 1500;
/** What the status line says about a comment / uncomment stays this long. */
const EDITOR_FLASH_MS = 2600;
const KLIPPER_CONFIG_DOCS = "https://www.klipper3d.org/Config_Reference.html";
const MOONRAKER_CONFIG_DOCS = "https://moonraker.readthedocs.io/en/latest/configuration/";

/* ---------------------------------------------------------------------------
   Colours: a Klipper config file (sections, keys, values, macros in Jinja2)
   and a G-code file. Token names are CodeMirror's highlighting tags.
   ------------------------------------------------------------------------- */
const CFG_SECTION_LINE = /^\[([^\]]*)\]/;
const CFG_KEY = /^[A-Za-z0-9_.-]+(?=\s*[:=])/;
const CFG_PIN_KEY = /^(pin|.*_pin|variable_.*)$/;
const CFG_GCODE_KEY = /gcode$/i;
const JINJA_KEYWORD = /^(set|if|elif|else|endif|for|endfor|in|is|not|and|or|macro|endmacro|call|endcall|filter|endfilter|raw|endraw)$/;
const JINJA_CONSTANT = /^(true|false|none|True|False|None)$/;

/** Only spaces before the stream's position: the token is the first of its line. */
const firstOfLine = (stream) => stream.string.slice(0, stream.pos).trim() === "";

/** A token inside a `gcode:` value: G-code commands and parameters, with Jinja2 between {% %} and {{ }}. */
function macroToken(stream, state) {
  if (stream.match("{%") || stream.match("{{")) {
    state.jinja++;
    return "meta";
  }
  if (stream.match("%}") || stream.match("}}")) {
    state.jinja = Math.max(0, state.jinja - 1);
    return "meta";
  }
  const ch = stream.peek();
  if (ch === "{" || ch === "}") {
    stream.next();
    return "meta";
  }
  if (stream.match(/^"(?:[^"\\]|\\.)*"?/) || stream.match(/^'(?:[^'\\]|\\.)*'?/)) return "string";
  if (stream.match(/^-?\d+(?:\.\d+)?/)) return "number";
  if (state.jinja > 0) {
    const word = stream.match(/^[A-Za-z_][A-Za-z0-9_]*/);
    if (word) return JINJA_KEYWORD.test(word[0]) ? "keyword" : JINJA_CONSTANT.test(word[0]) ? "bool" : "variableName";
  } else {
    const start = firstOfLine(stream);
    if (start && stream.match(/^[A-Za-z_][A-Za-z0-9_.]*/)) return "macroName";
    if (stream.match(/^[A-Za-z_][A-Za-z0-9_]*(?==)/)) return "propertyName";
    if (stream.match(/^[A-Za-z](?=[-+.\d{])/)) return "propertyName";
    if (stream.match(/^[A-Za-z_][A-Za-z0-9_]*/)) return null;
  }
  if (stream.match(/^[=|<>!+\-*/~%]+/)) return "operator";
  stream.next();
  return null;
}

/** The value of a key that is not G-code: numbers, true / false, text. */
function valueToken(stream) {
  if (stream.match(/^-?\d+(?:\.\d+)?(?![A-Za-z0-9_])/)) return "number";
  if (stream.match(/^(?:true|false|True|False)(?![A-Za-z0-9_])/)) return "bool";
  if (stream.match(/^"[^"]*"?/) || stream.match(/^'[^']*'?/)) return "string";
  if (stream.match(/^[^\s#;,"']+/)) return "string";
  stream.next();
  return null;
}

const klipperConfigParser = {
  name: "klipper",
  startState: () => ({ gcode: false, section: 0, afterKey: false, jinja: 0 }),
  copyState: (state) => Object.assign({}, state),
  languageData: { commentTokens: { line: "#" } },
  token(stream, state) {
    if (stream.sol()) {
      state.section = 0;
      state.afterKey = false;
      const first = stream.string.charAt(0);
      // a line that starts at the margin (and is no comment) ends the G-code of the key before
      if (first !== "" && !/\s/.test(first) && first !== "#" && first !== ";") {
        state.gcode = false;
        state.jinja = 0;
      }
    }
    if (stream.eatSpace()) return null;
    const ch = stream.peek();
    if ((ch === "#" || ch === ";") && state.jinja === 0 && (firstOfLine(stream) || /\s/.test(stream.string.charAt(stream.pos - 1)))) {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.column() === 0 && ch === "[") {
      stream.next();
      state.section = 1;
      return "bracket";
    }
    if (state.section) {
      if (stream.eat("]")) {
        state.section = 0;
        return "bracket";
      }
      if (stream.match(/^[^\s\]]+/)) {
        const tag = state.section === 1 ? "typeName" : "labelName";
        state.section = 2;
        return tag;
      }
      stream.next();
      return null;
    }
    if (stream.column() === 0) {
      const key = stream.match(CFG_KEY);
      if (key) {
        state.gcode = CFG_GCODE_KEY.test(key[0]);
        state.afterKey = true;
        return CFG_PIN_KEY.test(key[0]) ? "attributeName" : "propertyName";
      }
    }
    if (state.afterKey && (ch === ":" || ch === "=")) {
      stream.next();
      state.afterKey = false;
      return "operator";
    }
    return state.gcode ? macroToken(stream, state) : valueToken(stream);
  },
};

const gcodeFileParser = {
  name: "gcode",
  languageData: { commentTokens: { line: ";" } },
  token(stream) {
    if (stream.eatSpace()) return null;
    if (stream.peek() === ";") {
      stream.skipToEnd();
      return "comment";
    }
    if (firstOfLine(stream) && stream.match(/^(?:[A-Za-z]\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)/)) return "macroName";
    if (stream.match(/^[A-Za-z_][A-Za-z0-9_]*(?==)/)) return "propertyName";
    if (stream.eat("=")) return "operator";
    if (stream.match(/^[A-Za-z](?=[-+.\d])/)) return "propertyName";
    if (stream.match(/^[-+]?\d*\.?\d+/)) return "number";
    if (stream.match(/^"[^"]*"?/)) return "string";
    stream.next();
    return null;
  },
};

/** The colours (the ones of the editor before 1.41, after VS Code's dark theme). */
const editorHighlightStyle = () =>
  CM.HighlightStyle.define([
    { tag: CM.tags.comment, color: "#6a9955" },
    { tag: CM.tags.bracket, color: "#569cd6" },
    { tag: CM.tags.typeName, color: "#4ec9b0", fontWeight: "600" },
    { tag: CM.tags.labelName, color: "#d7ba7d", fontWeight: "600" },
    { tag: CM.tags.propertyName, color: "#9cdcfe" },
    { tag: CM.tags.attributeName, color: "#dcdcaa" },
    { tag: CM.tags.string, color: "#ce9178" },
    { tag: CM.tags.number, color: "#b5cea8" },
    { tag: CM.tags.bool, color: "#569cd6", fontWeight: "600" },
    { tag: CM.tags.meta, color: "#c586c0" },
    { tag: CM.tags.keyword, color: "#569cd6", fontWeight: "600" },
    { tag: CM.tags.variableName, color: "#9cdcfe" },
    { tag: CM.tags.macroName, color: "#d7ba7d", fontWeight: "600" },
    { tag: CM.tags.operator, color: "#d4d4d4" },
  ]);

/* ---------------------------------------------------------------------------
   Sections: folding, the list, the reference page
   ------------------------------------------------------------------------- */
/** Line number of the last line of the section that starts at line `number` (its last line that is not blank). */
function sectionEndLine(doc, number) {
  let last = number;
  for (let n = number + 1; n <= doc.lines; n++) {
    const text = doc.line(n).text;
    if (CFG_SECTION_LINE.test(text)) break;
    if (text.trim() !== "") last = n;
  }
  return last;
}

/** A [section] folds down to its last line . */
const sectionFolding = () =>
  CM.foldService.of((state, lineStart) => {
    const line = state.doc.lineAt(lineStart);
    if (!CFG_SECTION_LINE.test(line.text)) return null;
    const last = sectionEndLine(state.doc, line.number);
    return last > line.number ? { from: line.to, to: state.doc.line(last).to } : null;
  });

/** The [sections] of a text, in order: { name, line } (line numbers from 1). */
function configSections(text) {
  const sections = [];
  text.split("\n").forEach((line, index) => {
    const match = line.match(CFG_SECTION_LINE);
    if (match && match[1].trim()) sections.push({ name: match[1].trim(), line: index + 1 });
  });
  return sections;
}

/** The section that line `number` is in (the last one that starts at or before it), or null. */
const sectionAtLine = (sections, number) => sections.filter((section) => section.line <= number).pop() || null;

/**
 * The page of the reference that explains `section` of the file `path`: Klipper's Config Reference for a .cfg file (the
 * type of the section: [stepper_x] and [stepper_z1] are [stepper], [extruder1] is [extruder]), Moonraker's configuration
 * page for moonraker.conf. null for other files.
 */
function configDocsUrl(path, section) {
  const file = String(path || "").split("/").pop().toLowerCase();
  let type = section ? section.split(/\s+/)[0].toLowerCase() : "";
  if (/\.conf$/.test(file) && file.includes("moonraker")) return MOONRAKER_CONFIG_DOCS + (type ? "#" + type : "");
  if (!/\.cfg$/.test(file)) return null;
  type = type.replace(/^stepper_[a-z]\d*$/, "stepper").replace(/^extruder\d+$/, "extruder");
  return KLIPPER_CONFIG_DOCS + (type ? "#" + type : "");
}

/** The words of CodeMirror's own panels (search, folding), in the dashboard's language. */
const editorPhrases = () => ({
  Find: tx("Find"),
  Replace: tx("Replace"),
  next: tx("next"),
  previous: tx("previous"),
  all: tx("all"),
  "match case": tx("match case"),
  regexp: tx("regexp"),
  "by word": tx("by word"),
  replace: tx("replace"),
  "replace all": tx("replace all"),
  close: tx("close"),
  "current match": tx("current match"),
  "on line": tx("on line"),
  "replaced match on line $": tx("replaced match on line $"),
  "replaced $ matches": tx("replaced $ matches"),
  "Go to line": tx("Go to line"),
  go: tx("go"),
  "Folded lines": tx("Folded lines"),
  "Unfolded lines": tx("Unfolded lines"),
  to: tx("to"),
  "folded code": tx("folded code"),
  unfold: tx("unfold"),
  "Fold line": tx("Fold line"),
  "Unfold line": tx("Unfold line"),
});

/* ---------------------------------------------------------------------------
   Commenting lines
   ------------------------------------------------------------------------- */
/** The comment mark of a file: Klipper's files take #, G-code takes ; (a # line is no comment there). */
const commentMarkOf = (isGcode) => (isGcode ? ";" : "#");

/**
 * What commenting, uncommenting or toggling the lines touched by the selection [start, end] does to `text`:
 * { mode, from, to, replacement, count } (the lines from..to are replaced as a whole), or null when no line would change.
 *   comment    the mark goes in front of every line that is not blank, all at the indent of the least indented of them,
 *              so a block keeps its shape (a macro body stays indented); a line that already has one gets another;
 *   uncomment  one mark comes off every line that has one in front (after its indent);
 *   toggle     uncomment when every line that is not blank has a mark, comment otherwise.
 * A selection that ends at the very start of a line does not reach that line.
 */
function commentLines(text, start, end, mode, mark) {
  const from = start === 0 ? 0 : text.lastIndexOf("\n", start - 1) + 1;
  const lastOffset = end > start && text[end - 1] === "\n" ? end - 1 : end;
  const lineEnd = text.indexOf("\n", lastOffset);
  const to = lineEnd === -1 ? text.length : lineEnd;
  const lines = text.slice(from, to).split("\n");
  const indentOf = (line) => line.length - line.trimStart().length;
  const isBlank = (line) => line.trim() === "";
  const hasMark = (line) => line.trimStart().startsWith(mark);
  const filled = lines.filter((line) => !isBlank(line));
  const resolved = mode === "toggle" ? (filled.length > 0 && filled.every(hasMark) ? "uncomment" : "comment") : mode;
  let count = 0;
  let result;
  if (resolved === "comment") {
    const indent = Math.min(...filled.map(indentOf));
    result = lines.map((line) => {
      if (isBlank(line)) return line;
      count++;
      return line.slice(0, indent) + mark + line.slice(indent);
    });
  } else {
    result = lines.map((line) => {
      if (!hasMark(line)) return line;
      count++;
      const lead = indentOf(line);
      return line.slice(0, lead) + line.slice(lead + mark.length);
    });
  }
  return count === 0 ? null : { mode: resolved, from, to, replacement: result.join("\n"), count };
}

/* ---------------------------------------------------------------------------
   Saving
   ------------------------------------------------------------------------- */
const SAVE_STATUS = {
  saving: tx("Saving..."),
  saved: tx("Saved ✓"),
};
const restartingStatus = (name) => tx("Restarting {service}...", { service: name });
const restartedStatus = (name) => tx("{service} restarts ✓", { service: name });
const restartByHandStatus = (name) => tx("Saved, restart {service} by hand", { service: name });

/**
 * 1.63: what «Save and restart» restarts: the service the file belongs to (moonraker.conf → Moonraker, crowsnest.conf →
 * crowsnest, KlipperScreen.conf…), Klipper for the other .cfg files; null: nothing to restart (no button).
 */
const CONFIG_FILE_SERVICES = {
  moonraker: "moonraker",
  crowsnest: "crowsnest",
  klipperscreen: "KlipperScreen",
  sonar: "sonar",
  "moonraker-obico": "moonraker-obico",
  telegram: "moonraker-telegram-bot",
  "moonraker-telegram-bot": "moonraker-telegram-bot",
  octoeverywhere: "octoeverywhere",
  mobileraker: "mobileraker",
};
function restartTargetOf(path) {
  const name = String(path || "").split("/").pop().toLowerCase();
  const stem = name.replace(/\.[^.]*$/, "");
  if (CONFIG_FILE_SERVICES[stem]) return { kind: "service", service: CONFIG_FILE_SERVICES[stem], label: CONFIG_FILE_SERVICES[stem] === "moonraker" ? "Moonraker" : CONFIG_FILE_SERVICES[stem] };
  if (name.endsWith(".cfg")) return { kind: "klipper", label: "Klipper" };
  return null;
}

/**
 * Restarts what the file belongs to: a service through Moonraker; Klipper with SAVE_CONFIG when it holds changes to save
 * (they would be lost), otherwise FIRMWARE_RESTART. While a print runs, Klipper restarts only if confirmed.
 */
async function restartForFile(target) {
  if (target.kind === "service") {
    const response = await moonraker.serviceAction("restart", target.service);
    if (!response.ok) throw new Error("HTTP " + response.status);
    return;
  }
  const status = await moonraker.queryObjects("print_stats=state&configfile=save_config_pending", { timeout: 4000 }).catch(() => ({}));
  const state = (status.print_stats || {}).state;
  if ((state === "printing" || state === "paused") && !window.confirm(tx("A print is running: it will fail!") + " " + tx("Restart Klipper anyway?"))) throw new Error("cancelled");
  if ((status.configfile || {}).save_config_pending) return sendSaveConfig();
  const response = await moonraker.firmwareRestart();
  if (!response.ok) throw new Error("HTTP " + response.status);
}

/** Sends SAVE_CONFIG, falling back to the query-string form when the POST fails. */
async function sendSaveConfig() {
  try {
    await sendGcode("SAVE_CONFIG");
  } catch (error) {
    await postAction("/printer/gcode/script?script=SAVE_CONFIG");
  }
}

/* ---------------------------------------------------------------------------
   Component
   ------------------------------------------------------------------------- */
/** The «⋯» menu of the editor (1.101: one button instead of three, so that Comment / Uncomment keep their room on a
 * phone): the earlier versions of the file, the reference page of the section, fold or unfold, the sections. */
function EditorMoreButton({ sections, current, onJump, onFoldAll, onUnfoldAll, onVersions, docsUrl }) {
  const menu = useDropdown();
  // every row with its icon (1.101): fold / unfold, «go to» for a section, ✓ on the section the cursor is in
  const item = (key, title, subtitle, onClick, checked, icon) =>
    h(
      "button",
      { key, type: "button", className: cx("oui-menu__item console-option", typeof key === "number" ? "editor-section-item" : "editor-more-item"), role: "menuitem", "data-section-line": typeof key === "number" ? key : undefined, onClick: () => (menu.close(), onClick()) },
      h("span", { className: "oui-menu__icon" }, h(checked ? Icons.Check : icon, { size: 18 })),
      h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, title), subtitle && h("span", { className: "oui-menu__sub" }, subtitle)),
    );
  return h(
    React.Fragment,
    null,
    h(
      "button",
      { type: "button", ref: menu.anchorRef, className: cx("oui-btn oui-btn--sm editor-history editor-sections-btn", menu.open && "oui-btn--accent-soft"), title: tx("More"), "aria-label": tx("More"), "aria-haspopup": "menu", "aria-expanded": menu.open, onMouseDown: (event) => event.preventDefault(), onClick: menu.toggle },
      h(Icons.Dots, { size: 20 }),
    ),
    h(
      DropdownMenu,
      { menu },
      onVersions && h("button", { type: "button", className: "oui-menu__item console-option editor-more-item", role: "menuitem", "data-editor-versions": "1", onClick: () => (menu.close(), onVersions()) },
        h("span", { className: "oui-menu__icon" }, h(Icons.Clock, { size: 18 })), h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, tx("Earlier versions")))),
      docsUrl && h("a", { className: "oui-menu__item console-option editor-more-item editor-docs", role: "menuitem", href: docsUrl, target: "_blank", rel: "noopener noreferrer", onClick: () => menu.close() },
        h("span", { className: "oui-menu__icon" }, h(Icons.Doc, { size: 18 })), h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, tx("What this section does (the reference)")))),
      sections.length > 0 && h(MenuLabel, null, tx("Fold")),
      sections.length > 0 && item("fold", tx("Fold every section"), null, onFoldAll, false, Icons.Shrink),
      sections.length > 0 && item("unfold", tx("Unfold every section"), null, onUnfoldAll, false, Icons.Expand),
      sections.length > 0 && h(MenuLabel, null, tx("Go to the section")),
      sections.map((section) => item(section.line, "[" + section.name + "]", tx("line {line}", { line: section.line }), () => onJump(section.line), current && current.line === section.line, Icons.Forward)),
    ),
  );
}

/** How the two comment buttons fit in the tools row (1.101): "" icon and word, "words" (the icons step aside first),
 * "icons" (a narrow phone, a long language such as German or Russian: only # and #̸). Measured from the words, so it
 * changes back as soon as they fit. */
function useTightTools(rowRef, labels) {
  const [tight, setTight] = useState("");
  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row || typeof ResizeObserver === "undefined") return undefined;
    const canvas = document.createElement("canvas").getContext("2d");
    const check = () => {
      const buttons = [...row.querySelectorAll(".editor-comment")];
      if (!buttons.length) return;
      const style = getComputedStyle(buttons[0]);
      canvas.font = style.fontWeight + " " + style.fontSize + " " + style.fontFamily;
      const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
      const others = [...row.children].filter((child) => !child.classList.contains("editor-comment")).reduce((sum, child) => sum + child.getBoundingClientRect().width, 0);
      const available = row.clientWidth - others - gap * (row.children.length - 1);
      const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) + 2;
      const words = labels.reduce((sum, label) => sum + Math.ceil(canvas.measureText(label).width) + padding, 0);
      const icons = labels.length * (18 + (parseFloat(style.columnGap) || 6)); // each icon with its gap
      setTight(words + icons <= available ? "" : words <= available ? "words" : "icons");
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(row);
    return () => observer.disconnect();
  }, [rowRef, labels.join("|")]);
  return tight;
}

function EditorScreen({ session, onClose, inline, onDirtyChange }) {
  const { path } = session;
  const root = session.root || CONFIG_ROOT;
  const isGcode = root === GCODES_ROOT;
  const readOnly = Boolean(session.readOnly); // a long G-code file opens as its first lines only: never saved back
  const [text, setText] = useState(session.content);
  const [saved, setSaved] = useState(session.content);
  const [status, setStatus] = useState(session.note || "");
  const [busy, setBusy] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [historyDepth, setHistoryDepth] = useState({ undo: 0, redo: 0 });
  const [caretLine, setCaretLine] = useState(1);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false); // 1.81: the earlier versions of the file
  const hostRef = useRef(null);
  const toolsRef = useRef(null);
  const toolsTight = useTightTools(toolsRef, [tx("Comment"), tx("Uncomment")]);
  const viewRef = useRef(null);
  const statusTimer = useRef(0);
  const textTimer = useRef(0);
  const actions = useRef({}); // the latest save / comment, for CodeMirror's key bindings (set up once)
  const commentMark = commentMarkOf(isGcode);
  const restartTarget = isGcode ? null : restartTargetOf(path);
  const savedStatuses = [SAVE_STATUS.saved].concat(restartTarget ? [restartedStatus(restartTarget.label), restartByHandStatus(restartTarget.label)] : []);
  const sections = useMemo(() => (isGcode ? [] : configSections(text)), [text, isGcode]);
  const docsUrl = isGcode ? null : configDocsUrl(path, (sectionAtLine(sections, caretLine) || {}).name);
  const canOpenLinks = !IN_APP_WEBVIEW || APP_OPENS_LINKS;
  const keepsVersions = !readOnly && !isGcode && !session.onSave && root === CONFIG_ROOT;

  useBodyScrollLock(!inline);

  // CodeMirror is set up once, when the file opens; the page scroll position is restored on close.
  useEffect(() => {
    const pageScroll = window.scrollY;
    const extensions = [
      CM.lineNumbers(),
      CM.highlightActiveLineGutter(),
      CM.highlightSpecialChars(),
      CM.history(),
      CM.drawSelection(),
      CM.dropCursor(),
      CM.EditorState.allowMultipleSelections.of(true),
      CM.indentOnInput(),
      CM.bracketMatching(),
      CM.closeBrackets(),
      CM.rectangularSelection(),
      CM.crosshairCursor(),
      CM.highlightActiveLine(),
      CM.highlightSelectionMatches(),
      CM.search({ top: true }),
      CM.indentUnit.of(EDITOR_INDENT),
      CM.EditorState.tabSize.of(2),
      CM.EditorState.phrases.of(editorPhrases()),
      CM.StreamLanguage.define(isGcode ? gcodeFileParser : klipperConfigParser),
      CM.syntaxHighlighting(editorHighlightStyle()),
      CM.EditorView.theme({}, { dark: true }),
      CM.EditorView.contentAttributes.of({ spellcheck: "false", autocorrect: "off", autocapitalize: "off", "aria-label": path }),
      CM.Prec.highest(
        CM.keymap.of([
          { key: "Mod-s", preventDefault: true, run: () => (actions.current.save(false), true) },
          { key: "Mod-/", preventDefault: true, run: () => (actions.current.comment("toggle"), true) },
        ]),
      ),
      CM.keymap.of([].concat(CM.closeBracketsKeymap, CM.defaultKeymap, CM.searchKeymap, CM.historyKeymap, CM.foldKeymap, readOnly ? [] : [CM.indentWithTab])),
      CM.EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          // 1.58: a long G-code is copied out of the editor once typing pauses, not at every key
          clearTimeout(textTimer.current);
          const state = update.state;
          if (state.doc.length > EDITOR_LONG_DOC_CHARS) textTimer.current = setTimeout(() => setText(state.doc.toString()), EDITOR_LONG_DOC_PAUSE_MS);
          else setText(state.doc.toString());
        }
        if (update.docChanged || update.transactions.length) setHistoryDepth((current) => {
          const undo = CM.undoDepth(update.state);
          const redo = CM.redoDepth(update.state);
          return current.undo === undo && current.redo === redo ? current : { undo, redo };
        });
        if (update.selectionSet || update.docChanged) setCaretLine(update.state.doc.lineAt(update.state.selection.main.head).number);
        setSearchOpen(Boolean(update.view.dom.querySelector(".cm-search")));
      }),
    ];
    if (!isGcode)
      extensions.push(
        sectionFolding(),
        CM.codeFolding(),
        CM.foldGutter({ markerDOM: (open) => Object.assign(document.createElement("span"), { className: "editor-fold-mark" + (open ? " is-open" : ""), textContent: "›" }) }),
      );
    if (readOnly) extensions.push(CM.EditorState.readOnly.of(true));
    const view = new CM.EditorView({ state: CM.EditorState.create({ doc: session.content, extensions }), parent: hostRef.current });
    viewRef.current = view;
    if (!readOnly) view.focus();
    return () => {
      view.destroy();
      viewRef.current = null;
      setTimeout(() => window.scrollTo(0, pageScroll), 10);
    };
  }, []);

  useEffect(() => () => (clearTimeout(statusTimer.current), clearTimeout(textTimer.current)), []);

  const dirty = text !== saved;
  // inline (wide screen): the page around the editor needs to know before it replaces or closes this file
  useEffect(() => {
    if (!onDirtyChange) return undefined;
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty]);

  /* --- search --- */
  const toggleSearch = () => {
    const view = viewRef.current;
    if (!view) return;
    if (searchOpen) CM.closeSearchPanel(view);
    else CM.openSearchPanel(view);
  };

  /* --- sections --- */
  const jumpToLine = (number) => {
    const view = viewRef.current;
    if (!view) return;
    const line = view.state.doc.line(Math.min(number, view.state.doc.lines));
    view.dispatch({ selection: { anchor: line.from }, effects: CM.EditorView.scrollIntoView(line.from, { y: "start", yMargin: 8 }) });
    view.focus();
  };
  const foldEverything = (fold) => {
    const view = viewRef.current;
    if (!view) return;
    (fold ? CM.foldAll : CM.unfoldAll)(view);
    view.focus();
  };

  /* --- commenting --- */
  /** Says something on the status line for a moment (what it said before a save stays as it is). */
  const flashStatus = (message) => {
    clearTimeout(statusTimer.current);
    setStatus(message);
    statusTimer.current = setTimeout(() => setStatus((current) => (current === message ? "" : current)), EDITOR_FLASH_MS);
  };

  /**
   * Comments, uncomments or toggles (`mode`) the selected lines (the caret's line when nothing is selected) and keeps
   * them selected, so that pressing the other button undoes it. It is one step of the history: Annulla takes it back.
   */
  const markComments = (mode) => {
    const view = viewRef.current;
    if (readOnly || !view) return;
    const { from: start, to: end } = view.state.selection.main;
    const result = commentLines(view.state.doc.toString(), start, end, mode, commentMark);
    if (!result) return flashStatus(mode === "comment" ? tx("No line to comment") : tx("No line starts with {mark}", { mark: commentMark }));
    const { from, to, replacement, count } = result;
    view.dispatch({ changes: { from, to, insert: replacement }, selection: { anchor: from, head: from + replacement.length }, userEvent: "input.comment", scrollIntoView: true });
    view.focus();
    flashStatus(result.mode === "comment" ? (count === 1 ? tx("1 line commented") : tx("{count} lines commented", { count })) : count === 1 ? tx("1 line uncommented") : tx("{count} lines uncommented", { count }));
  };
  const runHistory = (command) => {
    const view = viewRef.current;
    if (!view || readOnly) return;
    command(view);
    view.focus();
  };
  /** A button of the tools bar must not take the focus (or the selection) away from the text. */
  const keepFocus = (event) => event.preventDefault();

  /* --- closing / saving --- */
  const requestClose = () => (dirty || (viewRef.current && viewRef.current.state.doc.toString() !== saved) ? setConfirmingDiscard(true) : onClose()); // the text of a long G-code may still wait for its pause

  /**
   * Uploads the file; "Save and restart" also restarts what the file belongs to (1.63, restartTargetOf).
   * Over the whole screen (phone) the editor closes when done, after a moment to read the status; inline (wide
   * screen) the file stays open for the next change and the status stays on view.
   */
  const save = async (alsoSaveConfig) => {
    const linger = (ms) => (inline ? Promise.resolve() : sleep(ms));
    const content = viewRef.current ? viewRef.current.state.doc.toString() : text;
    setBusy(true);
    setStatus(SAVE_STATUS.saving);
    try {
      // 1.81: the text the file had is kept by the service first (the «Versions» of the tools bar)
      if (keepsVersions && content !== saved) await configVersionsApi.keep(path, saved);
      await (session.onSave ? session.onSave(content) : configFilesApi.save(path, content, root));
    } catch (error) {
      setStatus(tx("Error: ") + (error.message || error));
      setBusy(false);
      return;
    }
    setSaved(content);
    setStatus(SAVE_STATUS.saved);
    await linger(EDITOR_SAVE_SETTLE_MS);
    if (alsoSaveConfig && restartTarget) {
      setStatus(restartingStatus(restartTarget.label));
      try {
        await restartForFile(restartTarget);
        setStatus(restartedStatus(restartTarget.label));
        await linger(EDITOR_AFTER_SAVE_CONFIG_MS);
      } catch (error) {
        setStatus(restartByHandStatus(restartTarget.label));
        await linger(EDITOR_SAVE_CONFIG_FAILED_MS);
      }
    }
    if (inline) setBusy(false);
    else onClose();
  };

  /** 1.81: an earlier version goes back into the editor as one change (Undo takes it back); it is written by Save. */
  const restoreVersion = (content) => {
    const view = viewRef.current;
    setVersionsOpen(false);
    if (!view) return;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: content }, userEvent: "input.restore", scrollIntoView: true });
    view.focus();
    flashStatus(tx("Version put back: Save to keep it"));
  };

  const saveDisabled = (!dirty && !session.onSave) || busy || readOnly; // a proposed macro can be saved as it is
  actions.current = { save: (also) => !saveDisabled && save(also), comment: markComments };

  return h(
    "div",
    { className: cx("screen screen--editor", inline && "screen--inline") },
    h(
      "div",
      { className: "screen-bar editor-bar" },
      h("button", { className: "oui-btn oui-btn--icon editor-close", title: tx("Close"), "aria-label": tx("Close"), onClick: requestClose }, "✕"),
      h(
        "div",
        { className: "editor-heading" },
        h("div", { className: "editor-title-row" }, h("span", { className: "editor-title" }, isGcode ? root + "/" + path : path), readOnly && h("span", { className: "oui-badge" }, tx("Read-only")), dirty && h("span", { className: "oui-badge oui-badge--warn" }, tx("Changed"))),
        h("span", { className: "editor-status" }, dirty && savedStatuses.includes(status) ? "" : status), // typing again after a save: "Saved ✓" no longer applies
      ),
      h(
        "div",
        { className: "editor-actions" },
        h("button", { className: cx("oui-btn oui-btn--icon editor-search-btn", searchOpen && "oui-btn--accent-soft"), title: tx("Search (Ctrl+F)"), "aria-label": tx("Search"), "aria-pressed": searchOpen, onMouseDown: keepFocus, onClick: toggleSearch }, h(Icons.Search, { size: 20 })),
        !readOnly && h("button", { className: "oui-btn oui-btn--primary editor-save", disabled: saveDisabled, onClick: () => save(false) }, tx("Save")),
        !readOnly && !isGcode && !session.onSave && restartTarget && h("button", { className: "oui-btn editor-save", "data-restarts": restartTarget.kind === "service" ? restartTarget.service : "klipper", title: tx("Save and restart {service}", { service: restartTarget.label }), disabled: saveDisabled, onClick: () => save(true) }, tx("Save and restart")),
      ),
    ),
    (!readOnly || sections.length > 0) &&
      h(
        "div",
        { className: cx("editor-tools", toolsTight && "editor-tools--" + (toolsTight === "words" ? "words" : "tight")), ref: toolsRef },
        !readOnly && h("button", { type: "button", className: "oui-btn oui-btn--sm editor-history", title: tx("Undo (Ctrl+Z)"), "aria-label": txc("edit", "Undo"), disabled: historyDepth.undo === 0, onMouseDown: keepFocus, onClick: () => runHistory(CM.undo) }, h(Icons.Undo, { size: 20 })),
        !readOnly && h("button", { type: "button", className: "oui-btn oui-btn--sm editor-history", title: tx("Redo (Ctrl+Y)"), "aria-label": txc("edit", "Redo"), disabled: historyDepth.redo === 0, onMouseDown: keepFocus, onClick: () => runHistory(CM.redo) }, h(Icons.Redo, { size: 20 })),
        !readOnly && h("button", { type: "button", className: "oui-btn oui-btn--sm editor-comment", title: tx("Puts {mark} in front of the selected lines (Ctrl+/)", { mark: commentMark }), onMouseDown: keepFocus, "aria-label": tx("Comment"), onClick: () => markComments("comment") }, h(Icons.Hash, { size: 18 }), h("span", { className: "editor-comment__label" }, tx("Comment"))),
        !readOnly && h("button", { type: "button", className: "oui-btn oui-btn--sm editor-comment", title: tx("Removes one {mark} from the selected lines that have it (Ctrl+/)", { mark: commentMark }), onMouseDown: keepFocus, "aria-label": tx("Uncomment"), onClick: () => markComments("uncomment") }, h(Icons.HashOff, { size: 18 }), h("span", { className: "editor-comment__label" }, tx("Uncomment"))),
        (keepsVersions || sections.length > 0 || (docsUrl && canOpenLinks)) &&
          h(EditorMoreButton, {
            sections,
            current: sectionAtLine(sections, caretLine),
            onJump: jumpToLine,
            onFoldAll: () => foldEverything(true),
            onUnfoldAll: () => foldEverything(false),
            onVersions: keepsVersions ? () => setVersionsOpen(true) : null,
            docsUrl: docsUrl && canOpenLinks ? docsUrl : null,
          }),
      ),
    h("div", { className: "editor-body", ref: hostRef }),
    versionsOpen && createPortal(h(ConfigVersionsDialog, { path, current: viewRef.current ? viewRef.current.state.doc.toString() : text, onRestore: restoreVersion, onClose: () => setVersionsOpen(false) }), document.body),
    h(ConfirmDialog, {
      open: confirmingDiscard,
      zIndex: 10002,
      icon: h(Icons.CancelCircle),
      title: tx("Unsaved changes"),
      subtitle: path,
      message: tx("You have unsaved changes. Close without saving?"),
      confirmLabel: tx("Close"),
      onConfirm: onClose,
      onCancel: () => setConfirmingDiscard(false),
    }),
  );
}

/**
 * `session` = { path, content, token } while a file is open, otherwise null. With `session.onSave(text)` (a promise) the text
 * is handed to it instead of being written to `path` (a macro or G-code being prepared, e.g. by Printer functions).
 * `inline` shows it inside the page (the wide Config page) instead of over it; `onDirtyChange(bool)` reports unsaved changes.
 */
function TextEditor({ session, onClose, inline, onDirtyChange }) {
  return session ? h(EditorScreen, { key: session.token, session, onClose, inline, onDirtyChange }) : null;
}
