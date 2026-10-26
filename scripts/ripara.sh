#!/usr/bin/env bash
# Old name of scripts/repair.sh (releases before 1.3.0): services installed by them still call this file before starting.
# Kept so that they keep working; scripts/install.sh writes the new name into the service.
exec bash "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/repair.sh" "$@"
