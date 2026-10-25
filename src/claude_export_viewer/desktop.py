"""Desktop icon: Linux (KDE, GNOME, Xfce… through the freedesktop standard) and Windows.

    python3 claude-export-viewer.py -o ~/claude_site --installer-icone

creates "Claude Archives" (translated) in the applications menu and on the desktop. A click
runs the program with --ouvrir: it starts the local server (or reuses the one
already running) and opens the index in the browser.

On Windows, shortcuts (.lnk) are written in the Start menu and on the desktop by
PowerShell; they run pythonw.exe, so no console window opens. Not tried on a
Windows machine yet.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from . import system
from .i18n import LANGUAGES, t

DESKTOP_NAME = "claude-export-viewer.desktop"
_PACKAGE_DIR = Path(__file__).parent


def _exec_quote(arg: str) -> str:
    """Quote an argument for the Exec key of a .desktop file."""
    # 1) quoting rule of the Exec key, 2) general escape rule of string values (doubles backslashes)
    quoted = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return ('"' + quoted.replace("\\", "\\\\") + '"').replace("%", "%%")


def desktop_entry(site_dir: Path, launcher: Path, icon: Path) -> str:
    exec_line = " ".join(_exec_quote(a) for a in (sys.executable, str(launcher), "-o", str(site_dir), "--ouvrir"))
    lines = ["[Desktop Entry]", "Type=Application", "Version=1.0",
             f"Name={t('desktop.name', 'en')}", f"Comment={t('desktop.comment', 'en')}"]
    # the menu and the desktop show the name in the language of the session
    for lang in LANGUAGES:
        if lang != "en":
            lines += [f"Name[{lang}]={t('desktop.name', lang)}", f"Comment[{lang}]={t('desktop.comment', lang)}"]
    lines += [f"Exec={exec_line}", f"Icon={icon}", "Terminal=false", "Categories=Office;Utility;", "StartupNotify=false"]
    return "\n".join(lines) + "\n"


def _desktop_folder(home: Path) -> Path | None:
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, encoding="utf-8",
                             errors="replace", timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            folder = Path(out.stdout.strip())
            if folder.is_dir() and folder.resolve() != home.resolve():
                return folder
    except (OSError, subprocess.SubprocessError):
        pass
    for name in ("Bureau", "Desktop"):
        if (home / name).is_dir():
            return home / name
    return None


def install_launcher(site_dir: Path, launcher: Path, home: Path | None = None,
                     desktop: Path | None | bool = True) -> list[Path]:
    """Write the icon and the menu entry (and a copy on the desktop). Returns the files written."""
    home = home or Path.home()
    site_dir, launcher = Path(site_dir).resolve(), Path(launcher).resolve()
    icon = home / ".local/share/icons/hicolor/scalable/apps/claude-export-viewer.svg"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_PACKAGE_DIR / "static" / "icon.svg", icon)
    entry = desktop_entry(site_dir, launcher, icon)
    written = [icon]

    menu = home / ".local/share/applications" / DESKTOP_NAME
    menu.parent.mkdir(parents=True, exist_ok=True)
    menu.write_text(entry, encoding="utf-8")
    menu.chmod(0o755)
    written.append(menu)

    folder = _desktop_folder(home) if desktop is True else (desktop or None)
    if folder:
        on_desktop = Path(folder) / DESKTOP_NAME
        on_desktop.write_text(entry, encoding="utf-8")
        on_desktop.chmod(0o755)  # KDE and GNOME only launch executable .desktop files
        written.append(on_desktop)
    try:
        subprocess.run(["update-desktop-database", str(menu.parent)], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass
    return written


# --- Windows ---------------------------------------------------------------------

# Values are passed through environment variables: no quoting problem with spaces,
# quotes or accents in the paths.
_PS_SHORTCUT = (
    "$ErrorActionPreference = 'Stop'; "
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CEV_LNK); "
    "$s.TargetPath = $env:CEV_TARGET; $s.Arguments = $env:CEV_ARGS; "
    "$s.WorkingDirectory = $env:CEV_DIR; $s.IconLocation = $env:CEV_ICON; "
    "$s.Description = $env:CEV_COMMENT; $s.Save()"
)


def _file_name(name: str) -> str:
    """A name usable as a Windows file name."""
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name)
    return re.sub(r"\s+", " ", clean).strip(" .") or "Claude Archives"


def windows_shortcuts(site_dir: Path, launcher: Path, icon: Path, folders: list[Path]) -> list[tuple[Path, dict[str, str]]]:
    """The shortcuts to write: (path of the .lnk, values given to PowerShell)."""
    values = {
        "CEV_TARGET": system.windowless_python(),
        "CEV_ARGS": subprocess.list2cmdline([str(launcher), "-o", str(site_dir), "--ouvrir"]),
        "CEV_DIR": str(launcher.parent),
        "CEV_ICON": f"{icon},0",
        "CEV_COMMENT": t("desktop.comment"),
    }
    name = _file_name(t("desktop.name")) + ".lnk"
    return [(folder / name, {**values, "CEV_LNK": str(folder / name)}) for folder in folders]


def install_windows(site_dir: Path, launcher: Path, run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                    env: dict[str, str] | None = None) -> list[Path]:
    """Write the icon and the shortcuts (Start menu, desktop). Returns the files written."""
    env = dict(os.environ if env is None else env)
    site_dir, launcher = Path(site_dir).resolve(), Path(launcher).resolve()
    home = Path(env.get("USERPROFILE") or Path.home())
    local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
    icon = local / "claude-export-viewer" / "icon.ico"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_PACKAGE_DIR / "static" / "icon.ico", icon)
    written = [icon]

    roaming = Path(env.get("APPDATA") or home / "AppData" / "Roaming")
    menu = roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    desktop = system.windows_shell_folder("Desktop") or home / "Desktop"
    folders = [f for f in (menu, desktop) if f.is_dir()]
    for lnk, values in windows_shortcuts(site_dir, launcher, icon, folders):
        proc = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SHORTCUT],
                   env={**env, **values}, capture_output=True, encoding="utf-8", errors="replace", timeout=60,
                   **system.no_window())
        if proc.returncode != 0:
            raise OSError(t("cli.icon.windows_failed", path=lnk, error=(proc.stderr or "").strip()[:300]))
        written.append(lnk)
    return written
