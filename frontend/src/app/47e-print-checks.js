/* ============================================================================
   47e · CHECKS BEFORE A PRINT (1.83)
   In the «Confirm print» dialog, what can be read before starting and would
   spoil the print: Klipper not ready, a print taller than the printer, a file
   sliced for another nozzle, temperatures over the printer's limits, a layer
   too thick for the nozzle, changes still waiting for SAVE_CONFIG. Nothing is
   blocked: the person decides. When all is well, one line says so.
   ========================================================================== */

const LAYER_TO_NOZZLE_MAX = 0.8; // a layer thicker than 80% of the nozzle prints badly
const checkNumber = (value, digits) => Number(value.toFixed(digits)).toLocaleString(LOCALE);

/**
 * The warnings for a file: [{ id, text }]. `meta`: Moonraker's metadata of the file; `caps`: the printer's capabilities
 * (13-capabilities.js); `state`: { klippy, pending } (Klipper's state, SAVE_CONFIG pending).
 */
function printChecks(meta, caps, state) {
  const out = [];
  const m = meta || {};
  const c = caps || {};
  const s = state || {};
  if (s.klippy && s.klippy !== "ready") out.push({ id: "klippy", text: tx("Klipper is not ready ({state}): the print would not start.", { state: s.klippy }) });
  const zMax = c.axisLimits && c.axisLimits.Z ? c.axisLimits.Z[1] : null;
  const height = Number(m.object_height);
  if (zMax && height > zMax) out.push({ id: "height", text: tx("The print is {height} mm tall, the printer reaches {max} mm.", { height: checkNumber(height, 1), max: checkNumber(zMax, 0) }) });
  const nozzle = Number(m.nozzle_diameter);
  if (c.nozzleDiameter && nozzle > 0 && Math.abs(nozzle - c.nozzleDiameter) > 0.01)
    out.push({ id: "nozzle", text: tx("Sliced for a {file} mm nozzle, printer.cfg says {printer} mm.", { file: checkNumber(nozzle, 2), printer: checkNumber(c.nozzleDiameter, 2) }) });
  const layer = Number(m.layer_height);
  const realNozzle = c.nozzleDiameter || nozzle;
  if (realNozzle > 0 && layer > realNozzle * LAYER_TO_NOZZLE_MAX) out.push({ id: "layer", text: tx("Layers of {layer} mm are thick for a {nozzle} mm nozzle (up to {max} mm).", { layer: checkNumber(layer, 2), nozzle: checkNumber(realNozzle, 2), max: checkNumber(realNozzle * LAYER_TO_NOZZLE_MAX, 2) }) });
  const hotend = Math.max(Number(m.first_layer_extr_temp) || 0, Number(m.extruder_temp) || 0);
  if (c.maxTemp && hotend > c.maxTemp.hotend) out.push({ id: "hotend", text: tx("The file heats the nozzle to {temp}°, the printer allows {max}°: Klipper would stop.", { temp: Math.round(hotend), max: Math.round(c.maxTemp.hotend) }) });
  const bed = Math.max(Number(m.first_layer_bed_temp) || 0, Number(m.bed_temp) || 0);
  if (c.maxTemp && bed > c.maxTemp.bed) out.push({ id: "bed", text: tx("The file heats the bed to {temp}°, the printer allows {max}°: Klipper would stop.", { temp: Math.round(bed), max: Math.round(c.maxTemp.bed) }) });
  if (s.pending) out.push({ id: "pending", text: tx("Some settings wait for SAVE_CONFIG: saving them restarts Klipper, so do it before the print, not during it.") });
  return out;
}

function PrintChecks({ path }) {
  const caps = usePrinterCapabilities();
  const [data, setData] = useState(null); // { meta, state }
  useEffect(() => {
    let cancelled = false;
    if (!path) return undefined;
    (async () => {
      const [meta, status] = await Promise.all([
        fetchJson("/server/files/metadata?filename=" + encodeURIComponent(path)).then((json) => (json && json.result) || {}).catch(() => ({})),
        moonraker.queryObjects("webhooks=state&configfile=save_config_pending", { timeout: 4000 }).catch(() => ({})),
      ]);
      if (!cancelled) setData({ meta, state: { klippy: (status.webhooks || {}).state, pending: Boolean((status.configfile || {}).save_config_pending) } });
    })();
    return () => {
      cancelled = true;
    };
  }, [path]);
  if (!data) return null;
  const warnings = printChecks(data.meta, caps, data.state);
  return h(
    "div",
    { className: "print-checks", "data-print-checks": warnings.map((one) => one.id).join(",") || "ok" },
    warnings.length === 0
      ? h("div", { className: "print-checks__ok" }, h(Icons.Check, { size: 14 }), tx("Checked: the file suits this printer."))
      : warnings.map((one) => h("div", { key: one.id, className: "print-spool__warn", "data-check": one.id }, h(Icons.Warning, { size: 14 }), one.text)),
  );
}
