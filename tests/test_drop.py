"""Files dropped on the index: pieces received by the server, checks before the import, the
import itself (real program in a subprocess) and the page (browser test skipped without Chromium)."""

import base64
import http.client
import io
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_export_viewer import drop
from claude_export_viewer.archive import Archive
from claude_export_viewer.server import Job

from .test_admin import conv, request, setup, token
from .test_topics_browser import page  # noqa: F401 - fixture

ID = "abcdefgh12345678"


def _zip(*convs: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as f:
        f.writestr("conversations.json", json.dumps(list(convs)))
    return buf.getvalue()


def _put(site: Path, name: str, data: bytes, mtime: float | None = None) -> None:
    half = len(data) // 2
    drop.receive(site, ID, name, 0, io.BytesIO(data[:half]), half, False, None)
    drop.receive(site, ID, name, half, io.BytesIO(data[half:]), len(data) - half, True, mtime)


def _manifest(created: datetime, *names: str) -> bytes:
    return json.dumps({"created_at": created.isoformat(), "data_files": [
        {"category": n.split("-")[0], "filename": n, "export_url": "https://claude.ai/x"} for n in names]}).encode()


def test_receive_pieces(tmp_path: Path) -> None:
    site = tmp_path / "site"
    data = _zip(conv("c1", "un"))
    _put(site, "conversations-000.zip", data, mtime=1_700_000_000_000 / 1000)
    got = drop.staging(site, ID) / "conversations-000.zip"
    assert got.read_bytes() == data and int(got.stat().st_mtime) == 1_700_000_000  # date of the original file
    # refused: a piece out of sequence, a path, another kind of file, a bad id
    drop.receive(site, ID, "b.zip", 0, io.BytesIO(b"abc"), 3, False, None)
    for args, key in (((ID, "b.zip", 10), "drop.bad_offset"), ((ID, "../x.zip", 0), "drop.bad_name"),
                      ((ID, "a.exe", 0), "drop.bad_name"), (("../..", "a.zip", 0), "drop.bad_request")):
        with pytest.raises(drop.DropError) as err:
            drop.receive(site, *args, io.BytesIO(b"x"), 1, True, None)
        assert err.value.key == key, args
    assert not (site / "archive" / "x.zip").exists() and not (tmp_path / "x.zip").exists()
    # sent again from the start: the piece already there is replaced
    drop.receive(site, ID, "b.zip", 0, io.BytesIO(b"xyz"), 3, True, None)
    assert (drop.staging(site, ID) / "b.zip").read_bytes() == b"xyz"
    drop.clean_all(site)
    assert not drop.depot_dir(site).exists()


def _plan(site: Path) -> tuple[list[str] | None, list[str]]:
    said: list[str] = []
    return drop.plan(site, ID, lambda key, **a: said.append(key)), said


def test_checks_before_import(tmp_path: Path) -> None:
    site = tmp_path / "site"
    # ZIPs alone: one export, stored in the archive
    _put(site, "conversations-000.zip", _zip(conv("c1", "un")))
    _put(site, "notes.json", b'{"pas": "un manifeste"}')
    args, said = _plan(site)
    assert said == ["drop.zip", "drop.not_export"]
    assert len(args) == 1 and "/archive/exports/depot-" in args[0] and Path(args[0]).is_file()
    # the same name twice: two exports mixed, refused (nothing stored)
    _put(site, "conversations-000.zip", _zip(conv("c1", "un")))
    _put(site, "conversations-000 (1).zip", _zip(conv("c1", "deux")))
    args, said = _plan(site)
    assert args is None and said[-1] == "drop.mixed"
    drop.clean_all(site)
    # parts of one export (different numbers): accepted together (counter-check of the rule above)
    _put(site, "conversations-000.zip", _zip(conv("c1", "un")))
    _put(site, "conversations-001.zip", _zip(conv("c2", "deux")))
    args, said = _plan(site)
    assert args is not None and len(args) == 2
    # two manifests: refused
    now = datetime.now(timezone.utc)
    _put(site, "manifest-a.json", _manifest(now, "conversations-000.zip"))
    _put(site, "manifest-b.json", _manifest(now, "conversations-000.zip"))
    args, said = _plan(site)
    assert args is None and said[-1] == "drop.two_manifests"
    drop.clean_all(site)
    # a manifest: with the ZIPs it lists, in the folder of that export; the others left out
    m = _manifest(now, "conversations-000.zip")
    _put(site, "manifest-a.json", m)
    _put(site, "conversations-000 (2).zip", _zip(conv("c1", "un")))
    _put(site, "projects-000.zip", _zip())
    args, said = _plan(site)
    assert said.count("drop.not_in_manifest") == 1
    stored = Path(args[0])
    assert stored.name == "manifest-a.json" and stored.parent.parent.name == "exports"
    assert (stored.parent / "conversations-000 (2).zip").is_file() and not (stored.parent / "projects-000.zip").exists()
    # nothing usable
    drop.clean_all(site)
    _put(site, "vide.json", b"[]")
    assert _plan(site) == (None, ["drop.not_export", "drop.nothing"])


def _upload(server, tok: str, name: str, data: bytes, mtime_ms: int) -> None:
    half = len(data) // 2
    for offset, piece, last in ((0, data[:half], False), (half, data[half:], True)):
        q = f"/__cev__/upload?id={ID}&name={name}&offset={offset}" + (f"&last=1&mtime={mtime_ms}" if last else "")
        port = server.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("POST", q, body=piece, headers={"Host": f"127.0.0.1:{port}", "X-CEV-Token": tok,
                                                  "Content-Type": "application/octet-stream"})
        r = c.getresponse()
        assert r.status == 200, r.read()
        c.close()


def _start(server, tok: str) -> None:
    port = server.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", "/__cev__/import-dropped", body=json.dumps({"id": ID}), headers={
        "Host": f"127.0.0.1:{port}", "X-CEV-Token": tok, "Content-Type": "application/json"})
    assert c.getresponse().status == 202
    c.close()


def _wait(server, tok: str) -> dict:
    deadline = time.time() + 120
    while time.time() < deadline:
        state = json.loads(request(server, "GET", "/__cev__/job", {"X-CEV-Token": tok})[1])
        if state["done"]:
            return state
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_drop_imports_through_the_server(tmp_path: Path) -> None:
    site, prog, dl, server = setup(tmp_path)
    tok = token(server)
    try:
        # a ZIP alone
        _upload(server, tok, "conversations-000.zip", _zip(conv("c1", "premier"), conv("c3", "déposé")),
                int(time.time() * 1000))
        _start(server, tok)
        state = _wait(server, tok)
        out = "\n".join(state["lines"])
        assert state["ok"] is True, out
        assert "c3" in Archive(site).conversations and (site / "conversations" / "c3.html").is_file()
        assert list((site / "archive" / "exports").glob("depot-*/conversations-000.zip"))  # kept in the archive
        assert not drop.depot_dir(site).exists() or not any(drop.depot_dir(site).iterdir())  # staging removed
        # a ZIP older than the manifest dropped with it: from an earlier export, left out (its
        # original date is kept: the date of the upload would let it through)
        # (an expired manifest, so that the missing ZIP is not waited for)
        created = datetime.now(timezone.utc) - timedelta(days=2)
        _upload(server, tok, "manifest-y.json", _manifest(created, "conversations-000.zip"), int(time.time() * 1000))
        _upload(server, tok, "conversations-000.zip", _zip(conv("c5", "ancien")), int((time.time() - 3 * 86400) * 1000))
        _start(server, tok)
        state = _wait(server, tok)
        assert state["ok"] is False and "c5" not in Archive(site).conversations, "\n".join(state["lines"])
        # during another job: refused, nothing written
        server.ctx.job = Job("import")
        port = server.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("POST", f"/__cev__/upload?id={ID}&name=a.zip&offset=0&last=1", body=b"x",
                  headers={"Host": f"127.0.0.1:{port}", "X-CEV-Token": tok})
        assert c.getresponse().status == 409
        c.close()
        assert not (drop.staging(site, ID) / "a.zip").exists()
        # without the token: refused
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("POST", f"/__cev__/upload?id={ID}&name=a.zip&offset=0&last=1", body=b"x",
                  headers={"Host": f"127.0.0.1:{port}"})
        assert c.getresponse().status == 403
        c.close()
    finally:
        server.shutdown()
        server.server_close()


def test_drop_on_the_page(tmp_path: Path, page) -> None:  # noqa: F811
    site, prog, dl, server = setup(tmp_path)
    created = datetime.now(timezone.utc) - timedelta(hours=1)
    files = {"manifest-x.json": _manifest(created, "conversations-000.zip"),
             "conversations-000.zip": _zip(conv("c1", "premier"), conv("c4", "glissé")),
             "photo.png": b"\x89PNG"}
    js_files = json.dumps([[n, base64.b64encode(d).decode()] for n, d in files.items()])
    pg = page
    try:
        pg.goto((site / "index.html").as_uri())  # as a file: the veil says why it cannot work
        pg.evaluate(f"""() => {{ const dt = new DataTransfer(); dt.items.add(new File(["x"], "a.zip"));
            window.dispatchEvent(new DragEvent("dragenter", {{dataTransfer: dt, cancelable: true}})); }}""")
        assert pg.inner_text(".drop-veil") == "Dépôt impossible ici : ouvrir la Bibliothèque par son icône « Bibliothèque Claude »"

        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.wait_for_selector("#tab-data:visible")  # 14/11: the frame of the import, in the tab of the data
        assert pg.is_hidden("#admin-import")
        assert pg.locator('[data-uuid="c4"]').count() == 0
        pg.evaluate(f"""() => {{
            const dt = new DataTransfer();
            for (const [name, b64] of {js_files}) {{
                const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                dt.items.add(new File([bytes], name, {{lastModified: Date.now()}}));
            }}
            window.dispatchEvent(new DragEvent("dragenter", {{dataTransfer: dt, cancelable: true}}));
            window.cevVeil = !document.querySelector(".drop-veil").hidden;
            window.dispatchEvent(new DragEvent("drop", {{dataTransfer: dt, cancelable: true}}));
        }}""")
        assert pg.evaluate("window.cevVeil") is True
        assert pg.is_visible("#admin-log")  # the tab of the data opened for the log
        pg.evaluate("window.cevMarker = 1")
        pg.wait_for_function("document.getElementById('admin-log').textContent.indexOf('Opération terminée') >= 0", timeout=60000)
        log = pg.inner_text("#admin-log")
        assert "photo.png : ni un manifeste (.json) ni un ZIP, ignoré" in log
        assert "Manifeste déposé : manifest-x.json" in log and "conversations-000.zip reçu" in log
        assert "actualisé à la fermeture de ce cadre" in log
        pg.wait_for_timeout(1000)  # a wrong reload would come at once after the end
        assert pg.evaluate("window.cevMarker") == 1 and pg.is_visible("#admin-log")  # never closed automatically
        with pg.expect_navigation():
            pg.click("#admin-close")  # closing the frame reloads the index
        pg.wait_for_selector('[data-uuid="c4"]', timeout=15000)  # with the new conversation
        assert pg.is_hidden(".drop-veil")
        assert (site / "archive" / "exports").glob("*/manifest-x.json")
        assert not pg.errors
    finally:
        server.shutdown()
        server.server_close()
