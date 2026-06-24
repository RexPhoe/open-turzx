#!/usr/bin/env bash
# Install the Open-Turzx RAPL udev rule and apply it immediately.
# Run as root:  sudo bash scripts/install_rapl_access.sh
set -Eeuo pipefail

SRC="$(dirname "$(readlink -f "$0")")/99-open-turzx-rapl.rules"
DST="/etc/udev/rules.d/99-open-turzx-rapl.rules"

install -m644 "$SRC" "$DST"
udevadm control --reload
# Immediate effect for the current boot (the rule itself covers reboots).
chmod -f a+r /sys/class/powercap/intel-rapl:*/energy_uj || true

echo "Installed: $DST"
ls -l /sys/class/powercap/intel-rapl:0/energy_uj
