#!/bin/sh
# Double-click (macOS): installs CEV from this folder, makes its icon and opens the Library.
# macOS may ask to confirm (right-click > Open the first time).
cd "$(dirname "$0")" || exit 1
out=$(python3 claude-export-viewer.py --installer 2>&1) && exit 0
printf "%s\n" "$out" > "${TMPDIR:-/tmp}/cev-installer.log"
msg="CEV: $(printf "%s" "$out" | tail -n 5)"
osascript -e "display alert \"CEV\" message \"$(printf "%s" "$msg" | tr "\"" "'")\"" 2>/dev/null || printf "%s\n" "$msg"
exit 1
