"""Desktop icon, local server lifecycle, and the index button (import a new manifest)."""

import http.client
import json
import shutil
import stat
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_export_viewer.cli import main
from claude_export_viewer.desktop import install_launcher
from claude_export_viewer.server import find_running, make_server, serve, stop_outdated

PROGRAM = Path(__file__).resolve().parents[1]  # the program folder (holds claude-export-viewer.py)
ROOT = "00000000-0000-4000-8000-000000000000"


def conv(uuid: str, text: str) -> dict:
    return {"uuid": uuid, "name": f"Conv {uuid}", "updated_at": "2026-10-20T10:00:00Z",
            "chat_messages": [{"uuid": uuid + "m", "parent_message_uuid": ROOT, "sender": "human",
                               "content": [{"type": "text", "text": text}]}]}


def setup(tmp: Path):
    """A site, a disposable copy of the program, a downloads folder and a running server."""
    prog = tmp / "prog" / "claude-export-viewer"
    shutil.copytree(PROGRAM, prog, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    z = tmp / "first.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv("c1", "premier")]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-20"])
    dl = tmp / "Téléchargements"
    dl.mkdir()
    server = make_server(site, 0, launcher=prog / "claude-export-viewer.py")
    server.ctx.downloads = lambda: dl
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return site, prog, dl, server


def request(server, method: str, path: str, headers: dict | None = None):
    port = server.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, headers={"Host": f"127.0.0.1:{port}", **(headers or {})})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, body


def token(server) -> str:
    return json.loads(request(server, "GET", "/__cev__/token")[1])["token"]


def run_job(server, path: str, timeout: float = 120) -> dict:
    tok = token(server)
    status, _ = request(server, "POST", path, {"X-CEV-Token": tok})
    assert status == 202, status
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = json.loads(request(server, "GET", "/__cev__/job", {"X-CEV-Token": tok})[1])
        if state["done"]:
            return state
        time.sleep(0.2)
    raise AssertionError("job did not finish")


# --- security ----------------------------------------------------------------


def test_actions_need_the_token_and_a_local_origin(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    try:
        assert request(server, "POST", "/__cev__/import")[0] == 403  # no token
        tok = token(server)
        port = server.server_address[1]
        assert request(server, "POST", "/__cev__/import",
                       {"X-CEV-Token": tok, "Origin": "https://evil.example"})[0] == 403  # another site
        assert request(server, "GET", "/__cev__/token", {"Host": f"evil.example:{port}"})[0] == 403  # rebinding
        assert request(server, "POST", "/__cev__/import", {"X-CEV-Token": "wrong"})[0] == 403
        assert request(server, "POST", "/__cev__/update", {"X-CEV-Token": tok})[0] == 404  # removed
        assert request(server, "GET", "/__cev__/job")[0] == 403
    finally:
        server.shutdown()


# --- import button -----------------------------------------------------------


def test_import_without_manifest_explains_what_to_do(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    try:
        state = run_job(server, "/__cev__/import")
        assert state["ok"] is False
        assert state["lines"] == [
            f"Aucun manifeste trouvé dans {dl}.",
            "1. Sur claude.ai : Paramètres > Confidentialité > Exporter les données.",
            '2. Il sera envoyé un premier e-mail d\'information "Votre exportation de données est en cours."',
            '3. Quand l\'e-mail arrive "Vos données sont prêtes à être téléchargées", '
            "cliquez sur son lien pour télécharger le manifeste.",
            "4. Revenez ici et cliquez de nouveau sur « Importer un nouveau manifeste ».",
        ]
    finally:
        server.shutdown()


def test_import_button_runs_the_whole_manifest_workflow(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    created = datetime.now(timezone.utc) - timedelta(hours=1)
    (dl / "manifest-x.json").write_text(json.dumps({"created_at": created.isoformat(), "data_files": [
        {"category": "conversations", "filename": "conversations-000.zip", "export_url": "https://claude.ai/x"}]}), encoding="utf-8")
    with zipfile.ZipFile(dl / "conversations-000 (1).zip", "w") as f:
        f.writestr("conversations.json", json.dumps([conv("c1", "premier"), conv("c2", "nouveau")]))
    try:
        state = run_job(server, "/__cev__/import")
        out = "\n".join(state["lines"])
        assert state["ok"] is True, out
        assert "déjà téléchargé" in out and "1 nouvelle," in out
        assert (site / "conversations" / "c2.html").is_file()
        assert not (dl / "conversations-000 (1).zip").exists()  # stored in the archive
    finally:
        server.shutdown()


def test_only_one_job_at_a_time(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    try:
        server.ctx.start_job("x", lambda job, ctx: time.sleep(1.5) or job.finish(True))
        tok = token(server)
        assert request(server, "POST", "/__cev__/import", {"X-CEV-Token": tok})[0] == 409
    finally:
        server.shutdown()


# --- server lifecycle --------------------------------------------------------


def test_idle_server_stops_by_itself(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    server.shutdown()
    t = threading.Thread(target=serve, args=(site, 8650, None), kwargs={"idle_minutes": 0.01}, daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive()


def test_icon_reuses_a_running_server(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    try:
        port = server.server_address[1]
        assert find_running(site, port, tries=1) == f"http://127.0.0.1:{port}/"
        assert find_running(tmp_path / "autre", port, tries=1) is None
    finally:
        server.shutdown()


# --- desktop icon ------------------------------------------------------------


def test_desktop_icon_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bureau = home / "Bureau"
    bureau.mkdir(parents=True)
    site = tmp_path / "mon site"
    launcher = tmp_path / "prog dir" / "claude-export-viewer.py"
    written = install_launcher(site, launcher, home=home, desktop=bureau)
    menu = home / ".local/share/applications/claude-export-viewer.desktop"
    assert menu in written and (bureau / "claude-export-viewer.desktop") in written
    text = menu.read_text(encoding="utf-8")
    assert "Name=Claude Archives" in text and "Name[fr]=Archives Claude" in text
    assert f'"{launcher.resolve()}" "-o" "{site.resolve()}" "--ouvrir"' in text
    icon = home / ".local/share/icons/hicolor/scalable/apps/claude-export-viewer.svg"
    assert icon.is_file() and f"Icon={icon}" in text
    assert (bureau / "claude-export-viewer.desktop").stat().st_mode & stat.S_IXUSR


def test_index_has_only_the_import_button(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    server.shutdown()
    index = (site / "index.html").read_text(encoding="utf-8")
    assert ">Importer un nouveau manifeste</span></button>" in index
    assert "admin-update" not in index and "Mettre à jour le programme" not in index
    assert 'id="admin-close"' in index and 'id="admin-panel"' in index
    js = (site / "admin.js").read_text(encoding="utf-8")
    assert "update" not in js and 'CEV.t("web.admin.failed")' in js


def test_server_of_an_older_version_is_stopped_not_reused(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    port = server.server_address[1]
    server.ctx.program = "ancienne-version"  # as if started before a program update
    try:
        assert find_running(site, port, tries=1) is None  # not reused
        assert stop_outdated(site, port, tries=1) == [f"http://127.0.0.1:{port}/"]
        try:
            request(server, "GET", "/__cev__/ping")
        except OSError:
            pass
        else:
            raise AssertionError("the old server should have stopped")
    finally:
        server.server_close()


def test_current_server_is_left_alone(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    port = server.server_address[1]
    try:
        assert stop_outdated(site, port, tries=1) == []
        assert request(server, "GET", "/__cev__/ping")[0] == 200
        assert request(server, "POST", "/__cev__/stop")[0] == 403  # needs the token
    finally:
        server.shutdown()


def test_static_files_are_not_kept_in_the_browser_cache(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    port = server.server_address[1]
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        for path in ("/export.js", "/index.html", "/conversations/c1.html"):
            c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse()
            r.read()
            assert r.status == 200 and r.getheader("Cache-Control") == "no-cache", path
        c.request("GET", "/__cev__/ping", headers={"Host": f"127.0.0.1:{port}"})
        r = c.getresponse()
        r.read()
        assert r.getheader("Cache-Control") == "no-store"  # not doubled
        c.close()
    finally:
        server.shutdown()
