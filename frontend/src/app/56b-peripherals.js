/* ============================================================================
   56b · DEVICES CONNECTED TO THE RASPBERRY (1.76)
   What is plugged in, as Moonraker sees it (/machine/peripherals/*): the serial
   ports (the boards: the address to write in printer.cfg's [mcu] serial:), the
   USB devices, the cameras and, on a CAN network, the boards waiting there
   (their canbus_uuid). Read only when the card is opened or «Look again» is
   pressed: asking the CAN network sends a query on it.
   A tap on an address copies it.
   ========================================================================== */

const PERIPHERAL_KINDS = [
  { id: "serial", label: () => tx("Serial"), path: "/machine/peripherals/serial" },
  { id: "usb", label: () => "USB", path: "/machine/peripherals/usb" },
  { id: "video", label: () => tx("Cameras"), path: "/machine/peripherals/video" },
  { id: "can", label: () => "CAN", path: "/machine/peripherals/canbus?interface=can0" },
];

/** Moonraker's answer → rows { title, detail, copy (the address to copy, if any) }. */
function peripheralRows(kind, result) {
  const r = result || {};
  if (kind === "serial")
    return (r.serial_devices || []).map((d) => ({
      title: [d.manufacturer, d.product].filter(Boolean).join(" ") || d.device_name || d.device_path,
      detail: [d.device_path, d.driver_name].filter(Boolean).join(" · "),
      copy: d.path_by_id || d.path_by_hardware || d.device_path || "",
    }));
  if (kind === "usb")
    return (r.usb_devices || []).map((d) => ({
      title: [d.manufacturer, d.product].filter(Boolean).join(" ") || d.description || tx("USB device"),
      detail: [d.vendor_id && d.product_id ? d.vendor_id + ":" + d.product_id : "", d.class, d.serial_number].filter(Boolean).join(" · "),
      copy: "",
    }));
  if (kind === "video")
    return (r.v4l2_devices || [])
      .map((d) => ({ title: d.camera_name || d.device_name || d.device_path, detail: [d.device_path, d.driver_name, d.hardware_bus].filter(Boolean).join(" · "), copy: d.path_by_id || d.device_path || "" }))
      .concat((r.libcamera_devices || []).map((d) => ({ title: d.model || tx("Camera module"), detail: "libcamera", copy: d.libcamera_id || "" })));
  if (kind === "can") return (r.can_uuids || []).map((d) => ({ title: d.application || "Klipper", detail: tx("waiting on the CAN network"), copy: d.uuid || "" }));
  return [];
}

async function readPeripherals(kind) {
  const entry = PERIPHERAL_KINDS.find((one) => one.id === kind);
  const response = await fetchFresh(entry.path, { timeout: 15000 });
  if (response.status === 404) throw new Error(kind === "can" ? tx("No CAN network on the Raspberry (can0).") : tx("Moonraker is too old to list them (0.8 or newer)."));
  if (!response.ok) throw new Error(await responseError(response));
  return peripheralRows(kind, (await response.json()).result);
}

function PeripheralsCard() {
  const [kind, setKind] = useState("serial");
  const [state, setState] = useState({ loading: false, rows: null, error: null });
  const look = async (which = kind) => {
    setState({ loading: true, rows: null, error: null });
    try {
      setState({ loading: false, rows: await readPeripherals(which), error: null });
    } catch (error) {
      setState({ loading: false, rows: null, error: error.message || String(error) });
    }
  };
  useEffect(() => {
    look(kind);
  }, [kind]);
  const copy = async (text) => {
    if (await copyText(text)) toast.notice(tx("Address copied"), 2500);
  };
  return h(
    SystemCard,
    {
      label: tx("Connected devices"),
      sublabel: tx("What is plugged into the Raspberry"),
      actions: h("button", { className: "oui-btn oui-btn--sm", "data-peripherals-refresh": "1", onClick: () => look(), disabled: state.loading }, h(Icons.Refresh, { size: 16 }), tx("Look again")),
    },
    h(
      "div",
      { className: "oui-segmented oui-segmented--sm peripherals-kinds", role: "group", "aria-label": tx("Kind of device") },
      PERIPHERAL_KINDS.map((one) => h("button", { key: one.id, type: "button", className: cx(kind === one.id && "is-selected"), "aria-pressed": kind === one.id, "data-peripherals": one.id, onClick: () => setKind(one.id) }, one.label())),
    ),
    state.loading && h("div", { className: "oui-caption peripherals-note" }, tx("Looking…")),
    state.error && h("div", { className: "oui-caption peripherals-note" }, state.error),
    state.rows && !state.rows.length && h("div", { className: "oui-caption peripherals-note" }, tx("Nothing of this kind is connected.")),
    state.rows &&
      state.rows.length > 0 &&
      h(
        "div",
        { className: "oui-list peripherals-list" },
        state.rows.map((row, index) =>
          h(
            "div",
            { key: index, className: "peripheral-row", "data-peripheral": row.copy || row.title },
            h("div", { className: "peripheral-row__title" }, row.title),
            row.detail && h("div", { className: "peripheral-row__detail" }, row.detail),
            row.copy && h("button", { type: "button", className: "peripheral-row__copy", title: tx("Copy"), onClick: () => copy(row.copy) }, h("code", null, row.copy), h(Icons.Doc, { size: 14 })),
          ),
        ),
      ),
    kind === "serial" && state.rows && state.rows.length > 0 && h("div", { className: "oui-caption peripherals-note" }, tx("The address to write after «serial:» in the [mcu] section of printer.cfg is the one under «/dev/serial/by-id/»: it does not change when the boards are plugged in another order.")),
    kind === "can" && state.rows && state.rows.length > 0 && h("div", { className: "oui-caption peripherals-note" }, tx("Only boards not yet set up answer: their code goes after «canbus_uuid:» in printer.cfg.")),
  );
}
