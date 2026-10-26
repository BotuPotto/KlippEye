/* ============================================================================
   44b · Z OFFSET
   Baby stepping while a job prints, in the place of the Movement card (jogging
   during a print would be an accident), and the way to keep the result: at the
   end of the print the card stays until the offset is applied, which writes it
   into printer.cfg (Z_OFFSET_APPLY_PROBE or _ENDSTOP, then SAVE_CONFIG, which
   restarts Klipper and so is never offered mid-print). Same approach as
   Mainsail's and Fluidd's Z-offset controls.
   ========================================================================== */

// The step sizes (mm per tap) are a setting (app/16-settings.js): the card offers the ones listed in the settings menu.
const Z_ADJUST_SEND_DELAY_MS = 250; // taps closer than this are sent as one adjustment
const Z_EPSILON = 0.0005; // an offset smaller than this is "zero" (the card shows three decimals)
const Z_END_STATES = ["complete", "cancelled"]; // print states in which a leftover offset is still worth saving

const roundMm = (value) => Math.round(value * 10000) / 10000;
/** "+0.050", "−0.125", "0.000": three decimals, a sign only when there is an offset. */
const formatZOffset = (value) => (Math.abs(value) < Z_EPSILON ? "0.000" : (value > 0 ? "+" : "−") + Math.abs(value).toFixed(3));

/** Which cards the Home tab shows: Z offset instead of Movement while printing, and above it after the print while an offset is left. */
function zOffsetPlacement(printStatus, zOffset) {
  if (printStatus.state === "printing") return "instead";
  if (!printStatus.printing && Z_END_STATES.includes(printStatus.state) && Math.abs(zOffset) >= Z_EPSILON) return "above";
  return null;
}

/* ---------------------------------------------------------------------------
   State
   ------------------------------------------------------------------------- */

/**
 * `status` is usePrinterStatus() (live offset, homed axes, refresh), `capabilities` says which
 * Z_OFFSET_APPLY_* command exists, `onSaveConfig` is useSaveConfig().confirm.
 */
function useZOffset({ status, capabilities, onSaveConfig }) {
  const { settings } = useSettings();
  const steps = settings.zOffset.steps;
  const [chosen, setChosen] = useState(() => parseFloat(storage.get(STORAGE_KEYS.zOffsetStep)));
  const step = steps.includes(chosen) ? chosen : steps[0]; // a step taken out of the list in the settings menu: the first one
  // Taps show at once and go out together: `pending` waits for the delay, `sending` waits for Klipper's answer.
  const [pending, setPending] = useState(0);
  const [sending, setSending] = useState(0);
  const pendingRef = useRef(0);
  const timer = useRef(null);
  const [confirming, setConfirming] = useState(null); // "reset" | "apply" while a question is open

  const moveNow = status.homedAxes === "xyz" ? " MOVE=1" : "";

  const flush = async () => {
    const total = roundMm(pendingRef.current);
    pendingRef.current = 0;
    setPending(0);
    if (Math.abs(total) < Z_EPSILON) return;
    setSending((value) => roundMm(value + total));
    const sent = await sendLongGcode("SET_GCODE_OFFSET Z_ADJUST=" + signed(total) + moveNow);
    if (!sent.ok) toast.action("Z-offset non cambiato: " + sent.message);
    await status.refresh();
    setSending((value) => roundMm(value - total));
  };

  const adjust = (direction) => {
    pendingRef.current = roundMm(pendingRef.current + direction * step);
    setPending(pendingRef.current);
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, Z_ADJUST_SEND_DELAY_MS);
  };
  useEffect(() => () => clearTimeout(timer.current), []);

  const chooseStep = (value) => {
    storage.set(STORAGE_KEYS.zOffsetStep, String(value));
    setChosen(value);
  };

  const reset = async () => {
    setConfirming(null);
    pendingRef.current = 0;
    setPending(0);
    const sent = await sendLongGcode("SET_GCODE_OFFSET Z=0" + moveNow);
    if (!sent.ok) toast.action("Z-offset non azzerato: " + sent.message);
    else toast.action("Z-offset azzerato");
    status.refresh();
  };

  const apply = async () => {
    setConfirming(null);
    const sent = await sendLongGcode(capabilities.zOffsetApply);
    if (!sent.ok) return toast.action("Z-offset non applicato: " + sent.message);
    onSaveConfig(); // SAVE_CONFIG: writes printer.cfg and restarts Klipper
  };

  return {
    live: roundMm(status.zOffset + pending + sending),
    steps,
    step,
    chooseStep,
    adjust,
    applyCommand: capabilities.zOffsetApply,
    confirming,
    ask: setConfirming,
    cancel: () => setConfirming(null),
    reset,
    apply,
  };
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */

/** `printing`: the job still runs, so saving (which restarts Klipper) has to wait. */
function ZOffsetCard({ zOffset: controller, printing }) {
  const { live, step, steps, applyCommand } = controller;
  const hasOffset = Math.abs(live) >= Z_EPSILON;
  const closer = live < -Z_EPSILON;

  return h(
    Card,
    null,
    h(CardHeader, { title: "Z-offset" }, h("span", { className: cx("oui-badge", printing ? "oui-badge--info" : "oui-badge--warn") }, printing ? "Live" : "A fine stampa")),
    h(
      "div",
      { className: "zoffset-readout" },
      h("div", { className: cx("zoffset-readout__value", hasOffset && "is-set") }, formatZOffset(live), h("span", { className: "zoffset-readout__unit" }, "mm")),
      h("div", { className: "oui-caption" }, hasOffset ? (closer ? "Ugello più vicino al piano" : "Ugello più lontano dal piano") : "Nessuna correzione attiva"),
    ),
    h(
      "div",
      { className: "zoffset-steps", role: "group", "aria-label": "Passo" },
      steps.map((value) => h("button", { key: value, className: cx("oui-chip", value === step && "is-selected"), onClick: () => controller.chooseStep(value) }, value)),
    ),
    h(
      "div",
      { className: "zoffset-adjust" },
      h("button", { className: "oui-btn zoffset-adjust__btn", onClick: () => controller.adjust(-1) }, h(Icons.ArrowDown), h("span", null, "Abbassa"), h("span", { className: "zoffset-adjust__step" }, "−" + step)),
      h("button", { className: "oui-btn zoffset-adjust__btn", onClick: () => controller.adjust(1) }, h(Icons.ArrowUp), h("span", null, "Alza"), h("span", { className: "zoffset-adjust__step" }, "+" + step)),
    ),
    h(
      "div",
      { className: "oui-btn-row zoffset-actions" },
      h("button", { className: "oui-btn", disabled: !hasOffset, onClick: () => controller.ask("reset") }, "Azzera"),
      applyCommand && h("button", { className: "oui-btn oui-btn--primary", disabled: printing || !hasOffset, onClick: () => controller.ask("apply") }, h(Icons.Save, { size: 18 }), "Salva offset"),
    ),
    h(
      "div",
      { className: "oui-caption zoffset-hint" },
      !applyCommand
        ? "Klipper non offre un comando per salvare l'offset (Z_OFFSET_APPLY_*): resta attivo fino al riavvio."
        : printing
          ? "Si salva a fine stampa: SAVE_CONFIG riavvia Klipper."
          : "Applica scrive l'offset in printer.cfg e riavvia Klipper.",
    ),
  );
}

/** The two questions of the card: clear the offset, write it into printer.cfg. */
function ZOffsetDialogs({ controller }) {
  const { confirming, live, applyCommand } = controller;
  return h(
    React.Fragment,
    null,
    h(ConfirmDialog, {
      open: confirming === "reset",
      tone: "neutral",
      icon: h(Icons.RotateCcw),
      title: "Azzerare lo Z-offset?",
      subtitle: formatZOffset(live) + " mm",
      message: ["L'ugello torna all'altezza senza correzione (", h("code", { key: "cmd" }, "SET_GCODE_OFFSET Z=0"), "), anche durante la stampa. Confermi?"],
      confirmLabel: "Azzera",
      onConfirm: controller.reset,
      onCancel: controller.cancel,
    }),
    h(ConfirmDialog, {
      open: confirming === "apply",
      tone: "neutral",
      icon: h(Icons.Save),
      title: "Applicare lo Z-offset?",
      subtitle: formatZOffset(live) + " mm",
      message: [
        "L'offset verrà scritto in printer.cfg con ",
        h("code", { key: "apply" }, applyCommand || ""),
        " e Klipper si riavvierà (",
        h("code", { key: "save" }, "SAVE_CONFIG"),
        "). Confermi?",
      ],
      confirmLabel: "Applica e salva",
      onConfirm: controller.apply,
      onCancel: controller.cancel,
    }),
  );
}
