"""The safe corrections of the review of 11/11 (S1 to S10)."""

from __future__ import annotations

import http.client
import json
import threading
import time
import zipfile
from pathlib import Path

from claude_export_viewer import annotations, jsonfile, topics
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .helpers import ExportData, build_site
from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def _msg(u: str, parent: str, sender: str, text: str) -> dict:
    return {"uuid": u, "parent_message_uuid": parent, "sender": sender, "created_at": "2026-10-23T10:00:00Z",
            "content": [{"type": "text", "text": text}]}


def _site(tmp: Path) -> Path:
    site = tmp / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai", "chat_messages": [
        _msg("q", ROOT, "human", "Bonjour"), _msg("a", "q", "assistant", "Réponse")]}]), site)
    return site


def test_unreadable_files_are_never_written_over(tmp_path: Path) -> None:
    """S1: an annotations or topics file that cannot be read is set aside, not taken as empty, and the index says so."""
    site = _site(tmp_path)
    annotations.change(site, {"action": "note", "conversation": "c1", "message": "q", "text": "Note précieuse"},
                       Archive(site).load_raw)
    path = site / "archive" / "annotations.json"
    damaged = path.read_text(encoding="utf-8")[:40]
    path.write_text(damaged, encoding="utf-8")
    annotations.change(site, {"action": "favorite", "conversation": "c1", "message": "q", "on": True}, Archive(site).load_raw)
    (aside,) = (site / "archive").glob("annotations.json" + jsonfile.MARK + "*")
    assert aside.read_text(encoding="utf-8") == damaged          # the user's work is still there
    (site / "archive" / "topics.json").write_text("{oops", encoding="utf-8")
    assert topics.load(site)["topics"] == [] and len(jsonfile.damaged(site)) == 2
    main(["-o", str(site), "--sans-navigateur"])
    index = (site / "index.html").read_text(encoding="utf-8")
    assert "Fichier illisible mis de côté" in index and aside.name in index


def test_cut_character_does_not_stop_the_import(tmp_path: Path) -> None:
    """S2: half of an emoji (a lone surrogate) in an export is replaced, the import goes on."""
    z = tmp_path / "e.zip"
    convo = {"uuid": "c1", "name": "Émoji \ud83d coupé", "chat_messages": [_msg("q", ROOT, "human", "fin \ud83d")]}
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([convo]))  # json escapes the lone half: "\ud83d"
    main([str(z), "-o", str(tmp_path / "site"), "--date-export", "2026-10-23", "--sans-navigateur"])
    assert len(list((tmp_path / "site" / "conversations").glob("*.html"))) == 1


def test_server_guards(tmp_path: Path) -> None:
    """S3: a long note is accepted; S4: another host name is refused (DNS rebinding), even for the pages;
    S5: no folder listing, HEAD refused on the archive."""
    site = _site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def ask(method: str, path: str, host: str = "", body: bytes | None = None, token: str = "") -> int:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.putrequest(method, path, skip_host=True)
        c.putheader("Host", host or f"127.0.0.1:{port}")
        if token:
            c.putheader("X-CEV-Token", token)
        if body is not None:
            c.putheader("Content-Length", str(len(body)))
        c.endheaders(body)
        status = c.getresponse().status
        c.close()
        return status

    try:
        assert ask("GET", "/index.html") == 200
        assert ask("GET", "/index.html", host=f"evil.example:{port}") == 403
        assert ask("GET", "/search/index.js", host=f"evil.example:{port}") == 403
        assert ask("GET", "/conversations/") == 404
        assert ask("HEAD", "/archive/etat.json") == 403
        c = http.client.HTTPConnection("127.0.0.1", port)
        c.request("GET", "/__cev__/token")
        token = json.loads(c.getresponse().read())["token"]
        note = json.dumps({"action": "note", "conversation": "c1", "message": "q", "text": "é" * 15000}).encode()
        assert ask("POST", "/__cev__/annotations", body=note, token=token) == 200
        assert len(annotations.load(site)["notes"]["c1"]["q"]["text"]) == 15000
    finally:
        server.shutdown()


def test_icons_order_boxes_and_tab_icon(tmp_path: Path, page) -> None:  # noqa: F811
    """S7: the icons of every message in one order (star, note, T); S9: the common box instead of the browser's;
    S10: the icon of CEV in the tab."""
    site = _site(tmp_path)
    annotations.change(site, {"action": "note", "conversation": "c1", "message": "q", "text": "Une note"}, Archive(site).load_raw)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html")
        pg.wait_for_selector("html.cev-server")
        pg.wait_for_timeout(300)
        orders = pg.eval_on_selector_all(".message[data-uuid] > .message-time", "ts => ts.map(t => "
                                         "[...t.querySelectorAll('.fav-star, .note-btn, .plan-add-title')].map(b => b.className.split(' ')[0]).join(' '))")
        assert set(orders) == {"fav-star note-btn plan-add-title"}
        pg.evaluate("CEV.alert('Message')")
        assert pg.inner_text("dialog.cev-confirm .cev-confirm-text") == "Message"
        pg.click("dialog.cev-confirm .cev-confirm-yes")
        assert pg.locator("dialog.cev-confirm").count() == 0
        pg.evaluate("() => { CEV.prompt('Dossier ?', '/tmp').then(v => { window.got = v; }); }")  # not awaited
        pg.fill(".cev-confirm-input", "/home/x")
        pg.keyboard.press("Enter")
        pg.wait_for_function("window.got === '/home/x'")
        assert pg.get_attribute("link[rel=icon]", "href") == "../icon.svg" and (site / "icon.svg").is_file()
        assert pg.errors == []
    finally:
        server.shutdown()


def test_first_launch_shows_the_welcome(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    """P1: the icon before any import opens an empty index with the way to start; its button imports."""
    from claude_export_viewer import server as server_module
    # (14/11: the pages are made by the server, build=…)
    monkeypatch.setattr(server_module, "serve", lambda *a, build=None, **k: build and build(lambda n, total: None))
    monkeypatch.setattr(server_module, "stop_outdated", lambda *a, **k: [])
    monkeypatch.setattr(server_module, "find_running", lambda *a, **k: None)
    site = tmp_path / "site"
    main(["-o", str(site), "--ouvrir", "--sans-navigateur"])           # stopped with an error before
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'id="welcome"' in index and "Exporter les données" in index
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        # 15/11: the scripts of the page slow to come (after an update, an import): the tab of the data is still there
        pg.route("**/dashboard.js", lambda route: (time.sleep(0.8), route.continue_()))
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.wait_for_selector("#admin-import:visible")                    # the tab of the data opened (nothing yet)
        assert not pg.is_visible(".filter-bar") and pg.locator("#welcome button:visible").count() == 0  # one import: the frame (no backup to offer here)
        assert pg.is_hidden("#admin-folders")                            # nothing to manage yet
        with pg.expect_file_chooser():                                   # no manifest yet: the window to choose
            pg.click("#admin-import")
        assert pg.errors == []
        # opened as a file (no server): the tab says why it is empty
        pg.unroute("**/dashboard.js")
        pg.goto((site / "index.html").as_uri())
        pg.wait_for_selector("#admin-noserver:visible")
        assert "icône" in pg.inner_text("#admin-noserver") and pg.is_hidden("#admin-import")
    finally:
        server.shutdown()


def test_the_import_reports_the_pages_for_a_bar() -> None:
    """15/11: the import (a program run by the server) gives the pages made again to its page, out of the log."""
    import sys

    from claude_export_viewer.server import Job, run_streaming
    job = Job("import", "fr")
    code = "print('Mise à jour'); print('\\x1fCEV-PROGRESS 3 10', flush=True); print('fin')"
    assert run_streaming([sys.executable, "-c", code], job) == 0
    state = job.state()
    assert state["progress"] == [3, 10] and state["lines"] == ["Mise à jour", "fin"]


def test_installer_places_the_program_and_never_the_site(tmp_path: Path, monkeypatch) -> None:
    """P2: --installer copies the program to ~/claude-export-viewer (replacing an earlier version, only a CEV folder,
    never one holding the site), makes the icon; run from its place, it copies nothing."""
    from claude_export_viewer import cli, install
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    unpacked = tmp_path / "dl" / "claude-export-viewer"
    (unpacked / "src").mkdir(parents=True)
    (unpacked / install.LAUNCHER).write_text("# v2", encoding="utf-8")
    (unpacked / "src" / "module.py").write_text("x = 2", encoding="utf-8")
    (unpacked / "__pycache__").mkdir()
    dest = install.target()
    assert dest == home / "claude-export-viewer"
    (dest / "src").mkdir(parents=True)
    (dest / install.LAUNCHER).write_text("# v1", encoding="utf-8")
    (dest / "src" / "old.py").write_text("x = 1", encoding="utf-8")
    monkeypatch.setattr(cli, "_program_path", lambda: unpacked / install.LAUNCHER)
    monkeypatch.setattr(cli, "_install_icon", lambda site, program: made.append((site, program)))
    made: list = []
    main(["--installer", "--sans-navigateur"])
    assert (dest / install.LAUNCHER).read_text(encoding="utf-8") == "# v2" and not (dest / "src" / "old.py").exists()
    assert not (dest / "__pycache__").exists() and not list(dest.parent.glob("claude-export-viewer.*"))
    assert made == [(home / "claude_site", dest / install.LAUNCHER)]
    assert install.place_program(dest, dest, home / "claude_site") is False      # already in its place
    other = tmp_path / "autre"
    other.mkdir()
    (other / "precieux.txt").write_text("à garder", encoding="utf-8")
    import pytest
    with pytest.raises(install.InstallError):
        install.place_program(unpacked, other, home / "claude_site")         # not a CEV folder: left alone
    with pytest.raises(install.InstallError):
        install.place_program(unpacked, dest, dest / "site")                  # the site inside: left alone
    assert (other / "precieux.txt").is_file() and (dest / install.LAUNCHER).is_file()


def test_plain_launch_without_archive_opens_the_welcome(tmp_path: Path, monkeypatch) -> None:
    """11/11: without archive nor export, the program opens the welcome (it stopped on an unclear error);
    no abbreviation of the options ("--installer" was taken for "--installer-icone")."""
    from claude_export_viewer import server as server_module
    opened: list = []
    monkeypatch.setattr(server_module, "serve",
                        lambda *a, build=None, **k: opened.append(a[0]) or build and build(lambda n, total: None))
    monkeypatch.setattr(server_module, "stop_outdated", lambda *a, **k: [])
    monkeypatch.setattr(server_module, "find_running", lambda *a, **k: None)
    site = tmp_path / "site"
    main(["-o", str(site), "--sans-navigateur"])
    assert opened == [site] and 'id="welcome"' in (site / "index.html").read_text(encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        main(["-o", str(site), "--installer-ic"])


def test_update_opens_the_browser_at_once_with_the_progress(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    """AF-m1 (14/11): opened after an update, the server answers before the pages are made again: the browser is
    opened at once on a page of progress (n / total), which opens the index at the end."""
    from claude_export_viewer import server as server_module
    site = _site(tmp_path)
    made = []
    real_make = server_module.make_server
    monkeypatch.setattr(server_module, "make_server", lambda *a, **k: made.append(real_make(*a, **k)) or made[-1])
    go, opened = threading.Event(), []

    def build(report) -> None:
        report(3, 10)
        go.wait(20)  # (the pages being made)
        report(10, 10)

    def opener(url: str) -> None:
        opened.append(url)

    threading.Thread(target=server_module.serve, args=(site, 0, opener),
                     kwargs={"launcher": PROGRAM / "claude-export-viewer.py", "build": build}, daemon=True).start()
    try:
        for _ in range(100):
            if opened:
                break
            time.sleep(0.05)
        assert opened and not go.is_set()  # the browser before the end of the build
        pg = page
        pg.goto(opened[0] + "index.html")
        pg.wait_for_function("document.getElementById('count').textContent === '3 / 10 conversations'")
        assert pg.title() == "Mise à jour de la Bibliothèque…"
        assert pg.eval_on_selector("#bar", "e => e.style.width") == "30%"
        go.set()
        pg.wait_for_selector("#conversation-list", timeout=10000)  # the index, once done
        assert pg.errors == []
    finally:
        go.set()
        if made:
            made[0].shutdown()
