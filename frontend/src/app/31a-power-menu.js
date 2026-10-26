/* ============================================================================
   31a · POWER MENU
   The header's power button, after Mainsail's: a sheet with
     · Klipper        restart / firmware restart (hidden while Moonraker has no Klipper);
     · Servizi        every service Moonraker manages (klipper, moonraker, crowsnest, ...), with its state;
                      restart (or start, when it is stopped) and stop;
     · Raspberry      restart and shut down the whole machine.
   Like Mainsail it asks first only while a job is printing (a restart would ruin it); the machine itself is
   always asked about, because a shutdown cannot be undone from the couch.
   The restarts of Klipper, Moonraker and the Raspberry run through the state panel (app/30-klipper-state.js),
   which shows the loading ring until everything is back.
   ========================================================================== */

/** After an action the list of services is read again after this long (the new state needs a moment). */
const SERVICES_REFRESH_MS = 2500;
const SERVICES_READ_TIMEOUT_MS = 8000;
/** A restarted camera service drops its stream: the camera view loads the page again after this long. */
const CAMERA_RELOAD_AFTER_RESTART_MS = 7000;

const capitalize = (text) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : text);
/** Friendly names of the services of KlippEye (the others keep their own name, capitalised). */
// (vzbot, vzbot-notifier: the names before the move to KlippEye, see scripts/passa-a-klippeye.sh)
const SERVICE_LABELS = { klippeye: "KlippEye (backend)", "klippeye-notifier": tx("KlippEye notifications"), vzbot: "KlippEye (backend)", "vzbot-notifier": tx("KlippEye notifications") };
const serviceLabel = (name) => SERVICE_LABELS[name] || capitalize(name);
const isCameraService = (name) => /crowsnest|webcam|camera|streamer|mjpg/i.test(name);
const SERVICE_STATE_TEXT = { active: txc("service", "running"), inactive: txc("service", "stopped"), failed: txc("service", "failed"), activating: txc("service", "starting"), deactivating: txc("service", "stopping") };

/** The services Moonraker manages, as [{ name, state, sub }] sorted by name (klipper_mcu is Klipper's own helper: not offered, as in Mainsail). */
async function loadServices() {
  const info = await moonraker.systemInfo({ timeout: SERVICES_READ_TIMEOUT_MS });
  const states = info.service_state || {};
  return (info.available_services || [])
    .filter((name) => name !== "klipper_mcu")
    .sort()
    .map((name) => ({ name, state: (states[name] || {}).active_state || "", sub: (states[name] || {}).sub_state || "" }));
}

const PRINT_WARNING = tx("A print is running and it will fail!");

/** What each confirmation says. `always`: asked even when nothing prints. `service`: the systemd name, for the ones that need their own words. */
function powerConfirmation(kind, label, service) {
  if (kind === "restart" && (service === "klippeye" || service === "vzbot")) {
    return { title: tx("Restart the backend?"), message: tx("The backend (dashboard, AI monitor, link to Moonraker) restarts: the page does not answer for a few seconds, then reloads by itself. A running print does not stop."), confirmLabel: tx("Restart") };
  }
  switch (kind) {
    case "klipper":
      return { title: tx("Restart Klipper?"), message: tx("Klipper restarts and the configuration is reloaded."), confirmLabel: tx("Restart") };
    case "firmware":
      return { title: tx("Restart the firmware?"), message: tx("Klipper and the firmware of the boards restart."), confirmLabel: tx("Restart") };
    case "restart":
      return { title: tx("Restart {service}?", { service: label }), message: tx("The service restarts."), confirmLabel: tx("Restart") };
    case "start":
      return { title: tx("Start {service}?", { service: label }), message: tx("The service starts."), confirmLabel: tx("Start") };
    case "stop":
      return { title: tx("Stop {service}?", { service: label }), message: tx("The service stops until you start it again."), confirmLabel: tx("Stop") };
    case "reboot":
      return { always: true, title: tx("Restart the Raspberry?"), message: tx("The Raspberry restarts: printer, camera and dashboard cannot be reached for about a minute."), confirmLabel: tx("Restart") };
    default:
      return { always: true, title: tx("Shut down the Raspberry?"), message: tx("The Raspberry shuts down and the dashboard stops answering. To turn it on again you have to unplug and plug the power back in."), confirmLabel: tx("Shut down") };
  }
}

/** `klipper` is useKlipperState(); `printing` is true while a job runs or is paused. */
function usePowerMenu({ klipper, printing }) {
  const [open, setOpen] = useState(false);
  const [services, setServices] = useState(null); // null: not read yet; otherwise { list, failed }
  const [pending, setPending] = useState(null); // the confirmation on screen: { kind, label, run }
  const openRef = useRef(false);
  openRef.current = open;

  const refresh = async () => {
    try {
      const list = await loadServices();
      setServices({ list, failed: false });
    } catch (error) {
      setServices((previous) => previous || { list: [], failed: true });
    }
  };

  const close = () => setOpen(false);

  /** Runs `run` now, or after the person agreed when a print is at stake (`always`: even when not). */
  const ask = (kind, label, run, service) => {
    const confirmation = powerConfirmation(kind, label, service);
    setOpen(false);
    if (printing || confirmation.always) setPending({ kind, label, service, run });
    else run();
  };

  const serviceAction = async (action, service) => {
    const label = serviceLabel(service);
    const ok = await klipper.serviceAction(action, service);
    if (ok === true) {
      toast.notice({ restart: tx("{service}: restart requested", { service: label }), start: tx("{service}: start requested", { service: label }), stop: tx("{service}: stop requested", { service: label }) }[action], 2400);
      if (isCameraService(service) && action !== "stop") setTimeout(requestCameraReload, CAMERA_RELOAD_AFTER_RESTART_MS);
    }
  };

  return {
    open,
    services,
    pending,
    printing,
    toggle: () => {
      if (!open) refresh();
      setOpen(!open);
    },
    close,
    restartKlipper: (firmware) => ask(firmware ? "firmware" : "klipper", "", () => klipper.restartKlipper(firmware)),
    service: (action, service) => ask(action, serviceLabel(service), () => serviceAction(action, service), service),
    rebootHost: () => ask("reboot", "", () => klipper.rebootHost()),
    shutdownHost: () => ask("shutdown", "", () => klipper.shutdownHost()),
    confirm: () => {
      const { run } = pending;
      setPending(null);
      run();
    },
    cancel: () => setPending(null),
  };
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */
function ServiceRow({ service, menu }) {
  const { name, state, sub } = service;
  const label = serviceLabel(name);
  const stopped = state === "inactive";
  const tone = state === "active" ? "on" : state === "failed" ? "bad" : "off";
  const stateText = (SERVICE_STATE_TEXT[state] || state || tx("unknown state")) + (sub && sub !== state ? " • " + sub : "");
  return h(
    "div",
    { className: "svc-row" },
    h("span", { className: "svc-row__dot svc-row__dot--" + tone, "aria-hidden": "true" }),
    h("span", { className: "svc-row__text" }, h("span", { className: "svc-row__name" }, label), h("span", { className: "svc-row__state" }, stateText)),
    h(
      "span",
      { className: "svc-row__actions" },
      stopped
        ? h("button", { className: "svc-row__btn", "aria-label": tx("Start ") + label, title: tx("Start"), onClick: () => menu.service("start", name) }, h(Icons.Play, { size: 18 }))
        : h("button", { className: "svc-row__btn", "aria-label": tx("Restart ") + label, title: tx("Restart"), onClick: () => menu.service("restart", name) }, h(Icons.RotateCw, { size: 18 })),
      // Moonraker cannot stop itself from here, nor the backend that serves this page (nothing would be left to start it again): the place stays, empty
      CUTS_CONNECTION.includes(name)
        ? h("span", { className: "svc-row__btn svc-row__btn--none", "aria-hidden": "true" })
        : h("button", { className: "svc-row__btn svc-row__btn--stop", "aria-label": tx("Stop ") + label, title: tx("Stop"), disabled: stopped, onClick: () => menu.service("stop", name) }, h(Icons.Stop, { size: 18 })),
    ),
  );
}

function PowerSheet({ menu, klipper }) {
  useBodyScrollLock(true);
  const { services } = menu;
  const view = klipper.view;
  const noKlipper = Boolean(view) && !view.restart && view.phase === "disconnected";
  const restarting = Boolean(view) && Boolean(view.restart);
  let serviceList;
  if (!services) serviceList = h("div", { className: "oui-notice" }, tx("Reading the services..."));
  else if (services.failed) serviceList = h("div", { className: "oui-notice" }, tx("List of services not available: Moonraker does not answer."));
  else if (services.list.length === 0) serviceList = h("div", { className: "oui-notice" }, tx("Moonraker manages no services."));
  else serviceList = h("div", { className: "oui-list" }, services.list.map((service) => h(ServiceRow, { key: service.name, service, menu })));

  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--power", onClick: (e) => e.target === e.currentTarget && menu.close() },
    h(
      "div",
      { className: "sheet-card sheet-card--column", role: "dialog", "aria-label": tx("Power and services") },
      h(
        "div",
        { className: "power-sheet__head" },
        h("div", { className: "dialog-head__icon" }, h(Icons.Power)),
        h("div", null, h("div", { className: "dialog-title" }, tx("Power and services")), h("div", { className: "dialog-sub" }, menu.printing ? tx("Printing: be careful") : tx("Klipper, services and Raspberry"))),
      ),
      h(
        "div",
        { className: "power-sheet__body" },
        !noKlipper &&
          h(
            React.Fragment,
            null,
            h("div", { className: "power-sheet__label" }, "Klipper"),
            h(
              "div",
              { className: "oui-list" },
              h(FileActionRow, { icon: h(Icons.RotateCw), title: "Klipper restart", subtitle: tx("Reload the configuration and restart Klipper"), disabled: restarting, onClick: () => menu.restartKlipper(false) }),
              h(FileActionRow, { icon: h(Icons.Chip), title: "Firmware restart", subtitle: tx("Also restart the firmware of the boards"), disabled: restarting, onClick: () => menu.restartKlipper(true) }),
            ),
          ),
        h("div", { className: "power-sheet__label" }, tx("Services")),
        serviceList,
        h("div", { className: "power-sheet__label" }, "Raspberry"),
        h(
          "div",
          { className: "oui-list" },
          h(FileActionRow, { icon: h(Icons.RotateCw), title: tx("Restart the Raspberry"), subtitle: tx("Turns the printer's computer off and on again"), disabled: restarting, onClick: menu.rebootHost }),
          h(FileActionRow, { icon: h(Icons.Power), title: tx("Shut down the Raspberry"), subtitle: tx("To turn it on again, unplug and plug the power back in"), danger: true, disabled: restarting, onClick: menu.shutdownHost }),
        ),
      ),
      h("div", { className: "sheet-footer" }, h("button", { className: "oui-btn", onClick: menu.close }, tx("Close"))),
    ),
  );
}

/** The sheet and its confirmation, driven by usePowerMenu. */
function PowerMenuDialogs({ menu, klipper }) {
  const { pending } = menu;
  const confirmation = pending ? powerConfirmation(pending.kind, pending.label, pending.service) : null;
  return h(
    React.Fragment,
    null,
    h(Presence, null, menu.open && h(PowerSheet, { menu, klipper })),
    h(ConfirmDialog, {
      open: Boolean(pending),
      tone: "danger",
      icon: h(Icons.Power),
      title: confirmation ? confirmation.title : "",
      subtitle: menu.printing ? PRINT_WARNING : "",
      message: confirmation ? confirmation.message : "",
      confirmLabel: confirmation ? confirmation.confirmLabel : "",
      onConfirm: menu.confirm,
      onCancel: menu.cancel,
    }),
  );
}
