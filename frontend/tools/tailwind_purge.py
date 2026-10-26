#!/usr/bin/env python3
"""
Reduces the compiled Tailwind stylesheet in vendor/ to the utilities that src/app/*.js uses, and
pretty-prints it (one rule per line). build.py calls `generate()` on every build; running this file
directly writes the result to a path, which is handy to inspect it:

    python3 tools/tailwind_purge.py  [out.css]

vendor/tailwind-3.4.18.compiled.css was produced by Tailwind 3.4.18 for the dashboard's original
markup. Only rules that already exist in it are kept, so a class name that has no rule there stays
a no-op, exactly as before.
"""
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_APP = os.path.join(HERE, "..", "src", "app")
COMPILED = os.path.join(HERE, "..", "vendor", "tailwind-3.4.18.compiled.css")
HEADER = ("/* Tailwind CSS v3.4.18 (compiled), reduced to the utilities this dashboard uses. */\n")


def split_top(text, sep):
    """Split on `sep` at brace/paren/bracket/quote depth 0 (ignores escaped chars)."""
    parts, depth, cur, i, quote = [], 0, [], 0, None
    while i < len(text):
        c = text[i]
        if c == "\\":
            cur.append(text[i:i + 2]); i += 2; continue
        if quote:
            if c == quote: quote = None
        elif c in "\"'":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == sep and depth == 0 and not quote:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def parse_blocks(css):
    """Top-level items: ('rule', selector, body) | ('at', prelude, [items]) | ('raw', text)."""
    items, i, n = [], 0, len(css)
    while i < n:
        if css[i].isspace():
            i += 1; continue
        if css.startswith("/*", i):
            j = css.index("*/", i) + 2
            items.append(("raw", css[i:j])); i = j; continue
        j = i; depth = 0; quote = None
        while j < n:
            c = css[j]
            if c == "\\": j += 2; continue
            if quote:
                if c == quote: quote = None
            elif c in "\"'": quote = c
            elif c == "{": break
            j += 1
        prelude = css[i:j].strip()
        k = j + 1; depth = 1; quote = None
        while k < n and depth:
            c = css[k]
            if c == "\\": k += 2; continue
            if quote:
                if c == quote: quote = None
            elif c in "\"'": quote = c
            elif c == "{": depth += 1
            elif c == "}": depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        if prelude.startswith("@media") or prelude.startswith("@supports"):
            items.append(("at", prelude, parse_blocks(body)))
        else:
            items.append(("rule", prelude, body))
        i = k
    return items


CLASS_RE = re.compile(r"\.((?:\\[0-9a-fA-F]{1,6} ?|\\.|[A-Za-z0-9_-])+)")


def unescape(text):
    """CSS identifier escapes: `\\2c ` (hex) and `\\:` (character)."""
    text = re.sub(r"\\([0-9a-fA-F]{1,6}) ?", lambda m: chr(int(m.group(1), 16)), text)
    return re.sub(r"\\(.)", r"\1", text)


def used_tokens():
    toks = set()
    for p in glob.glob(os.path.join(SRC_APP, "*.js")):
        text = open(p, encoding="utf-8").read()
        toks.update(re.findall(r"[^\s\"'`]+", text))
        # tokens glued to template placeholders: `foo ${x} bar` is split already; also cut on ${...}
        for t in list(toks):
            if "${" in t: toks.update(re.split(r"\$\{[^}]*\}", t))
    return toks


def selector_survives(sel, used):
    # strip :not([hidden]) etc. attribute parts so that only real class names are inspected
    classes = [unescape(c) for c in CLASS_RE.findall(re.sub(r"\[[^\]]*\]", lambda m: "", sel) if False else sel)]
    classes = [c for c in classes if not c.startswith("[")]
    return all(c in used for c in classes)


def is_app_base_rule(it):
    """Page-level rules the dashboard author appended to the Tailwind build.

    They are not utilities, so they live in src/css/10-base.css instead of the generated file:
    `#root,body,html{min-height:100%}`, `body{margin:0;font-family:...}` and the pointer cursor.
    """
    if it[0] != "rule":
        return False
    sel = it[1].replace(" ", "")
    if sel == "#root,body,html":
        return True
    if sel == "body" and it[2].replace(" ", "").startswith("margin:0"):
        return True
    return sel.startswith("[role=button]:not([aria-disabled=true])")


def purge(items, used):
    out = []
    for it in items:
        if is_app_base_rule(it):
            continue
        if it[0] == "raw":
            out.append(it)
        elif it[0] == "rule":
            sels = [s.strip() for s in split_top(it[1], ",")]
            keep = [s for s in sels if selector_survives(s, used)]
            if keep:
                out.append(("rule", ",".join(keep), it[2]))
        else:
            sub = purge(it[2], used)
            if any(x[0] != "raw" for x in sub):
                out.append(("at", it[1], sub))
    return out


def clean_decl(d):
    d = d.strip()
    name, _, value = d.partition(":")
    value = value.strip()
    # `--tw-x: ;` (a single space) is how Tailwind writes an "empty" custom property: keep it
    return f"{name.strip()}: {value}" if value else f"{name.strip()}: "


def fmt_rule(sel, body, indent=""):
    decls = [clean_decl(d) for d in split_top(body, ";") if d.strip()]
    sels = [x.strip() for x in split_top(sel, ",")]
    head = (",\n" + indent).join(sels) if len(sels) > 3 else ", ".join(sels)
    if len(decls) > 8:  # the custom-property blocks: one declaration per line
        inner = "".join(f"\n{indent}  {d};" for d in decls)
        return f"{indent}{head} {{{inner}\n{indent}}}"
    return f"{indent}{head} {{ " + "; ".join(decls) + "; }" if decls else f"{indent}{head} {{}}"


def emit(items, indent=""):
    lines = []
    for it in items:
        if it[0] == "raw":
            lines.append(indent + it[1])
        elif it[0] == "rule":
            lines.append(fmt_rule(it[1], it[2], indent))
        else:
            lines.append(f"{indent}{it[1]} {{")
            lines.extend(emit(it[2], indent + "  "))
            lines.append(f"{indent}}}")
    return lines


def referenced_vars(items):
    names = set()
    for it in items:
        if it[0] == "rule":
            names.update(re.findall(r"var\((--tw-[a-z0-9-]+)", it[2]))
        elif it[0] == "at":
            names |= referenced_vars(it[2])
    return names


def trim_custom_properties(items):
    """Drops the `::backdrop` twin and every `--tw-*` initial value no kept rule reads."""
    needed = referenced_vars(items)
    out = []
    for it in items:
        if it[0] == "rule" and it[1] == "::backdrop":
            continue
        if it[0] == "rule" and it[1].replace(" ", "") == "*,:after,:before" and it[2].lstrip().startswith("--tw-"):
            decls = [d for d in split_top(it[2], ";") if d.strip() and d.split(":")[0].strip() in needed]
            it = ("rule", it[1], ";".join(decls))
        out.append(it)
    return out


def generate(compiled_path=COMPILED):
    """The reduced stylesheet as text."""
    items = parse_blocks(open(compiled_path, encoding="utf-8").read())
    kept = trim_custom_properties(purge(items, used_tokens()))
    return HEADER + "\n".join(emit(kept)) + "\n"


if __name__ == "__main__":
    css = generate()
    if len(sys.argv) > 1:
        open(sys.argv[1], "w", encoding="utf-8").write(css)
    else:
        sys.stdout.write(css)
