/* ============================================================================
   53 · AI RESULT VIEWS
   Turns what the AI answers into cards:
     · <LogAnalysis>   – markdown about the system logs, shown as a report,
     · <PrintAnalysis> – the JSON verdict on a running print (spaghetti, empty
                         bed, layer shift, warping and the suggested action).
   ========================================================================== */

/** The AI's answer about the system logs, as a report (see 53-ai-markdown.js). */
function LogAnalysis({ text }) {
  if (!text) return h("div", { className: "oui-caption" }, "Nessun contenuto");
  return h(AiReport, { key: text, text });
}

/* ---------------------------------------------------------------------------
   Print analysis (spaghetti / empty bed / layer shift / warping)
   ------------------------------------------------------------------------- */
const ACTION_TONES = { CANCELLA: "danger", PAUSA: "warn", CONTINUA: "ok" };
const actionTone = (action) => (action.includes("CANCELLA") ? ACTION_TONES.CANCELLA : action.includes("PAUSA") ? ACTION_TONES.PAUSA : ACTION_TONES.CONTINUA);

/** Verdict JSON inside the AI text, or null when the answer is plain prose. */
function parsePrintVerdict(text) {
  try {
    const embedded = text.match(/\{[\s\S]*"spaghetti"[\s\S]*\}/);
    return JSON.parse(embedded ? embedded[0] : text);
  } catch (e) {
    return null;
  }
}

const StatusDot = ({ alert }) => h("span", { className: cx("oui-dot", alert ? "ai-dot--alert" : "ai-dot--ok") });

/** Confidence of a detection: red from 70 %, amber from 50 %, green below. */
function ConfidenceBadge({ value }) {
  const percent = value || 0;
  const tone = percent >= 70 ? "oui-badge--danger" : percent >= 50 ? "oui-badge--warn" : "oui-badge--ok";
  return h("span", { className: cx("oui-badge", tone) }, percent + "%");
}

function CheckTile({ title, detected, label, badge, note }) {
  return h(
    "div",
    { className: cx("check-tile", detected && "check-tile--alert") },
    h("div", { className: "check-tile__title" }, title),
    h("div", { className: "check-tile__status" }, h(StatusDot, { alert: detected }), h("span", null, label || (detected ? "Rilevato" : "OK")), badge),
    note && h("div", { className: "oui-caption mt-2" }, note),
  );
}

const WARMUP_PROGRESS_PERCENT = 2; // below this the print is still heating / meshing

/**
 * `detector` carries what the live monitor knows about the print
 * ({ realStarted, realReason }); `progress` comes with the analysis.
 */
function PrintAnalysis({ text, progress, detector }) {
  let realStarted = detector.realStarted !== false;
  let realReason = detector.realReason || "";
  if (progress !== undefined && progress !== null && parseFloat(progress) < WARMUP_PROGRESS_PERCENT) {
    realStarted = false;
    realReason = "progress " + parseFloat(progress) + "% <2% - riscaldamento/mesh";
  }

  const verdict = parsePrintVerdict(text);
  if (!verdict) return h("div", { className: "ai-print" }, h("div", { className: "ai-summary__text" }, h(MarkdownBody, { text })));

  const spaghetti = verdict.spaghetti || {};
  const emptyBed = verdict.empty_bed || {};
  const layerShift = verdict.layer_shift || {};
  const warping = verdict.warping || {};
  const action = (verdict.action || "CONTINUA").toUpperCase();

  return h(
    "div",
    { className: "ai-print" },
    h(
      "div",
      { className: "flex items-center justify-between gap-2" },
      h("div", { className: "flex items-center gap-2" }, h(StatusDot, { alert: spaghetti.detected || emptyBed.detected || layerShift.detected }), h("span", { className: "oui-label" }, "Analisi AI completata")),
      h("span", { className: "oui-badge oui-badge--" + actionTone(action) }, action),
    ),
    h("div", { className: "ai-summary" }, h("div", { className: "oui-caption mb-1" }, "Riepilogo"), h("div", { className: "ai-summary__text" }, verdict.summary || "Nessun riassunto")),
    h(
      "div",
      { className: "check-grid" },
      h(CheckTile, { title: "Spaghetti", detected: spaghetti.detected, badge: h(ConfidenceBadge, { value: spaghetti.confidence }), note: spaghetti.note }),
      h(CheckTile, {
        title: "Piatto vuoto",
        detected: realStarted ? emptyBed.detected : false,
        label: realStarted ? undefined : "OK (riscaldamento)",
        badge: realStarted ? h(ConfidenceBadge, { value: emptyBed.confidence }) : h("span", { className: "oui-badge" }, "Ignorato"),
        note: !realStarted && "Riscaldamento/mesh in corso (" + realReason + "), piatto vuoto normale - monitoraggio piatto vuoto sospeso",
      }),
      h(CheckTile, { title: "Layer shift", detected: layerShift.detected, badge: h(ConfidenceBadge, { value: layerShift.confidence }) }),
      h(CheckTile, { title: "Warping", detected: warping.detected, badge: warping.confidence ? h(ConfidenceBadge, { value: warping.confidence }) : null }),
    ),
  );
}
