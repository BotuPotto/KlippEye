/* ============================================================================
   45a · HOW DID THE PRINT GO? (1.103)
   When a print ends (finished or cancelled) a card on the home page asks how it went: went fine, or a problem (which
   kinds, and from about which picture). Optional: «Don't ask again» here, or Settings → Recordings → «Ask how each print
   went». The answers mark the print's alarms and are the examples the AI monitor learns from (backend/print_review.py).
   ========================================================================== */

const REVIEW_POLL_MS = 20000;
/** The problems to choose from, each with a small drawing of it, in two groups: the ones that ruin a print (what the AI
 * monitor must catch) and the defects of quality. The order and the ids are backend/print_review.py's PROBLEMS. */
const reviewPaths = (...paths) => ({ size = 30 }) => h(Svg, { size, strokeWidth: "1.7" }, paths.map((d, i) => h("path", { key: i, d })));
const REVIEW_PROBLEMS = {
  spaghetti: { group: "failed", label: () => tx("Spaghetti / tangled filament"), icon: reviewPaths("M3 21h18", "M4 17c2-5 4 3 6-2s3 4 5-1 3 3 5 0", "M5 13c2-3 3 2 5-1s4 2 6-1 2 2 3 0", "M10 3h4v3l-2 2-2-2z") },
  detached: { group: "failed", label: () => tx("Part detached from the bed"), icon: reviewPaths("M3 21h18", "M6 17l2-8 8 2-2 8z", "M9 3h4v3l-2 2-2-2z") },
  layer_shift: { group: "failed", label: () => tx("Layer shift"), icon: reviewPaths("M3 21h18", "M5 21v-5h8v5", "M9 16v-5h8v5", "M9 11V6h8v5") },
  nozzle_blob: { group: "failed", label: () => tx("Blob on the nozzle"), icon: reviewPaths("M9 3h6v4l-3 3-3-3z", "M12 10c4 0 6 2 6 4.5S15.5 19 12 19s-6-2-6-4.5S8 10 12 10z", "M3 21h18") },
  clog: { group: "failed", label: () => tx("No filament coming out (clog)"), icon: reviewPaths("M9 3h6v4l-3 3-3-3z", "M12 13v1.5M12 17v1.5", "M3 21h18", "M6 12l12 6") },
  warping: { group: "failed", label: () => tx("Warping (corners lifted)"), icon: reviewPaths("M3 21h18", "M4 17c1-3 2-3 4-3h8c2 0 3 0 4 3", "M8 14V7h8v7") },
  stringing: { group: "quality", label: () => tx("Stringing (thin hairs)"), icon: reviewPaths("M3 21h18", "M4 21V9h4v12", "M16 21V9h4v12", "M8 11c3 2 5 2 8 0", "M8 14c3 1.5 5 1.5 8 0", "M8 17c3 1 5 1 8 0") },
  under_extrusion: { group: "quality", label: () => tx("Under-extrusion / gaps"), icon: reviewPaths("M3 21h18", "M4 17h3m3 0h4m3 0h3", "M4 13h5m4 0h7", "M4 9h2m3 0h6m3 0h2", "M4 5h4m4 0h2m3 0h3") },
  over_extrusion: { group: "quality", label: () => tx("Over-extrusion / blobs on the surface"), icon: reviewPaths("M3 21h18", "M5 18h14", "M5 14h14", "M5 10h14", "M8 6h0M14 8h0M17 13h0M9 16h0") },
  elephant_foot: { group: "quality", label: () => tx("Elephant foot (wider bottom)"), icon: reviewPaths("M3 21h18", "M7 4h10v12l3 5H4l3-5z") },
  ghosting: { group: "quality", label: () => tx("Ringing / ghosting (echoes on the walls)"), icon: reviewPaths("M3 21h18", "M6 19V5", "M10 19V5", "M13 8v8M15.5 9v6M18 10v4") },
  overhangs: { group: "quality", label: () => tx("Drooping overhangs or bridges"), icon: reviewPaths("M3 21h18", "M4 21V8h16v13", "M8 21v-6c0 3 8 3 8 0v6", "M4 8c2 2 4 1 5 3") },
  supports: { group: "quality", label: () => tx("Supports failed"), icon: reviewPaths("M3 21h18", "M5 9h14V5H5z", "M7 21v-4M7 14v-2M12 21v-12M17 21v-5") },
  rough_surface: { group: "quality", label: () => tx("Rough or bumpy surface"), icon: reviewPaths("M3 21h18", "M4 21V9l2-2 2 2 2-2 2 2 2-2 2 2 2-2 2 2v12") },
  other: { group: "quality", label: () => tx("Something else"), icon: reviewPaths("M3 21h18", "M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7v1", "M12 17.5v.5") },
};
const REVIEW_GROUPS = [
  { id: "failed", title: () => tx("The print failed") },
  { id: "quality", title: () => tx("Defects of quality") },
];
const REVIEW_END = { complete: () => tx("Finished"), cancelled: () => tx("Cancelled"), error: () => tx("Stopped by an error") };

function usePrintReview(printing) {
  const [state, setState] = useState({ review: null, problems: Object.keys(REVIEW_PROBLEMS) });
  const load = React.useCallback(async () => {
    try {
      const response = await fetchFresh("/api/print/review", { timeout: BACKEND_READ_TIMEOUT_MS });
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

const reviewPicture = (review, thumb) => "/api/print/review/" + encodeURIComponent(review.id) + "/" + thumb.n + ".jpg";

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
    const reply = await backendPost("/api/print/review/" + encodeURIComponent(review.id), { outcome, problems: outcome === "failed" ? chosen : [], failed_at: at });
    setBusy(false);
    if (!reply.ok) return setProblem(tx("Not saved: ") + (reply.message || tx("the KlippEye service does not answer")));
    if (outcome === "skipped") return clear();
    const marked = reply.data && reply.data.alarms_marked;
    setDone(tx("Thank you: saved.") + (marked ? " " + tx("Alarms judged with it: {count}", { count: marked }) : ""));
    setStep("done");
  };
  const stopAsking = async () => {
    setBusy(true);
    const reply = await backendPost("/api/backend/config", { values: { print_review: false } });
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
      shown && step !== "problem" && h("img", { className: "print-review__thumb", src: reviewPicture(review, shown), alt: "" }),
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
        REVIEW_GROUPS.map((group) => {
          const ids = problems.filter((problemId) => REVIEW_PROBLEMS[problemId].group === group.id);
          return (
            ids.length > 0 &&
            h(
              "div",
              { key: group.id, className: "print-review__group" },
              h("div", { className: "oui-label print-review__group-title" }, group.title()),
              h(
                "div",
                { className: "print-review__problems", role: "group", "aria-label": group.title() },
                ids.map((problemId) =>
                  h(
                    "button",
                    { key: problemId, type: "button", className: cx("print-review__problem", chosen.includes(problemId) && "is-selected"), "aria-pressed": chosen.includes(problemId), "data-review-problem": problemId, onClick: () => toggle(problemId) },
                    h("span", { className: "print-review__problem-icon", "aria-hidden": "true" }, h(REVIEW_PROBLEMS[problemId].icon)),
                    h("span", { className: "print-review__problem-label" }, REVIEW_PROBLEMS[problemId].label()),
                    chosen.includes(problemId) && h("span", { className: "print-review__problem-check", "aria-hidden": "true" }, h(Icons.Check, { size: 14 })),
                  ),
                ),
              ),
            )
          );
        }),
        thumbs.length > 1 && h(ReviewWhen, { review, thumbs, picture, setPicture }),
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

/**
 * «From when can it be seen?» (1.122): the picture big, across the card, with the slider and the ‹ › steps right under
 * it, so that the eyes stay on the picture while choosing. A tap opens it over the whole screen, to zoom on a small
 * defect. Until the slider is touched it shows the last picture and nothing is chosen.
 */
function ReviewWhen({ review, thumbs, picture, setPicture }) {
  const index = picture === null ? thumbs.length - 1 : picture;
  const thumb = thumbs[index];
  const go = (to) => setPicture(Math.max(0, Math.min(thumbs.length - 1, to)));
  const when = [reviewClock(thumb.t), Number.isFinite(thumb.progress) ? Math.round(thumb.progress) + "%" : null, thumb.layer ? tx("layer {layer}", { layer: thumb.layer }) : null].filter(Boolean).join(" · ");
  return h(
    "div",
    { className: "print-review__when" },
    h("div", { className: "rec-labels__question" }, tx("From when can it be seen? (optional)")),
    h(
      "div",
      { className: "print-review__picture" },
      h(ZoomablePhoto, { src: reviewPicture(review, thumb), title: (review.file || "") + " · " + when, className: "print-review__photo" }),
      h("span", { className: "print-review__stamp", "data-review-stamp": "1" }, tx("{n} of {total}", { n: index + 1, total: thumbs.length }) + " · " + when),
    ),
    h(
      "div",
      { className: "print-review__scrub" },
      h("button", { type: "button", className: "oui-btn oui-btn--icon", "aria-label": tx("Previous picture"), title: tx("Previous picture"), disabled: index === 0, "data-review-step": "-1", onClick: () => go(index - 1) }, h("span", { "aria-hidden": "true", className: "print-review__arrow" }, "‹")),
      h("input", {
        type: "range",
        className: "print-review__slider",
        min: 0,
        max: thumbs.length - 1,
        step: 1,
        value: index,
        "aria-label": tx("From when can it be seen? (optional)"),
        "aria-valuetext": when,
        "data-review-when": "1",
        onChange: (event) => setPicture(Number(event.target.value)),
      }),
      h("button", { type: "button", className: "oui-btn oui-btn--icon", "aria-label": tx("Next picture"), title: tx("Next picture"), disabled: index === thumbs.length - 1, "data-review-step": "1", onClick: () => go(index + 1) }, h("span", { "aria-hidden": "true", className: "print-review__arrow" }, "›")),
    ),
    h("div", { className: "oui-caption" }, picture === null ? tx("Move the slider to the first picture where the problem shows. Tap the picture to enlarge it.") : tx("Tap the picture to enlarge it.")),
  );
}
