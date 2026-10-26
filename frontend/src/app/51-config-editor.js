/* ============================================================================
   51 · TEXT EDITOR
   Full-screen editor for Klipper/Moonraker config files and G-code files (also
   used to read the system logs). A colour-coded copy of the text sits under a transparent
   <textarea>, so the caret and selection stay native; line numbers and the
   highlight layer follow the textarea's scroll. The tools bar has Annulla / Ripristina (the history is in 50c-text-history.js)
   and the comment bar, which puts a # in front of the selected lines or takes one off.
   ========================================================================== */

const EDITOR_LINE_HEIGHT = 21; // px — line numbers, highlight layer and textarea must agree
const EDITOR_INDENT = "  ";
const EDITOR_SAVE_SETTLE_MS = 300;
const EDITOR_AFTER_SAVE_CONFIG_MS = 1000;
const EDITOR_SAVE_CONFIG_FAILED_MS = 1500;
/** After a scroll the layers are checked every frame until the textarea has not moved for this many frames. */
const EDITOR_SCROLL_SETTLE_FRAMES = 12;
/** What the status line says about a comment / uncomment stays this long. */
const EDITOR_FLASH_MS = 2600;

/* ---------------------------------------------------------------------------
   Syntax highlighting (returns HTML; every piece of user text is escaped first)
   ------------------------------------------------------------------------- */
const tokenSpan = (cls, html) => '<span class="' + cls + '">' + html + "</span>";
const tokenBold = (cls, html) => tokenSpan(cls, "<b>" + html + "</b>");

const GCODE_SECTION_START = /^\s*gcode:\s*$/;
const SECTION_LINE = /^\s*\[.*\]\s*$/;
const SECTION_PARTS = /^(\s*)(\[.*?\])(.*)$/;
const KEY_VALUE = /^(\s*)([a-zA-Z0-9_-]+)(\s*:\s*)(.*)$/;
const PIN_KEY = /^(pin|heater_pin|sensor_pin|step_pin|dir_pin|enable_pin|endstop_pin|switch_pin|variable_.*)$/;
const LOOKS_LIKE_MACRO = /\b(SET_|M300|M118|G92|G1|G0|PARK|PAUSE|FORCE_MOVE|TEMPERATURE_WAIT|SET_GCODE_VARIABLE)\b/i;
const JINJA_KEYWORD = /^(set|if|elif|else|endif|for|endfor|in|is|not|and|or)$/;
const JINJA_VARIABLE = /^(printer|params|sensor)$/;
const GCODE_WORD =
  /^(M300|M400|M118|M117|M104|M106|M107|M140|M190|M109|M84|M82|G92|G4|G28|G1|G0|G90|G91|PARK|_CG28|TURN_OFF_HEATERS|Luci_OFF|SAVE_GCODE_STATE|RESTORE_GCODE_STATE|SET_IDLE_TIMEOUT|BASE_PAUSE|SET_LED|FORCE_MOVE|TEMPERATURE_WAIT|WIPE|PAUSE|SET_GCODE_VARIABLE|UPDATE_DELAYED_GCODE|SET_HEATER_TEMPERATURE|stop_led_effects|set_led_effect|runout_init|filament_change_state1)$/i;
const BOOLEAN_WORD = /^(True|False|true|false)$/;

function highlightSection(match) {
  const [, indent, bracketed, rest] = match;
  const parts = bracketed.slice(1, -1).trim().split(/\s+/);
  const name = parts.slice(1).join(" ");
  let html = tokenSpan("hl-bracket", "[") + tokenBold("hl-type", parts[0] || "");
  if (name) html += " " + tokenBold("hl-name", name);
  html += tokenSpan("hl-bracket", "]");
  if (rest.trim().startsWith("#")) html += tokenSpan("hl-comment", rest);
  else if (rest) html += tokenSpan("hl-value", rest);
  return indent + html;
}

/** `key: value  # comment` */
function highlightKeyValue(match) {
  const [, indent, key, separator, value] = match;
  const hash = value.indexOf("#");
  const valuePart = hash !== -1 ? value.slice(0, hash) : value;
  const commentPart = hash !== -1 ? value.slice(hash) : "";
  const core = valuePart.trim();
  let html = "";
  if (core === "") html = valuePart;
  else if (/^[0-9.-]+$/.test(core)) html = tokenSpan("hl-number", valuePart);
  else if (BOOLEAN_WORD.test(core)) html = tokenBold("hl-bool", valuePart);
  else {
    const inner = valuePart
      .replace(/"([^"]*)"/g, tokenSpan("hl-string", '"$1"'))
      .replace(/'([^']*)'/g, tokenSpan("hl-string", "'$1'"))
      .replace(/\b(\d+\.\d+|\d+)\b/g, tokenSpan("hl-number", "$1"))
      .replace(/\b(True|False|true|false)\b/g, tokenBold("hl-bool", "$1"));
    html = tokenSpan("hl-value", inner);
  }
  if (commentPart) html += tokenSpan("hl-comment", commentPart);
  return indent + tokenSpan(PIN_KEY.test(key) ? "hl-key-pin" : "hl-key", key) + tokenSpan("hl-value", separator) + html;
}

/** G-code / Jinja2 line inside a `gcode:` block. */
function highlightMacroLine(line) {
  let html = "";
  let i = 0;
  while (i < line.length) {
    const rest = line.slice(i);
    const delimiter = rest.slice(0, 2);
    if (delimiter === "{%" || delimiter === "%}" || delimiter === "{{" || delimiter === "}}") {
      html += tokenSpan("hl-jinja", delimiter);
      i += 2;
      continue;
    }
    const entity = rest.match(/^&(?:lt|gt|amp);/); // already-escaped character: copy as is
    if (entity) {
      html += entity[0];
      i += entity[0].length;
      continue;
    }
    if (rest[0] === '"' || rest[0] === "'") {
      const end = rest.indexOf(rest[0], 1);
      if (end !== -1) {
        html += tokenSpan("hl-string", rest.slice(0, end + 1));
        i += end + 1;
        continue;
      }
    }
    if (rest[0] === "#") {
      html += tokenSpan("hl-comment", rest);
      break;
    }
    const wordMatch = rest.match(/^([A-Za-z_][A-Za-z0-9_.]*)/);
    if (wordMatch) {
      const word = wordMatch[1];
      const lower = word.toLowerCase();
      let consumed = word.length;
      if (JINJA_KEYWORD.test(lower)) html += tokenBold("hl-jinja-kw", word);
      else if (JINJA_VARIABLE.test(lower)) html += tokenSpan("hl-jinja-var", word);
      else if (GCODE_WORD.test(word)) html += tokenBold("hl-gcode", word);
      else if (BOOLEAN_WORD.test(word)) html += tokenBold("hl-bool", word);
      else if (rest[word.length] === "=") {
        html += tokenSpan("hl-gcode-param", word) + tokenSpan("hl-value", "=");
        consumed++;
      } else if (word.includes("_") || /^[a-z_][a-z0-9_]+$/i.test(word)) html += tokenSpan("hl-jinja-var", word);
      else html += word;
      i += consumed;
      continue;
    }
    if (rest[0] === "|") {
      html += tokenSpan("hl-value", "|");
      i++;
      continue;
    }
    const number = rest.match(/^(\d+\.\d+|\d+)/);
    if (number) {
      html += tokenSpan("hl-number", number[1]);
      i += number[1].length;
      continue;
    }
    html += rest[0] === "{" || rest[0] === "}" ? tokenSpan("hl-jinja", rest[0]) : rest[0];
    i++;
  }
  return html;
}

/** Wraps every occurrence of `term` in the text parts (not the tags) of `html`. */
function highlightSearchTerm(html, term) {
  const pattern = new RegExp("(" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "gi");
  return html
    .split(/(<[^>]+>)/g)
    .map((part) => (part.startsWith("<") ? part : part.replace(pattern, tokenSpan("hl-search", "$1"))))
    .join("");
}

/** Whole file → highlighted HTML. `searchTerm` is marked when it has matches. */
function highlightConfig(text, searchTerm) {
  if (!text) return "";
  let inGcodeBlock = false;
  return escapeHtml(text)
    .split("\n")
    .map((line) => {
      if (GCODE_SECTION_START.test(line)) {
        inGcodeBlock = true;
        return tokenSpan("hl-key", "<b>" + line + "</b>");
      }
      if (SECTION_LINE.test(line)) inGcodeBlock = false;

      let html;
      const trimmed = line.trim();
      const section = line.match(SECTION_PARTS);
      if (trimmed.startsWith("#") || trimmed.startsWith(";")) html = tokenSpan("hl-comment", line);
      else if (section) html = highlightSection(section);
      else if (inGcodeBlock || line.includes("{%") || line.includes("{{") || LOOKS_LIKE_MACRO.test(line)) html = highlightMacroLine(line);
      else {
        const keyValue = line.match(KEY_VALUE);
        html = keyValue ? highlightKeyValue(keyValue) : line;
      }
      return searchTerm && line.toLowerCase().includes(searchTerm.toLowerCase()) ? highlightSearchTerm(html, searchTerm) : html;
    })
    .join("\n");
}

/** A G-code line: `G1 X10 Y20 E0.5 F1800`, `M104 S215`, `SET_PRESSURE_ADVANCE ADVANCE=0.04`. */
const GCODE_COMMAND = /^(\s*)([A-Za-z]\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)(.*)$/;
const GCODE_PARAM = /(\s)(?:([A-Za-z_][A-Za-z0-9_]*)=([^\s]*)|([A-Za-z])(-?\d*\.?\d+))(?=\s|$)/g;

/** Parameters of an already escaped command: `X10.5` and `KEY=value`. */
function highlightGcodeParams(rest) {
  return rest.replace(GCODE_PARAM, (all, space, key, value, letter, number) => {
    if (key) return space + tokenSpan("hl-gcode-param", key) + tokenSpan("hl-value", "=") + tokenSpan(/^-?[\d.]+$/.test(value) ? "hl-number" : "hl-string", value);
    return space + tokenSpan("hl-gcode-param", letter) + tokenSpan("hl-number", number);
  });
}

/** Whole G-code file → highlighted HTML: commands, parameters and `; comments`. */
function highlightGcodeFile(text, searchTerm) {
  if (!text) return "";
  const term = searchTerm ? searchTerm.toLowerCase() : "";
  return text
    .split("\n")
    .map((line) => {
      const semicolon = line.indexOf(";");
      const code = semicolon === -1 ? line : line.slice(0, semicolon);
      const comment = semicolon === -1 ? "" : line.slice(semicolon);
      const command = code.match(GCODE_COMMAND);
      let html = command ? escapeHtml(command[1]) + tokenBold("hl-gcode", escapeHtml(command[2])) + highlightGcodeParams(escapeHtml(command[3])) : escapeHtml(code);
      if (comment) html += tokenSpan("hl-comment", escapeHtml(comment));
      return term && line.toLowerCase().includes(term) ? highlightSearchTerm(html, searchTerm) : html;
    })
    .join("\n");
}

/** Start offsets of every case-insensitive occurrence of `term` in `text`. */
function findMatches(text, term) {
  const found = [];
  if (!term) return found;
  const haystack = text.toLowerCase();
  const needle = term.toLowerCase();
  for (let index = haystack.indexOf(needle); index !== -1; index = haystack.indexOf(needle, index + needle.length)) found.push(index);
  return found;
}

const lineOfOffset = (text, offset) => text.slice(0, offset).split("\n").length;

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
  saving: "Salvataggio...",
  saved: "Salvato ✓",
  sendingSaveConfig: "Invio SAVE_CONFIG...",
  saveConfigSent: "SAVE_CONFIG inviato ✓",
  manualSaveConfig: "Salvato, invia manualmente SAVE_CONFIG",
};

const SAVED_STATUSES = [SAVE_STATUS.saved, SAVE_STATUS.saveConfigSent, SAVE_STATUS.manualSaveConfig];

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
function LineNumbers({ lineCount, matchLines, currentMatchLine, scrollRef }) {
  const numbers = [];
  for (let line = 1; line <= lineCount; line++) {
    const cls = cx("ke-line-num", line === currentMatchLine ? "search-current" : matchLines.has(line) && "search-match");
    numbers.push(h("span", { key: line, className: cls }, line), "\n");
  }
  return h("div", { className: "editor-lines", ref: scrollRef }, numbers);
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
  const [searchTerm, setSearchTerm] = useState("");
  const [matchIndex, setMatchIndex] = useState(-1);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const textareaRef = useRef(null);
  const layerRef = useRef(null);
  const linesRef = useRef(null);
  const searchInputRef = useRef(null);
  const statusTimer = useRef(0);
  const scrollFollow = useRef(0);
  const commentMark = commentMarkOf(isGcode);

  useBodyScrollLock(!inline);

  // Opens with the caret at the top; the page scroll position is restored on close.
  useEffect(() => {
    const pageScroll = window.scrollY;
    if (!readOnly) textareaRef.current.focus();
    return () => {
      setTimeout(() => window.scrollTo(0, pageScroll), 10);
    };
  }, []);

  useEffect(() => () => clearTimeout(statusTimer.current), []);

  // The search box takes the focus as soon as it appears (before the next key press).
  useEffect(() => {
    if (searchOpen) searchInputRef.current.focus();
  }, [searchOpen]);

  const dirty = text !== saved;
  // inline (wide screen): the page around the editor needs to know before it replaces or closes this file
  useEffect(() => {
    if (!onDirtyChange) return undefined;
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty]);
  const matches = useMemo(() => findMatches(text, searchTerm), [text, searchTerm]);
  const html = useMemo(() => (isGcode ? highlightGcodeFile : highlightConfig)(text, matches.length > 0 ? searchTerm : ""), [text, searchTerm, matches.length]);

  /** The colour layer and the line numbers are scrolled to where the textarea is (the textarea is the one the user scrolls). */
  const syncScroll = () => {
    const textarea = textareaRef.current;
    const layer = layerRef.current;
    const lines = linesRef.current;
    if (!textarea || !layer || !lines) return;
    const { scrollTop, scrollLeft } = textarea;
    if (layer.scrollTop !== scrollTop) layer.scrollTop = scrollTop;
    if (layer.scrollLeft !== scrollLeft) layer.scrollLeft = scrollLeft;
    if (lines.scrollTop !== scrollTop) lines.scrollTop = scrollTop;
  };
  useEffect(syncScroll, [text]);

  /**
   * A scroll event can come late or not at all (a selection handle dragged to the edge of the box, the keyboard opening or
   * closing and the box changing height under the text). So the layers are checked again every frame after anything that
   * may move the text, until the textarea has stood still for a moment, and all the time while the textarea has the focus
   * (when the user is editing or selecting): they cannot stay behind it for more than a frame.
   */
  const followScroll = () => {
    cancelAnimationFrame(scrollFollow.current);
    let last = "";
    let still = 0;
    const step = () => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      syncScroll();
      const now = textarea.scrollTop + "/" + textarea.scrollLeft;
      still = now === last ? still + 1 : 0;
      last = now;
      if (still < EDITOR_SCROLL_SETTLE_FRAMES || document.activeElement === textarea) scrollFollow.current = requestAnimationFrame(step);
    };
    step();
  };
  useEffect(() => {
    // the visible part of the screen changes when the keyboard opens or closes
    const viewport = window.visualViewport;
    if (viewport) viewport.addEventListener("resize", followScroll);
    return () => {
      if (viewport) viewport.removeEventListener("resize", followScroll);
      cancelAnimationFrame(scrollFollow.current);
    };
  }, []);

  const scrollToMatch = (offset) => {
    const textarea = textareaRef.current;
    textarea.scrollTop = Math.max(0, (lineOfOffset(text, offset) - 1) * EDITOR_LINE_HEIGHT - textarea.clientHeight / 2);
    syncScroll();
  };

  /** Brings the line of `offset` into view when it is out of it (after an undo, which may be far from where the user is). */
  const revealOffset = (offset) => {
    const textarea = textareaRef.current;
    const top = (lineOfOffset(text, offset) - 1) * EDITOR_LINE_HEIGHT;
    const margin = EDITOR_LINE_HEIGHT * 2;
    if (top - margin < textarea.scrollTop) textarea.scrollTop = Math.max(0, top - margin);
    else if (top + EDITOR_LINE_HEIGHT + margin > textarea.scrollTop + textarea.clientHeight) textarea.scrollTop = top + EDITOR_LINE_HEIGHT + margin - textarea.clientHeight;
    syncScroll();
  };
  const history = useTextHistory(text, setText, textareaRef, revealOffset);

  /* --- search --- */
  const runSearch = (term) => {
    setSearchTerm(term);
    const found = findMatches(text, term);
    setMatchIndex(found.length > 0 ? 0 : -1);
    if (found.length > 0) scrollToMatch(found[0]);
    searchInputRef.current.focus();
  };
  const jumpTo = (index) => {
    if (index < 0 || index >= matches.length) return;
    setMatchIndex(index);
    scrollToMatch(matches[index]);
    if (searchOpen && document.activeElement !== searchInputRef.current) searchInputRef.current.focus();
  };
  const nextMatch = () => matches.length > 0 && jumpTo((matchIndex + 1) % matches.length);
  const previousMatch = () => matches.length > 0 && jumpTo((matchIndex - 1 + matches.length) % matches.length);
  const clearSearch = () => {
    setSearchTerm("");
    setMatchIndex(-1);
    setSearchOpen(false);
  };
  const openSearch = () => setSearchOpen(true);
  const searchCount = !searchTerm ? "" : matches.length === 0 ? "0/0" : Math.max(0, matchIndex) + 1 + "/" + matches.length;

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
    const textarea = textareaRef.current;
    if (readOnly || !textarea) return;
    const result = commentLines(textarea.value, textarea.selectionStart, textarea.selectionEnd, mode, commentMark);
    if (!result) return flashStatus(mode === "comment" ? "Nessuna riga da commentare" : "Nessuna riga con " + commentMark + " davanti");
    const { from, to, replacement, count } = result;
    textarea.focus({ preventScroll: true });
    history.replace(from, to, replacement, [from, to], [from, from + replacement.length]);
    flashStatus(count + (count === 1 ? " riga " : " righe ") + (result.mode === "comment" ? "commentat" : "decommentat") + (count === 1 ? "a" : "e"));
  };
  /** A button of the tools bar must not take the focus (or the selection) away from the text. */
  const keepFocus = (event) => event.preventDefault();

  /* --- closing / saving --- */
  const requestClose = () => (dirty ? setConfirmingDiscard(true) : onClose());

  /**
   * Uploads the file; "Salva e riavvia" also sends SAVE_CONFIG to Klipper.
   * Over the whole screen (phone) the editor closes when done, after a moment to read the status; inline (wide
   * screen) the file stays open for the next change and the status stays on view.
   */
  const save = async (alsoSaveConfig) => {
    const linger = (ms) => (inline ? Promise.resolve() : sleep(ms));
    setBusy(true);
    setStatus(SAVE_STATUS.saving);
    try {
      await configFilesApi.save(path, text, root);
    } catch (error) {
      setStatus("Errore: " + (error.message || error));
      setBusy(false);
      return;
    }
    setSaved(text);
    setStatus(SAVE_STATUS.saved);
    await linger(EDITOR_SAVE_SETTLE_MS);
    if (alsoSaveConfig) {
      setStatus(SAVE_STATUS.sendingSaveConfig);
      try {
        await sendSaveConfig();
        setStatus(SAVE_STATUS.saveConfigSent);
        await linger(EDITOR_AFTER_SAVE_CONFIG_MS);
      } catch (error) {
        setStatus(SAVE_STATUS.manualSaveConfig);
        await linger(EDITOR_SAVE_CONFIG_FAILED_MS);
      }
    }
    if (inline) setBusy(false);
    else onClose();
  };

  /* --- keyboard inside the textarea --- */
  const onTextareaKeyDown = (event) => {
    const textarea = event.currentTarget;
    const modifier = event.ctrlKey || event.metaKey;
    if (readOnly && event.key === "Tab") return;
    if (event.key === "Tab") {
      event.preventDefault();
      const { selectionStart: start, selectionEnd: end } = textarea;
      const caret = start + EDITOR_INDENT.length;
      history.replace(start, end, EDITOR_INDENT, [start, end], [caret, caret]);
    } else if (modifier && event.key === "s") {
      event.preventDefault();
      if (!readOnly) save(false);
    } else if (modifier && event.key === "f") {
      event.preventDefault();
      openSearch();
    } else if (modifier && event.key === "/") {
      event.preventDefault();
      if (!readOnly) markComments("toggle");
    } else if (modifier && !event.altKey && /^[zy]$/i.test(event.key)) {
      // Ctrl+Z takes back, Ctrl+Y and Ctrl+Shift+Z do again (Cmd in place of Ctrl on a Mac)
      event.preventDefault();
      if (!readOnly) (event.key.toLowerCase() === "y" || event.shiftKey ? history.redo : history.undo)();
    } else if (event.key === "Escape" && searchOpen) clearSearch();
  };

  const matchLines = new Set(matches.map((offset) => lineOfOffset(text, offset)));
  const currentMatchLine = matches[matchIndex] !== undefined ? lineOfOffset(text, matches[matchIndex]) : -1;
  const saveDisabled = !dirty || busy || readOnly;

  return h(
    "div",
    { className: cx("screen screen--editor", inline && "screen--inline") },
    h(
      "div",
      { className: "screen-bar editor-bar" },
      h("button", { className: "oui-btn oui-btn--icon editor-close", title: "Chiudi", "aria-label": "Chiudi", onClick: requestClose }, "✕"),
      h(
        "div",
        { className: "editor-heading" },
        h("div", { className: "editor-title-row" }, h("span", { className: "editor-title" }, isGcode ? root + "/" + path : path), readOnly && h("span", { className: "oui-badge" }, "Solo lettura"), dirty && h("span", { className: "oui-badge oui-badge--warn" }, "Modificato")),
        h("span", { className: "editor-status" }, dirty && SAVED_STATUSES.includes(status) ? "" : status), // typing again after a save: "Salvato ✓" no longer applies
      ),
      h(
        "div",
        { className: "editor-actions" },
        h("button", { className: cx("oui-btn oui-btn--icon", searchOpen && "oui-btn--accent-soft"), title: "Cerca", "aria-label": "Cerca", onClick: () => (searchOpen ? setSearchOpen(false) : openSearch()) }, h(Icons.Search, { size: 20 })),
        !readOnly && h("button", { className: "oui-btn oui-btn--primary editor-save", disabled: saveDisabled, onClick: () => save(false) }, "Salva"),
        !readOnly && !isGcode && h("button", { className: "oui-btn editor-save", disabled: saveDisabled, onClick: () => save(true) }, "Salva e riavvia"),
      ),
    ),
    searchOpen &&
      h(
        "div",
        { className: "editor-search" },
        h("input", {
          ref: searchInputRef,
          type: "text",
          value: searchTerm,
          placeholder: "Cerca nel file...",
          onChange: (e) => runSearch(e.target.value),
          onKeyDown: (e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              e.shiftKey ? previousMatch() : nextMatch();
            } else if (e.key === "Escape") clearSearch();
          },
        }),
        h("span", { className: "editor-search-count" }, searchCount),
        h("button", { className: "editor-icon-btn", title: "Precedente", onClick: previousMatch }, "▲"),
        h("button", { className: "editor-icon-btn", title: "Successivo", onClick: nextMatch }, "▼"),
        h("button", { className: "editor-icon-btn", title: "Chiudi ricerca", onClick: clearSearch }, "✕"),
      ),
    !readOnly &&
      h(
        "div",
        { className: "editor-tools" },
        h("button", { type: "button", className: "oui-btn oui-btn--sm editor-history", title: "Annulla (Ctrl+Z)", "aria-label": "Annulla", disabled: !history.canUndo, onMouseDown: keepFocus, onClick: history.undo }, h(Icons.Undo, { size: 20 })),
        h("button", { type: "button", className: "oui-btn oui-btn--sm editor-history", title: "Ripristina (Ctrl+Y)", "aria-label": "Ripristina", disabled: !history.canRedo, onMouseDown: keepFocus, onClick: history.redo }, h(Icons.Redo, { size: 20 })),
        h("button", { type: "button", className: "oui-btn oui-btn--sm", title: "Aggiunge " + commentMark + " davanti alle righe selezionate (Ctrl+/)", onMouseDown: keepFocus, onClick: () => markComments("comment") }, h(Icons.Hash, { size: 18 }), "Commenta"),
        h("button", { type: "button", className: "oui-btn oui-btn--sm", title: "Toglie un " + commentMark + " dalle righe selezionate che ce l'hanno (Ctrl+/)", onMouseDown: keepFocus, onClick: () => markComments("uncomment") }, h(Icons.HashOff, { size: 18 }), "Decommenta"),
      ),
    h(
      "div",
      { className: "editor-body" },
      h(LineNumbers, { lineCount: text.split("\n").length, matchLines, currentMatchLine, scrollRef: linesRef }),
      h(
        "div",
        { className: "editor-area" },
        h("div", { className: "editor-layer", ref: layerRef, dangerouslySetInnerHTML: { __html: html } }),
        h("textarea", {
          ref: textareaRef,
          className: "editor-input",
          value: text,
          readOnly,
          spellCheck: false,
          autoComplete: "off",
          autoCorrect: "off",
          autoCapitalize: "off",
          onChange: history.input,
          onScroll: followScroll,
          onSelect: followScroll,
          onTouchEnd: followScroll,
          onFocus: followScroll,
          onBlur: followScroll,
          onKeyDown: onTextareaKeyDown,
        }),
      ),
    ),
    h(ConfirmDialog, {
      open: confirmingDiscard,
      zIndex: 10002,
      icon: h(Icons.CancelCircle),
      title: "Modifiche non salvate",
      subtitle: path,
      message: "Hai modifiche non salvate. Chiudere senza salvare?",
      confirmLabel: "Chiudi",
      onConfirm: onClose,
      onCancel: () => setConfirmingDiscard(false),
    }),
  );
}

/**
 * `session` = { path, content, token } while a file is open, otherwise null.
 * `inline` shows it inside the page (the wide Config page) instead of over it; `onDirtyChange(bool)` reports unsaved changes.
 */
function TextEditor({ session, onClose, inline, onDirtyChange }) {
  return session ? h(EditorScreen, { key: session.token, session, onClose, inline, onDirtyChange }) : null;
}
