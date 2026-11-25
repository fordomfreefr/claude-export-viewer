#!/bin/sh
# Double-click (Linux): installs CEV from this folder, makes its icon and opens the Library.
# KDE asks once whether to run it; GNOME: right-click > Run as a Program.
cd "$(dirname "$0")" || exit 1
out=$(python3 claude-export-viewer.py --installer 2>&1) && exit 0
printf "%s\n" "$out" > "${TMPDIR:-/tmp}/cev-installer.log"
msg="CEV: $(printf "%s" "$out" | tail -n 5)"
kdialog --error "$msg" 2>/dev/null || zenity --error --text="$msg" 2>/dev/null || notify-send "CEV" "$msg" 2>/dev/null || printf "%s\n" "$msg"
exit 1
