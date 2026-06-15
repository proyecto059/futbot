#!/usr/bin/env bash
set -euo pipefail

config=/boot/firmware/config.txt
backup="${config}.bak-$(date +%Y%m%d-%H%M%S)"

if [[ ${EUID} -ne 0 ]]; then
  printf 'Run as root: sudo %s\n' "$0" >&2
  exit 1
fi

cp -a "$config" "$backup"

python3 - "$config" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
out = []
camera_line_seen = False
overlay_seen = False

for line in lines:
    stripped = line.strip()
    if stripped.startswith("camera_auto_detect="):
        if not camera_line_seen:
            out.append("camera_auto_detect=1")
            camera_line_seen = True
        continue

    if stripped == "dtoverlay=imx219,cam0":
        continue

    if stripped == "dtoverlay=imx219":
        if not overlay_seen:
            out.append("dtoverlay=imx219")
            overlay_seen = True
        continue

    out.append(line)

if not camera_line_seen:
    out.append("camera_auto_detect=1")

if not overlay_seen:
    if out and out[-1].strip():
        out.append("")
    out.append("dtoverlay=imx219")

path.write_text("\n".join(out) + "\n")
PY

printf 'Backup: %s\n' "$backup"
grep -nE '^[[:space:]]*(camera_auto_detect|dtoverlay=imx219)' "$config"
