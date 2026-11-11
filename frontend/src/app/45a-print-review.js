/* ============================================================================
   45a · HOW DID THE PRINT GO? (1.103)
   When a print ends (finished or cancelled) a card on the home page asks how it went: went fine, or a problem (which
   kinds, and from about which picture). Optional: «Don't ask again» here, or Settings → Recordings → «Ask how each print
   went». The answers mark the print's alarms and are the examples the AI monitor learns from (backend/print_review.py).
   ========================================================================== */

const REVIEW_POLL_MS = 20000;
const REVIEW_PROBLEMS = {
  spaghetti: () => tx("Spaghetti / tangled filament"),
  detached: () => tx("Part detached from the bed"),
  layer_shift: () => tx("Layer shift"),
  warping: () => tx("Warping (corners lifted)"),
  nozzle_blob: () => tx("Blob on the nozzle"),
  under_extrusion: () => tx("Under-extrusion / gaps"),
  other: () => tx("Something else"),
};
const REVIEW_END = { complete: () => tx("Finished"), cancelled: () => tx("Cancelled"), error: () => tx("Stopped by an error") };

function usePrintReview(printing) {
  const [state, setState] = useState({ review: null, problems: Object.keys(REVIEW_PROBLEMS) });
  const load = React.useCallback(async () => {
    try {
      const response = await fetchFresh("/api/print/review", { timeout: BRAIN_READ_TIMEOUT_MS });
      if (!response.ok) return setState((old) => ({ ...old, review: null }));
      const json = await response.json();
      setState({ review: json.review || null, problems: Array.isArray(json.problems) ? json.problems.filter((id) => REVIEW_PROBLEMS[id]) : Object.keys(REVIEW_PROBLEMS) });
    } catch (error) {
      /* the KlippEye service does not answer: nothing to ask */
    }
  }, []);
  useEffect(() => {
    if (printing) {
      setState((old) => ({ ...old, review: null }));
      return undefined;
    }
    load();
    const timer = setInterval(load, REVIEW_POLL_MS);
    return () => clearInterval(timer);
  }, [printing, load]);
  return { ...state, reload: load, clear: () => setState((old) => ({ ...old, review: null })) };
}

const reviewClock = (seconds) => new Date(seconds * 1000).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });

/** The card. `printing`: no question while a print runs. */
function PrintReviewCard({ printing }) {
  const { review, problems, clear } = usePrintReview(printing);
  const [step, setStep] = useState("ask"); // ask | problem | done
  const [chosen, setChosen] = useState([]);
  const [picture, setPicture] = useState(null); // index of the picture where the problem shows; null: not known
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [done, setDone] = useState(null);
  const id = review ? review.id : null;
  useEffect(() => {
    setStep("ask");
    setChosen([]);
    setPicture(null);
    setProblem("");
  }, [id]);
  useEffect(() => {
    if (step !== "done") return undefined;
    const timer = setTimeout(() => {
      setDone(null);
      clear();
    }, 4000);
    return () => clearTimeout(timer);
  }, [step]);
  if (!review && !done) return null;
  if (done) {
    return h(Card, { className: "print-review", "data-print-review": "done" }, h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), done));
  }
  const thumbs = Array.isArray(review.thumbs) ? review.thumbs : [];
  const send = async (outcome) => {
    setBusy(true);
    setProblem("");
    const at = outcome === "failed" && picture !== null && thumbs[picture] ? thumbs[picture].t : null;
    const reply = await brainPost("/api/print/review/" + encodeURIComponent(review.id), { outcome, problems: outcome === "failed" ? chosen : [], failed_at: at });
    setBusy(false);
    if (!reply.ok) return setProblem(tx("Not saved: ") + (reply.message || tx("the KlippEye service does not answer")));
    if (outcome === "skipped") return clear();
    const marked = reply.data && reply.data.alarms_marked;
    setDone(tx("Thank you: saved.") + (marked ? " " + tx("Alarms judged with it: {count}", { count: marked }) : ""));
    setStep("done");
  };
  const stopAsking = async () => {
    setBusy(true);
    const reply = await brainPost("/api/backend/config", { values: { print_review: false } });
    setBusy(false);
    if (!reply.ok) return setProblem(tx("Not saved: ") + (reply.message || tx("the KlippEye service does not answer")));
    clear();
  };
  const end = REVIEW_END[review.end_state];
  const shown = picture !== null ? thumbs[picture] : thumbs[thumbs.length - 1];
  const toggle = (problemId) => setChosen((old) => (old.includes(problemId) ? old.filter((x) => x !== problemId) : [...old, problemId]));
  return h(
    Card,
    { className: "print-review md:col-span-2", "data-print-review": review.id },
    h(CardHeader, { title: tx("How did the print go?") }),
    h(
      "div",
      { className: "print-review__head" },
      shown && h("img", { className: "print-review__thumb", src: "/api/print/review/" + encodeURIComponent(review.id) + "/" + shown.n + ".jpg", alt: "" }),
      h(
        "div",
        { className: "print-review__text" },
        h("div", { className: "print-review__file" }, review.file || "-"),
        h("div", { className: "oui-caption" }, [end ? end() : null, review.ended ? reviewClock(review.ended) : null].filter(Boolean).join(" · ")),
      ),
    ),
    step === "ask" &&
      h(
        "div",
        { className: "rec-labels print-review__choice", role: "group", "aria-label": tx("How did the print go?") },
        h("button", { type: "button", className: "oui-chip rec-labels__chip rec-labels__good", disabled: busy, "data-review": "ok", onClick: () => send("ok") }, h("span", { className: "rec-labels__main" }, h(Icons.Check, { size: 18 }), tx("Went fine")), h("span", { className: "rec-labels__detail" }, tx("no problem in the print"))),
        h("button", { type: "button", className: "oui-chip rec-labels__chip rec-labels__bad", disabled: busy, "data-review": "failed", onClick: () => setStep("problem") }, h("span", { className: "rec-labels__main" }, h(Icons.Warning, { size: 18 }), tx("There was a problem")), h("span", { className: "rec-labels__detail" }, tx("choose which"))),
      ),
    step === "problem" &&
      h(
        React.Fragment,
        null,
        h("div", { className: "rec-labels__question" }, tx("What went wrong? (one or more)")),
        h(
          "div",
          { className: "print-review__problems", role: "group" },
          problems.map((problemId) =>
            h("button", { key: problemId, type: "button", className: cx("oui-chip", chosen.includes(problemId) && "is-selected"), "aria-pressed": chosen.includes(problemId), "data-review-problem": problemId, onClick: () => toggle(problemId) }, REVIEW_PROBLEMS[problemId]()),
          ),
        ),
        thumbs.length > 1 &&
          h(
            "div",
            { className: "print-review__when" },
            h("div", { className: "rec-labels__question" }, tx("From when can it be seen? (optional)")),
            h("input", {
              type: "range",
              className: "print-review__slider",
              min: 0,
              max: thumbs.length - 1,
              step: 1,
              value: picture === null ? thumbs.length - 1 : picture,
              "aria-label": tx("From when can it be seen? (optional)"),
              "data-review-when": "1",
              onChange: (event) => setPicture(Number(event.target.value)),
            }),
            h(
              "div",
              { className: "oui-caption" },
              picture === null
                ? tx("Move the slider to the first picture where the problem shows.")
                : [reviewClock(thumbs[picture].t), Number.isFinite(thumbs[picture].progress) ? Math.round(thumbs[picture].progress) + "%" : null, thumbs[picture].layer ? tx("layer {layer}", { layer: thumbs[picture].layer }) : null].filter(Boolean).join(" · "),
            ),
          ),
        h(
          "div",
          { className: "print-review__actions" },
          h("button", { type: "button", className: "oui-btn", disabled: busy, onClick: () => setStep("ask") }, tx("Back")),
          h("button", { type: "button", className: "oui-btn oui-btn--primary", disabled: busy || chosen.length === 0, "data-review-save": "1", onClick: () => send("failed") }, tx("Save")),
        ),
      ),
    problem && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), problem),
    h(
      "div",
      { className: "print-review__more" },
      h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", disabled: busy, "data-review": "skipped", onClick: () => send("skipped") }, tx("Skip")),
      h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", disabled: busy, "data-review-never": "1", onClick: stopAsking }, tx("Don't ask again")),
    ),
  );
}
