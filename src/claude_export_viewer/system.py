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
    return subprocess.list2cmdline(args) if WINDOWS else shlex.join(args)


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
