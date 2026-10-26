"""The user's own copies of the files of the conversations, found on the computer and copied into the site."""

import json
import os
import threading
from pathlib import Path

from claude_export_viewer import settings, userfiles
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.html_builder import build_site_from_archive
from claude_export_viewer.models import ChatMessage, Conversation
from claude_export_viewer.server import make_server

from .helpers import ExportData, build_site
from .test_admin import request, token

CREATED = {"type": "tool_use", "name": "present_files", "input": {"filepaths": ["/mnt/user-data/outputs/plan.docx"]}}


def _conv(uuid: str, files=(), attachments=(), content=()) -> Conversation:
    return Conversation(uuid=uuid, name=uuid, chat_messages=[ChatMessage.model_validate({
        "sender": "human", "files": [{"file_name": f} for f in files],
        "attachments": [{"file_name": a, "extracted_content": "texte"} for a in attachments],
        "content": [{"type": "text", "text": "Bonjour"}, *content]})])


def _write(path: Path, data: bytes, age: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = path.stat().st_mtime - age
    os.utime(path, (t, t))
    return path


def _page(site: Path, uuid: str) -> str:
    return (site / "conversations" / f"{uuid}.html").read_text(encoding="utf-8")


def _update(site: Path, folders: list[Path]) -> int:
    archive = Archive(site)
    n = userfiles.update(archive, site, folders)
    build_site_from_archive(archive, site)
    return n


def test_names_in_a_conversation() -> None:
    raw = {"chat_messages": [{"files": [{"file_name": "photo.png"}], "attachments": [{"file_name": "a.pdf"}],
                              "content": [CREATED, {"type": "text", "text": "[Voir](computer:///mnt/user-data/outputs/sous/b.zip)"}]}]}
    assert userfiles.names_in(raw) == [["file", "photo.png"], ["attachment", "a.pdf"],
                                       ["created", "plan.docx"], ["created", "b.zip"]]


def test_found_copied_and_shown(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_conv("c1", ["photo.png"], ["rapport.pdf"], [CREATED])]), site)
    _write(dl / "vieux" / "photo.png", b"old", age=1000)
    _write(dl / "photo.png", b"new")  # the most recent of the same name wins
    _write(dl / "photo (1).png", b"variant")  # another name: never taken for photo.png
    _write(dl / "docs" / "rapport.pdf", b"%PDF")
    _write(dl / ".cache" / "plan.docx", b"hidden")  # hidden folders are skipped
    assert _update(site, [dl]) == 2
    assert (site / "files" / "c1" / "photo.png").read_bytes() == b"new"
    assert (site / "files" / "c1" / "rapport.pdf").read_bytes() == b"%PDF"
    assert not (site / "files" / "c1" / "plan.docx").exists()
    page = _page(site, "c1")
    assert '<img src="../files/c1/photo.png"' in page
    assert 'data-open="files/c1/rapport.pdf"' in page  # the icon opens the original document
    assert 'data-open="attachments/c1/rapport.pdf.txt"' not in page
    assert page.count('class="userfile-check"') == 2 and str(dl / "photo.png") in page

    # saved later (back on claude.ai): found at the next run, the others are kept
    _write(dl / "plan.docx", b"docx")
    assert _update(site, [dl]) == 1
    assert 'data-open="files/c1/plan.docx"' in _page(site, "c1")
    # a copy removed from the site is copied again from its source, even outside the folders now
    # searched, and keeps the answer given
    assert userfiles.decide(site, "c1", "photo.png", action="ok")
    (site / "files" / "c1" / "photo.png").unlink()
    _update(site, [])
    assert (site / "files" / "c1" / "photo.png").read_bytes() == b"new"
    assert userfiles.load(site)["found"]["c1"]["photo.png"]["state"] == "ok"


def test_refused_then_accepted(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_conv("c1", ["photo.png"])]), site)
    _write(dl / "a" / "photo.png", b"older", age=1000)
    _write(dl / "b" / "photo.png", b"newer")
    _update(site, [dl])
    assert userfiles.decide(site, "c1", "photo.png", action="reject")
    assert not (site / "files" / "c1" / "photo.png").exists()
    _update(site, [dl])  # the refused file is never proposed again: the other one is
    assert (site / "files" / "c1" / "photo.png").read_bytes() == b"older"
    assert userfiles.decide(site, "c1", "photo.png", action="reject")
    assert _update(site, [dl]) == 0 and 'class="userfile"' not in _page(site, "c1")
    assert not userfiles.decide(site, "c1", "photo.png", action="ok")  # nothing left to decide

    _write(dl / "c" / "photo.png", b"third")
    _update(site, [dl])
    assert userfiles.decide(site, "c1", "photo.png", action="ok")
    build_site_from_archive(Archive(site), site)
    page = _page(site, "c1")
    assert 'class="userfile"' in page and "userfile-check" not in page and 'data-action="undo"' in page
    assert userfiles.decide(site, "c1", "photo.png", action="undo")  # "Change": the question comes back
    build_site_from_archive(Archive(site), site)
    page = _page(site, "c1")
    assert "userfile-check" in page and 'data-action="undo"' not in page
    assert (site / "files" / "c1" / "photo.png").read_bytes() == b"third"


def test_same_name_in_two_conversations(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_conv("c1", ["image.png"]), _conv("c2", ["image.png"])]), site)
    _write(dl / "image.png", b"img")
    assert _update(site, [dl]) == 2
    assert (site / "files" / "c1" / "image.png").exists() and (site / "files" / "c2" / "image.png").exists()
    userfiles.decide(site, "c1", "image.png", action="reject")  # refused for one conversation only
    assert (site / "files" / "c2" / "image.png").exists()


def test_folders_setting_and_command_line(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_conv("c1", ["photo.png"])]), site)
    _write(dl / "x" / "photo.png", b"img")
    try:
        settings.set_file_folders(site, [str(tmp_path / "absent")])
        raise AssertionError("missing folder accepted")
    except ValueError:
        pass
    assert settings.set_file_folders(site, [str(dl), str(dl)]) == [dl.resolve()]
    main(["-o", str(site), "--sans-navigateur"])  # a run of the program looks for the missing files
    assert (site / "files" / "c1" / "photo.png").exists()
    assert '<img src="../files/c1/photo.png"' in _page(site, "c1")
    settings.set_file_folders(site, None)
    assert not settings.file_folders_set(site)


def _post(server, path: str, body: dict, tok: str | None):
    import http.client
    port = server.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
    if tok:
        headers["X-CEV-Token"] = tok
    c.request("POST", path, body=json.dumps(body).encode(), headers=headers)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def test_server_routes(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_conv("c1", ["photo.png"])]), site)
    _write(dl / "photo.png", b"img")
    _update(site, [dl])
    server = make_server(site, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = {"page": "c1", "name": "photo.png", "action": "ok"}
        assert _post(server, "/__cev__/file", body, None)[0] == 403
        tok = token(server)
        assert _post(server, "/__cev__/file", {**body, "name": "autre.png"}, tok)[0] == 404
        assert _post(server, "/__cev__/file", {**body, "action": "oui"}, tok)[0] == 400
        assert "userfile-check" in _page(site, "c1")
        assert _post(server, "/__cev__/file", body, tok)[0] == 200
        assert "userfile-check" not in _page(site, "c1")  # the page is regenerated at once
        assert _post(server, "/__cev__/file", {**body, "action": "undo"}, tok)[0] == 200  # "Change"
        assert "userfile-check" in _page(site, "c1")

        assert _post(server, "/__cev__/settings", {"file_folders": [str(tmp_path / "absent")]}, tok)[0] == 400
        status, answer = _post(server, "/__cev__/settings", {"file_folders": [str(dl)]}, tok)
        assert status == 200 and json.loads(answer)["file_folders"] == [str(dl.resolve())]
        got = json.loads(request(server, "GET", "/__cev__/settings", {"X-CEV-Token": tok})[1])
        assert got["file_folders"] == [str(dl.resolve())] and got["file_folders_set"] is True
    finally:
        server.shutdown()
        server.server_close()
