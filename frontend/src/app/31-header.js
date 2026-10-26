/* ============================================================================
   31 · APP HEADER
   Fixed top bar: the settings menu button, logo and name (KlippEye, or the printer chosen in the settings) on the left, the power menu, SAVE_CONFIG and
   EMERGENCY STOP on the right. The small round "AI" badge next to the name shows the verdict of
   the AI print monitor (see 55-ai-monitor.js).
   ========================================================================== */

/**
 * `wide` (a screen wide enough for the desktop layout) puts the page tabs in the bar, between the brand and
 * the actions: { tabs: [{ id, label }], active, onSelect, state: { text, tone } }.
 */
function AppHeader({ onSettings, onPower, onSaveConfig, onEmergencyStop, saveBusy, aiBadge, wide }) {
  const { settings } = useSettings();
  const printer = settings.printer;
  return h(
    "header",
    { className: cx("app-header", wide && "app-header--wide") },
    h(
      "div",
      { className: "app-header__bar" },
      h(
        "div",
        { className: "app-header__brand" },
        h("button", { onClick: onSettings, className: "header-btn header-btn--menu", "aria-label": "Impostazioni", title: "Impostazioni della dashboard" }, h(Icons.Menu)),
        h(PrinterLogo, { id: printer.brand, className: "app-header__logo" }),
        isKlippEyeWordmark(printer)
          ? h("span", { className: "app-header__name" }, "Klipp", h("span", { className: "app-header__eye" }, "Eye"))
          : h("span", { className: "app-header__name", "data-printer": printer.brand }, printerName(printer)),
        h(AiHeaderBadge, { badge: aiBadge }),
      ),
      wide && h(HeaderTabs, wide),
      h(
        "div",
        { className: "app-header__actions" },
        wide && wide.state && h("span", { className: cx("oui-badge header-state", "oui-badge--" + wide.state.tone) }, h("span", { className: "oui-dot" }), wide.state.text),
        h("button", { onClick: onPower, className: "header-btn", "aria-label": "Alimentazione e servizi", title: "Riavvia Klipper, servizi e Raspberry" }, h(Icons.Power)),
        h(
          "button",
          {
            onClick: onSaveConfig,
            className: cx("header-btn", saveBusy && "is-busy"),
            "aria-label": "Save config",
            title: "SAVE_CONFIG - Salva configurazione e riavvia",
          },
          h(Icons.Save),
        ),
        h("button", { onClick: onEmergencyStop, className: "header-btn header-btn--danger", "aria-label": "Emergency stop" }, h(Icons.Emergency)),
      ),
    ),
  );
}

/** The page tabs of the desktop layout: a glass pill in the middle of the top bar. */
function HeaderTabs({ tabs, active, onSelect }) {
  const navRef = useRef(null);
  const [marker, setMarker] = useState(null); // { x, w }: where the blue marker sits (the active tab); null until measured
  const measure = () => {
    const tab = navRef.current && navRef.current.querySelector(".is-active");
    setMarker(tab ? { x: tab.offsetLeft, w: tab.offsetWidth } : null);
  };
  useLayoutEffect(measure, [active, tabs]);
  useEffect(() => {
    if (typeof ResizeObserver !== "function") return undefined;
    const observer = new ResizeObserver(measure); // fonts arriving late, a narrower window: the tabs change width
    observer.observe(navRef.current);
    return () => observer.disconnect();
  }, []);
  return h(
    "nav",
    { className: "header-tabs", "aria-label": "Pagine", ref: navRef },
    marker && h("span", { className: "header-tabs__pill", "aria-hidden": "true", style: { width: marker.w + "px", transform: "translateX(" + marker.x + "px)" } }),
    tabs.map((tab) => h("button", { key: tab.id, className: cx("header-tabs__tab", active === tab.id && "is-active"), "data-tab": tab.id, onClick: () => onSelect(tab.id) }, tab.label)),
  );
}
