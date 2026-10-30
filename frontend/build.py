#!/usr/bin/env python3
"""
Builds the dashboard: one self-contained HTML file, served as is by the Flask backend.

    python3 build.py [out.html]          (default: klippeye_frontend.html next to this script: the file the backend serves)

    src/index.html          page skeleton with three placeholders, {{icons}}, {{styles}} and {{script}}
    src/icons/*.png         tab icon (drawn by tools/make_favicon.py), embedded as data URIs
    src/css/*.css           the application stylesheet, in file-name order
    vendor/tailwind-*.css   compiled Tailwind, reduced by tools/tailwind_purge.py to the classes in use
    vendor/react-dom-*.js   React 18 + ReactDOM client, third-party code, kept unmodified
    vendor/qrcode-generator-*.js  QR codes (Kazuhiko Arase, MIT licence), kept unmodified: the code that pairs a phone (1.20)
    src/app/*.js            the application, in file-name order (99-main.js starts it)
    src/i18n/<lang>.json    translations of the English texts (English text -> translation), see app/02-i18n.js

The result has no external files and no network dependency: the font is the device's own (One UI Sans on Samsung).
"""
import base64
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import tailwind_purge  # noqa: E402


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def files(pattern):
    return sorted(glob.glob(os.path.join(HERE, pattern)))


def banner(text):
    return "/* " + "=" * 76 + "\n   " + text + "\n   " + "=" * 73 + " */\n"


def styles():
    """Tailwind subset first, then the application styles; @import rules must lead the sheet."""
    parts = [banner("Tailwind utilities (generated from vendor/, only the classes in use)"), tailwind_purge.generate()]
    parts += [read(path) for path in files("src/css/*.css")]
    css = "\n".join(parts)
    imports = re.findall(r"^@import[^\n]*\n", css, flags=re.M)
    return "".join(imports) + re.sub(r"^@import[^\n]*\n", "", css, flags=re.M)


def release():
    """The release written into the page (DASHBOARD_RELEASE in app/17-brain.js): the environment variable KLIPPEYE_RELEASE, else
    the VERSION file of the repository (../VERSION), else "sviluppo"."""
    chosen = os.environ.get("KLIPPEYE_RELEASE", "").strip()
    for path in (os.path.join(HERE, "..", "VERSION"),):
        if not chosen and os.path.isfile(path):
            chosen = read(path).strip()
    chosen = chosen or "sviluppo"
    assert re.fullmatch(r"[0-9A-Za-z.+_-]{1,32}", chosen), "the release must be a short word like 1.0.0, not %r" % chosen
    return chosen


LOGO_TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp"}


def logos():
    """The files of src/logos/ (<brand id>.png|svg|webp) as the body of the EMBEDDED_LOGOS object of app/01-assets.js."""
    entries = []
    for path in files("src/logos/*"):
        name, extension = os.path.splitext(os.path.basename(path))
        if extension not in LOGO_TYPES or not re.fullmatch(r"[a-z0-9_-]{1,32}", name):
            continue
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        entries.append('"%s": "data:%s;base64,%s"' % (name, LOGO_TYPES[extension], data))
    return ", ".join(entries)


def dictionaries():
    """The files of src/i18n/ (<lang>.json: English text -> translation) as the body of I18N_DICTIONARIES (app/02-i18n.js)."""
    import json
    entries = []
    for path in files("src/i18n/*.json"):
        lang = os.path.splitext(os.path.basename(path))[0]
        assert re.fullmatch(r"[a-z]{2}", lang), "dictionary names are two-letter language codes, not %r" % lang
        with open(path, encoding="utf-8") as f:
            table = json.load(f)
        assert isinstance(table, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in table.items()), path
        entries.append('"%s": %s' % (lang, json.dumps(table, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
    return ", ".join(entries)


def script():
    """Vendor React first (the app calls into it), then the application, 99-main.js last."""
    parts = [banner("VENDOR: React + ReactDOM client 18.3.1 (minified, unmodified). The application starts below.")]
    parts += [read(path) for path in files("vendor/react-dom-*.js")]
    parts.append("\n" + banner("VENDOR: qrcode-generator 2.0.4 by Kazuhiko Arase (MIT licence, unmodified)"))
    parts += [read(path) for path in files("vendor/qrcode-generator-*.js")]
    parts.append("\n" + banner("APPLICATION"))
    parts += [read(path) for path in files("src/app/*.js")]
    code = "\n".join(parts)
    assert code.count("__KLIPPEYE_RELEASE__") == 1, "the release placeholder must appear once (app/17-brain.js)"
    assert code.count("/*__EMBEDDED_LOGOS__*/") == 1, "the logos placeholder must appear once (app/01-assets.js)"
    assert code.count("/*__I18N__*/") == 1, "the dictionaries placeholder must appear once (app/02-i18n.js)"
    return code.replace("__KLIPPEYE_RELEASE__", release()).replace("/*__EMBEDDED_LOGOS__*/", logos()).replace("/*__I18N__*/", dictionaries())


def icons():
    """<link> tags of the tab icon and of the icon for "add to home screen", embedded as data URIs (src/icons/, see tools/make_favicon.py)."""
    tags = []
    for name, rel, sizes in (("favicon-32.png", "icon", "32x32"), ("favicon-64.png", "icon", "64x64"), ("apple-touch-icon.png", "apple-touch-icon", "180x180")):
        with open(os.path.join(HERE, "src", "icons", name), "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        tags.append('  <link rel="%s" sizes="%s" type="image/png" href="data:image/png;base64,%s">' % (rel, sizes, data))
    return "\n".join(tags)


def build(out):
    html = read(os.path.join(HERE, "src", "index.html"))
    code = script()
    assert "</script" not in code, "an inline script must not contain a closing script tag"
    html = html.replace("{{icons}}", icons()).replace("{{styles}}", styles()).replace("{{script}}", code)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", out, len(html), "bytes, release", release())


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "klippeye_frontend.html"))
