/* ============================================================================
   42a · DEVICES: POWER, OUTPUTS, FILAMENT SENSORS (1.45, roadmap 6d part 4)
   Power devices, outputs and sensors:
     · Moonraker's [power] devices (smart plugs, relays, GPIO…): on / off, the
       off asked first (it may be the printer's own power);
     · Klipper's [output_pin]s: a switch, or a slider for a PWM pin (0 – scale);
     · the filament sensors: filament there or not, and the switch that turns
       the sensor on or off (SET_FILAMENT_SENSOR).
   A name starting with _ stays hidden. Nothing to show: no card.
   ========================================================================== */

const DEVICES_POLL_MS = 3000;
const DEVICE_SLIDER_SEND_MS = 250;

const powerApi = {
  async devices() {
    const json = await fetchJson("/machine/device_power/devices");
    return ((json && json.result) || {}).devices || [];
  },
  async set(device, on) {
    const response = await fetchFresh("/machine/device_power/device?device=" + encodeURIComponent(device) + "&action=" + (on ? "on" : "off"), { method: "POST" });
    if (!response.ok) throw new Error(await responseError(response));
  },
};

const visibleObject = (name) => !/^\S+ _/.test(name);
const objectName = (object) => object.split(" ").slice(1).join(" ");
/** "case_light" → "Case light". */
const prettyName = (name) => {
  const words = String(name).replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/**
 * One store: { power: [devices] | null (no [power]), pins: [{ object, name, pwm, scale, value }], sensors: [{ object, name,
 * kind, detected, enabled }], ready }. Read every DEVICES_POLL_MS while the card is on screen.
 */
const devicesStore = (() => {
  const listeners = new Set();
  let state = { power: null, pins: [], sensors: [], ready: false };
  let users = 0;
  let stop = null;
  let layout = null; // { pins, sensors } from the objects and the configuration, read once
  const set = (next) => {
    state = next;
    listeners.forEach((fn) => fn());
  };
  async function readLayout() {
    const objects = (await moonraker.objectsList()).filter(visibleObject);
    let settings = {};
    try {
      settings = (await moonraker.configfile("settings")).settings || {};
    } catch (error) {}
    const pins = objects
      .filter((object) => object.startsWith("output_pin "))
      .map((object) => {
        const section = settings[object.toLowerCase()] || settings[object] || {};
        const pwm = section.pwm === true || String(section.pwm).toLowerCase() === "true";
        return { object, name: objectName(object), pwm, scale: Number(section.scale) > 0 ? Number(section.scale) : 1 };
      });
    const sensors = objects.filter((object) => /^filament_(switch|motion)_sensor /.test(object)).map((object) => ({ object, name: objectName(object), kind: object.split(" ")[0] }));
    return { pins, sensors };
  }
  async function refresh() {
    if (!layout) layout = await readLayout();
    const components = await moonrakerComponents();
    let power = null;
    if (components.has("power")) {
      try {
        power = (await powerApi.devices()).filter((device) => !String(device.device).startsWith("_"));
      } catch (error) {
        power = state.power;
      }
    }
    const query = layout.pins.map((pin) => encodeURIComponent(pin.object) + "=value").concat(layout.sensors.map((sensor) => encodeURIComponent(sensor.object) + "=filament_detected,enabled"));
    const status = query.length ? await moonraker.queryObjects(query.join("&")) : {};
    set({
      power,
      pins: layout.pins.map((pin) => ({ ...pin, value: Number((status[pin.object] || {}).value) || 0 })),
      sensors: layout.sensors.map((sensor) => ({ ...sensor, detected: Boolean((status[sensor.object] || {}).filament_detected), enabled: (status[sensor.object] || {}).enabled !== false })),
      ready: true,
    });
  }
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => state,
    refresh: () => refresh().catch(noop),
    /** Shows a change at once (the next reading confirms it). */
    patch(fn) {
      set(fn(state));
    },
    use() {
      users++;
      if (users === 1) stop = startPolling(refresh, DEVICES_POLL_MS);
      return () => {
        users--;
        if (users === 0 && stop) {
          stop();
          stop = null;
        }
      };
    },
  };
})();

function useDevices() {
  useEffect(() => devicesStore.use(), []);
  return useSyncExternalStore(devicesStore.subscribe, devicesStore.snapshot);
}

/** A PWM pin: a slider, sent a moment after the finger stops (and at once when it lets go). */
function PinSlider({ pin }) {
  const [draft, setDraft] = useState(null);
  const timer = useRef(0);
  const percent = draft !== null ? draft : Math.round((pin.value / pin.scale) * 100);
  const send = (value) => {
    clearTimeout(timer.current);
    fireGcode("SET_PIN PIN=" + pin.name + " VALUE=" + Number(((value / 100) * pin.scale).toFixed(3)));
    devicesStore.patch((state) => ({ ...state, pins: state.pins.map((one) => (one.object === pin.object ? { ...one, value: (value / 100) * pin.scale } : one)) }));
    setTimeout(() => setDraft(null), DEVICES_POLL_MS);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  return h(
    "div",
    { className: "device-row device-row--slider", "data-pin": pin.name },
    h("div", { className: "device-row__head" }, h("span", { className: "device-row__name" }, prettyName(pin.name)), h("span", { className: "device-row__value" }, percent + "%")),
    h("input", {
      type: "range",
      className: "device-row__range",
      min: 0,
      max: 100,
      step: 1,
      value: percent,
      "aria-label": prettyName(pin.name),
      onChange: (event) => {
        const value = Number(event.target.value);
        setDraft(value);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => send(value), DEVICE_SLIDER_SEND_MS);
      },
      onPointerUp: (event) => send(Number(event.target.value)),
    }),
  );
}

function DevicesCard() {
  const devices = useDevices();
  const [confirmOff, setConfirmOff] = useState(null); // the power device about to be switched off
  const setPower = async (device, on) => {
    setConfirmOff(null);
    devicesStore.patch((state) => ({ ...state, power: state.power.map((one) => (one.device === device.device ? { ...one, status: on ? "on" : "off" } : one)) }));
    try {
      await powerApi.set(device.device, on);
    } catch (error) {
      toast.action(prettyName(device.device) + ": " + (error.message || error));
    }
    devicesStore.refresh();
  };
  const setPin = (pin, on) => {
    fireGcode("SET_PIN PIN=" + pin.name + " VALUE=" + (on ? pin.scale : 0));
    devicesStore.patch((state) => ({ ...state, pins: state.pins.map((one) => (one.object === pin.object ? { ...one, value: on ? pin.scale : 0 } : one)) }));
  };
  const setSensor = (sensor, enabled) => {
    fireGcode("SET_FILAMENT_SENSOR SENSOR=" + sensor.name + " ENABLE=" + (enabled ? 1 : 0));
    devicesStore.patch((state) => ({ ...state, sensors: state.sensors.map((one) => (one.object === sensor.object ? { ...one, enabled } : one)) }));
  };
  const power = devices.power || [];
  if (!devices.ready || (power.length === 0 && devices.pins.length === 0 && devices.sensors.length === 0)) return null;
  return h(
    React.Fragment,
    null,
    h(
      Card,
      { cardId: "devices", className: "devices-card" },
      h(CardHeader, { title: tx("Devices") }),
      power.length > 0 &&
        h(
          "section",
          { className: "devices-group", "data-group": "power" },
          h("div", { className: "devices-group__label" }, txc("supply", "Power")),
          h(
            "div",
            { className: "oui-list" },
            power.map((device) =>
              h(
                "div",
                { key: device.device, "data-power": device.device },
                h(SwitchRow, {
                  title: prettyName(device.device),
                  detail: device.status === "error" ? tx("Error: Moonraker cannot reach it") : device.locked_while_printing ? tx("Locked while printing") : null,
                  checked: device.status === "on",
                  danger: device.status === "error",
                  onChange: (on) => (on ? setPower(device, true) : setConfirmOff(device)),
                }),
              ),
            ),
          ),
        ),
      devices.pins.length > 0 &&
        h(
          "section",
          { className: "devices-group", "data-group": "pins" },
          h("div", { className: "devices-group__label" }, tx("Outputs")),
          h(
            "div",
            { className: "oui-list" },
            devices.pins.map((pin) => (pin.pwm ? h(PinSlider, { key: pin.object, pin }) : h("div", { key: pin.object, "data-pin": pin.name }, h(SwitchRow, { title: prettyName(pin.name), checked: pin.value > 0, onChange: (on) => setPin(pin, on) })))),
          ),
        ),
      devices.sensors.length > 0 &&
        h(
          "section",
          { className: "devices-group", "data-group": "sensors" },
          h("div", { className: "devices-group__label" }, tx("Filament sensors")),
          h(
            "div",
            { className: "oui-list" },
            devices.sensors.map((sensor) =>
              h(
                "div",
                { key: sensor.object, className: cx("device-sensor", sensor.enabled && (sensor.detected ? "is-loaded" : "is-empty")), "data-sensor": sensor.name },
                h(SwitchRow, {
                  title: prettyName(sensor.name),
                  detail: !sensor.enabled ? tx("Off: a runout does not pause the print") : sensor.detected ? tx("Filament detected") : tx("No filament"),
                  checked: sensor.enabled,
                  onChange: (on) => setSensor(sensor, on),
                }),
              ),
            ),
          ),
        ),
    ),
    h(ConfirmDialog, {
      open: Boolean(confirmOff),
      tone: "danger",
      icon: h(Icons.Power),
      title: tx("Switch off {name}?", { name: confirmOff ? prettyName(confirmOff.device) : "" }),
      subtitle: txc("supply", "Power"),
      message: tx("Whatever it powers stops at once: if it is the printer, Klipper loses it and a print going on is lost."),
      confirmLabel: tx("Switch off"),
      onConfirm: () => setPower(confirmOff, false),
      onCancel: () => setConfirmOff(null),
    }),
  );
}
