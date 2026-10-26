/* ============================================================================
   48 · EXTRUDER CARD (Controllo tab)
   Hotend tile, one-tap macros, and manual extrusion / retraction with a
   configurable length and speed.
   ========================================================================== */

const EXTRUDER_MACROS = [
  { gcode: "PARK", toast: "PARK", label: "Park" },
  { gcode: "WIPE", toast: "WIPE", label: "Wipe" },
  { gcode: "FILAMENT_LOAD", toast: "FILAMENT LOAD", label: "Filament load" },
  { gcode: "FILAMENT_UNLOAD", toast: "FILAMENT UNLOAD", label: "Filament unload" },
];
const EXTRUDE_LENGTH_PRESETS_MM = [50, 25, 10, 5, 1];
const EXTRUDE_SPEED_PRESETS_MM_S = [10, 5, 2, 1];

/** Number input with unit and a row of preset chips. */
function PresetField({ title, unit, value, onChange, presets }) {
  return h(
    "div",
    { className: "oui-tile preset-field" },
    h("div", { className: "oui-label mb-2" }, title),
    h(
      "div",
      { className: "flex items-center gap-2 min-w-0" },
      h("input", {
        type: "number",
        value,
        onChange: (e) => onChange(parseFloat(e.target.value) || 0),
        className: "oui-field oui-field--num preset-field__input",
      }),
      h("span", { className: "oui-label shrink-0" }, unit),
    ),
    h(
      "div",
      { className: "preset-chips" },
      presets.map((preset) => h("button", { key: preset, onClick: () => onChange(preset), className: cx("oui-chip", value === preset && "is-selected") }, preset)),
    ),
  );
}

function ExtruderCard({ hotend, onGcode, onEditTemperature }) {
  const [lengthMm, setLengthMm] = useState(5);
  const [speedMmS, setSpeedMmS] = useState(10);

  /** direction: 1 = extrude, -1 = retract */
  const moveFilament = (direction) => {
    onGcode(`G91\nG1 E${direction * lengthMm} F${speedMmS * 60}\nG90`);
    toast.action(direction === 1 ? tx("Extrude {length}mm @ {speed}mm/s", { length: lengthMm, speed: speedMmS }) : tx("Retract {length}mm", { length: lengthMm }));
  };

  return h(
    Card,
    null,
    h(CardHeader, { title: tx("Extruder") }),
    h(
      "div",
      { className: "grid grid-cols-2 mb-4 w-full" },
      h(HeaterTile, { kind: "hotend", heater: hotend, onEdit: () => onEditTemperature("hotend", hotend.target), className: "h-full" }),
      h(
        "div",
        { className: "grid grid-cols-2 h-full gap-2" },
        EXTRUDER_MACROS.map((macro) =>
          h(
            "button",
            {
              key: macro.gcode,
              onClick: () => {
                onGcode(macro.gcode);
                toast.action(macro.toast);
              },
              className: "macro-btn",
            },
            macro.label,
          ),
        ),
      ),
    ),
    h(
      "div",
      { className: "extruder-fields grid w-full max-w-full" },
      h(PresetField, { title: tx("Filament length"), unit: "mm", value: lengthMm, onChange: setLengthMm, presets: EXTRUDE_LENGTH_PRESETS_MM }),
      h(PresetField, { title: tx("Extrusion feedrate"), unit: "mm/s", value: speedMmS, onChange: setSpeedMmS, presets: EXTRUDE_SPEED_PRESETS_MM_S }),
    ),
    h(
      "div",
      { className: "oui-btn-row mt-4" },
      h("button", { onClick: () => moveFilament(-1), className: "oui-btn" }, h("span", null, "↑"), " Retract"),
      h("button", { onClick: () => moveFilament(1), className: "oui-btn" }, h("span", null, "↓"), " Extrude"),
    ),
  );
}
