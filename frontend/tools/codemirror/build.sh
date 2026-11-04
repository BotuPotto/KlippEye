#!/bin/bash
# Builds frontend/vendor/codemirror-6.js: the CodeMirror 6 modules KlippEye's editor uses (entry.js), as one script that
# sets the global CM. The sources are taken at the tags below straight from GitHub (TypeScript and plain ES modules) and
# bundled with Bun (https://bun.sh), so no npm registry is needed. Usage: bash frontend/tools/codemirror/build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../../vendor/codemirror-6.js"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# package name | GitHub repository | tag | entry file inside the repository
SOURCES="
@codemirror/state|codemirror/state|6.5.2|src/index.ts
@codemirror/view|codemirror/view|6.36.8|src/index.ts
@codemirror/language|codemirror/language|6.11.0|src/index.ts
@codemirror/commands|codemirror/commands|6.8.1|src/commands.ts
@codemirror/search|codemirror/search|6.5.10|src/search.ts
@codemirror/autocomplete|codemirror/autocomplete|6.18.6|src/index.ts
@lezer/common|lezer-parser/common|1.2.3|src/index.ts
@lezer/highlight|lezer-parser/highlight|1.2.1|src/highlight.ts
@lezer/lr|lezer-parser/lr|1.4.2|src/index.ts
style-mod|marijnh/style-mod|4.1.2|src/style-mod.js
w3c-keyname|marijnh/w3c-keyname|2.2.8|index.js
crelt|marijnh/crelt|1.0.6|index.js
@marijn/find-cluster-break|marijnh/find-cluster-break|1.0.2|src/index.js
"
for line in $SOURCES; do
  IFS="|" read -r name repo tag entry <<<"$line"
  dest="$WORK/node_modules/$name"
  git clone -q --depth 1 --branch "$tag" "https://github.com/$repo" "$dest" 2>/dev/null
  printf '{"name":"%s","version":"%s","main":"%s","module":"%s","type":"module","sideEffects":false}\n' "$name" "$tag" "$entry" "$entry" >"$dest/package.json"
  # CodeMirror's TypeScript declares fields it keeps on the prototype (RangeValue.point, …): they must not become own
  # properties set to undefined, as the "define" semantics of class fields would make them (folding breaks, for one)
  echo '{"compilerOptions":{"useDefineForClassFields":false}}' >"$dest/tsconfig.json"
done
echo '{"compilerOptions":{"useDefineForClassFields":false}}' >"$WORK/tsconfig.json"
cp "$HERE/entry.js" "$WORK/entry.js"
printf 'import * as CM from "./entry.js";\nglobalThis.CM = CM;\n' >"$WORK/iife.js"
(cd "$WORK" && bun build iife.js --minify --format=iife --target=browser --outfile="$WORK/bundle.js")
{
  echo "/* CodeMirror 6 (codemirror.net) and Lezer: @codemirror/state, view, language, commands, search, autocomplete;"
  echo "   @lezer/common, highlight, lr; style-mod, w3c-keyname, crelt, find-cluster-break. Built by frontend/tools/codemirror/build.sh."
  echo "   MIT License. Copyright (C) 2018-2021 by Marijn Haverbeke <marijn@haverbeke.berlin>, Adrian Heine <mail@adrianheine.de>, and others."
  echo "   Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation"
  echo "   files (the \"Software\"), to deal in the Software without restriction, including without limitation the rights to use, copy,"
  echo "   modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software"
  echo "   is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be"
  echo "   included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY"
  echo "   KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND"
  echo "   NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,"
  echo "   WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR"
  echo "   OTHER DEALINGS IN THE SOFTWARE. */"
  cat "$WORK/bundle.js"
} >"$OUT"
echo "wrote $OUT"
