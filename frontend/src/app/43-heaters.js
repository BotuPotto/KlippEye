/* ============================================================================
   43 · HEATERS CARD & TEMPERATURE DIALOG
   Hotend and bed tiles (tap to change the target), then the fan lock and fans.
   ========================================================================== */

const HEATERS = {
  hotend: { label: "HOTEND", icon: HOTEND_ICON_PNG, maxTemp: 300, gcode: "M104 S" },
  bed: { label: "BED", icon: BED_ICON_PNG, maxTemp: 120, gcode: "M140 S" },
};

function HeaterTile({ kind, heater, onEdit, className }) {
  const spec = HEATERS[kind];
  const tone = isHot(heater) ? "hot" : "cold";
  return h(
    "button",
    { onClick: onEdit, className: cx("oui-tile heater-tile", "heater-tile--" + tone, className) },
    h(
      "div",
      { className: "heater-tile__top" },
      h("span", { className: "heater-tile__icon" }, h("span", { className: "heater-tile__glyph", style: { "--glyph": `url(${spec.icon})` } })),
      h("span", { className: "heater-tile__name" }, spec.label),
    ),
    h(
      "div",
      { className: "heater-tile__reading" },
      h("span", { className: "oui-value" }, heater.cur.toFixed(1), "°"),
      h("span", { className: "heater-tile__target" }, "/ ", heater.target, "°"),
    ),
    h("div", { className: "oui-caption" }, tx("Tap to change")),
  );
}

function HeatersFansCard({ hotend, bed, onEditTemperature }) {
  return h(
    Card,
    null,
    h(CardHeader, { title: tx("Heaters and fans") }),
    h(
      "div",
      { className: "grid grid-cols-2 heater-tiles" },
      h(HeaterTile, { kind: "hotend", heater: hotend, onEdit: () => onEditTemperature("hotend", hotend.target) }),
      h(HeaterTile, { kind: "bed", heater: bed, onEdit: () => onEditTemperature("bed", bed.target) }),
    ),
    h(FanList),
  );
}

/* ---------------------------------------------------------------------------
   Temperature dialog (shared by the Home card and the Controllo extruder card)
   ------------------------------------------------------------------------- */
function useTemperatureDialog() {
  const [dialog, setDialog] = useState({ open: false, kind: "hotend", value: "" });

  /** Opens the dialog for "hotend" or "bed", pre-filled with the current target. */
  const edit = (kind, currentTarget) => {
    const prefill = Number.isInteger(currentTarget) && currentTarget >= 0 ? String(currentTarget) : "";
    setDialog({ open: true, kind, value: prefill });
  };
  const close = () => setDialog((d) => ({ ...d, open: false }));
  const setValue = (value) => setDialog((d) => ({ ...d, value }));
  const confirm = () => {
    sendBrainGcode(HEATERS[dialog.kind].gcode + (parseInt(dialog.value) || 0)).catch(noop);
    close();
  };
  return { dialog, edit, close, setValue, confirm };
}

function TemperatureDialog({ dialog, onChange, onClose, onConfirm }) {
  const inputRef = useRef(null);
  useEffect(() => {
    if (!dialog.open) return;
    const timer = setTimeout(() => inputRef.current && inputRef.current.focus(), 100);
    return () => clearTimeout(timer);
  }, [dialog.open]);

  if (!dialog.open) return null;
  const spec = HEATERS[dialog.kind];
  return h(
    "div",
    { className: "modal", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "modal-card", onClick: (e) => e.stopPropagation() },
      h(
        "div",
        { className: "flex items-center justify-between mb-5" },
        h("span", { className: "dialog-title" }, spec.label),
        h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕"),
      ),
      h(
        "div",
        { className: "mb-6" },
        h("label", { className: "oui-label mb-2 block" }, tx("Temperature ") + spec.label.toLowerCase()),
        h(
          "div",
          { className: "flex items-center gap-3" },
          h("input", {
            ref: inputRef,
            type: "number",
            inputMode: "numeric",
            max: spec.maxTemp,
            placeholder: "0",
            value: dialog.value,
            onChange: (e) => onChange(e.target.value),
            onKeyDown: (e) => e.key === "Enter" && onConfirm(),
            className: "oui-field oui-field--num modal-input",
          }),
          h("span", { className: "dialog-unit" }, "°C"),
        ),
      ),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { className: "oui-btn", onClick: onClose }, tx("Cancel")),
        h("button", { className: "oui-btn oui-btn--primary", onClick: onConfirm }, tx("Set")),
      ),
    ),
  );
}
