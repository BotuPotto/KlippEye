/* ============================================================================
   31b · MORE PRINTERS (1.61)
   Each printer has its own KlippEye (on its own Raspberry). The list of the
   others is in the settings (Settings → Your printers, shared by every device
   of this printer); from here:
     · the switcher: a tap on the logo and name in the top bar lists the
       printers, with their state, and opens another one (its address, port
       8085); the overview shows them all at once, with progress and
       temperatures;
     · their state comes through this printer's KlippEye service
       (/api/printers/peek, which asks the other one's /api/printers/self):
       a page may not read another address by itself;
     · arriving from another printer (?from=…): the page offers to add it to
       the list, so the lists fill in by themselves.
   ========================================================================== */

const PRINTER_PEEK_MS = 5000;
const KLIPPEYE_PORT = 8085;

/** The address a printer's dashboard opens at: http://host:8085/ (the port given in the host wins). */
const printerBaseUrl = (host) => "http://" + host + (/:\d+$/.test(host) ? "" : ":" + KLIPPEYE_PORT);

/** The state of one printer, asked through this KlippEye; `host` null: this printer itself. */
async function peekPrinter(host) {
  try {
    const json = await fetchJson(host ? "/api/printers/peek?host=" + encodeURIComponent(host) : "/api/printers/self", { timeout: 6000 });
    return json || { ok: false, error: "unreachable" };
  } catch (error) {
    return { ok: false, error: "unreachable" };
  }
}

/** The state of this printer and of the others, every few seconds while `active`: { self, [host]: peek }. */
function usePrinterPeeks(printers, active) {
  const [peeks, setPeeks] = useState({});
  const hosts = printers.map((one) => one.host).join("|");
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const refresh = async () => {
      const list = [null].concat(hosts ? hosts.split("|") : []);
      const answers = await Promise.all(list.map(peekPrinter));
      if (!cancelled) setPeeks(Object.fromEntries(list.map((host, index) => [host || "self", answers[index]])));
    };
    const stop = startPolling(refresh, PRINTER_PEEK_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [hosts, active]);
  return peeks;
}

const PRINTER_STATE_TEXT = () => ({
  printing: tx("Printing"),
  paused: tx("Paused"),
  complete: tx("Finished"),
  cancelled: tx("Cancelled"),
  error: tx("Error"),
  standby: tx("Ready"),
  offline: tx("Klipper off"),
});
const PRINTER_PEEK_ERRORS = () => ({
  unreachable: tx("Not reachable"),
  locked: tx("Protected by a password"),
  old: tx("Its KlippEye is older: update it"),
  not_klippeye: tx("No KlippEye at this address"),
  outside: tx("Not an address of your network"),
  address: tx("Not an address"),
});
const PRINTER_STATE_TONE = { printing: "info", paused: "warn", complete: "ok", cancelled: "warn", error: "danger", standby: "ok", offline: "warn" };

/** The words and colour of a printer's state (or of why it cannot be seen). */
function printerStateBadge(peek) {
  if (!peek) return { text: tx("Asking…"), tone: "neutral" };
  if (!peek.ok) return { text: PRINTER_PEEK_ERRORS()[peek.error] || tx("Not reachable"), tone: "danger" };
  const text = PRINTER_STATE_TEXT()[peek.state] || peek.state;
  return { text: peek.state === "printing" || peek.state === "paused" ? text + " · " + Math.round(peek.progress * 100) + "%" : text, tone: PRINTER_STATE_TONE[peek.state] || "neutral" };
}

/** The name to show: the one written in the list, else the one the printer gives itself, else its address. */
const printerLabel = (printer, peek) => printer.name || (peek && peek.ok && peek.name) || printer.host;

/** Opens another printer's dashboard: the app keeps it inside (when it can), the browser goes to its address. */
function openPrinter(printer, here) {
  const from = "?from=" + encodeURIComponent(window.location.host) + "&fromName=" + encodeURIComponent(here || "");
  const bridge = nativeBridge();
  if (bridge && typeof bridge.switchPrinter === "function") {
    bridge.switchPrinter(JSON.stringify({ host: printer.host, name: printer.name || "" }));
    return;
  }
  if (IN_APP_WEBVIEW) toast.notice(tx("It opens in the browser: update the KlippEye app to open it here"), 4000); // an app before 1.6.0
  window.location.href = printerBaseUrl(printer.host) + "/" + from;
}

/** The overview and the arrival question are layers over the page: one store, opened from the switcher. */
const printersOverviewStore = (() => {
  const listeners = new Set();
  let open = false;
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => open,
    set(value) {
      open = value;
      listeners.forEach((fn) => fn());
    },
  };
})();

/** The logo and name in the top bar: a tap lists the printers (this one first). */
function PrinterSwitcher({ printer, onManage }) {
  const { settings } = useSettings();
  const menu = useDropdown();
  const printers = settings.printers;
  const peeks = usePrinterPeeks(printers, menu.open);
  return h(
    React.Fragment,
    null,
    h(
      "button",
      { type: "button", ref: menu.anchorRef, className: cx("app-header__switch", menu.open && "is-open"), "aria-haspopup": "menu", "aria-expanded": menu.open, "aria-label": tx("Your printers") + ": " + printerName(printer), "data-printers": printers.length, onClick: menu.toggle },
      h(PrinterLogo, { id: printer.brand, className: "app-header__logo" }),
      isKlippEyeWordmark(printer) ? h("span", { className: "app-header__name" }, "Klipp", h("span", { className: "app-header__eye" }, "Eye")) : h("span", { className: "app-header__name", "data-printer": printer.brand }, printerName(printer)),
      h("span", { className: "app-header__switch-mark", "aria-hidden": "true" }, h(Icons.Chevron, { size: 14 })),
    ),
    h(
      DropdownMenu,
      { menu },
      h(MenuLabel, null, tx("Your printers")),
      h(
        "button",
        { type: "button", className: "oui-menu__item", role: "menuitemradio", "aria-checked": true, "data-printer-row": "self", onClick: menu.close },
        h("span", { className: "oui-menu__icon" }, h(Icons.Check, { size: 18 })),
        h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, printerName(printer)), h("span", { className: "oui-menu__sub" }, tx("This printer") + (peeks.self ? " · " + printerStateBadge(peeks.self).text : ""))),
      ),
      printers.map((one) =>
        h(
          "button",
          { key: one.id, type: "button", className: "oui-menu__item", role: "menuitemradio", "aria-checked": false, "data-printer-row": one.host, onClick: () => (menu.close(), openPrinter(one, printerName(printer))) },
          h("span", { className: cx("oui-menu__icon printer-dot", "printer-dot--" + printerStateBadge(peeks[one.host]).tone) }, h(PrinterLogo, { id: (peeks[one.host] && peeks[one.host].brand) || "klippeye", className: "printer-dot__logo" })),
          h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, printerLabel(one, peeks[one.host])), h("span", { className: "oui-menu__sub" }, printerStateBadge(peeks[one.host]).text + " · " + one.host)),
        ),
      ),
      printers.length > 0 && h(MenuItem, { icon: h(Icons.Layers, { size: 18 }), title: txc("printers", "Overview"), subtitle: tx("Every printer at once"), onClick: () => (menu.close(), printersOverviewStore.set(true)) }),
      h(MenuItem, { icon: h(Icons.Plus, { size: 18 }), title: printers.length ? tx("Manage the printers") : tx("Add a printer"), subtitle: printers.length ? null : tx("Another printer with KlippEye on your network"), onClick: () => (menu.close(), onManage()) }),
    ),
  );
}

/** One printer of the overview: logo, name, state, progress, file, temperatures. */
function PrinterTile({ label, host, peek, self, onOpen }) {
  const badge = printerStateBadge(peek);
  const busy = peek && peek.ok && (peek.state === "printing" || peek.state === "paused");
  const temp = (pair, name) => pair && name + " " + Math.round(pair[0]) + "°" + (pair[1] ? "/" + Math.round(pair[1]) + "°" : "");
  return h(
    "button",
    { type: "button", className: cx("printer-tile", self && "is-self"), "data-printer-tile": host || "self", disabled: self, onClick: onOpen },
    h(
      "span",
      { className: "printer-tile__head" },
      h("span", { className: "printer-tile__logo" }, h(PrinterLogo, { id: (peek && peek.ok && peek.brand) || "klippeye", className: "printer-tile__img" })),
      h("span", { className: "printer-tile__name" }, label, self && h("span", { className: "printer-tile__self" }, tx("This printer"))),
      h("span", { className: cx("oui-badge", "oui-badge--" + badge.tone) }, badge.text),
    ),
    busy && h("span", { className: "printer-tile__bar" }, h("span", { className: "printer-tile__fill", style: { width: Math.round(peek.progress * 100) + "%" } })),
    peek && peek.ok && peek.filename && h("span", { className: "printer-tile__file" }, peek.filename),
    peek && peek.ok && h("span", { className: "printer-tile__temps" }, [temp(peek.extruder, tx("Nozzle")), temp(peek.bed, tx("Bed"))].filter(Boolean).join(" · ")),
    host && h("span", { className: "printer-tile__host" }, host),
  );
}

function PrintersOverview({ onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const { settings } = useSettings();
  const printers = settings.printers;
  const peeks = usePrinterPeeks(printers, true);
  const here = printerName(settings.printer);
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--details sheet-overlay--printers", onClick: (event) => event.target === event.currentTarget && onClose() },
    h(
      "div",
      { className: "sheet-card sheet-card--column printers-overview", role: "dialog", "aria-label": txc("printers", "Overview") },
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title" }, tx("Your printers")), h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕")),
      h(
        "div",
        { className: "file-details__body printers-grid" },
        h(PrinterTile, { label: here, host: null, peek: peeks.self, self: true }),
        printers.map((one) => h(PrinterTile, { key: one.id, label: printerLabel(one, peeks[one.host]), host: one.host, peek: peeks[one.host], onOpen: () => openPrinter(one, here) })),
      ),
    ),
  );
}

function PrintersOverviewLayer() {
  const open = useSyncExternalStore(printersOverviewStore.subscribe, printersOverviewStore.snapshot);
  return h(Presence, null, open && h(PrintersOverview, { onClose: () => printersOverviewStore.set(false) }));
}

/** Read once: the printer this page was opened from (?from=host&fromName=…), then the address is cleaned. */
const PRINTER_ARRIVAL = (() => {
  try {
    const params = new URLSearchParams(window.location.search);
    const host = cleanHost(params.get("from") || "");
    const name = cleanPrinterName(params.get("fromName") || "") || "";
    if (!params.has("from")) return null;
    params.delete("from");
    params.delete("fromName");
    const rest = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (rest ? "?" + rest : "") + window.location.hash);
    return host && host.toLowerCase() !== window.location.host.toLowerCase() ? { host, name } : null;
  } catch (error) {
    return null;
  }
})();

/** Arrived from another printer that is not in the list: «Add it to your printers?». */
function PrinterArrivalInvite() {
  const { settings, update } = useSettings();
  const [arrival, setArrival] = useState(PRINTER_ARRIVAL);
  if (!arrival || settings.printers.some((one) => one.host.toLowerCase() === arrival.host.toLowerCase()) || settings.printers.length >= PRINTERS_MAX) return null;
  const add = () => {
    update((draft) => {
      draft.printers = cleanPrinters(draft.printers.concat({ id: "p" + Date.now().toString(36), name: arrival.name, host: arrival.host }));
    });
    toast.notice(tx("Added to your printers: {name}", { name: arrival.name || arrival.host }));
    setArrival(null);
  };
  return h(
    "div",
    { className: "nt-invite printer-arrival", role: "status", "data-printer-arrival": arrival.host },
    h("span", { className: "nt-invite__icon" }, h(Icons.Cube, { size: 20 })),
    h("span", { className: "nt-invite__text" }, tx("You came from «{name}»: add it to your printers?", { name: arrival.name || arrival.host })),
    h("span", { className: "nt-invite__buttons" }, h("button", { type: "button", className: "oui-btn oui-btn--sm", onClick: () => setArrival(null) }, tx("No")), h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", onClick: add }, tx("Add"))),
  );
}
