"""AE-m11 (all the conversations in Markdown), AF-m1 (b) (uninstall: copies, removal, restore), 14/11."""

from __future__ import annotations

import shutil
import threading
import zipfile
from pathlib import Path

import pytest

from claude_export_viewer import allexport, annotations, speech, uninstall
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .helpers import ExportData, build_site
from .test_admin import PROGRAM
from .test_review_fixes import ROOT, _msg
from .test_topics_browser import page  # noqa: F401 - fixture


def _site(tmp: Path) -> Path:
    site = tmp / "site"
    build_site(ExportData(conversations=[
        {"uuid": "c1", "name": "Essai [un]", "chat_messages": [_msg("q", ROOT, "human", "Bonjour"),
                                                               _msg("a", "q", "assistant", "Réponse")]},
        {"uuid": "c2", "name": "Essai [un]", "chat_messages": [_msg("q2", ROOT, "human", "Autre")]}]), site)
    data = annotations.load(site)
    data["notes"]["c1"] = {"a": {"text": "Ma note à garder", "updated": "2026-11-14T10:00:00"}}
    annotations.save(site, data)
    (site / "archive" / "exports" / "2026-11-01").mkdir(parents=True)
    with zipfile.ZipFile(site / "archive" / "exports" / "2026-11-01" / "conversations.zip", "w") as z:
        z.writestr("conversations.json", "[]")  # a readable ZIP: the uninstall checks the archive first (AE-m10)
    return site


def _home(tmp: Path, monkeypatch) -> tuple[Path, Path]:
    """A home of its own (icon, Piper), and a program folder of its own: never the real ones."""
    home = tmp / "home"
    (home / ".local/share/applications").mkdir(parents=True)
    (home / ".local/share/applications/claude-export-viewer.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")
    (home / ".local/share/cev-piper").mkdir(parents=True)
    (home / ".local/share/cev-piper/voix.onnx").write_bytes(b"v" * 100)
    monkeypatch.setenv("HOME", str(home))
    program = tmp / "prog" / "claude-export-viewer"
    shutil.copytree(PROGRAM / "src", program / "src", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(PROGRAM / "claude-export-viewer.py", program / "claude-export-viewer.py")
    speech.cache_dir().mkdir(parents=True, exist_ok=True)
    (speech.cache_dir() / "son.ogg").write_bytes(b"s")
    return home, program


def test_all_conversations_in_markdown(tmp_path: Path) -> None:
    site = _site(tmp_path)
    dest = tmp_path / "dl"
    dest.mkdir()
    out = allexport.build_all(Archive(site), site, dest, "fr")
    assert out.name.startswith("site-markdown-") and out.suffix == ".zip"
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        mds = sorted(n for n in names if n.endswith(".md") and n != "Sommaire.md")
        assert len(mds) == 2 and any(n.endswith(" (2).md") for n in mds)  # same title, same day: a number
        assert any("Ma note à garder" in z.read(n).decode() for n in mds)  # the annotations go with it
        summary = z.read("Sommaire.md").decode()
    assert "conversations : 2" in summary and "[Essai \\[un\\]](<" in summary and summary.count("](<") == 2


def test_uninstall_copies_then_removes_and_the_backup_restores(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path)
    home, program = _home(tmp_path, monkeypatch)
    entries = uninstall.targets(site, program, home)
    keys = [e["key"] for e in entries]
    assert keys[:2] == ["site", "program"] and "icon" in keys and "piper" in keys and "sounds" in keys
    with pytest.raises(uninstall.UninstallError):  # the copies never go where things are removed
        uninstall.check_dest(site / "copies", site, program)
    (tmp_path / "dl").mkdir()
    (tmp_path / "dl" / "fichier").write_text("x", encoding="utf-8")
    with pytest.raises(uninstall.UninstallError):  # a copy that fails stops everything (nothing removed then)
        uninstall.make_copies(Archive(site), site, tmp_path / "dl" / "fichier", ["exports"], lambda k, a: None,
                              program=program)
    real = uninstall.backup_count
    monkeypatch.setattr(uninstall, "backup_count", lambda z: 0)  # a ZIP of the site missing conversations
    with pytest.raises(uninstall.UninstallError) as err:
        uninstall.make_copies(Archive(site), site, tmp_path / "dl" / "bad", ["site"], lambda k, a: None, program=program)
    assert err.value.key == "uninstall.copy_incomplete"
    monkeypatch.setattr(uninstall, "backup_count", real)
    dest = tmp_path / "dl" / "CEV-sauvegarde"
    said = []
    written = uninstall.make_copies(Archive(site), site, dest, list(uninstall.COPIES),
                                    lambda key, args: said.append(key), program=program, lang="fr")
    names = sorted(p.name for p in written)
    assert "exports-claude.ai" in names and "LISEZMOI.txt" in names and "uninstall.copy_checked" in said
    assert any(n.startswith("site-markdown-") for n in names)
    site_zip = next(p for p in written if p.name.startswith("site-") and "markdown" not in p.name)
    readme = (dest / "LISEZMOI.txt").read_text(encoding="utf-8")
    assert "--installer" in readme and f"--restaurer \"{dest}/{site_zip.name}\"" in readme
    with zipfile.ZipFile(next(p for p in written if p.name.startswith("claude-export-viewer-"))) as z:
        assert "claude-export-viewer/claude-export-viewer.py" in z.namelist()  # as given out: --installer from it
    assert uninstall.remove(entries, lambda key, args: None) == []
    assert not site.exists() and not program.exists() and not (home / ".local/share/cev-piper").exists()
    assert not (home / ".local/share/applications/claude-export-viewer.desktop").exists()
    assert dest.is_dir() and (dest / "exports-claude.ai" / "2026-11-01" / "conversations.zip").is_file()
    # the ZIP of the site puts everything back, into a folder without archive only
    again = tmp_path / "again"
    assert uninstall.restore(site_zip, again) > 0
    assert len(Archive(again).conversations) == 2 and annotations.load(again)["notes"]["c1"]["a"]["text"]
    with pytest.raises(uninstall.UninstallError):
        uninstall.restore(site_zip, again)  # never written over
    with pytest.raises(uninstall.UninstallError):
        uninstall.restore(next(p for p in written if "markdown" in p.name), tmp_path / "x")  # not a backup


def test_restore_command_then_the_archives_open(tmp_path: Path, monkeypatch) -> None:
    from claude_export_viewer import backup
    from claude_export_viewer import server as server_module
    site = _site(tmp_path)
    (tmp_path / "dl").mkdir()
    zip_path = backup.make_backup(site, tmp_path / "dl")
    opened = []
    monkeypatch.setattr(server_module, "serve",
                        lambda *a, build=None, **k: opened.append(a[0]) or build and build(lambda n, total: None))
    monkeypatch.setattr(server_module, "stop_outdated", lambda *a, **k: [])
    monkeypatch.setattr(server_module, "find_running", lambda *a, **k: None)
    target = tmp_path / "new"
    main(["-o", str(target), "--restaurer", str(zip_path), "--sans-navigateur"])
    assert opened == [target] and (target / "index.html").is_file() and len(Archive(target).conversations) == 2


def test_uninstall_from_the_index(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    site = _site(tmp_path)
    home, program = _home(tmp_path, monkeypatch)
    (tmp_path / "dl").mkdir()
    from claude_export_viewer import settings
    settings.set_downloads_folder(site, str(tmp_path / "dl"))
    server = make_server(site, 0, launcher=program / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.evaluate("localStorage.setItem('cev-theme', 'dark')")
        pg.wait_for_selector("#tab-data:visible")
        pg.click("#tab-data")
        pg.click("#admin-uninstall")
        pg.wait_for_selector("#uninstall-go")
        assert pg.is_checked("#uninstall-copy-site") and pg.is_checked("#uninstall-copy-markdown")
        assert "CEV-sauvegarde-" in pg.inner_text(".uninstall-where code")
        listed = pg.inner_text(".uninstall-list")
        assert str(site) in listed and str(program) in listed and "Lecture à voix haute" in listed
        pg.uncheck("#uninstall-copy-program")
        pg.click("#uninstall-go")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector(".uninstalled",
                             timeout=60000)
        assert pg.evaluate("localStorage.length") == 0
        copies = next((tmp_path / "dl").glob("CEV-sauvegarde-*"))
        assert (copies / "LISEZMOI.txt").is_file() and not list(copies.glob("claude-export-viewer-*.zip"))
        assert not site.exists() and not program.exists()
        # 15/11: only the top of the page stays, with the last word (the log under "Détails")
        assert pg.is_visible(".uninstalled") and "Vous pouvez fermer cet onglet" in pg.inner_text(".uninstalled")
        assert pg.is_visible(".site-header") and not pg.is_visible(".index-tabs") and not pg.is_visible("#page-nav")
    finally:
        server.shutdown()


def test_an_empty_library_offers_the_backup_found(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    """15/11: after an uninstall, the new (empty) Library finds the copy in the downloads: one click puts it back."""
    from claude_export_viewer import backup, settings
    from claude_export_viewer import server as server_module
    old = _site(tmp_path)
    copies = tmp_path / "dl" / "CEV-sauvegarde-2026-11-14"
    copies.mkdir(parents=True)
    backup.make_backup(old, copies)
    monkeypatch.setattr(server_module, "serve", lambda *a, build=None, **k: build and build(lambda n, total: None))
    monkeypatch.setattr(server_module, "stop_outdated", lambda *a, **k: [])
    monkeypatch.setattr(server_module, "find_running", lambda *a, **k: None)
    site = tmp_path / "new"
    main(["-o", str(site), "--ouvrir", "--sans-navigateur"])  # a first launch: empty
    settings.set_downloads_folder(site, str(tmp_path / "dl"))
    # a more recent backup of an empty Library (the same name, in the downloads themselves): never offered, never
    # restored (15/11: the one with the conversations is chosen)
    empty = tmp_path / "e" / "site"
    main(["-o", str(empty), "--ouvrir", "--sans-navigateur"])
    small = backup.make_backup(empty, tmp_path / "dl")
    assert small.name == next(copies.glob("*.zip")).name and uninstall.backup_count(small) == 0
    assert uninstall.find_backup(site).parent == copies
    with pytest.raises(uninstall.UninstallError) as err:
        uninstall.restore(small, tmp_path / "x")
    assert err.value.key == "restore.empty"
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.wait_for_selector("#restore-found:visible")
        assert "site-" in pg.inner_text("#restore-text")
        pg.click("#restore-go")
        pg.wait_for_selector(".conversation-item", timeout=60000)  # restored, made again, the page reloaded
        assert len(Archive(site).conversations) == 2 and annotations.load(site)["notes"]["c1"]["a"]["text"]
    finally:
        server.shutdown()


def test_the_installer_to_double_click(tmp_path: Path) -> None:
    """15/11 (AE-f6): "Installer CEV" runs --installer from its own folder (a fake python3 here); in the ZIP of the
    program, the Linux / macOS ones stay executable."""
    import os
    import stat
    import subprocess
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "python3").write_text('#!/bin/sh\necho "$PWD $*" > "$CALLS"\n', encoding="utf-8")
    (fake / "python3").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "CALLS": str(tmp_path / "calls")}
    assert subprocess.run(["sh", str(PROGRAM / "Installer CEV.sh")], cwd=tmp_path, env=env).returncode == 0
    assert (tmp_path / "calls").read_text(encoding="utf-8").strip() == f"{PROGRAM} claude-export-viewer.py --installer"
    for name in ("Installer CEV.sh", "Installer CEV.command"):
        assert (PROGRAM / name).stat().st_mode & stat.S_IXUSR
    assert "--installer" in (PROGRAM / "Installer CEV.cmd").read_text(encoding="utf-8") and b"\r\n" in (PROGRAM / "Installer CEV.cmd").read_bytes()
    program = tmp_path / "prog"
    for name in ("claude-export-viewer.py", "Installer CEV.sh"):
        (program).mkdir(exist_ok=True)
        shutil.copy2(PROGRAM / name, program / name)
    with zipfile.ZipFile(uninstall._zip_program(program, tmp_path)) as z:
        assert (z.getinfo("claude-export-viewer/Installer CEV.sh").external_attr >> 16) & stat.S_IXUSR
