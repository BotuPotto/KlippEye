/* ============================================================================
   50c · TEXT HISTORY
   Undo and redo for the text editor, kept by the editor itself (not by the browser) so that every way of changing
   the text — typing, paste, Tab, the comment bar — lands in the same list, the buttons know when there is
   something to take back, and a phone does the same as a PC.
     useTextHistory   the hook the editor uses: input / replace / undo / redo, canUndo / canRedo
     diffText         what changed between two texts
     joinEdits        two edits in a row as one
   An edit is stored as the piece of text that changed ({ start, removed, inserted }) and not as a copy of the whole
   file, so a long list of steps stays small.
   ========================================================================== */

/** The steps kept; the oldest one is forgotten after that. */
const HISTORY_LIMIT = 300;
/** Letters typed one after the other within this time are one step (like Ctrl+Z in any editor). */
const HISTORY_TYPING_GAP_MS = 900;

/** What changed from `before` to `after`: from `start`, the text `removed` became `inserted`. */
function diffText(before, after) {
  const shortest = Math.min(before.length, after.length);
  let start = 0;
  while (start < shortest && before.charCodeAt(start) === after.charCodeAt(start)) start++;
  let tail = 0;
  while (tail < shortest - start && before.charCodeAt(before.length - 1 - tail) === after.charCodeAt(after.length - 1 - tail)) tail++;
  return { start, removed: before.slice(start, before.length - tail), inserted: after.slice(start, after.length - tail) };
}

/**
 * `first` and the edit `second` made on its result as a single edit, when `second` touches what `first` wrote
 * (letters typed one after another, a backspace right after them); otherwise null.
 */
function joinEdits(first, second) {
  const firstEnd = first.start + first.inserted.length; // what `first` wrote sits in [first.start, firstEnd)
  const secondEnd = second.start + second.removed.length;
  if (second.start > firstEnd || secondEnd < first.start) return null;
  // the part of the text `second` removed that `first` had not written belongs to the joined edit as well
  const removedBefore = second.start < first.start ? second.removed.slice(0, first.start - second.start) : "";
  const removedAfter = secondEnd > firstEnd ? second.removed.slice(firstEnd - second.start) : "";
  // and the part of what `first` wrote that `second` left alone stays in what the joined edit writes
  const keptBefore = second.start > first.start ? first.inserted.slice(0, second.start - first.start) : "";
  const keptAfter = secondEnd < firstEnd ? first.inserted.slice(secondEnd - first.start) : "";
  return { start: Math.min(first.start, second.start), removed: removedBefore + first.removed + removedAfter, inserted: keptBefore + second.inserted + keptAfter };
}

/** Typed letters and composed words are one run, erasing another: a run is joined into one step, never mixed with the other. */
const HISTORY_RUN = { type: "write", compose: "write", erase: "erase" };

/** "type" / "erase": one character; "compose": a word the keyboard is building (phones); "other": anything bigger. */
function editKind(edit, composing) {
  if (composing) return "compose";
  if (edit.removed === "" && edit.inserted.length === 1 && edit.inserted !== "\n") return "type";
  if (edit.inserted === "" && edit.removed.length === 1) return "erase";
  return "other";
}

/**
 * Undo / redo for a controlled <textarea>.
 *   input(event)                          the textarea's onChange: records what the user did, then sets the text
 *   replace(start, end, text, before, after)   an edit made by the editor (Tab, the comment bar); `before` / `after` are
 *                                         the selections [start, end] to give back on undo / redo
 *   undo(), redo(), canUndo, canRedo
 * `reveal(offset)` is told where the text changed, to bring that place into view.
 */
function useTextHistory(text, setText, textareaRef, reveal) {
  const steps = useRef({ undo: [], redo: [], sealed: false }); // sealed: the next edit starts a new step
  const latest = useRef(text); // the text as of the last edit (the state follows on the next render)
  const selectionBefore = useRef(null); // taken by "beforeinput", the moment before the browser changes the text
  const pendingSelection = useRef(null); // given to the textarea once React has put the new text in it
  const [, redraw] = useState(0);
  latest.current = text;

  const push = (edit) => {
    const stacks = steps.current;
    stacks.redo.length = 0;
    const now = Date.now();
    const top = stacks.undo[stacks.undo.length - 1];
    const run = HISTORY_RUN[edit.kind];
    if (top && !stacks.sealed && run && run === HISTORY_RUN[top.kind] && now - top.time <= HISTORY_TYPING_GAP_MS) {
      const joined = joinEdits(top, edit);
      if (joined) {
        stacks.undo.pop();
        if (joined.removed !== joined.inserted) stacks.undo.push({ ...joined, kind: edit.kind, before: top.before, after: edit.after, time: now });
        return;
      }
    }
    stacks.sealed = false;
    stacks.undo.push({ ...edit, time: now });
    if (stacks.undo.length > HISTORY_LIMIT) stacks.undo.shift();
  };

  const input = (event) => {
    const textarea = event.target;
    const value = textarea.value;
    const type = event.nativeEvent && event.nativeEvent.inputType;
    if (type === "historyUndo" || type === "historyRedo") {
      // the browser did its own undo (execCommand, or a browser that does not announce it first): it has already changed
      // the text, so the text is put back as it was and the step is done from this list instead
      textarea.value = latest.current;
      move(type === "historyUndo");
      return;
    }
    if (value === latest.current) return;
    const edit = diffText(latest.current, value);
    edit.kind = editKind(edit, event.nativeEvent && event.nativeEvent.isComposing);
    edit.before = selectionBefore.current || [edit.start, edit.start + edit.removed.length];
    edit.after = [textarea.selectionStart, textarea.selectionEnd];
    selectionBefore.current = null;
    push(edit);
    latest.current = value;
    setText(value);
  };

  const replace = (start, end, insertion, before, after) => {
    const current = latest.current;
    const value = current.slice(0, start) + insertion + current.slice(end);
    push({ start, removed: current.slice(start, end), inserted: insertion, kind: "other", before, after });
    latest.current = value;
    pendingSelection.current = after;
    setText(value);
  };

  /** Takes back (`undoing`) or does again the last step of one list and moves it to the other list. */
  const move = (undoing) => {
    const stacks = steps.current;
    const [from, to] = undoing ? [stacks.undo, stacks.redo] : [stacks.redo, stacks.undo];
    const edit = from.pop();
    if (!edit) return;
    const [out, into] = undoing ? [edit.inserted, edit.removed] : [edit.removed, edit.inserted];
    const current = latest.current;
    if (current.slice(edit.start, edit.start + out.length) !== out) {
      // the text is not what this step left: the list no longer fits it, so it is dropped rather than applied wrongly
      stacks.undo.length = 0;
      stacks.redo.length = 0;
      redraw((n) => n + 1);
      return;
    }
    const value = current.slice(0, edit.start) + into + current.slice(edit.start + out.length);
    to.push(edit);
    stacks.sealed = true;
    latest.current = value;
    pendingSelection.current = undoing ? edit.before : edit.after;
    setText(value);
  };
  const undo = () => move(true);
  const redo = () => move(false);

  useEffect(() => {
    const textarea = textareaRef.current;
    const onBeforeInput = (event) => {
      // the browser's own undo (keyboard of a phone, Edit menu) is stopped before it starts and done from this list
      if (event.inputType === "historyUndo" || event.inputType === "historyRedo") {
        event.preventDefault();
        move(event.inputType === "historyUndo");
      } else selectionBefore.current = [textarea.selectionStart, textarea.selectionEnd];
    };
    textarea.addEventListener("beforeinput", onBeforeInput);
    return () => textarea.removeEventListener("beforeinput", onBeforeInput);
  }, []);

  // React has just put the text in the textarea (which sends the caret to the end): give the selection back
  useLayoutEffect(() => {
    const selection = pendingSelection.current;
    if (!selection) return;
    pendingSelection.current = null;
    textareaRef.current.setSelectionRange(selection[0], selection[1]);
    reveal(selection[0]);
  }, [text]);

  return { input, replace, undo, redo, canUndo: steps.current.undo.length > 0, canRedo: steps.current.redo.length > 0 };
}
