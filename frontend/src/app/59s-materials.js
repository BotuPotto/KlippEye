/* ===========================================================================
   Settings → Materials (1.113): the materials of the temperature window — a
   name, the nozzle's and the bed's temperature — the printer's own list
   (shared by every device, like the other settings). The spool in use comes
   from Spoolman by itself and is not in this list.
   ========================================================================= */

/** One line for the menu: the names. */
function materialsSummary(materials) {
  return materials && materials.length ? materials.map((one) => one.name).join(" · ") : tx("None");
}

/** One material: its name and two temperatures, saved when a field is left; the bin removes it. */
function MaterialRow({ material, index, onChange, onRemove }) {
  const [draft, setDraft] = useState(material);
  useEffect(() => setDraft(material), [material.name, material.hotend, material.bed]);
  const commit = () => {
    const name = String(draft.name || "").trim().slice(0, MATERIAL_NAME_MAX);
    const hotend = Math.round(clamp(Number(draft.hotend) || 0, 0, MATERIAL_HOTEND_MAX));
    const bed = Math.round(clamp(Number(draft.bed) || 0, 0, MATERIAL_BED_MAX));
    if (!name) return setDraft(material); // a name is needed: the old one comes back
    if (name !== material.name || hotend !== material.hotend || bed !== material.bed) onChange({ name, hotend, bed });
    else setDraft(material);
  };
  const field = (key, extra) =>
    h("input", {
      className: "oui-field material-row__" + key,
      value: draft[key],
      onChange: (event) => setDraft({ ...draft, [key]: event.target.value }),
      onBlur: commit,
      onKeyDown: (event) => event.key === "Enter" && event.target.blur(),
      "data-material-field": key,
      ...extra,
    });
  return h(
    "div",
    { className: "material-row", "data-material": index },
    field("name", { maxLength: MATERIAL_NAME_MAX, "aria-label": tx("Name") }),
    h("label", { className: "material-row__temp" }, field("hotend", { inputMode: "numeric", "aria-label": tx("Nozzle") }), h("span", null, "°")),
    h("label", { className: "material-row__temp" }, field("bed", { inputMode: "numeric", "aria-label": tx("Bed") }), h("span", null, "°")),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm oui-btn--icon", "aria-label": tx("Remove"), "data-material-remove": index, onClick: onRemove }, h(Icons.Trash, { size: 16 })),
  );
}

function MaterialsPage() {
  const { settings, update } = useSettings();
  const materials = settings.materials || [];
  const set = (fn) => update((draft) => fn(draft.materials));
  const isDefault = JSON.stringify(materials) === JSON.stringify(MATERIAL_PRESETS);
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      {
        title: tx("Materials"),
        note: tx("A tap on a material in the temperature window sets the nozzle and the bed together. The temperatures are a starting point: the ones on your spool's label come first."),
      },
      h(
        "div",
        { className: "material-list" },
        h("div", { className: "material-row material-row--head", "aria-hidden": "true" }, h("span", null, tx("Name")), h("span", null, tx("Nozzle")), h("span", null, tx("Bed")), h("span")),
        materials.map((material, index) =>
          h(MaterialRow, {
            key: index + ":" + material.name,
            material,
            index,
            onChange: (value) => set((list) => (list[index] = value)),
            onRemove: () => set((list) => list.splice(index, 1)),
          }),
        ),
      ),
      h(
        "div",
        { className: "oui-btn-row material-actions" },
        materials.length < MATERIALS_MAX &&
          h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", "data-material-add": "", onClick: () => set((list) => list.push({ name: tx("New"), hotend: 200, bed: 60 })) }, h(Icons.Plus, { size: 16 }), tx("Add a material")),
        !isDefault &&
          h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", "data-material-reset": "", onClick: () => update((draft) => (draft.materials = MATERIAL_PRESETS.map((one) => ({ ...one })))) }, h(Icons.Undo, { size: 16 }), tx("Back to the usual ones")),
      ),
    ),
    h(
      "p",
      { className: "set-group__note" },
      tx("With Spoolman, the spool in use is offered first in the temperature window, with the temperatures of its filament (fill «Extruder Temp» and «Bed Temp» of the filament in Spoolman)."),
    ),
  );
}
