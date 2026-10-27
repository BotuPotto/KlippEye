#!/usr/bin/env python3
"""
Translation helpers for the dashboard (see app/02-i18n.js).

    python3 tools/i18n.py check                     every tx()/txc() text has an Italian translation; lists Italian texts left outside tx()
    python3 tools/i18n.py extract src/app/FILE.js   prints the visible string literals of a file as a JSON object {"text": ""}
    python3 tools/i18n.py apply src/app/FILE.js MAP.json
                                                    MAP = {"original text": "English text"}: every literal "original text" in FILE
                                                    becomes tx("English text") and src/i18n/it.json gets "English text": "original text".
                                                    A value of null leaves that literal alone (it is not shown to people).

`check` exits with 1 when a translation is missing, so the tests can use it.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IT = os.path.join(ROOT, "src", "i18n", "it.json")
BACKEND = os.path.join(os.path.dirname(ROOT), "backend", "klippeye_backend.py")

LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"()')   # the sources use double quotes for text (Prettier)
CALL = re.compile(r'\btx[n]?\(\s*"((?:[^"\\\n]|\\.)*)"|\btxc\(\s*"((?:[^"\\\n]|\\.)*)"\s*,\s*"((?:[^"\\\n]|\\.)*)"')
ITALIAN = re.compile(r"[àèéìòùÀÈÌÒÙ]|\b(il|lo|la|gli|le|di|da|del|della|delle|dei|per|con|non|che|una|uno|sono|questo|questa|alla|al|nel|nella|dal|dalla|più|stampa|stampante|"
                     r"attiva|attivo|salva|annulla|chiudi|apri|riavvia|aggiorna|impostazioni|file|cartella|errore|spegni|accendi|tutto|nessun|nessuno|ancora|"
                     r"scegli|scrivi|tocca|premi|leggo|riprova|pronto|riavvio|velocità|ventola|ventole|temperatura|piatto|ugello|asse|assi|camera|monitor|"
                     r"soglie|aggiornamenti|sistema|controllo|calibrazioni|calibrazione|indirizzi|notifiche|accesso|lingua|si|sì|no)\b", re.I)


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"(?m)^(\s*)//.*$", r"\1", src)


def unescape(text):
    try:
        return json.loads('"' + text + '"')
    except ValueError:
        return text


def visible(text):
    """A string literal that looks like text for people (not a class name, path, key, G-code or SVG path)."""
    if not re.search(r"[A-Za-zÀ-ú]{2}", text):
        return False
    if re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9 .,-]+", text):   # SVG path
        return False
    if re.search(r"__|--|^(Escape|Enter|Tab|Content-Type|currentColor)$", text):
        return False                                            # BEM class names, key names, headers
    if ITALIAN.search(text):
        return True
    core = text.strip()
    if re.fullmatch(r"[A-ZÀ-Ú][a-zà-ú]+", core):                 # one capitalised word: "Home", "Download"
        return True
    if " " not in core:
        return False                                            # keys, ids, classes, paths, URLs
    if re.fullmatch(r"[a-z0-9_\[\]/.:-]+(\s+[a-z0-9_\[\]/.:-]+)*", core):
        return False                                            # CSS/Tailwind classes
    if re.fullmatch(r"[A-Z0-9_]+(\s+[A-Z0-9_=.%{}$-]+)*", core):
        return False                                            # G-code commands
    if re.search(r"var\(--|[{};]|^[.#\[]|\b(rgba?|translate|cubic-bezier)\(", core):
        return False                                            # CSS values and selectors
    return True


def load_it():
    try:
        with open(IT, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_it(table):
    with open(IT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(table.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")


def extract(path):
    src = strip_comments(open(path, encoding="utf-8").read())
    seen = {}
    for m in LITERAL.finditer(src):
        before = src[max(0, m.start() - 3):m.start()]
        if re.search(r"\btx[n]?\($|txc\($", before):
            continue
        text = unescape(m.group(1) if m.group(1) is not None else m.group(2))
        if visible(text):
            seen.setdefault(text, "")
    print(json.dumps(seen, ensure_ascii=False, indent=1))


def js_string(text):
    return json.dumps(text, ensure_ascii=False)


def apply(path, mapping_path):
    with open(mapping_path, encoding="utf-8") as f:
        mapping = json.load(f)
    src = open(path, encoding="utf-8").read()
    table = load_it()
    done, missing = 0, []
    for original, english in mapping.items():
        if english is None:
            continue
        key = english if isinstance(english, str) else english[0] + "|" + english[1]
        if key in table and table[key] != original:
            raise SystemExit("conflict: %r is already the translation of %r, not %r: use tc(context, text)" % (key, table[key], original))
        call = ("tx(%s)" % js_string(english)) if isinstance(english, str) else ("txc(%s, %s)" % (js_string(english[0]), js_string(english[1])))
        count = 0
        for quoted in (js_string(original), "'" + original.replace("'", "\\'") + "'"):
            pattern = re.compile(r'(?<![\w$.])' + re.escape(quoted))
            src, n = pattern.subn(lambda m: call, src)
            count += n
        if count == 0:
            missing.append(original)
            continue
        table[key] = original
        done += count
    open(path, "w", encoding="utf-8").write(src)
    save_it(table)
    print("%s: %d literals translated, %d texts in it.json" % (os.path.basename(path), done, len(table)))
    for text in missing:
        print("  not found (written differently?):", repr(text))


def backend_texts():
    """The texts the backend sends for the dashboard to show (names and explanations of the monitor thresholds)."""
    try:
        src = open(BACKEND, encoding="utf-8").read()
    except OSError:
        return []
    start, end = src.find("CONFIG_GROUPS = ["), src.find("SPEC_BY_KEY")
    schema = [unescape(m.group(2)) for m in re.finditer(r'"(title|note|label|help)":\s*"((?:[^"\\]|\\.)*)"', src[start:end]) if m.group(2)]
    # and the messages the backend translates itself with bt("English text", lang)
    calls = [unescape(m.group(1)) for m in re.finditer(r'\bbt\(\s*"((?:[^"\\]|\\.)*)"', strip_python_comments(src))]
    return schema + calls


def strip_python_comments(src):
    return re.sub(r"(?m)^\s*#.*$", "", src)


def check():
    table = load_it()
    used, missing, left = set(), [], []
    for key in backend_texts():
        used.add(key)
        if key not in table:
            missing.append(("klippeye_backend.py", key))
    for path in sorted(glob.glob(os.path.join(ROOT, "src", "app", "*.js"))):
        src = strip_comments(open(path, encoding="utf-8").read())
        for m in CALL.finditer(src):
            key = unescape(m.group(1)) if m.group(1) is not None else unescape(m.group(2)) + "|" + unescape(m.group(3))
            used.add(key)
            if key not in table:
                missing.append((os.path.basename(path), key))
        for m in LITERAL.finditer(src):
            before = src[max(0, m.start() - 3):m.start()]
            if re.search(r"\btx[n]?\($|txc\($|, $", before) and re.search(r"\btx[cn]?\(", src[max(0, m.start() - 40):m.start()]):
                continue
            text = unescape(m.group(1) if m.group(1) is not None else m.group(2))
            if visible(text) and text not in used:
                left.append((os.path.basename(path), text))
    unused = sorted(set(table) - used)
    print("%d texts in tx()/txc(), %d Italian translations, %d missing, %d unused, %d literals outside tx() that might be text (list: check -v)" % (len(used), len(table), len(missing), len(unused), len(left)))
    for name, key in missing:
        print("  MISSING  %s: %r" % (name, key))
    for key in unused:
        print("  unused   %r" % key)
    if "-v" in sys.argv:
        for name, text in left:
            print("  left     %s: %r" % (name, text))
    return 1 if missing else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "check":
        sys.exit(check())
    if len(sys.argv) == 3 and sys.argv[1] == "extract":
        extract(sys.argv[2])
        sys.exit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "apply":
        apply(sys.argv[2], sys.argv[3])
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
