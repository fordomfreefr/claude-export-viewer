"""What changes on Windows, checked on Linux by simulating it (no Windows machine was used)."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from claude_export_viewer import desktop, system
from claude_export_viewer.markdown_export import export_filename
from claude_export_viewer.server import Job, run_streaming

from .helpers import ExportData, build_site

LAUNCHER = Path(__file__).resolve().parents[1] / "claude-export-viewer.py"


def convo() -> dict:
    return {"uuid": "c1", "name": "Test", "updated_at": "2026-10-20T10:00:00Z",
            "chat_messages": [{"uuid": "m1", "sender": "human", "content": [{"type": "text", "text": "Bonjour"}]}]}


def test_commands_shown_in_the_pages(tmp_path: Path, monkeypatch) -> None:
    linux = tmp_path / "Mes archives"
    build_site(ExportData(conversations=[convo()]), linux)
    page = (linux / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert 'data-cmd-odt="python3 ' in page
    assert f"-o &#39;{linux}&#39; --odt c1" in page or f"-o '{linux}' --odt c1" in page  # POSIX quoting

    monkeypatch.setattr(system, "WINDOWS", True)
    windows = tmp_path / "Mes archives W"
    build_site(ExportData(conversations=[convo()]), windows)
    page = (windows / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert 'data-cmd-odt="py ' in page
    assert f"-o &#34;{windows}&#34; --odt c1" in page  # cmd / PowerShell quoting "…" (escaped in the attribute)
    assert f"&#39;{windows}&#39;" not in page and f"'{windows}'" not in page


def test_command_line_quoting(monkeypatch) -> None:
    args = ["py", r"C:\Program Files\cev\claude-export-viewer.py", "-o", r"C:\Users\Dom\Mes archives", "--odt", "c1"]
    monkeypatch.setattr(system, "WINDOWS", True)
    assert system.command_line(args) == (
        r'py "C:\Program Files\cev\claude-export-viewer.py" -o "C:\Users\Dom\Mes archives" --odt c1')
    monkeypatch.setattr(system, "WINDOWS", False)
    assert system.command_line(["python3", "/home/dom/Mes archives"]) == "python3 '/home/dom/Mes archives'"


def test_python_for_child_processes(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "python.exe").write_bytes(b"")
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    assert system.console_python() == str(tmp_path / "python.exe")  # its output must be readable
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(system, "WINDOWS", True)
    assert system.windowless_python() == str(tmp_path / "pythonw.exe")  # the icon opens no console
    monkeypatch.setattr(system, "WINDOWS", False)
    assert system.windowless_python() == str(tmp_path / "python.exe")


def test_job_output_is_read_as_utf8_whatever_the_parent_setting(monkeypatch) -> None:
    # On Windows a pipe uses the ANSI code page (cp1252): simulated by a parent set to latin-1.
    monkeypatch.setenv("PYTHONIOENCODING", "latin-1")
    job = Job("import", "ja")
    code = run_streaming([sys.executable, "-c", "print('日本語 — €')"], job)
    assert code == 0 and job.lines == ["日本語 — €"]


def test_console_never_stops_on_an_unknown_character(monkeypatch) -> None:
    raw_out = io.BytesIO()
    stream = io.TextIOWrapper(raw_out, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", None)  # as under pythonw.exe
    with pytest.raises(UnicodeEncodeError):
        print("日本")  # counter-check: without the fix
    system.safe_console()
    print("é 日本")
    stream.flush()
    assert raw_out.getvalue().decode("cp1252").endswith("é ??\n")


def test_reserved_windows_names() -> None:
    assert export_filename("CON", None) == "CON_.md"
    assert export_filename("nul.txt", None) == "nul.txt_.md"
    assert export_filename("Console", None) == "Console.md"


def test_missing_library_message_is_translated_with_the_right_command() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(CEV_LANG="fr", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-S", str(LAUNCHER), "x"], capture_output=True, encoding="utf-8", env=env)
    if proc.returncode == 0 or "Module manquant" not in proc.stderr:
        pytest.skip("the libraries are reachable even without site-packages here")
    assert proc.returncode == 1
    assert "Installez les dépendances avec :" in proc.stderr
    assert system.install_hint() in proc.stderr


# --- desktop icon on Windows ---------------------------------------------------------


def windows_env(tmp_path: Path) -> dict:
    home = tmp_path / "Users" / "Dom"
    menu = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    menu.mkdir(parents=True)
    (home / "Desktop").mkdir()
    return {"USERPROFILE": str(home), "APPDATA": str(home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"), "PATH": os.environ.get("PATH", "")}


def test_windows_shortcuts(tmp_path: Path, monkeypatch) -> None:
    env = windows_env(tmp_path)
    home = Path(env["USERPROFILE"])
    calls = []

    def fake_powershell(cmd, env, **kw):
        calls.append((cmd, env, kw))
        Path(env["CEV_LNK"]).write_bytes(b"lnk")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(system, "WINDOWS", True)
    site = tmp_path / "clé USB" / "claude_site"
    written = desktop.install_windows(site, LAUNCHER, run=fake_powershell, env=env)
    icon = home / "AppData" / "Local" / "claude-export-viewer" / "icon.ico"
    menu_lnk = home / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Archives Claude.lnk"
    assert written == [icon, menu_lnk, home / "Desktop" / "Archives Claude.lnk"]
    assert icon.read_bytes()[:4] == b"\x00\x00\x01\x00"  # an .ico file
    assert len(calls) == 2
    cmd, values, kw = calls[0]
    assert cmd[0] == "powershell" and "CreateShortcut($env:CEV_LNK)" in cmd[-1]
    assert "$ErrorActionPreference = 'Stop'" in cmd[-1]
    assert values["CEV_LNK"] == str(menu_lnk)
    assert values["CEV_ARGS"] == subprocess.list2cmdline([str(LAUNCHER), "-o", str(site.resolve()), "--ouvrir"])
    assert values["CEV_ICON"] == f"{icon},0"
    assert values["CEV_COMMENT"].startswith("Consulter")
    assert kw["encoding"] == "utf-8"


def test_windows_shortcut_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    env = windows_env(tmp_path)
    monkeypatch.setattr(system, "WINDOWS", True)
    fail = lambda cmd, env, **kw: subprocess.CompletedProcess(cmd, 1, "", "Accès refusé")
    with pytest.raises(OSError, match="Impossible de créer le raccourci .*Accès refusé"):
        desktop.install_windows(tmp_path / "site", LAUNCHER, run=fail, env=env)


def test_shortcut_names_are_valid_file_names() -> None:
    assert desktop._file_name('Archives: "Claude"?') == "Archives Claude"
    assert desktop._file_name("...") == "Claude Archives"


def test_pandoc_hint_follows_the_system(monkeypatch) -> None:
    from claude_export_viewer import office_export

    monkeypatch.setattr(office_export, "pandoc_path", lambda: None)
    monkeypatch.setattr(system, "WINDOWS", True)
    with pytest.raises(office_export.PandocMissing, match="winget install .*JohnMacFarlane.Pandoc"):
        office_export.run_pandoc("x", "odt")
    monkeypatch.setattr(system, "WINDOWS", False)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(office_export.PandocMissing, match="sudo apt install pandoc"):
        office_export.run_pandoc("x", "odt")
