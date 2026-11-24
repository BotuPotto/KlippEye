#!/usr/bin/env bash
# A Pi whose printer folder is not ~/printer_data (KIAUH's printer_1_data, or any custom folder).
R="${KE_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"; mkdir -p /tmp/zoneH
H=$(mktemp -d /tmp/zoneH/home.XXXX); mkdir -p "$H/printer_1_data/config"
# what install.sh decides (lines 57-66), with Moonraker's answer given as KLIPPEYE_PRINTER_DATA
inst=$(HOME=$H KLIPPEYE_PRINTER_DATA=$H/printer_1_data bash -c "$(sed -n 57,66p $R/scripts/install.sh); echo \$DATA")
echo "install.sh data folder (what the services get): $inst"
# what the 'klippeye' command uses (the /usr/local/bin wrapper passes no KLIPPEYE_DATA)
HOME=$H KLIPPEYE_SYSTEMCTL=true KLIPPEYE_BACKEND_URL=http://127.0.0.1:1 bash $R/scripts/klippeye status | grep "Data and settings"
# 'klippeye password set' runs access.py with KLIPPEYE_DATA="$DATA" of the command (scripts/klippeye line 119):
echo "klippeye password writes the password into: $(HOME=$H bash -c 'if [ -d "$HOME/printer_data" ]; then echo $HOME/printer_data/klippeye; else echo $HOME/klippeye_data; fi')/access.json (the backend reads $inst)"
