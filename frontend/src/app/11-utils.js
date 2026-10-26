/* ============================================================================
   11 · UTILITIES
   Small, dependency-free helpers.
   ========================================================================== */

const noop = () => {};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Sign-prefixed number: 5 -> "+5", -5 -> "-5". */
const signed = (n) => (n > 0 ? "+" : "") + n;

/** localStorage that never throws (private mode, blocked storage, ...). */
const storage = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {}
  },
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch (e) {}
  },
  getJson(key) {
    try {
      return JSON.parse(localStorage.getItem(key));
    } catch (e) {
      return null;
    }
  },
};

/** Before KlippEye the keys of this device's storage began with "vz_": a value found under the old name is moved to the new one (once). */
(function moveOldStorageKeys() {
  try {
    Object.keys(localStorage)
      .filter((key) => key.indexOf("vz_") === 0)
      .forEach((oldKey) => {
        const newKey = "ke_" + oldKey.slice(3);
        if (localStorage.getItem(newKey) === null) localStorage.setItem(newKey, localStorage.getItem(oldKey));
        localStorage.removeItem(oldKey);
      });
  } catch (e) {}
})();

/** Scroll the page back to the top (used when switching tab). */
function scrollPageToTop() {
  try {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    const main = document.querySelector("main");
    if (main) main.scrollTop = 0;
  } catch (e) {}
}

/** Clock time as shown in the console, e.g. "10:53:21". */
const localTimeString = () => new Date().toLocaleTimeString("it-IT");

/** Formats a Unix timestamp (seconds) as HH:MM:SS for the console. */
const consoleTimeFormatter = new Intl.DateTimeFormat("it-IT", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
function formatUnixTime(unixSeconds) {
  try {
    return consoleTimeFormatter.format(new Date((unixSeconds || 0) * 1000));
  } catch (e) {
    return "";
  }
}

/** Escapes text for safe interpolation into HTML strings. */
const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
