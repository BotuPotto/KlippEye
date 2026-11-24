#!/usr/bin/env bash
# A power cut during an update or a repair leaves .git/index.lock. The Pi has no clock of its own: after the reboot,
# until the network gives the time, the clock is behind (fake-hwclock: the time saved up to an hour before the cut).
# The lock then looks "younger than 120 s" (its age is negative) and repair.sh steps aside, though no git runs.
R="${KE_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"; mkdir -p /tmp/zoneH
W=$(mktemp -d /tmp/zoneH/lock.XXXX)
git init -q "$W/repo" && cd "$W/repo"
mkdir -p scripts frontend && cp "$R/scripts/repair.sh" scripts/ && echo '<html>dashboard</html>' > frontend/klippeye_frontend.html
git add -A && git -c user.name=t -c user.email=t@t commit -qm one
: > frontend/klippeye_frontend.html                # the half-written page
touch -d '+40 minutes' .git/index.lock             # written 40 min "in the future" of the clock at boot
pgrep -x git >/dev/null && echo "(a git process is running elsewhere: result not meaningful)"
KLIPPEYE_DATA="$W/data" bash scripts/repair.sh
echo "dashboard size after repair: $(stat -c %s frontend/klippeye_frontend.html) bytes (0 = not repaired)"
