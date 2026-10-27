/* ============================================================================
   53 · AI MARKDOWN
   The AI answers in markdown: headings, tables, lists, code. This module reads
   that text into blocks and shows it as a report that fits the screen:
     · a summary (how many errors / warnings, which files, the conclusion),
     · one collapsible card per section,
     · tables turned into one card per row (nothing scrolls sideways),
     · code blocks with a "Copy" button.
   Everything is built as React elements: the AI's text is never inserted as HTML.
   ========================================================================== */

/* ---------------------------------------------------------------------------
   Reading the markdown into blocks
   block = { type: "heading", level, text } | { type: "paragraph", text } | { type: "rule" }
         | { type: "list", ordered, items: [{ text, number, children: [{ text }] }] }
         | { type: "table", headers, rows } | { type: "code", lang, code } | { type: "quote", text }
   ------------------------------------------------------------------------- */
const MD_FENCE = /^\s*(`{3,}|~{3,})\s*([\w+#-]*)\s*$/;
const MD_HEADING = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/;
const MD_RULE = /^\s*([-*_])(?:\s*\1){2,}\s*$/;
const MD_LIST_ITEM = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/;
const MD_QUOTE = /^\s*>\s?/;
/** A line that is only a bold title, e.g. "**3) Errori critici**": a heading when there are no # headings. */
const MD_BOLD_TITLE = /^\s*\*\*([^*]+)\*\*\s*:?\s*$/;
const BOLD_TITLE_LEVEL = 7; // below every # heading, so it only organises the text when nothing else does

const isTableSeparator = (line) => !!line && line.includes("|") && line.includes("--") && /^[\s|:-]+$/.test(line);
const isTableStart = (line, next) => line.includes("|") && isTableSeparator(next);

const startsNewBlock = (line, next) =>
  MD_FENCE.test(line) || MD_HEADING.test(line) || MD_RULE.test(line) || MD_LIST_ITEM.test(line) || MD_QUOTE.test(line) || MD_BOLD_TITLE.test(line) || isTableStart(line, next);

/** Cells of a table row; a `|` inside a code span or written `\|` does not split. */
function splitTableRow(line) {
  let text = line.trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|") && !text.endsWith("\\|")) text = text.slice(0, -1);
  const cells = [];
  let current = "";
  let inCode = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === "\\" && text[i + 1] === "|") {
      current += "|";
      i++;
    } else if (char === "|" && !inCode) {
      cells.push(current.trim());
      current = "";
    } else {
      if (char === "`") inCode = !inCode;
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

function parseTable(lines, start) {
  const headers = splitTableRow(lines[start]);
  const rows = [];
  let i = start + 2;
  while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
    const cells = splitTableRow(lines[i]);
    while (cells.length > headers.length && headers.length > 0) cells.splice(headers.length - 1, 2, cells[headers.length - 1] + " | " + cells[headers.length]); // stray `|` in the last column
    while (cells.length < headers.length) cells.push("");
    rows.push(cells);
    i++;
  }
  return { block: { type: "table", headers, rows }, next: i };
}

function parseList(lines, start) {
  const first = lines[start].match(MD_LIST_ITEM);
  const baseIndent = first[1].length;
  const ordered = /\d/.test(first[2]);
  const items = [];
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    const match = line.match(MD_LIST_ITEM);
    if (!line.trim()) {
      const next = lines[i + 1];
      const nextMatch = next !== undefined && next.match(MD_LIST_ITEM);
      if (nextMatch && nextMatch[1].length >= baseIndent) {
        i++; // one blank line between items keeps the list going
        continue;
      }
      break;
    }
    if (match && match[1].length <= baseIndent + 1) {
      items.push({ text: match[3], number: ordered ? parseInt(match[2], 10) : null, children: [] });
    } else if (match && items.length) {
      items[items.length - 1].children.push({ text: match[3] });
    } else if (items.length && /^\s+\S/.test(line) && !MD_FENCE.test(line)) {
      const parent = items[items.length - 1];
      const target = parent.children.length ? parent.children[parent.children.length - 1] : parent;
      target.text += "\n" + line.trim();
    } else break;
    i++;
  }
  return { block: { type: "list", ordered, items }, next: i };
}

function parseMarkdown(text) {
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];
    let match;
    if (!line.trim()) {
      i++;
    } else if ((match = line.match(MD_FENCE))) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(match[1].slice(0, 3))) code.push(lines[i++]);
      i++; // closing fence (a missing one just ends the block at the end of the text)
      blocks.push({ type: "code", lang: match[2].toLowerCase(), code: code.join("\n").replace(/\s+$/, "") });
    } else if ((match = line.match(MD_HEADING))) {
      blocks.push({ type: "heading", level: match[1].length, text: match[2] });
      i++;
    } else if (MD_RULE.test(line)) {
      blocks.push({ type: "rule" });
      i++;
    } else if (isTableStart(line, next)) {
      const parsed = parseTable(lines, i);
      blocks.push(parsed.block);
      i = parsed.next;
    } else if (MD_LIST_ITEM.test(line)) {
      const parsed = parseList(lines, i);
      blocks.push(parsed.block);
      i = parsed.next;
    } else if (MD_QUOTE.test(line)) {
      const quote = [];
      while (i < lines.length && MD_QUOTE.test(lines[i])) quote.push(lines[i++].replace(MD_QUOTE, ""));
      blocks.push({ type: "quote", text: quote.join("\n").trim() });
    } else if ((match = line.match(MD_BOLD_TITLE))) {
      blocks.push({ type: "heading", level: BOLD_TITLE_LEVEL, text: match[1].trim() });
      i++;
    } else {
      const paragraph = [line.trim()];
      i++;
      while (i < lines.length && lines[i].trim() && !startsNewBlock(lines[i], lines[i + 1])) paragraph.push(lines[i++].trim());
      blocks.push({ type: "paragraph", text: paragraph.join("\n") });
    }
  }
  return blocks;
}

/* ---------------------------------------------------------------------------
   Inline text: `code`, **bold**, *italic*, links and <br>
   ------------------------------------------------------------------------- */
const INLINE_MARK = /``([\s\S]+?)``|`([^`\n]+)`|\*\*([\s\S]+?)\*\*|\*(?=[^\s*])([^*\n]*?[^\s*])\*(?!\w)|\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s<>)\]]+)/g;
const LINE_BREAK = /<br\s*\/?>/gi;

/** Text with the marks removed (for labels, matching and the copy button). */
const plainText = (text) =>
  String(text || "")
    .replace(LINE_BREAK, " ")
    .replace(/``([\s\S]+?)``|`([^`\n]+)`/g, (all, a, b) => a || b)
    .replace(/\*\*([\s\S]+?)\*\*/g, "$1")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, "$1")
    .trim();

function renderInline(text, keyPrefix = "i") {
  const source = String(text || "");
  if (LINE_BREAK.test(source)) {
    LINE_BREAK.lastIndex = 0;
    return source.split(LINE_BREAK).flatMap((part, index) => (index === 0 ? [] : [h("br", { key: keyPrefix + "br" + index })]).concat(renderInline(part, keyPrefix + index)));
  }
  LINE_BREAK.lastIndex = 0;
  // A cell written as `...` around text that itself holds backticks is one piece of code.
  if (source.length > 2 && source.startsWith("`") && source.endsWith("`") && source.slice(1, -1).includes("`")) return [h("code", { key: keyPrefix + "c", className: "ai-code" }, source.slice(1, -1))];

  const nodes = [];
  let last = 0;
  let count = 0;
  for (const match of source.matchAll(INLINE_MARK)) {
    if (match.index > last) nodes.push(source.slice(last, match.index));
    const key = keyPrefix + "-" + count++;
    const [, doubleCode, code, bold, italic, linkText, linkUrl, bareUrl] = match;
    if (doubleCode !== undefined || code !== undefined) nodes.push(h("code", { key, className: "ai-code" }, doubleCode !== undefined ? doubleCode.trim() : code));
    else if (bold !== undefined) nodes.push(h("strong", { key, className: "ai-b" }, renderInline(bold, key)));
    else if (italic !== undefined) nodes.push(h("em", { key }, italic));
    else if (linkUrl !== undefined) nodes.push(h("a", { key, className: "ai-link", href: linkUrl, target: "_blank", rel: "noopener noreferrer" }, linkText));
    else nodes.push(h("a", { key, className: "ai-link", href: bareUrl, target: "_blank", rel: "noopener noreferrer" }, bareUrl));
    last = match.index + match[0].length;
  }
  if (last < source.length) nodes.push(source.slice(last));
  return nodes;
}

/* ---------------------------------------------------------------------------
   Severity of a finding ("Gravità" column of a table)
   ------------------------------------------------------------------------- */
const SEVERITY_RULES = [
  { tone: "danger", test: /^(critic\w*|critical|errore|errori|error|fatal\w*|grave|alta|high|bloccante|failed)\b/i },
  { tone: "warn", test: /^(warn\w*|avvis\w*|attenzione|media|medium|moderat\w*)\b/i },
  { tone: "info", test: /^(info\w*|bassa|low|ok|minore|nota)\b/i },
];

/** "danger" | "warn" | "info", or null when the text is not a severity word. */
function severityOf(cell) {
  const word = plainText(cell).replace(/^[^\p{L}]+/u, "");
  if (!word || word.length > 30) return null;
  const rule = SEVERITY_RULES.find((candidate) => candidate.test.test(word));
  return rule ? rule.tone : null;
}

/** Which column is the title, which the severity and which are shown as fields. */
function tableLayout(table) {
  const headers = table.headers.map((header) => plainText(header).toLowerCase());
  let severity = headers.findIndex((header) => /gravit|severity|livello|criticit/.test(header));
  if (severity < 0 && table.rows.length > 0) severity = headers.findIndex((_, column) => column > 0 && table.rows.every((row) => !row[column] || severityOf(row[column]) !== null));
  let title = headers.findIndex((header, column) => column !== severity && /^(file|log|servizio|service|componente|modulo|nome|azione|voce|problema|errore|sezione|comando)\b/.test(header));
  if (title < 0) title = severity === 0 ? 1 : 0;
  const fields = headers.map((_, column) => column).filter((column) => column !== title && column !== severity);
  return { title, severity, fields };
}

/** A cell that is only code (a log line, a command): shown in its own box. */
const isCodeCell = (cell) => /^`[\s\S]*`$/.test(cell.trim()) && cell.trim().length > 2;
const looksLikeFile = (text) => /\.(log|cfg|conf|txt|json|py|yaml|yml|ini)\b/i.test(plainText(text));
const isEmptyCell = (cell) => !cell || /^[-–—]+$/.test(cell.trim());

/* ---------------------------------------------------------------------------
   Copy to clipboard (works on plain http too, where navigator.clipboard is missing)
   ------------------------------------------------------------------------- */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {}
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    return copied;
  } catch (error) {
    return false;
  }
}

const COPIED_LABEL_MS = 1600;
async function copyWithToast(text) {
  const copied = await copyText(text);
  toast.notice(copied ? tx("Copied") : tx("Copy failed"));
  return copied;
}

/* ---------------------------------------------------------------------------
   Showing the blocks
   ------------------------------------------------------------------------- */
const CODE_LANGUAGE_LABELS = { bash: tx("Terminal"), sh: tx("Terminal"), shell: tx("Terminal"), zsh: tx("Terminal"), gcode: tx("Klipper console"), klipper: tx("Klipper console"), ini: tx("Configuration"), cfg: tx("Configuration"), conf: tx("Configuration"), yaml: tx("Configuration"), json: "JSON", python: "Python" };

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (await copyWithToast(code)) {
      setCopied(true);
      setTimeout(() => setCopied(false), COPIED_LABEL_MS);
    }
  };
  return h(
    "div",
    { className: "ai-codeblock" },
    h("div", { className: "ai-codeblock__bar" }, h("span", { className: "ai-codeblock__lang" }, CODE_LANGUAGE_LABELS[lang] || lang || tx("Code")), h("button", { className: "ai-codeblock__copy", onClick: copy }, copied ? tx("Copied ✓") : tx("Copy"))),
    h("pre", { className: "ai-codeblock__code" }, code),
  );
}

/** A one-word cell ("Sì", "No", "Consigliato"): label and value share a line. */
function isShortCell(cell) {
  const text = plainText(cell || "").trim();
  return text.length > 0 && text.length <= 24 && !isCodeCell(cell);
}

function FindingCard({ row, layout, headers, showLabels }) {
  const severity = layout.severity >= 0 ? severityOf(row[layout.severity]) : null;
  const title = row[layout.title];
  const fields = layout.fields.filter((column) => !isEmptyCell(row[column]));
  return h(
    "div",
    { className: cx("ai-finding", severity && "ai-finding--" + severity) },
    h(
      "div",
      { className: "ai-finding__head" },
      h("span", { className: cx("ai-finding__title", looksLikeFile(title) && "ai-finding__title--file") }, looksLikeFile(title) ? plainText(title) : renderInline(title, "t")),
      severity && h("span", { className: "oui-badge ai-sev ai-sev--" + severity }, plainText(row[layout.severity])),
    ),
    fields.map((column) =>
      h(
        "div",
        { key: column, className: cx("ai-field", isShortCell(row[column]) && "ai-field--inline") },
        showLabels && h("div", { className: "ai-field__label" }, plainText(headers[column])),
        isCodeCell(row[column]) ? h("div", { className: "ai-msg" }, plainText(row[column])) : h("div", { className: "ai-field__text" }, renderInline(row[column], "f" + column)),
      ),
    ),
  );
}

/** A table as a column of cards: title (+ severity badge) and one labelled field per other column. */
function FindingList({ table }) {
  const layout = tableLayout(table);
  const showLabels = layout.fields.length > 1;
  return h("div", { className: "ai-findings" }, table.rows.map((row, index) => h(FindingCard, { key: index, row, layout, headers: table.headers, showLabels })));
}

function MdList({ block }) {
  const Tag = block.ordered ? "ol" : "ul";
  return h(
    Tag,
    { className: cx("ai-list", block.ordered && "ai-list--ol") },
    block.items.map((item, index) =>
      h(
        "li",
        { key: index, "data-n": block.ordered ? (item.number != null ? item.number : index + 1) : undefined },
        renderInline(item.text, "l" + index),
        item.children.length > 0 && h("ul", { className: "ai-list" }, item.children.map((child, childIndex) => h("li", { key: childIndex }, renderInline(child.text, "c" + childIndex)))),
      ),
    ),
  );
}

function renderBlock(block, index) {
  switch (block.type) {
    case "heading":
      return h("div", { key: index, className: "ai-sub" }, renderInline(block.text, "h" + index));
    case "paragraph":
      return h("p", { key: index, className: "ai-p" }, renderInline(block.text, "p" + index));
    case "list":
      return h(MdList, { key: index, block });
    case "table":
      return h(FindingList, { key: index, table: block });
    case "code":
      return h(CodeBlock, { key: index, code: block.code, lang: block.lang });
    case "quote":
      return h("blockquote", { key: index, className: "ai-quote" }, renderInline(block.text, "q" + index));
    default:
      return h("hr", { key: index, className: "oui-divider" });
  }
}

/** Markdown with no extra structure (used where the answer is a few lines of prose). */
function MarkdownBody({ text }) {
  const blocks = useMemo(() => parseMarkdown(text), [text]);
  return h("div", { className: "ai-md" }, blocks.map(renderBlock));
}

/* ---------------------------------------------------------------------------
   The report: summary + sections
   ------------------------------------------------------------------------- */
const CONCLUSION_TITLE = /conclusion|sintesi|riassunt|in breve|in short|sommario|riepilogo|verdetto|verdict|bottom line/i;
const CONCLUSION_LINE = /^\W*(conclusion\w*|sintesi|riassunto|in breve|in short|bottom line)\b/i;
const CONCLUSION_MAX_CHARS = 900;
const SUMMARY_FALLBACK_PARAGRAPHS = 2;

const blockChars = (blocks) => JSON.stringify(blocks).length;
/** Red / amber only when the section really lists such findings; blue for fixes and actions. */
function sectionTone(section) {
  const severities = section.blocks.filter((block) => block.type === "table").flatMap((table) => {
    const layout = tableLayout(table);
    return layout.severity >= 0 ? table.rows.map((row) => severityOf(row[layout.severity])) : [];
  });
  if (severities.includes("danger")) return "danger";
  if (severities.includes("warn")) return "warn";
  return /fix|soluzion|rimedi|suggerim|comand|azion|raccomand|priorit|cosa fare|intervent|riavvi/i.test(section.title) ? "accent" : "neutral";
}

/** "1. Errori / warning" → { title: "Errori / warning" } (the position in the report numbers the card). */
function cleanSectionTitle(raw) {
  const text = String(raw).replace(/\*\*/g, "").replace(/:\s*$/, "").trim();
  const numbered = text.match(/^\d{1,2}\s*[.)\]:\-–]\s+(.*)$/);
  return numbered ? numbered[1] : text;
}

function buildReport(text) {
  const blocks = parseMarkdown(text);
  const levels = blocks.filter((block) => block.type === "heading").map((block) => block.level);
  const sectionLevel = levels.length ? Math.min(...levels) : 0;

  let intro = [];
  const sections = [];
  let current = null;
  for (const block of blocks) {
    if (sectionLevel && block.type === "heading" && block.level === sectionLevel) {
      current = { title: cleanSectionTitle(block.text), blocks: [] };
      sections.push(current);
    } else if (current) current.blocks.push(block);
    else intro.push(block);
  }
  if (sections.length === 0) {
    sections.push({ title: "", blocks: intro });
    intro = [];
  }

  // The conclusion goes up into the summary: a section named so, or a "Conclusione ..." paragraph.
  let conclusion = [];
  const conclusionIndex = sections.findIndex((section) => section.title && CONCLUSION_TITLE.test(section.title) && blockChars(section.blocks) < CONCLUSION_MAX_CHARS && !section.blocks.some((block) => block.type === "table"));
  if (conclusionIndex >= 0) conclusion = sections.splice(conclusionIndex, 1)[0].blocks;
  for (const section of sections) {
    const lifted = section.blocks.filter((block) => block.type === "paragraph" && CONCLUSION_LINE.test(plainText(block.text)));
    if (lifted.length) {
      conclusion = conclusion.concat(lifted);
      section.blocks = section.blocks.filter((block) => !lifted.includes(block));
    }
  }
  let leadText = intro;
  if (conclusion.length === 0) {
    conclusion = intro.filter((block) => block.type === "paragraph").slice(0, SUMMARY_FALLBACK_PARAGRAPHS);
    leadText = intro.filter((block) => !conclusion.includes(block));
  }

  const stats = { danger: 0, warn: 0, info: 0, files: [] };
  for (const section of sections) {
    for (const block of section.blocks) {
      if (block.type !== "table") continue;
      const layout = tableLayout(block);
      for (const row of block.rows) {
        const tone = layout.severity >= 0 ? severityOf(row[layout.severity]) : null;
        if (tone) stats[tone]++;
        const file = plainText(row[layout.title]);
        if (looksLikeFile(file) && !stats.files.includes(file)) stats.files.push(file);
      }
    }
  }
  return { leadText, conclusion, sections: sections.filter((section) => section.blocks.length > 0), stats };
}

const plural = (count, one, many) => count + " " + (count === 1 ? one : many);

function ReportSummary({ report }) {
  const { stats, conclusion } = report;
  const chips = [
    stats.danger > 0 && h("span", { key: "d", className: "oui-badge oui-badge--danger" }, h("span", { className: "oui-dot" }), plural(stats.danger, tx("error"), tx("errors"))),
    stats.warn > 0 && h("span", { key: "w", className: "oui-badge oui-badge--warn" }, h("span", { className: "oui-dot" }), plural(stats.warn, "avviso", "avvisi")),
    stats.info > 0 && h("span", { key: "i", className: "oui-badge oui-badge--info" }, h("span", { className: "oui-dot" }), plural(stats.info, "nota", "note")),
  ].filter(Boolean);
  if (chips.length === 0 && conclusion.length === 0) return null;
  return h(
    "div",
    { className: "ai-sum" },
    h("div", { className: "ai-sum__title" }, tx("Summary")),
    chips.length > 0 && h("div", { className: "ai-sum__stats" }, chips),
    conclusion.length > 0 && h("div", { className: "ai-sum__text" }, conclusion.map(renderBlock)),
    stats.files.length > 0 && h("div", { className: "ai-sum__files" }, h("span", { className: "ai-sum__caption" }, tx("Files involved")), stats.files.slice(0, 8).map((file) => h("span", { key: file, className: "ai-chip-file" }, file))),
  );
}

function ReportSection({ section, number }) {
  if (!section.title) return h("div", { className: "ai-sec__body ai-sec__body--plain" }, section.blocks.map(renderBlock));
  const findings = section.blocks.filter((block) => block.type === "table").reduce((total, block) => total + block.rows.length, 0);
  return h(
    "details",
    { className: "ai-sec ai-sec--" + sectionTone(section), open: true },
    h(
      "summary",
      { className: "ai-sec__head" },
      h("span", { className: "ai-sec__num" }, number),
      h("span", { className: "ai-sec__title" }, renderInline(section.title, "s")),
      findings > 0 && h("span", { className: "oui-badge" }, plural(findings, "voce", "voci")),
      h("span", { className: "ai-sec__chev" }, h(Icons.Chevron, { size: 18 })),
    ),
    h("div", { className: "ai-sec__body" }, section.blocks.map(renderBlock)),
  );
}

/** The whole answer. A button switches to the AI's original text. */
function AiReport({ text }) {
  const [showRaw, setShowRaw] = useState(false);
  const [folded, setFolded] = useState(false);
  const rootRef = useRef(null);
  const report = useMemo(() => buildReport(text), [text]);
  const foldable = report.sections.filter((section) => section.title).length > 1;
  let number = 0;

  // The sections are plain <details>: fold or unfold them all at once.
  const toggleAll = () => {
    if (rootRef.current) rootRef.current.querySelectorAll("details.ai-sec").forEach((node) => (node.open = folded));
    setFolded(!folded);
  };
  return h(
    "div",
    { className: "ai-report", ref: rootRef },
    showRaw
      ? h("pre", { className: "ai-raw" }, text)
      : h(
          React.Fragment,
          null,
          h(ReportSummary, { report }),
          report.leadText.length > 0 && h("div", { className: "ai-lead" }, report.leadText.map(renderBlock)),
          report.sections.map((section, index) => h(ReportSection, { key: index, section, number: section.title ? ++number : 0 })),
        ),
    h(
      "div",
      { className: "ai-report__tools" },
      foldable && !showRaw && h("button", { className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: toggleAll }, folded ? tx("Expand all") : tx("Collapse all")),
      h("button", { className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: () => setShowRaw(!showRaw) }, showRaw ? tx("Tidy view") : tx("Original text")),
      h("button", { className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: () => copyWithToast(text) }, tx("Copy all")),
    ),
  );
}
