"""Topics of the conversations (archive/topics.json, topics-data.js, POST /__cev__/topics)."""

import json
import threading
import zipfile
from pathlib import Path

import pytest

from claude_export_viewer import topics
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM, conv, request, token

KNOWN = {"c1", "c2", "c3"}


def change(site: Path, **request):
    return topics.change(site, request, KNOWN)


def test_assign_create_and_case(tmp_path: Path) -> None:
    s = change(tmp_path, action="assign", uuid="c1", topic="  math  ")
    assert s == {"topics": ["math"], "assign": {"c1": "math"}}
    s = change(tmp_path, action="assign", uuid="c2", topic="MATH")  # the existing topic, whatever the case
    assert s == {"topics": ["math"], "assign": {"c1": "math", "c2": "math"}}
    s = change(tmp_path, action="assign", uuid="c3", topic="Médecine   générale")
    assert s["topics"] == ["math", "Médecine générale"] and s["assign"]["c3"] == "Médecine générale"
    s = change(tmp_path, action="assign", uuid="c2", topic="")
    assert s["assign"] == {"c1": "math", "c3": "Médecine générale"}
    assert s["topics"] == ["math", "Médecine générale"]  # an unused topic stays (until deleted)
    assert topics.load(tmp_path) == s


def test_rename_merge_and_delete(tmp_path: Path) -> None:
    change(tmp_path, action="assign", uuid="c1", topic="math")
    change(tmp_path, action="assign", uuid="c2", topic="maths")
    change(tmp_path, action="assign", uuid="c3", topic="médecine")
    s = change(tmp_path, action="rename", topic="médecine", name="Médecine")  # only the case
    assert s["topics"] == ["math", "maths", "Médecine"] and s["assign"]["c3"] == "Médecine"
    s = change(tmp_path, action="rename", topic="maths", name="Math")  # into an existing topic: merged
    assert s == {"topics": ["math", "Médecine"], "assign": {"c1": "math", "c2": "math", "c3": "Médecine"}}
    s = change(tmp_path, action="delete", topic="MATH")
    assert s == {"topics": ["Médecine"], "assign": {"c3": "Médecine"}}


@pytest.mark.parametrize("request_, key", [
    ({"action": "assign", "uuid": "inconnue", "topic": "x"}, "web.topics.unknown_conversation"),
    ({"action": "assign", "uuid": "c1", "topic": "   "}, "web.topics.bad_name"),
    ({"action": "assign", "uuid": "c1", "topic": 3}, "web.topics.bad_name"),
    ({"action": "assign", "uuid": "c1", "topic": "x" * 41}, "web.topics.too_long"),
    ({"action": "rename", "topic": "absente", "name": "y"}, "web.topics.unknown_topic"),
    ({"action": "rename", "topic": "math", "name": ""}, "web.topics.bad_name"),
    ({"action": "delete", "topic": "absente"}, "web.topics.unknown_topic"),
    ({"action": "effacer-tout"}, "server.bad_request"),
])
def test_refused_changes_leave_everything_unchanged(tmp_path: Path, request_, key) -> None:
    change(tmp_path, action="assign", uuid="c1", topic="math")
    before = (tmp_path / "archive" / "topics.json").read_bytes()
    with pytest.raises(topics.TopicError) as exc:
        topics.change(tmp_path, request_, KNOWN)
    assert exc.value.key == key
    assert (tmp_path / "archive" / "topics.json").read_bytes() == before
    change(tmp_path, action="assign", uuid="c2", topic="x" * 40)  # (40 characters are accepted)


def test_broken_file_is_cleaned(tmp_path: Path) -> None:
    (tmp_path / "archive").mkdir()
    f = tmp_path / "archive" / "topics.json"
    f.write_text("{pas du json", encoding="utf-8")
    assert topics.load(tmp_path) == {"topics": [], "assign": {}}
    f.write_text(json.dumps({"topics": ["a", 3, "  ", "b"], "assign": {"c1": "a", "c2": "inconnu", "c3": 5}}), encoding="utf-8")
    assert topics.load(tmp_path) == {"topics": ["a", "b"], "assign": {"c1": "a"}}


def test_data_script_for_the_index(tmp_path: Path) -> None:
    change(tmp_path, action="assign", uuid="c1", topic="</script><b>")
    js = (tmp_path / "topics-data.js").read_text(encoding="utf-8")
    assert js.startswith("window.CEV_TOPICS = ") and "</script>" not in js
    assert json.loads(js.removeprefix("window.CEV_TOPICS = ").rstrip(";\n")) == topics.load(tmp_path)


# --- site and server -----------------------------------------------------------------


def make_site(tmp_path: Path, uuids=("c1", "c2")) -> Path:
    z = tmp_path / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv(u, "texte") for u in uuids]))
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-20"])
    return site


def post(server, body: dict | bytes, tok: str | None):
    import http.client

    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    port = server.server_address[1]
    headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json", "Content-Length": str(len(data))}
    if tok:
        headers["X-CEV-Token"] = tok
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", "/__cev__/topics", body=data, headers=headers)
    r = c.getresponse()
    out = r.status, r.read().decode("utf-8")
    c.close()
    return out


def test_index_page_has_the_topic_cells_and_filter(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    index = (site / "index.html").read_text(encoding="utf-8")
    assert index.count('<div class="topic-cell"></div>') == 2
    assert 'data-uuid="c1"' in index and 'id="filter-topic"' in index
    data, script, inline = (index.index('src="topics-data.js"'), index.index('src="topics.js"'),
                            index.index("CEVTopics.init(items)"))
    assert data < script < inline  # the data, then the code, then the page that uses them
    assert (site / "topics.js").is_file()
    assert json.loads((site / "topics-data.js").read_text(encoding="utf-8")
                      .removeprefix("window.CEV_TOPICS = ").rstrip(";\n")) == {"topics": [], "assign": {}}


def test_topics_survive_a_new_import(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    topics.change(site, {"action": "assign", "uuid": "c1", "topic": "math"}, {"c1", "c2"})
    (site / "topics-data.js").unlink()  # rewritten from the archive at every build
    make_site(tmp_path, ("c1", "c2", "c3"))
    assert topics.load(site) == {"topics": ["math"], "assign": {"c1": "math"}}
    assert '"c1": "math"' in (site / "topics-data.js").read_text(encoding="utf-8")


def test_server_route(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert post(server, {"action": "assign", "uuid": "c1", "topic": "math"}, None)[0] == 403
        assert topics.load(site)["assign"] == {}  # refused: nothing written
        tok = token(server)
        status, body = post(server, {"action": "assign", "uuid": "c1", "topic": "math"}, tok)
        assert status == 200 and json.loads(body) == {"topics": ["math"], "assign": {"c1": "math"}}
        assert post(server, {"action": "assign", "uuid": "c9", "topic": "x"}, tok) == (
            400, "Conversation introuvable dans l'archive.")
        assert post(server, {"action": "assign", "uuid": "c1", "topic": "y" * 50}, tok) == (
            400, "Nom trop long (40 caractères au plus).")
        assert post(server, b"[1, 2]", tok) == (400, "Requête invalide.")
        # the page reads the topics from the file served by the server (never from the archive)
        status, js = request(server, "GET", "/topics-data.js")
        assert status == 200 and '"c1": "math"' in js.decode("utf-8")
        assert request(server, "GET", "/archive/topics.json")[0] == 403
    finally:
        server.shutdown()


def test_files_are_always_sent_again(tmp_path: Path) -> None:
    """A file rewritten in the same second as the browser's copy must not be answered 304."""
    site = make_site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, body = request(server, "GET", "/topics-data.js", {"If-Modified-Since": "Fri, 01 Jan 2100 00:00:00 GMT"})
        assert status == 200 and body.startswith(b"window.CEV_TOPICS")
    finally:
        server.shutdown()
