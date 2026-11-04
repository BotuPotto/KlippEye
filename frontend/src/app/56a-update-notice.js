/* ============================================================================
   56a · NEW VERSIONS, BY ITSELF (1.67)
   The dashboard asks Moonraker once a day (never while printing) to look for new versions of KlippEye, Klipper,
   Moonraker and the other programs it updates, and reads the answer every 15 minutes. When there are some:
     · a number on the «System» tab (the bar at the bottom on a phone, the tabs at the top on a computer);
     · a message, once for each new set of versions.
   The operating system's packages are left out: there are nearly always some, and they would keep the number on.
   It can be switched off in Settings → Software (it is remembered by each browser / phone): then nothing
   is read or shown.
   ========================================================================== */
const UPDATE_NOTICE_POLL_MS = 15 * 60 * 1000;
const UPDATE_AUTO_CHECK_MS = 24 * 60 * 60 * 1000;
const UPDATE_REFRESH_WAIT_MS = 20000; // Moonraker needs a while to ask every repository
const UPDATE_AUTO_KEY = "klippeye.updates.auto";
const UPDATE_LAST_CHECK_KEY = "klippeye.updates.lastCheck";
const UPDATE_ANNOUNCED_KEY = "klippeye.updates.announced";

function readStored(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
  } catch (e) {
    return fallback;
  }
}
function writeStored(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {}
}

const updateNoticeListeners = new Set();
let updateNotice = { count: 0, names: [], auto: readStored(UPDATE_AUTO_KEY, "1") !== "0" };
function setUpdateNotice(next) {
  updateNotice = { ...updateNotice, ...next };
  updateNoticeListeners.forEach((listener) => listener(updateNotice));
}

/** { count, names, auto }: the programs with a new version (the OS packages left out). */
function useUpdateNotice() {
  const [state, setState] = useState(updateNotice);
  useEffect(() => {
    updateNoticeListeners.add(setState);
    setState(updateNotice);
    return () => updateNoticeListeners.delete(setState);
  }, []);
  return state;
}

const updateWatchTriggers = new Set();
function setAutoUpdateCheck(on) {
  writeStored(UPDATE_AUTO_KEY, on ? "1" : "0");
  setUpdateNotice({ auto: on });
  if (on) updateWatchTriggers.forEach((run) => run());
  else setUpdateNotice({ count: 0, names: [] });
}

/** Reads what Moonraker knows now; announces a set of versions not announced before. */
async function readUpdateNotice() {
  if (!updateNotice.auto) return;
  const status = await fetchResult("/machine/update/status");
  if (!status) return;
  const found = describeUpdates(status).components.filter((component) => component.hasUpdate && !component.isSystem);
  const names = found.map((component) => (component.key === PROGRAM_COMPONENT ? "KlippEye" : component.name.charAt(0).toUpperCase() + component.name.slice(1)));
  setUpdateNotice({ count: found.length, names });
  if (!found.length) return;
  const signature = found.map((component) => component.key + "@" + component.remote).sort().join(",");
  if (readStored(UPDATE_ANNOUNCED_KEY, "") === signature) return;
  writeStored(UPDATE_ANNOUNCED_KEY, signature);
  toast.notice(tx("New versions: {names}. See System.", { names: names.join(", ") }), 6000);
}

/** Mounted once by the application. */
function useUpdateWatch(printing) {
  const printingRef = useRef(printing);
  printingRef.current = printing;
  useEffect(() => {
    let alive = true;
    let waiting = null;
    const tick = async () => {
      if (!updateNotice.auto) return;
      await readUpdateNotice();
      const last = Number(readStored(UPDATE_LAST_CHECK_KEY, "0")) || 0;
      if (!alive || printingRef.current || Date.now() - last < UPDATE_AUTO_CHECK_MS) return;
      writeStored(UPDATE_LAST_CHECK_KEY, String(Date.now()));
      await refreshUpdateStatus();
      clearTimeout(waiting);
      waiting = setTimeout(() => alive && readUpdateNotice(), UPDATE_REFRESH_WAIT_MS);
    };
    const stop = startPolling(tick, UPDATE_NOTICE_POLL_MS);
    updateWatchTriggers.add(tick);
    return () => {
      updateWatchTriggers.delete(tick);
      alive = false;
      clearTimeout(waiting);
      stop();
    };
  }, []);
}

/** The number on the «System» tab. */
function UpdateTabBadge({ className }) {
  const { count } = useUpdateNotice();
  if (!count) return null;
  return h("span", { className: cx("update-badge", className), "data-update-badge": count, title: tx("New versions to install: {count}", { count }), "aria-label": tx("New versions to install: {count}", { count }) }, count);
}
