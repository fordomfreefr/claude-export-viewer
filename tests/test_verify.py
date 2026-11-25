"""AE-m10 (15/11): "Vérifier l'archive" (verify.py): what is unreadable or missing said; conversations repaired from the
exports kept; checked before a backup and before an uninstall."""

from __future__ import annotations

import gzip
import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

from claude_export_viewer import server, verify
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.i18n import t
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_favorites import _site
from .test_topics_browser import page  # noqa: F401 - fixture
from .test_uninstall import _home


def _kept(tmp: Path) -> Path:
    """The site of test_favorites, its export kept in archive/exports/ (as fetch / drop do)."""
    site = _site(tmp)
    kept = site / "archive" / "exports" / "2026-10-22"
    kept.mkdir(parents=True)
    shutil.copy(tmp / "e.zip", kept / "conversations-000.zip")
    return site


def _lines() -> tuple[list[str], verify.Say]:
    out: list[str] = []
    return out, lambda key, args: out.append(t(key, **args))


def _break(site: Path) -> dict:
    """c1 unreadable (garbage instead of gzip), c2 missing; returns c1 as it was."""
    a = Archive(site)
    before = a.load_raw("c1")
    a.raw_path(a.conversations["c1"]).write_bytes(b"not gzip")
    a.raw_path(a.conversations["c2"]).unlink()
    return before


def test_all_readable(tmp_path: Path) -> None:
    site = _kept(tmp_path)
    out, say = _lines()
    rep = verify.check(site, say)
    assert rep.problems == 0 and rep.counts["conversations"] == 2 and rep.counts["zips"] == 1
    assert out[-1].startswith("Tout est lisible (conversations : 2, ZIP d'export : 1")


def test_problems_found_and_repaired(tmp_path: Path) -> None:
    site = _kept(tmp_path)
    before = _break(site)
    (site / "archive" / "topics.json").write_text("{pas du json", encoding="utf-8")
    bad_zip = site / "archive" / "exports" / "2026-10-01"
    bad_zip.mkdir()
    data = bytearray((tmp_path / "e.zip").read_bytes())
    data[60:70] = b"XXXXXXXXXX"  # inside the compressed data: the check sum fails
    (bad_zip / "conversations-000.zip").write_bytes(bytes(data))
    out, say = _lines()
    rep = verify.check(site, say)
    text = "\n".join(out)
    assert "Conversation illisible : « Lois stables »" in text and "Conversation manquante : « Autre »" in text
    assert "Fichier illisible :" in text and "topics.json" in text
    assert "2026-10-01" in text and ("Export abîmé" in text or "Export illisible" in text)
    assert rep.problems == 4 and sorted(rep.repairable) == ["c1", "c2"] and "réparables depuis les exports gardés : 2" in text
    out2, say2 = _lines()
    assert verify.repair(site, rep.repairable, say2) == 2
    a2 = Archive(site)
    assert a2.load_raw("c1")["chat_messages"] == before["chat_messages"] and a2.load_raw("c2")["uuid"] == "c2"
    assert any("Conversation rétablie : « Lois stables »" in x for x in out2)
    (site / "archive" / "topics.json").unlink()
    shutil.rmtree(bad_zip)
    assert verify.check(site, lambda k, a: None).problems == 0


def test_not_repairable_without_export(tmp_path: Path) -> None:
    site = _site(tmp_path)  # no export kept
    _break(site)
    out, say = _lines()
    rep = verify.check(site, say)
    assert rep.problems == 2 and rep.repairable == []
    assert "absentes des exports gardés (à reprendre d'une sauvegarde) : 2" in "\n".join(out)


def test_command_line(tmp_path: Path, capsys) -> None:
    site = _kept(tmp_path)
    capsys.readouterr()
    main(["-o", str(site), "--verifier"])
    assert "Tout est lisible" in capsys.readouterr().out
    _break(site)
    page_c1 = next(site.rglob(Archive(site).conversations["c1"]["filename"]))
    page_c1.unlink()
    main(["-o", str(site), "--reparer"])
    out = capsys.readouterr().out
    assert "Conversation rétablie : « Lois stables »" in out and "Conversation rétablie : « Autre »" in out
    assert page_c1.is_file()  # the pages made again after the repair
    assert Archive(site).load_raw("c2")["uuid"] == "c2"


def test_backup_and_uninstall_check_first(tmp_path: Path, monkeypatch) -> None:
    site = _kept(tmp_path)
    _break(site)
    home, program = _home(tmp_path, monkeypatch)  # never the real program folder (it would be removed)
    dl = tmp_path / "dl"
    dl.mkdir()
    job = server.Job("uninstall", "fr")
    ctx = SimpleNamespace(site_dir=site, launcher=program / "claude-export-viewer.py", server=None)
    server.uninstall_job(job, ctx, {"copies": [], "dest": str(dl)})
    assert job.done and not job.ok and job.extra["problems"] == 2
    assert "Rien n'a été copié ni effacé." in job.lines and (site / "archive" / "etat.json").is_file() and program.is_dir()
    monkeypatch.setattr("claude_export_viewer.fetch.user_download_dirs", lambda: [dl])
    job = server.Job("backup", "fr")
    server.backup_job(job, SimpleNamespace(site_dir=site))
    assert job.ok and any("la sauvegarde est faite quand même" in x for x in job.lines) and list(dl.glob("site-*.zip"))


def test_button_and_repair(tmp_path: Path, page) -> None:  # noqa: F811
    site = _kept(tmp_path)
    _break(site)
    srv = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    pg = page
    log = "document.getElementById('admin-log').textContent"
    try:
        pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
        pg.wait_for_selector("#tab-data:visible")
        pg.click("#tab-data")
        assert pg.inner_text("#admin-verify") == "Vérifier l'archive"
        pg.click("#admin-verify")
        pg.wait_for_selector("#verify-repair:visible", timeout=60000)
        assert "Problèmes trouvés : 2." in pg.inner_text("#admin-log")
        pg.click("#verify-repair")
        pg.click(".cev-confirm-yes")
        pg.wait_for_function(f"{log}.indexOf('Conversation rétablie') >= 0", timeout=60000)
        pg.wait_for_function(f"{log}.indexOf('✓') >= 0", timeout=60000)
        assert Archive(site).load_raw("c2")["uuid"] == "c2" and not pg.errors
    finally:
        srv.shutdown()
        srv.server_close()
