"""The other data of the export (extras.py, 11/11): memory (one version per export where it changed, compared),
reflections, Claude Design chats, artifacts (a version extracted when opened, served on its own port: another
origin, no Internet). The fake export copies the shapes of the user's export of 23/10/2026."""

import json
import threading
import urllib.request
import zipfile
from pathlib import Path

from claude_export_viewer import extras
from claude_export_viewer.cli import main

from .test_topics_browser import page  # noqa: F401 - fixture

ART = "7413157d-93fe-44f2-ba82-31d303916d1c"


def _zip(path: Path, files: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, (str, bytes)) else json.dumps(data))


def _export(site: Path, folder: str, profile: str) -> None:
    d = site / "archive" / "exports" / folder
    _zip(d / "memories-000.zip", {"memories/acc.json": {"account_uuid": "acc", "memory_files": [
        {"path": "/profile.md", "content": profile, "updated_at": "2026-10-22T16:22:53+00:00"},
        {"path": "/preferences.md", "content": "- écrire en français", "updated_at": "2026-10-07T17:35:31+00:00"}]}})
    _zip(d / "feedback-000.zip", {"reflections/acc.json": {"account_uuid": "acc", "feedback": [], "reflections": [
        {"content": "Un mois **chargé**.", "created_at": "2026-09-20T06:10:07+00:00", "period": "2026-08", "updated_at": ""}]}})
    _zip(d / "design_chats-000.zip", {"design_chats/9160035a-6515-486b-8ae0-af4adf316e0e.json": {
        "uuid": "9160035a-6515-486b-8ae0-af4adf316e0e", "title": "Affiche", "created_at": "2026-10-20T10:00:00+00:00",
        "updated_at": "2026-10-20T11:00:00+00:00", "project": {"name": "Projet D", "uuid": "p"}, "messages": [
            {"uuid": "m1", "role": "user", "created_at": "2026-10-20T10:00:00+00:00", "content": {
                "attachments": [{"content": "texte joint", "id": "a", "name": "notes.txt", "type": "text"}],
                "authorName": "Dom", "content": "Fais une affiche", "id": "m1", "role": "user", "timestamp": "x"}},
            {"uuid": "m2", "role": "assistant", "created_at": "2026-10-20T10:01:00+00:00", "content": {
                "content": "Voici **l'affiche**.", "contentBlocks": [{"type": "toolCall", "toolCall": {
                    "id": "t", "input": {"path": "x"}, "name": "write_file", "output": "ok", "type": "tool"}}],
                "id": "m2", "role": "assistant", "timestamp": "y", "turnInputTokens": 5}}]}})
    base = f"artifacts/{ART}/versions/v2"
    _zip(d / "frames-000.zip", {
        f"artifacts/{ART}/artifact.json": {"id": ART, "kind": "artifact", "active_version": "v2", "owner_account": "acc",
                                           "updated_at": "2026-10-21T09:00:00+00:00", "visibility": "private", "versions": [
            {"id": "v1", "title": "Premier jet", "created_at": "2026-10-20T09:00:00+00:00"},
            {"id": "v2", "title": "Affiche finale", "created_at": "2026-10-21T09:00:00+00:00"}]},
        base + ".files.json": {"files": [
            {"original_path": "index.html", "exported_as": "index.html", "mime_type": "text/html", "sha256": "a", "size_bytes": 60},
            {"original_path": "artifact-type/app.js", "exported_as": "artifact-type/app.js", "mime_type": "text/javascript", "sha256": "b", "size_bytes": 40},
            {"original_path": "../evil", "exported_as": "index.html", "mime_type": "text/plain", "sha256": "c", "size_bytes": 1}]},
        base + "/index.html": '<html><body><p id="art">artefact ouvert</p><script src="artifact-type/app.js"></script></body></html>',
        base + "/artifact-type/app.js": 'document.getElementById("art").dataset.ok = "1";',
        base + "/project/canvas.json": {"title": "Affiche", "boards": {"Main.dc.html": {"title": "Planche A", "x": 0},
                                                                       "B.dc.html": {"title": "Planche B"}},
                                        "order": ["Main.dc.html", "B.dc.html"]},
        f"artifacts/{ART}/versions/v1.files.json": {"files": []}})


def _site(tmp_path: Path) -> Path:
    z = tmp_path / "c.zip"
    _zip(z, {"conversations.json": [{"uuid": "c1", "name": "Une", "chat_messages": [
        {"uuid": "q", "sender": "human", "content": [{"type": "text", "text": "Bonjour"}]}]}]})
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-23"])
    _export(site, "2026-10-23_175235", "- prénom Dom\n- chercheur")
    _export(site, "2026-11-05_080000", "- prénom Dom\n- chercheur en mathématiques\n- joue au poker")
    later = site / "archive" / "exports" / "2026-11-05_080000"
    _zip(later / "scheduled_tasks-000.zip", {"scheduled_tasks/t.json": {"name": "Veille", "cron": "0 8 * * 1"}})
    _zip(later / "data-2024-10-23-batch-0000.zip", {"x.json": {}})   # an old single ZIP: not a category
    main(["-o", str(site)])
    return site


def test_reading_the_other_data(tmp_path: Path) -> None:
    site = _site(tmp_path)
    mem = extras.memory_versions(site)
    assert [v["date"] for v in mem] == ["2026-10-23", "2026-11-05"] and [f["path"] for f in mem[1]["files"]] == ["/preferences.md", "/profile.md"]
    diff = extras.diff_html("- chercheur", "- chercheur en mathématiques\n- poker")
    assert '<del class="ex-del">- chercheur</del>' in diff and '<ins class="ex-add">- poker</ins>' in diff
    assert [r["period"] for r in extras.reflections(site)] == ["2026-08"]           # merged over the exports
    (chat,) = extras.design_chats(site)
    assert chat["project"] == "Projet D" and [m["role"] for m in chat["messages"]] == ["human", "assistant"]
    assert chat["messages"][0]["text"] == "Fais une affiche" and chat["messages"][0]["files"][0]["name"] == "notes.txt"
    assert chat["messages"][1]["tools"][0]["name"] == "write_file"
    (art,) = extras.artifacts(site)
    v2, v1 = art.versions
    assert art.title == "Affiche finale" and v2.openable and [p for p, _ in v2.boards] == ["Main.dc.html", "B.dc.html"]
    assert [f["path"] for f in v2.files] == ["index.html", "artifact-type/app.js"]   # "../evil" refused
    assert not v1.files
    # the pages and the index
    for name in ("memory.html", "reflections.html", "design.html", "artifacts.html", f"design-{chat['uuid']}.html"):
        assert (site / "extras" / name).is_file(), name
    index = (site / "index.html").read_text(encoding="utf-8")
    assert "Autres données importées de claude.ai" in index and 'href="extras/memory.html"' in index
    assert 'href="extras/reflections.html"' in index and 'href="extras/artifacts.html"' in index
    # a category CEV does not know: found by the name of its ZIP, shown as it is (11/11)
    assert list(extras.other_categories(site)) == ["scheduled_tasks"]
    assert 'href="extras/other-scheduled_tasks.html">Scheduled tasks</a>' in index
    other = (site / "extras" / "other-scheduled_tasks.html").read_text(encoding="utf-8")
    assert "scheduled_tasks/t.json" in other and ("&#34;cron&#34;" in other or '"cron"' in other)
    page_ = (site / "extras" / f"design-{chat['uuid']}.html").read_text(encoding="utf-8")
    assert "<strong>l&#39;affiche</strong>" in page_ or "<strong>l'affiche</strong>" in page_
    assert "notes.txt" in page_ and "write_file" in page_
    # extracted when opened, then served on its own port: another origin, the Internet closed
    folder = extras.extract(site, ART, "v2")
    assert (folder / "artifact-type" / "app.js").is_file() and not (site / "extras" / "evil").exists()
    port = extras.artifact_server(folder)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html") as r:
        assert b"artefact ouvert" in r.read() and "default-src 'self'" in r.headers["Content-Security-Policy"]
    req = urllib.request.Request(f"http://127.0.0.1:{port}/index.html", headers={"Host": "evil.example"})
    try:
        urllib.request.urlopen(req)
        raise AssertionError("another host served")
    except urllib.error.HTTPError as e:
        assert e.code == 403
    for bad in (("../x", "v2"), (ART, "v1"), (ART, "nope")):
        try:
            extras.extract(site, *bad)
            raise AssertionError(bad)
        except KeyError:
            pass
    assert extras.clear_extracted(site) > 0 and not folder.exists()
    extras.stop_servers()


def test_pages_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    from claude_export_viewer.server import make_server
    site = _site(tmp_path)
    page.goto((site / "extras" / "memory.html").as_uri())
    assert page.input_value("#ex-version") == "1" and "joue au poker" in page.inner_text(".ex-version:not([hidden])")
    page.check("#ex-compare")
    assert page.locator('.ex-version:not([hidden]) ins.ex-add', has_text="joue au poker").is_visible()
    # a file unchanged from the previous export: nothing added nor removed (the loop of the files was taken
    # for the one of the versions)
    same = page.locator('.ex-version:not([hidden]) .ex-card', has_text="/preferences.md")
    assert same.locator("ins, del").count() == 0 and same.locator(".ex-same").count() == 1
    page.select_option("#ex-version", "0")
    assert page.is_disabled("#ex-compare") and "joue au poker" not in page.inner_text(".ex-version:not([hidden])")
    page.goto((site / "extras" / "artifacts.html").as_uri())                      # as a file: the server is needed
    page.click(".ex-open.admin-btn")
    assert "serveur local" in page.inner_text("#ex-status")
    server = make_server(site, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/extras/artifacts.html")
        with page.context.expect_page() as tab:
            page.click(".ex-open.admin-btn")
        art = tab.value
        art.wait_for_selector('#art[data-ok="1"]', timeout=15000)                   # its script ran
        assert art.url.startswith("http://127.0.0.1:") and str(server.server_address[1]) not in art.url.split("/")[2]
        assert art.evaluate("() => { try { return localStorage.getItem('cev-theme') === null; } catch (e) { return true; } }")
        # AF-f1 (14/11): the version extracted is shown in "Nettoyage" of the index and deleted after "Oui"
        assert extras.extracted_state(site)["count"] == 1
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        page.wait_for_selector("#tab-data:visible")
        page.click("#tab-data")
        page.click("#admin-clean")
        page.wait_for_selector("#clean-artifacts-delete")
        assert page.inner_text("#clean-artifacts").startswith("1 version d'artefact extraite")
        page.click("#clean-artifacts-delete")
        page.click(".cev-confirm-yes")
        page.wait_for_selector("#clean-artifacts:not(:has(button))")
        assert page.inner_text("#clean-artifacts").startswith("✓ 1 version effacée")
        assert extras.extracted_state(site) == {"count": 0, "size": 0}
    finally:
        server.shutdown()
        extras.stop_servers()
