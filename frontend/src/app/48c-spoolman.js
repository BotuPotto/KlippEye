/* ============================================================================
   48c · FILAMENT SPOOLS: SPOOLMAN (1.47, roadmap 6d part 6)
   Moonraker's [spoolman] (Spoolman keeps the spools; Moonraker tells it how
   much filament each print uses):
     · the Spool card: the spool in use — colour, name, material, maker, how
       much is left (weight, length, a bar) — or none;
     · "Change spool": the spools from Spoolman (newest used first), searched;
       a tap makes one the active spool; "Remove" leaves none in use.
   Only with the component in Moonraker; Spoolman unreachable: the card says so.
   ========================================================================== */

const SPOOLMAN_POLL_MS = 10000;

const spoolmanApi = {
  async status() {
    const json = await fetchJson("/server/spoolman/status");
    return (json && json.result) || {};
  },
  async setActive(id) {
    const response = await fetchFresh("/server/spoolman/spool_id", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(id === null ? {} : { spool_id: id }) });
    if (!response.ok) throw new Error(await responseError(response));
  },
  /** A request to Spoolman itself, through Moonraker (its v2 answer: { response, error }). */
  async proxy(path, query) {
    const response = await fetchFresh("/server/spoolman/proxy", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ request_method: "GET", path, query: query || undefined, use_v2_response: true }) });
    if (!response.ok) throw new Error(await responseError(response));
    const result = ((await response.json()) || {}).result || {};
    if (result.error) throw new Error(result.error.message || String(result.error));
    return result.response;
  },
  spool: (id) => spoolmanApi.proxy("/v1/spool/" + id),
  spools: () => spoolmanApi.proxy("/v1/spool", "allow_archived=false"),
};

/** "#rrggbb" of a spool's filament (Spoolman keeps it without #), or null. */
const spoolColor = (spool) => {
  const hex = spool && spool.filament && (spool.filament.color_hex || (spool.filament.multi_color_hexes || "").split(",")[0]);
  return hex && /^[0-9a-f]{6}([0-9a-f]{2})?$/i.test(hex) ? "#" + hex.slice(0, 6) : null;
};
const spoolName = (spool) => {
  const filament = (spool && spool.filament) || {};
  return [filament.vendor && filament.vendor.name, filament.name].filter(Boolean).join(" ") || tx("Spool {id}", { id: spool.id });
};
/** What is left, as a fraction of the full spool (null when Spoolman does not know). */
function spoolLeft(spool) {
  const full = Number(spool.initial_weight) || Number((spool.filament || {}).weight) || 0;
  const left = Number(spool.remaining_weight);
  return full > 0 && isFinite(left) ? Math.max(0, Math.min(1, left / full)) : null;
}
const grams = (value) => (isFinite(Number(value)) ? (Number(value) >= 1000 ? (Number(value) / 1000).toFixed(2) + " kg" : Math.round(Number(value)) + " g") : "--");

function useSpoolman() {
  const [state, setState] = useState({ available: null, connected: true, activeId: null, active: null, error: null });
  const refreshRef = useRef(null);
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      if (!(await moonrakerComponents()).has("spoolman")) return !cancelled && setState((previous) => ({ ...previous, available: false }));
      try {
        const status = await spoolmanApi.status();
        const activeId = status.spool_id === undefined || status.spool_id === null ? null : Number(status.spool_id);
        let active = null;
        if (activeId !== null && status.spoolman_connected !== false) active = await spoolmanApi.spool(activeId).catch(() => null);
        if (!cancelled) setState({ available: true, connected: status.spoolman_connected !== false, activeId, active, error: null });
      } catch (error) {
        if (!cancelled) setState((previous) => ({ ...previous, available: true, error: error.message || tx("Error") }));
      }
    };
    refreshRef.current = refresh;
    const stop = startPolling(refresh, SPOOLMAN_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, []);
  return {
    ...state,
    async choose(spool) {
      try {
        await spoolmanApi.setActive(spool ? spool.id : null);
        setState((previous) => ({ ...previous, activeId: spool ? spool.id : null, active: spool }));
        toast.notice(spool ? tx("Spool in use: {name}", { name: spoolName(spool) }) : tx("No spool in use"));
      } catch (error) {
        toast.action("Spoolman: " + (error.message || error));
      }
      refreshRef.current && refreshRef.current();
    },
  };
}

function SpoolSwatch({ spool, size = 40 }) {
  const color = spoolColor(spool);
  return h("span", { className: "spool-swatch", style: { width: size + "px", height: size + "px", "--spool-color": color || "transparent" }, "aria-hidden": "true" }, h("span", { className: "spool-swatch__hole" }));
}

function SpoolFacts({ spool }) {
  const left = spoolLeft(spool);
  const filament = spool.filament || {};
  return h(
    "div",
    { className: "spool-facts" },
    h("div", { className: "spool-facts__name" }, spoolName(spool), h("span", { className: "spool-facts__id" }, "#" + spool.id)),
    h("div", { className: "spool-facts__meta" }, [filament.material, filament.diameter ? filament.diameter + " mm" : "", spool.location].filter(Boolean).join(" · ")),
    left !== null && h("div", { className: "spool-bar", role: "img", "aria-label": tx("{percent}% left", { percent: Math.round(left * 100) }) }, h("span", { className: "spool-bar__fill", style: { width: left * 100 + "%", background: spoolColor(spool) || "var(--oui-accent)" } })),
    h("div", { className: "spool-facts__left" }, h("b", null, grams(spool.remaining_weight)), " " + tx("left"), spool.remaining_length > 0 ? " · " + formatFilamentLength(spool.remaining_length) : "", left !== null ? " · " + Math.round(left * 100) + "%" : ""),
  );
}

function SpoolPicker({ activeId, onChoose, onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const [spools, setSpools] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  useEffect(() => {
    spoolmanApi
      .spools()
      .then((list) => setSpools((Array.isArray(list) ? list : []).slice().sort((a, b) => String(b.last_used || "").localeCompare(String(a.last_used || "")) || b.id - a.id)))
      .catch((failure) => setError(failure.message || tx("Error")));
  }, []);
  const needle = query.trim().toLowerCase();
  const shown = (spools || []).filter((spool) => !needle || [spoolName(spool), (spool.filament || {}).material, spool.location, "#" + spool.id].filter(Boolean).join(" ").toLowerCase().includes(needle));
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--details", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "sheet-card sheet-card--column spool-picker", role: "dialog", "aria-label": tx("Change spool") },
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title" }, tx("Change spool")), h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕")),
      h(
        "div",
        { className: "file-details__body" },
        h("div", { className: "files-search" }, h(Icons.Search, { size: 16 }), h("input", { type: "search", className: "oui-field files-search__input spool-search", value: query, placeholder: tx("Search spools..."), "aria-label": tx("Search spools..."), onChange: (event) => setQuery(event.target.value) })),
        error ? h("div", { className: "oui-caption" }, error) : spools === null ? h("div", { className: "oui-caption" }, tx("Loading...")) : shown.length === 0 ? h("div", { className: "oui-caption" }, tx("No spool")) : null,
        h(
          "div",
          { className: "spool-list" },
          shown.map((spool) =>
            h(
              "button",
              { key: spool.id, type: "button", className: cx("spool-choice", spool.id === activeId && "is-active"), "data-spool": spool.id, onClick: () => (onChoose(spool), onClose()) },
              h(SpoolSwatch, { spool, size: 36 }),
              h(SpoolFacts, { spool }),
              spool.id === activeId && h("span", { className: "oui-badge oui-badge--info spool-choice__badge" }, tx("In use")),
            ),
          ),
        ),
      ),
      h("div", { className: "sheet-footer" }, activeId !== null && h("button", { className: "oui-btn spool-clear", onClick: () => (onChoose(null), onClose()) }, tx("No spool")), h("button", { className: "oui-btn", onClick: onClose }, tx("Close"))),
    ),
  );
}

function SpoolCard() {
  const spoolman = useSpoolman();
  const [picking, setPicking] = useState(false);
  if (!spoolman.available) return null;
  let body;
  if (!spoolman.connected) body = h("div", { className: "oui-tile oui-tile--warn spool-offline" }, tx("Moonraker cannot reach Spoolman: check that it is running and the address in [spoolman]."));
  else if (spoolman.activeId === null) body = h("div", { className: "spool-none" }, h(SpoolSwatch, { spool: null }), h("div", { className: "spool-none__text" }, tx("No spool in use: the filament of the prints is not counted on any spool.")));
  else if (!spoolman.active) body = h("div", { className: "oui-caption" }, tx("Loading..."));
  else body = h("div", { className: "spool-active" }, h(SpoolSwatch, { spool: spoolman.active, size: 52 }), h(SpoolFacts, { spool: spoolman.active }));
  return h(
    React.Fragment,
    null,
    h(
      Card,
      { cardId: "spool", className: "spool-card" },
      h(CardHeader, { title: tx("Spool") }, spoolman.connected && h("button", { type: "button", className: "oui-btn oui-btn--sm spool-change", onClick: () => setPicking(true) }, h(Icons.Spool, { size: 16 }), tx("Change spool"))),
      body,
    ),
    h(Presence, null, picking && h(SpoolPicker, { activeId: spoolman.activeId, onChoose: spoolman.choose, onClose: () => setPicking(false) })),
  );
}
