"""Text of joined documents: whole (no 3,000-character cut), saved as files, opened by the local server."""

import json
import threading
from pathlib import Path

from claude_export_viewer import attachments, system
from claude_export_viewer.models import ChatMessage, Conversation, TextContent
from claude_export_viewer.server import make_server

from .helpers import ExportData, build_site
from .test_admin import token


def _data(*atts: dict) -> ExportData:
    return ExportData(conversations=[Conversation(uuid="c1", name="C", chat_messages=[
        ChatMessage(sender="human", content=[TextContent(text="Hi")], attachments=list(atts))])])


def test_whole_text_is_shown_and_saved(tmp_path: Path) -> None:
    long_text = "début " + "x" * 5000 + " FIN"
    out = tmp_path / "site"
    build_site(_data({"file_name": "notes.md", "extracted_content": long_text},
                     {"file_name": "court.pdf", "extracted_content": "petit"}), out)
    page = (out / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert " FIN</pre>" in page  # nothing cut
    assert "web.attachment.view_long" in page and "web.attachment.long" in page
    saved = out / "attachments" / "c1" / "notes.md"
    assert saved.read_text(encoding="utf-8") == long_text
    assert str(saved.resolve()) in page  # the path is given for long documents
    # a .pdf has only its text: .txt added, and the page says so
    assert (out / "attachments" / "c1" / "court.pdf.txt").read_text(encoding="utf-8") == "petit"
    assert page.count("web.attachment.text_only") == 1
    assert 'data-open="attachments/c1/court.pdf.txt"' in page


def test_same_name_twice_in_a_conversation(tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(_data({"file_name": "a.txt", "extracted_content": "un"},
                     {"file_name": "a.txt", "extracted_content": "deux"}), out)
    folder = out / "attachments" / "c1"
    assert (folder / "a.txt").read_text(encoding="utf-8") == "un"
    assert (folder / "a (2).txt").read_text(encoding="utf-8") == "deux"


def test_dangerous_names_stay_in_the_folder(tmp_path: Path) -> None:
    attachments.begin(tmp_path, "k")
    try:
        saved = attachments.save("../../etc/passwd", "x")
    finally:
        attachments.end()
    assert saved and tmp_path.resolve() / "attachments" / "k" in saved.path.parents
    assert attachments.save("a.txt", "x") is None  # outside a page rendering


def test_resolve_refuses_paths_outside(tmp_path: Path) -> None:
    (tmp_path / "attachments" / "k").mkdir(parents=True)
    (tmp_path / "attachments" / "k" / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    assert attachments.resolve(tmp_path, "attachments/k/a.txt") == (tmp_path / "attachments/k/a.txt").resolve()
    for bad in ("index.html", "attachments/../index.html", "attachments/k", "attachments/k/none.txt", "/etc/passwd"):
        assert attachments.resolve(tmp_path, bad) is None, bad


def test_open_route(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "site"
    build_site(_data({"file_name": "a.txt", "extracted_content": "x"}), out)
    opened: list[Path] = []
    monkeypatch.setattr(system, "open_file", opened.append)
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = json.dumps({"path": "attachments/c1/a.txt"})
        assert post(server, body, None)[0] == 403
        tok = token(server)
        assert post(server, json.dumps({"path": "index.html"}), tok)[0] == 404
        assert post(server, json.dumps({"path": "attachments/c1/../../index.html"}), tok)[0] == 404
        assert opened == []
        status, answer = post(server, body, tok)
        assert status == 200 and opened == [(out / "attachments/c1/a.txt").resolve()]
    finally:
        server.shutdown()
        server.server_close()


def post(server, body: str, tok: str | None):
    import http.client
    port = server.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
    if tok:
        headers["X-CEV-Token"] = tok
    c.request("POST", "/__cev__/open", body=body.encode(), headers=headers)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def test_repeated_injected_instructions_shown_once(tmp_path: Path) -> None:
    def block(text: str) -> dict:
        return {"type": "injected_prompt_block", "prompt": text, "injection_source": {"type": "memory_block_head"}}

    msgs = [ChatMessage.model_validate({"sender": "human", "content": [block(t), {"type": "text", "text": f"q{i}"}]})
            for i, t in enumerate(["Mémoire A", "Mémoire A", "Mémoire B", "Mémoire A"])]
    out = tmp_path / "site"
    build_site(ExportData(conversations=[Conversation(uuid="c1", name="C", chat_messages=msgs)]), out)
    page = (out / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert page.count("Mémoire A") == 1 and page.count("Mémoire B") == 1
    assert all(f"q{i}" in page for i in range(4))


def test_archive_never_served(tmp_path: Path) -> None:
    """The private archive is refused however the path is written (".." and encoded forms)."""
    import http.client
    out = tmp_path / "site"
    build_site(_data({"file_name": "a.txt", "extracted_content": "x"}), out)
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        for path in ("/archive/etat.json", "/archive", "/conversations/../archive/etat.json", "//archive/etat.json",
                     "/%2e%2e/archive/etat.json", "/x/%2e%2e/archive/etat.json", "/ARCHIVE/../archive/etat.json",
                     "/archive%2fetat.json", "/./archive/etat.json"):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            c.putrequest("GET", path, skip_host=True)
            c.putheader("Host", f"127.0.0.1:{port}")
            c.endheaders()
            r = c.getresponse()
            body = r.read()
            c.close()
            assert r.status in (403, 404) and b"conversations" not in body, (path, r.status)
        assert request_ok(port, "/index.html") and request_ok(port, "/conversations/c1.html")  # the site still served
    finally:
        server.shutdown()
        server.server_close()


def request_ok(port: int, path: str) -> bool:
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
    r = c.getresponse()
    r.read()
    c.close()
    return r.status == 200
