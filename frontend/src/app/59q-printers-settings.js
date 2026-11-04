/* ============================================================================
   59q · SETTINGS → YOUR PRINTERS (1.61)
   The other printers with KlippEye on the network (31b-printers.js): their
   name and address, in the order of the switcher; "Try" asks the address
   before adding it. Shared by every device of this printer.
   ========================================================================== */

function PrintersPage() {
  const { settings, update } = useSettings();
  const printers = settings.printers;
  const peeks = usePrinterPeeks(printers, true);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [trial, setTrial] = useState(null); // null | "asking" | peek
  const host = cleanHost(address);
  const here = window.location.host;
  const duplicate = host && (host.toLowerCase() === here.toLowerCase() || printers.some((one) => one.host.toLowerCase() === host.toLowerCase()));
  const edit = (fn) => update((draft) => (draft.printers = cleanPrinters(fn(draft.printers.slice()))));
  const tryIt = async () => {
    setTrial("asking");
    setTrial(await peekPrinter(host));
  };
  const add = () => {
    const label = cleanPrinterName(name) || (trial && trial !== "asking" && trial.ok && trial.name) || "";
    edit((list) => list.concat({ id: "p" + Date.now().toString(36), name: label, host }));
    setName("");
    setAddress("");
    setTrial(null);
  };
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Your printers"), note: tx("Every printer has its own KlippEye. Add the others here: a tap on the name at the top lists them, and the overview shows them all at once. The list is the same on every device of this printer.") },
      h(
        "div",
        { className: "oui-list", "data-printers-list": printers.length },
        h("div", { className: "oui-row printer-row is-self" }, h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, printerName(settings.printer)), h("span", { className: "oui-row__meta" }, tx("This printer") + " · " + here)), h("span", { className: cx("oui-badge", "oui-badge--" + printerStateBadge(peeks.self).tone) }, printerStateBadge(peeks.self).text)),
        printers.map((one, index) =>
          h(
            "div",
            { key: one.id, className: "oui-row printer-row", "data-printer": one.host },
            h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, printerLabel(one, peeks[one.host])), h("span", { className: "oui-row__meta" }, printerStateBadge(peeks[one.host]).text + " · " + one.host)),
            h(MacroEditButton, { label: tx("Move up"), icon: h(Icons.ArrowUp, { size: 16 }), disabled: index === 0, onClick: () => edit((list) => (list.splice(index - 1, 0, list.splice(index, 1)[0]), list)) }),
            h(MacroEditButton, { label: tx("Move down"), icon: h(Icons.ArrowDown, { size: 16 }), disabled: index === printers.length - 1, onClick: () => edit((list) => (list.splice(index + 1, 0, list.splice(index, 1)[0]), list)) }),
            h(MacroEditButton, { label: tx("Remove") + " " + printerLabel(one, peeks[one.host]), icon: h(Icons.Trash, { size: 16 }), danger: true, onClick: () => edit((list) => list.filter((item) => item.id !== one.id)) }),
          ),
        ),
      ),
    ),
    printers.length < PRINTERS_MAX &&
      h(
        SettingsGroup,
        { title: tx("Add a printer"), note: tx("Its address, as you open its KlippEye (the port 8085 is added by itself): 192.168.1.50, voron.local…") },
        h("label", { className: "set-field" }, h("span", { className: "set-field__label" }, tx("Address")), h("input", { className: "oui-field set-field__input", value: address, placeholder: "192.168.1.50", inputMode: "url", autoCapitalize: "none", spellCheck: false, "data-printer-address": "1", onChange: (event) => (setAddress(event.target.value), setTrial(null)) })),
        h("label", { className: "set-field" }, h("span", { className: "set-field__label" }, tx("Name (optional)")), h("input", { className: "oui-field set-field__input", value: name, placeholder: (trial && trial !== "asking" && trial.ok && trial.name) || tx("The one it gives itself"), "data-printer-name": "1", onChange: (event) => setName(event.target.value) })),
        address && !host && h("p", { className: "set-field__error", role: "alert" }, tx("Not an address")),
        duplicate && h("p", { className: "set-field__error", role: "alert" }, tx("This printer is already there")),
        trial && trial !== "asking" && h("div", { className: cx("set-status", trial.ok ? "set-status--ok" : "set-status--warn"), "data-printer-trial": trial.ok ? "ok" : trial.error }, h("span", { className: "set-status__dot" }), trial.ok ? tx("KlippEye answers: {name} · {state}", { name: trial.name || host, state: printerStateBadge(trial).text }) : printerStateBadge(trial).text),
        h(
          "div",
          { className: "oui-btn-row" },
          h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-printer-try": "1", disabled: !host || duplicate || trial === "asking", onClick: tryIt }, trial === "asking" ? tx("Asking…") : tx("Try")),
          h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", "data-printer-add": "1", disabled: !host || duplicate, onClick: add }, h(Icons.Plus, { size: 16 }), tx("Add")),
        ),
      ),
  );
}

/** One line for the menu. */
function printersSummary(settings) {
  const count = settings.printers.length;
  return count === 0 ? tx("Only this one") : count === 1 ? tx("This one and 1 more") : tx("This one and {count} more", { count });
}
