"""Backup of the whole site folder in one dated ZIP: module, command line, button of the index
(browser test skipped without Chromium)."""

import threading
import zipfile
from datetime import date
from pathlib import Path

import pytest

from claude_export_viewer import backup, fetch, settings
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_favorites import _site
from .test_topics_browser import page  # noqa: F401 - fixture

DAY = date(2026, 10, 27)


def test_backup_whole_folder(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path)
    (site / "archive" / "annotations.json.tmp").write_text("en cours", encoding="utf-8")  # being written: left out
    dest = tmp_path / "dl"
    dest.mkdir()
    out = backup.make_backup(site, dest, today=DAY)
    assert out == dest / "site-2026-10-27.zip"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert {"site/index.html", "site/archive/etat.json", "site/annotations-data.js"} <= names
        assert not any(n.endswith(".tmp") for n in names)
        # every file of the folder, identical (counter-check: the number of files matches)
        files = [p for p in site.rglob("*") if p.is_file() and not p.name.endswith(".tmp")
                 and p != site / "archive" / "verrou"]  # the lock (tests/test_concurrent.py)
        assert len(names) == len(files)
        assert z.read("site/index.html") == (site / "index.html").read_bytes()
        gz = next(i for i in z.infolist() if i.filename.endswith(".jsonl.gz"))
        assert gz.compress_type == zipfile.ZIP_STORED  # already compressed: stored as it is
        assert z.getinfo("site/index.html").compress_type == zipfile.ZIP_DEFLATED
    # unpacked elsewhere, the site opens: index and pages are there
    z2 = tmp_path / "restored"
    zipfile.ZipFile(out).extractall(z2)
    assert (z2 / "site" / "index.html").is_file() and list((z2 / "site" / "conversations").glob("*.html"))
    # a second backup the same day does not overwrite the first; no partial file left
    assert backup.make_backup(site, dest, today=DAY) == dest / "site-2026-10-27 (2).zip"
    assert not list(dest.glob("*" + backup.PART))


def test_destination(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path)
    system_dl = tmp_path / "Téléchargements"
    system_dl.mkdir()
    monkeypatch.setattr(fetch, "user_download_dirs", lambda: [system_dl])
    assert backup.destination(site) == system_dl
    chosen = tmp_path / "clé"
    chosen.mkdir()
    settings.set_downloads_folder(site, str(chosen))
    assert backup.destination(site) == chosen  # the folder chosen on the index first
    inside = site / "archive" / "exports"
    inside.mkdir(parents=True, exist_ok=True)
    settings.set_downloads_folder(site, str(inside))
    assert backup.destination(site) == system_dl  # inside the site folder: never there
    monkeypatch.setattr(fetch, "user_download_dirs", lambda: [site])
    with pytest.raises(backup.BackupError):
        backup.destination(site)
    with pytest.raises(backup.BackupError):
        backup.make_backup(site, site / "archive", today=DAY)


def test_command_line(tmp_path: Path, monkeypatch, capsys) -> None:
    site = _site(tmp_path)
    dest = tmp_path / "dl"
    dest.mkdir()
    monkeypatch.setattr(fetch, "user_download_dirs", lambda: [dest])
    capsys.readouterr()
    main(["-o", str(site), "--sauvegarder"])
    out = capsys.readouterr().out
    made = list(dest.glob("site-*.zip"))
    assert len(made) == 1 and "Sauvegarde terminée" in out and str(made[0]) in out


def test_button(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    site = _site(tmp_path)
    dest = tmp_path / "dl"
    dest.mkdir()
    settings.set_downloads_folder(site, str(dest))
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pg = page
    try:
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.wait_for_selector("#tab-data:visible")
        assert pg.is_hidden("#admin-backup")  # 14/11: in the tab of the data, closed at the opening
        pg.click("#tab-data")
        pg.wait_for_selector("#admin-backup:visible")
        assert pg.inner_text("#admin-backup") == "Sauvegarder la Bibliothèque"  # the name of the site folder
        tiles = lambda: pg.text_content("#dash-tiles")  # noqa: E731
        assert "taille du site" in tiles() and "Sauvegarde conseillée : aucune pour l'instant" in tiles() and " Mo" in tiles()
        assert "due" in pg.get_attribute("#admin-backup", "class")  # AF-f4: the reminder in the tab of the data too
        pg.evaluate("window.cevMarker = 1")
        pg.click("#admin-backup")
        pg.wait_for_function("document.getElementById('admin-log').textContent.indexOf('Sauvegarde terminée') >= 0")
        pg.wait_for_timeout(1000)  # a wrong reload would come at once after the end
        assert pg.evaluate("window.cevMarker") == 1  # the page is not reloaded: the log stays
        made = list(dest.glob("site-*.zip"))
        assert len(made) == 1 and str(made[0]) in pg.inner_text("#admin-log")
        pg.wait_for_function("document.getElementById('admin-log').textContent.indexOf('✓ Opération terminée.') >= 0")
        assert "dernière sauvegarde : aujourd'hui" in tiles()  # updated at once
        assert "due" not in pg.get_attribute("#admin-backup", "class") and pg.locator("#dash-save-due").count() == 0
        assert backup.last_backup(site) is not None and backup.site_size(site) > 0
        assert pg.get_attribute("#admin-backup", "aria-expanded") == "true"  # the button of the frame shown
        assert pg.get_attribute("#admin-import", "aria-expanded") == "false"
        pg.click("#admin-close")  # the cross closes the frame; nothing to reload after a backup
        pg.wait_for_timeout(500)
        assert pg.is_hidden("#admin-log") and pg.evaluate("window.cevMarker") == 1
        assert not pg.errors
    finally:
        server.shutdown()
        server.server_close()


def test_first_run_hint_in_red(tmp_path: Path) -> None:
    from claude_export_viewer.archive import Archive
    from claude_export_viewer.html_builder import build_site_from_archive
    site = tmp_path / "vide"
    build_site_from_archive(Archive(site), site)  # first launch: nothing imported yet
    html = (site / "index.html").read_text(encoding="utf-8")
    # 14/11: nothing imported yet: the frame of the import, alone (no overview nor filters)
    assert 'id="admin-import"' in html and "manifest.json" in html and 'id="tab-overview"' not in html
    full = (_site(tmp_path)  / "index.html").read_text(encoding="utf-8")
    assert 'id="tab-overview"' in full and 'id="tab-filters"' in full  # counter-check: with conversations
