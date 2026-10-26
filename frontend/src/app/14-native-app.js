/* ============================================================================
   14 · ANDROID APP
   The dashboard also runs inside the KlippEye Android app, which is a WebView. A
   plain WebView does not open a file chooser for a file input and does not
   download anything, so the app does both itself and says so by adding
   "KlippEyeApp/<n>" to its user agent, n being what it can do for the page:
     2  the file chooser ("Carica file" in the config card)
     3  saving files into the phone's Download folder (window.KlippEyeApp.saveUrl)
     4  using the addresses of the settings menu (window.KlippEyeApp.setAddresses / getAddresses, see app/16-settings.js)
     5  updating itself with the APK the backend offers (window.KlippEyeApp.appInfo / updateApp, see app/59c-app-update.js)
   A WebView without that marker still shows "; wv)" in its user agent.
   The app of VzBot 1.0.x (package com.vzbot.dashboard) is the same thing under the old names: "VzBotApp/<n>" and window.VzBotApp.
   It keeps working with this page; it is replaced by the KlippEye app (another package) through its own updater, see app/59c-app-update.js.
   ========================================================================== */

const APP_VERSION = Number((/(?:KlippEye|VzBot)App\/(\d+)/.exec(navigator.userAgent) || [])[1]) || 0;
/** The object the app puts in the page (null in a browser). */
const nativeBridge = () => window.KlippEyeApp || window.VzBotApp || null;
/** True in the app of VzBot 1.0.x: the new app is another package, installed beside it. */
const isLegacyApp = () => !window.KlippEyeApp && Boolean(window.VzBotApp);
const IN_APP_WEBVIEW = /; wv\)/.test(navigator.userAgent) || APP_VERSION > 0;
const APP_CAN_PICK_FILES = !IN_APP_WEBVIEW || APP_VERSION >= 2;
const APP_CAN_SAVE_FILES = !IN_APP_WEBVIEW || APP_VERSION >= 3;
const APP_KNOWS_ADDRESSES = APP_VERSION >= 4;
const APP_CAN_UPDATE = APP_VERSION >= 5;

/**
 * Saves a file of the Raspberry as `name`. `url` is an address on this server ("/server/files/config/printer.cfg").
 * A browser downloads it through a link; the app saves it into Download by itself (and tells the user where).
 * A WebView of an older app can do neither, so it is told to update.
 */
function downloadFile(url, name) {
  const bridge = nativeBridge();
  if (bridge && typeof bridge.saveUrl === "function") {
    bridge.saveUrl(url, name);
    return;
  }
  if (!APP_CAN_SAVE_FILES) {
    toast.action(tx("Downloads do not work in this version of the app: update it or open the dashboard in the browser"));
    return;
  }
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
