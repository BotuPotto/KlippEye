/* ============================================================================
   02 · TRANSLATIONS
   The dashboard is written in English; other languages are dictionaries in
   src/i18n/<lang>.json, embedded at build time (build.py). A dictionary maps
   the English text to the translation:

     tx("Restart")                          -> "Riavvia" in Italian
     tx("Restarted: {service}", { service }) -> placeholders in braces, filled in after translating
     txc("verb", "Print")                   -> the same English word in two meanings: the key is "verb|Print"
   (short names that the minified React code, which shares the same top-level scope, does not use)

   The language is the one chosen in Settings → Language (kept on this device,
   "ke_lang"), otherwise the device's own (navigator.languages), otherwise English.
   Changing it reloads the page, so every text, also the ones computed when the
   modules load, is in the new language. A text missing from a dictionary stays
   in English (tests/i18n checks that none is missing).
   ========================================================================== */

/** Dictionaries filled in by build.py from src/i18n/*.json: { it: { "English": "Italiano", ... } }. */
const I18N_DICTIONARIES = {/*__I18N__*/};
/** Languages offered in the settings, with their own names. */
const I18N_LANGUAGES = [
  { code: "en", name: "English" },
  { code: "it", name: "Italiano" },
];
const I18N_STORAGE_KEY = "ke_lang";

/** "auto" (follow the device) or a code of I18N_LANGUAGES, as saved on this device. */
function savedLanguageChoice() {
  try {
    const value = localStorage.getItem(I18N_STORAGE_KEY);
    return value && I18N_LANGUAGES.some((l) => l.code === value) ? value : "auto";
  } catch (e) {
    return "auto";
  }
}

/** The language of the device, if the dashboard has it; else English. */
function deviceLanguage() {
  const wanted = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"]).map((l) => String(l).toLowerCase());
  for (const tag of wanted) {
    const base = tag.split("-")[0];
    if (I18N_LANGUAGES.some((l) => l.code === base)) return base;
  }
  return "en";
}

const LANG = (() => {
  const choice = savedLanguageChoice();
  return choice === "auto" ? deviceLanguage() : choice;
})();
/** Locale for dates and numbers: the device's own when it is in the chosen language (en-US, en-GB...), else the language. */
const LOCALE = (() => {
  const device = String(navigator.language || "");
  if (device.toLowerCase().split("-")[0] === LANG) return device;
  return LANG === "it" ? "it-IT" : LANG;
})();
try {
  document.documentElement.lang = LANG;
} catch (e) {}

/** Saves the choice ("auto", "en", "it"...) and reloads the page in that language. */
function setLanguageChoice(choice) {
  try {
    if (choice === "auto") localStorage.removeItem(I18N_STORAGE_KEY);
    else localStorage.setItem(I18N_STORAGE_KEY, choice);
  } catch (e) {}
  window.location.reload();
}

function i18nFill(text, values) {
  if (!values) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : whole));
}

/** The translation of an English text in the current language, with {placeholders} filled in. */
function tx(text, values) {
  const dictionary = I18N_DICTIONARIES[LANG];
  const translated = dictionary && Object.prototype.hasOwnProperty.call(dictionary, text) ? dictionary[text] : text;
  return i18nFill(translated, values);
}

/** An English text to be translated later, in a language chosen then (see txIn): marks it for tools/i18n.py check. */
function txn(text) {
  return text;
}

/** The translation of an English text in a given language (not necessarily the page's): the notifications' own language. */
function txIn(language, text) {
  const dictionary = I18N_DICTIONARIES[language];
  return dictionary && Object.prototype.hasOwnProperty.call(dictionary, text) ? dictionary[text] : text;
}

/** Like tx(), for an English text that needs a different translation in a given context (key "context|text"). */
function txc(context, text, values) {
  const dictionary = I18N_DICTIONARIES[LANG];
  const key = context + "|" + text;
  const translated = dictionary && Object.prototype.hasOwnProperty.call(dictionary, key) ? dictionary[key] : text;
  return i18nFill(translated, values);
}
