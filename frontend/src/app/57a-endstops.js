/* ============================================================================
   57a · ENDSTOPS & PROBE
   Collapsible section at the foot of the Calibrazioni card: the state of every
   endstop (Klipper's QUERY_ENDSTOPS) and of the Z probe (QUERY_PROBE), the way
   Mainsail's "Endstops" panel shows them. Nothing is read when the page or the
   section opens: the sensors are queried only when the Aggiorna button is pressed.
   Querying moves the MCU's attention away from the printing queue, so it is off
   while a job runs.
   ========================================================================== */

const endstopsApi = {
  /** { x: "open" | "TRIGGERED", y: ..., z: ... } of every endstop Klipper has registered. */
  async query() {
    const json = await fetchJson("/printer/query_endstops/status");
    if (json.error) throw new Error((json.error && json.error.message) || String(json.error));
    const result = json.result || {};
    return Object.keys(result)
      .filter((name) => result[name] === "open" || result[name] === "TRIGGERED")
      .sort((a, b) => a.localeCompare(b))
      .map((name) => ({ name, triggered: result[name] === "TRIGGERED" }));
  },
  /** QUERY_PROBE, then what Klipper remembers of it: { name, triggered }, or null when there is no probe. */
  async probe() {
    await sendGcode("QUERY_PROBE").catch(noop);
    const status = await moonraker.queryObjects("probe").catch(() => ({}));
    const probe = status.probe;
    return probe && "last_query" in probe ? { name: probe.name || "probe", triggered: Boolean(probe.last_query) } : null;
  },
};

function useEndstops({ probe: hasProbe }) {
  const [state, setState] = useState({ endstops: null, probe: null, loading: false, error: null, updatedAt: "" });

  const refresh = async () => {
    setState((previous) => ({ ...previous, loading: true, error: null }));
    try {
      const endstops = await endstopsApi.query();
      const probe = hasProbe ? await endstopsApi.probe().catch(() => null) : null;
      setState({ endstops, probe, loading: false, error: null, updatedAt: localTimeString() });
    } catch (error) {
      setState((previous) => ({ ...previous, loading: false, error: error.message || "Klipper non risponde" }));
    }
  };

  return { ...state, refresh };
}

/** One endstop (or the probe): its name and whether it is open or triggered. */
function EndstopRow({ icon, name, detail, triggered }) {
  return h(
    "div",
    { className: "oui-row" },
    h("span", { className: "oui-row__icon" }, icon),
    h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, name), h("span", { className: "oui-row__meta" }, detail)),
    h("span", { className: cx("oui-badge", triggered ? "oui-badge--danger" : "oui-badge--ok") }, h("span", { className: "oui-dot" }), triggered ? "Attivato" : "Aperto"),
  );
}

/** `capabilities` says whether there is a probe to ask; a `lockReason` (printLockReason) switches the queries off. */
function EndstopsSection({ capabilities, lockReason }) {
  const [open, setOpen] = useState(() => storage.get(STORAGE_KEYS.endstopsOpen) === "1");
  const state = useEndstops(capabilities);

  const toggle = () => {
    storage.set(STORAGE_KEYS.endstopsOpen, open ? "0" : "1");
    setOpen(!open);
  };

  let body = null;
  if (open) {
    if (lockReason) body = h("div", { className: "oui-notice" }, lockReason + ".");
    else {
      const { endstops, probe, loading, error, updatedAt } = state;
      let content;
      if (error && !endstops) content = h("div", { className: "oui-tile oui-tile--danger oui-notice" }, "Impossibile leggere gli endstop: " + error);
      else if (!endstops) content = h("div", { className: "oui-notice" }, loading ? "Lettura in corso..." : "Premi Aggiorna per leggere lo stato di endstop e probe.");
      else if (endstops.length === 0 && !probe) content = h("div", { className: "oui-notice" }, "Klipper non ha endstop registrati.");
      else
        content = h(
          "div",
          { className: "oui-list" },
          endstops.map((endstop) => h(EndstopRow, { key: endstop.name, icon: h(Icons.Endstop), name: endstop.name.toUpperCase(), detail: "Endstop", triggered: endstop.triggered })),
          probe && h(EndstopRow, { key: "probe", icon: h(Icons.Probe), name: "Probe", detail: probe.name, triggered: probe.triggered }),
        );
      // the caption says how old what is shown is (nothing is read on its own)
      const caption = !endstops ? (error ? "Lettura non riuscita" : "Non ancora letti") : error ? "Ultimo aggiornamento non riuscito: " + error : "Aggiornato alle " + updatedAt;
      body = h(
        React.Fragment,
        null,
        content,
        h(
          "div",
          { className: "endstops-foot" },
          h("span", { className: "oui-caption" }, caption),
          h("button", { className: "oui-btn oui-btn--sm", disabled: loading, onClick: state.refresh }, h(Icons.Refresh, { size: 16 }), "Aggiorna"),
        ),
      );
    }
  }

  return h(
    "div",
    { className: "endstops" },
    h(
      "button",
      { className: "endstops-head", "aria-expanded": open, onClick: toggle },
      h("span", { className: "endstops-head__icon" }, h(Icons.Endstop, { size: 20 })),
      h("span", { className: "endstops-head__title" }, "Endstop e probe"),
      h("span", { className: cx("menu-chevron", open && "is-open") }, h(Icons.Chevron, { size: 18 })),
    ),
    h(Collapse, { open }, body && h("div", { className: "endstops-body" }, body)),
  );
}
