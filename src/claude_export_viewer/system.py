"""What differs between Linux, macOS and Windows: commands, child processes, console output.

Windows support is written from the documentation of Python and Windows; it has
not been tried on a Windows machine yet.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

WINDOWS = os.name == "nt"


def python_command() -> str:
    """How the user starts Python in a terminal ("py" is the launcher installed with Python on Windows)."""
    return "py" if WINDOWS else "python3"


def command_line(args: list[str]) -> str:
    """A command to copy into a terminal (cmd/PowerShell on Windows, a POSIX shell elsewhere)."""
    if not WINDOWS:
        return shlex.join(args)
    # list2cmdline quotes only blanks; cmd.exe would take > < | & ^ for redirections ("piper-tts[http]>=1.8.0")
    return " ".join(f'"{a}"' if any(c in a for c in '<>|&^') and not a.startswith('"') else subprocess.list2cmdline([a])
                    for a in args)


def console_python() -> str:
    """Python for a child process whose output is read: python.exe, even if we run under pythonw.exe."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            return str(console)
    return sys.executable


def windowless_python() -> str:
    """Python for the desktop icon: pythonw.exe on Windows (no console window opens)."""
    exe = Path(sys.executable)
    if WINDOWS and exe.name.lower() == "python.exe" and exe.with_name("pythonw.exe").exists():
        return str(exe.with_name("pythonw.exe"))
    return sys.executable


def no_window() -> dict[str, Any]:
    """Popen arguments so that a child process does not flash a console window on Windows."""
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if WINDOWS else {}


def safe_console() -> None:
    """Never stop on a character the console cannot show (a pipe on Windows is not UTF-8)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # the stream is None under pythonw.exe
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def windows_shell_folder(name: str) -> Path | None:
    """Windows: a folder of the user (Desktop, Downloads…) wherever it was moved (OneDrive, another disk).

    ``name`` is the value name in the registry of the shell folders: "Desktop", or a
    known folder id such as Downloads' "{374DE290-123F-4565-9164-39C4925E467B}".
    """
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            value, _ = winreg.QueryValueEx(k, name)
        return Path(os.path.expandvars(value))
    except (ImportError, OSError):
        return None


def pandoc_hint() -> str:
    """The command that installs Pandoc (needed for the .odt and .docx exports)."""
    if WINDOWS:
        return "winget install --source winget --exact --id JohnMacFarlane.Pandoc"
    if sys.platform == "darwin":
        return "brew install pandoc"
    return "sudo apt install pandoc"


# (25/11) Types that a double click may run instead of showing (Windows runs them directly): a document of an export
# with one of these is never opened, its folder is (attachments in server._open_attachment)
RUNNABLE = frozenset(
    ".app .appimage .bash .bat .bin .cmd .com .command .cpl .csh .desktop .exe .hta .jar .js .jse .ksh .lnk .msi "
    ".msp .pif .pl .ps1 .psm1 .py .pyw .reg .run .scpt .scr .sh .url .vb .vbe .vbs .workflow .wsf .wsh .zsh".split())


def runnable(path: Path) -> bool:
    """True when a double click on ``path`` could run it (by its extension)."""
    return Path(path).suffix.lower() in RUNNABLE


def open_file(path: Path) -> None:
    """Open a file with the program the computer associates with it (like a double click)."""
    if WINDOWS:
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        return
    command = ["open" if sys.platform == "darwin" else "xdg-open", str(path)]
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def install_hint() -> str:
    """The command that installs the libraries needed by the program."""
    if WINDOWS:
        return "py -m pip install jinja2 mistune pydantic pygments"
    if sys.platform == "darwin":
        return "python3 -m pip install jinja2 mistune pydantic pygments"
    return "sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments"


# --- Choosing a folder (the ZIP of an export) ------------------------------------------
#
# The window of the system itself: kdialog (Plasma) or zenity (GNOME and others) on Linux,
# "choose folder" on macOS, the folder dialog of Windows Forms (PowerShell) on Windows; else the
# Tk dialog of Python when it is installed. Each in a child process: the server is not blocked
# for the other requests. Windows and macOS: written from their documentation, not tried yet.

_TK_SCRIPT = (
    "import sys, tkinter, tkinter.filedialog as f\n"
    "r = tkinter.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "p = f.askdirectory(initialdir=sys.argv[1], title=sys.argv[2], mustexist=True)\n"
    "sys.stdout.write(p or '')\n"
)


def _folder_commands(start: str, title: str) -> list[list[str]]:
    import shutil
    if WINDOWS:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
              "$d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description=$env:CEV_TITLE; "
              "$d.SelectedPath=$env:CEV_START; if($d.ShowDialog() -eq 'OK'){[Console]::Out.Write($d.SelectedPath)}")
        cmds = [["powershell", "-NoProfile", "-STA", "-Command", ps]]
    elif sys.platform == "darwin":
        script = ('POSIX path of (choose folder with prompt (system attribute "CEV_TITLE") '
                  'default location (POSIX file (system attribute "CEV_START")))')
        cmds = [["osascript", "-e", script]]
    else:
        cmds = []
        if shutil.which("kdialog"):
            cmds.append(["kdialog", "--getexistingdirectory", start, "--title", title])
        if shutil.which("zenity"):
            cmds.append(["zenity", "--file-selection", "--directory", "--filename", start.rstrip("/") + "/",
                         "--title", title])
    cmds.append([sys.executable, "-c", _TK_SCRIPT, start, title])
    return cmds


def choose_folder(start: Path, title: str) -> str | None:
    """The folder chosen in a window of the system, "" when cancelled, None when no such window
    could be shown (the page then asks for the path itself)."""
    env = {**os.environ, "CEV_START": str(start), "CEV_TITLE": title}
    for cmd in _folder_commands(str(start), title):
        if cmd[0] == sys.executable:
            try:
                import tkinter  # noqa: F401
            except ImportError:
                continue
        try:
            proc = subprocess.run(cmd, capture_output=True, env=env, timeout=1800, **no_window())
        except (OSError, subprocess.TimeoutExpired):
            continue
        out = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode == 0 and out:
            return out.rstrip("/\\") if len(out) > 1 else out
        if proc.returncode in (0, 1):  # closed or cancelled (kdialog, zenity, PowerShell, Tk: 1 or empty)
            return ""
    return None


def available_memory() -> int | None:
    """Bytes of memory free for a program now (Linux: MemAvailable; Windows: the free physical memory; elsewhere what
    os.sysconf gives), None when unknown (review of 21/11: the parts of a very long conversation follow it)."""
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    if WINDOWS:
        try:
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                return int(status.ullAvailPhys)
        except (OSError, AttributeError, ValueError):
            return None
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None  # (macOS has no free-pages count there: the default sizes are used)

