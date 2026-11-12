/* ============================================================================
   43 · HEATERS CARD & TEMPERATURE DIALOG
   Hotend and bed tiles (tap to change the target), then the fan lock and fans.
   ========================================================================== */

const HEATERS = {
  hotend: { label: "HOTEND", icon: HOTEND_ICON_PNG, gcode: "M104 S" },
  bed: { label: "BED", icon: BED_ICON_PNG, gcode: "M140 S" },
};

/**
 * 1.112: the usual materials: one tap sets the nozzle and the bed together (the common starting points; a spool's own
 * temperatures may differ a little).
 */
const MATERIAL_PRESETS = [
  { name: "PLA", hotend: 210, bed: 60 },
  { name: "PETG", hotend: 240, bed: 80 },
  { name: "ABS", hotend: 250, bed: 100 },
  { name: "ASA", hotend: 255, bed: 100 },
  { name: "TPU", hotend: 225, bed: 50 },
];

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
    h("div", { className: "oui-caption ui-hint" }, tx("Tap to change")),
  );
}

function HeatersFansCard({ hotend, bed, onEditTemperature }) {
  return h(
    Card,
    { cardId: "heaters" },
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
  /** 1.112: a material: the nozzle and the bed at once. */
  const material = (preset) => {
    sendBrainGcode(HEATERS.hotend.gcode + preset.hotend + "\n" + HEATERS.bed.gcode + preset.bed).catch(noop);
    close();
  };
  /** 1.112: this heater off. */
  const off = () => {
    sendBrainGcode(HEATERS[dialog.kind].gcode + "0").catch(noop);
    close();
  };
  return { dialog, edit, close, setValue, confirm, material, off };
}

function TemperatureDialog({ dialog, onChange, onClose, onConfirm, onMaterial, onOff, maxTemp }) {
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
            max: (maxTemp || DEFAULT_MAX_TEMP)[dialog.kind],
            placeholder: "0",
            value: dialog.value,
            onChange: (e) => onChange(e.target.value),
            onKeyDown: (e) => e.key === "Enter" && onConfirm(),
            className: "oui-field oui-field--num modal-input",
          }),
          h("span", { className: "dialog-unit" }, "°C"),
        ),
      ),
      onMaterial &&
        h(
          "div",
          { className: "temp-presets" },
          h("div", { className: "oui-label mb-2" }, tx("Material: nozzle and bed together")),
          h(
            "div",
            { className: "temp-presets__chips" },
            MATERIAL_PRESETS.map((preset) =>
              h(
                "button",
                { key: preset.name, type: "button", className: "oui-chip temp-preset", "data-temp-preset": preset.name, onClick: () => onMaterial(preset) },
                h("span", { className: "temp-preset__name" }, preset.name),
                h("span", { className: "temp-preset__values" }, preset.hotend + "° / " + preset.bed + "°"),
              ),
            ),
            onOff && h("button", { type: "button", className: "oui-chip temp-preset temp-preset--off", "data-temp-preset": "off", onClick: onOff }, h(Icons.Power, { size: 14 }), txc("heater", "Off")),
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
