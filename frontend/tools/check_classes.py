"""Lists class names used in src/app/*.js that have no CSS rule (they would do nothing).
   python3 tools/check_classes.py [built.html]
   Heuristic: every double-quoted string whose words all look like class names is a candidate."""
import re, sys, glob, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
html = open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", "index.html"), encoding="utf-8").read()
css = html[html.index("<style>"):html.index("</style>")]
defined = set()
for m in re.finditer(r"\.((?:\\.|[A-Za-z0-9_-])+)", css):
    defined.add(re.sub(r"\\(.)", r"\1", m.group(1)))
TOKEN = re.compile(r"^[!A-Za-z0-9_:\-\[\]\/\.\(\)#%,'>&*=~$+]+$")
unknown = {}
for f in sorted(glob.glob(os.path.join(ROOT, "src", "app", "*.js"))):
    src = open(f, encoding="utf-8").read()
    for line_no, line in enumerate(src.split("\n"), 1):
        for m in re.finditer(r'"([^"\n]{2,300})"', line):
            words = m.group(1).split()
            if not words or not all(TOKEN.match(w) for w in words): continue
            # skip obvious non-class strings
            if any(w in ("div","span","button","input","svg","path","circle","line","rect","text","img","iframe","main","header","nav") and len(words) == 1 for w in words): continue
            for w in words:
                base = w
                if base in defined: continue
                # variants like hover:bg-x are defined with escaped colon; defined set already unescaped
                if re.match(r"^[a-z0-9-]+(:[a-z0-9-]+)*:?[A-Za-z0-9_\[\]\/\.\-#%()]+$", w) and ("-" in w or ":" in w or "[" in w):
                    unknown.setdefault(w, set()).add(os.path.basename(f) + ":" + str(line_no))
for w, where in sorted(unknown.items()):
    print(f"{w:48} {sorted(where)[0]}" + (f" (+{len(where)-1})" if len(where) > 1 else ""))
