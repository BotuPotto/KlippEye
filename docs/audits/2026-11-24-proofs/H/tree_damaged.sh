#!/usr/bin/env bash
# git's own copy damaged (a loose tree object left empty by a power cut right after an update: git does not fsync
# loose objects by default). repair.sh cannot list the files, ignores the error and says "All program files are intact".
R="${KE_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"; mkdir -p /tmp/zoneH
W=$(mktemp -d /tmp/zoneH/tree.XXXX)
git init -q "$W/repo" && cd "$W/repo"
mkdir -p scripts backend && cp "$R/scripts/repair.sh" scripts/ && echo 'print("backend")' > backend/klippeye_backend.py
git add -A && git -c user.name=t -c user.email=t@t commit -qm one
tree=$(git rev-parse HEAD:backend)
obj=".git/objects/${tree:0:2}/${tree:2}"
chmod u+w "$obj" && : > "$obj"                     # the tree of backend/ is now an empty file
echo 'print("bac' > backend/klippeye_backend.py     # and the backend half written
KLIPPEYE_DATA="$W/data" bash scripts/repair.sh; echo "exit $?"
echo "git ls-tree says: $(git ls-tree -r HEAD -- backend 2>&1 | head -1)"
echo "backend now: $(cat backend/klippeye_backend.py)"
