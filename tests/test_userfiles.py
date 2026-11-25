"""The user's own files, associated link by link (userfiles.py): automatic choice, choice of the
user through the local server, warnings, copies in the site and their cleaning."""

import http.client
import json
import os
import re
import threading
from pathlib import Path

from claude_export_viewer import backup, settings, userfiles
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.html_builder import build_site_from_archive
from claude_export_viewer.server import make_server

from .helpers import ExportData, build_site
from .test_admin import request, token

ROOT = "00000000-0000-4000-8000-000000000000"
OUT = "/mnt/user-data/outputs/"


def msg(uuid, parent, sender, files=(), attachments=(), content=()):
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender, "created_at": f"2026-07-01T10:{len(uuid):02d}:00Z",
            "files": [{"file_name": f} for f in files], "attachments": list(attachments),
            "content": [{"type": "text", "text": "Texte"}, *content]}


def conv(uuid, *messages):
    return {"uuid": uuid, "name": uuid, "created_at": "2026-07-01T10:00:00Z", "chat_messages": list(messages)}


def simple(uuid="c1", files=("photo.png",), attachments=()):
    return conv(uuid, msg(uuid + "h", ROOT, "human", files, attachments))


def write(path: Path, data: bytes, age: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = path.stat().st_mtime - age
    os.utime(path, (t, t))
    return path


def page(site: Path, uuid: str) -> str:
    return (site / "conversations" / f"{uuid}.html").read_text(encoding="utf-8").split('<script type="application/json"')[0]


def update(site: Path, folders: list[Path]) -> int:
    archive = Archive(site)
    n = userfiles.update(archive, site, folders)
    build_site_from_archive(archive, site)
    return n


def assoc(site: Path, uuid: str) -> dict:
    return userfiles.load(site)["assoc"][uuid]


def box(html: str, link_id: str) -> str:
    """The part of the page showing one link."""
    start = html.index(f'data-link="{link_id}"')
    return html[start:html.index('<div class="userfile"', start + 1) if '<div class="userfile"' in html[start + 1:] else None]


def test_links_of_a_conversation() -> None:
    raw = conv("c", msg("h1", ROOT, "human", ["photo.png", "photo.png"],
                        [{"file_name": "notes.md", "extracted_content": "# Notes\r\n"},
                         {"file_name": "rapport.pdf", "extracted_content": "texte du pdf"}]),
               msg("a1", "h1", "assistant", content=[
                   {"type": "tool_use", "name": "create_file", "input": {"path": OUT + "c.py", "file_text": "x"}},
                   {"type": "tool_use", "name": "bash_tool", "input": {"command": "python3 g.py > /mnt/user-data/outputs/g.png"}},
                   {"type": "tool_use", "name": "present_files", "input": {"filepaths": [OUT + "c.py", OUT + "g.png"]}}]))
    links = userfiles.links_in(raw)
    assert [x["id"] for x in links] == ["h1/file/photo.png", "h1/file/photo.png#2", "h1/attachment/notes.md",
                                        "h1/attachment/rapport.pdf", "a1/created/g.png"]  # c.py: its content is in the export
    assert links[2]["text"] == userfiles.text_hash("# Notes\n") and "text" not in links[3]  # a PDF's text is not the file


def test_automatic_association_and_copies(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[simple(attachments=[{"file_name": "rapport.pdf", "extracted_content": "t"}])]), site)
    write(dl / "vieux" / "photo.png", b"old", age=1000)
    write(dl / "photo.png", b"new")  # the most recent of the exact name wins
    write(dl / "photo (1).png", b"variant", age=-100)  # a renamed copy: offered, never taken automatically
    write(dl / ".cache" / "rapport.pdf", b"hidden")  # hidden folders are skipped
    assert update(site, [dl]) == 1
    a = assoc(site, "c1")
    photo = a["c1h/file/photo.png"]
    assert photo["how"] == "auto" and photo["status"] == "auto" and photo["source"] == str(dl / "photo.png")
    assert re.fullmatch(r"files/c1/[0-9a-f]{12}/photo\.png", photo["copy"]) and (site / photo["copy"]).read_bytes() == b"new"
    assert a["c1h/attachment/rapport.pdf"]["status"] == "none"
    html = page(site, "c1")
    b = box(html, "c1h/file/photo.png")
    assert f'<img src="../{photo["copy"]}"' in b and f'data-open="{photo["copy"]}"' in b
    assert "Associé automatiquement" in b and 'class="cf-link"' in b and 'title="Changer le fichier"' in b
    cands = json.loads(re.search(r'data-cands="([^"]*)"', b).group(1).replace("&quot;", '"'))
    assert [Path(c["path"]).name for c in cands] == ["photo (1).png", "photo.png", "photo.png"]
    assert [c["current"] for c in cands] == [False, True, False]
    r = box(html, "c1h/attachment/rapport.pdf")
    assert "Fichier d'origine non associé : l'icône ouvre le texte extrait par claude.ai" in r and 'title="Associer un fichier"' in r
    assert 'title="Ouvrir le texte extrait par claude.ai"' in r  # (22/11) no longer "Ouvrir avec le logiciel associé"
    assert 'data-open="attachments/c1/rapport.pdf.txt"' in r  # without the original, the text of the export opens

    # saved later: associated at the next run; the copy follows a more recent file of the exact name
    write(dl / "docs" / "rapport.pdf", b"%PDF")
    write(dl / "photo.png", b"newer", age=-200)
    assert update(site, [dl]) == 2
    assert (site / assoc(site, "c1")["c1h/file/photo.png"]["copy"]).read_bytes() == b"newer"
    # removed from the computer: a file found once stays associated (the site is an archive)
    (dl / "docs" / "rapport.pdf").unlink()
    update(site, [dl])
    assert assoc(site, "c1")["c1h/attachment/rapport.pdf"]["status"] == "auto"
    assert 'data-open="files/c1/' in box(page(site, "c1"), "c1h/attachment/rapport.pdf")


def test_text_documents_recognized_by_their_content(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    joined = [{"file_name": "notes.md", "extracted_content": "# Notes\nligne\n"},
              {"file_name": "plan.md", "extracted_content": "# Plan\n"}]
    build_site(ExportData(conversations=[simple(files=(), attachments=joined)]), site)
    write(dl / "notes.md", b"# Notes\nautre chose\n")  # same name, other text: the more recent
    write(dl / "notes (2).md", b"# Notes\r\nligne\r\n", age=500)  # the same text (Windows line ends), renamed
    write(dl / "plan.md", b"# Plan\nmodifi\xc3\xa9 depuis\n")
    update(site, [dl])
    a = assoc(site, "c1")
    assert a["c1h/attachment/notes.md"]["status"] == "same" and a["c1h/attachment/notes.md"]["source"] == str(dl / "notes (2).md")
    assert a["c1h/attachment/plan.md"]["status"] == "modified"
    html = page(site, "c1")
    assert "✓ Contenu identique au texte de l'export" in box(html, "c1h/attachment/notes.md")
    assert "⚠ Probablement le bon fichier, mais modifié depuis l'envoi" in box(html, "c1h/attachment/plan.md")


def _versions_and_edit():
    """photo.png sent in two successive messages, and again in an edited copy of the first one."""
    return conv("c1", msg("h1", ROOT, "human", ["photo.png"]), msg("a1", "h1", "assistant"),
                msg("h2", "a1", "human", ["photo.png"]), msg("a2", "h2", "assistant"),
                {**msg("h1bis", ROOT, "human", ["photo.png"]), "created_at": "2026-07-01T09:59:00Z"})


def test_one_file_for_successive_versions_is_surely_wrong(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_versions_and_edit()]), site)
    write(dl / "photo.png", b"img")
    update(site, [dl])
    data = userfiles.load(site)
    raw = Archive(site).load_raw("c1")
    wrong = userfiles.shared(raw, data["links"]["c1"]["list"], data["assoc"]["c1"])
    assert wrong == {"h1/file/photo.png": 2, "h2/file/photo.png": 2}  # not h1bis: another version of h1
    html = page(site, "c1")
    w = box(html, "h2/file/photo.png")
    assert "⚠ Association sûrement fausse : un même fichier pour 2 liens" in w and "Retéléchargez chaque version" in w
    assert "sûrement fausse" not in box(html, "h1bis/file/photo.png")


def test_choices_of_the_user(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_versions_and_edit()]), site)
    write(dl / "photo.png", b"v2")
    write(dl / "photo (1).png", b"v1", age=100)
    update(site, [dl])
    archive = Archive(site)
    assert userfiles.associate(archive, site, "c1", "h1/file/photo.png", "path", path=str(dl / "photo (1).png"))
    assert not userfiles.associate(archive, site, "c1", "h1/file/photo.png", "path", path=str(tmp_path / "x.png"))
    assert not userfiles.associate(archive, site, "c1", "h9/file/photo.png", "none")  # unknown link
    assert not userfiles.associate(archive, site, "c1", "h1/file/photo.png", "oui")
    assert userfiles.associate(archive, site, "c1", "h1bis/file/photo.png", "none")
    write(dl / "photo.png", b"v3", age=-100)
    update(site, [dl])  # the choices of the user are never changed by the program
    a = assoc(site, "c1")
    assert a["h1/file/photo.png"]["how"] == "user" and (site / a["h1/file/photo.png"]["copy"]).read_bytes() == b"v1"
    assert a["h1bis/file/photo.png"] == {"how": "user", "status": "user", "copy": None}
    assert (site / a["h2/file/photo.png"]["copy"]).read_bytes() == b"v3"
    html = page(site, "c1")
    mine = box(html, "h1/file/photo.png")
    assert 'data-how="user"' in mine and "cf-info" not in mine and "cf-warn" not in mine and "cf-ok" not in mine
    assert "sûrement fausse" not in box(html, "h2/file/photo.png")  # the other link now has its own file
    assert "Aucun fichier associé" in box(html, "h1bis/file/photo.png")
    # back to the automatic choice
    assert userfiles.associate(Archive(site), site, "c1", "h1/file/photo.png", "auto")
    a = assoc(site, "c1")
    assert a["h1/file/photo.png"]["how"] == "auto" and (site / a["h1/file/photo.png"]["copy"]).read_bytes() == b"v3"
    # a copy removed from the site is copied again from its source
    userfiles.associate(Archive(site), site, "c1", "h2/file/photo.png", "path", path=str(dl / "photo (1).png"))
    copy = site / assoc(site, "c1")["h2/file/photo.png"]["copy"]
    copy.unlink()
    update(site, [])
    assert copy.read_bytes() == b"v1"


def test_replaced_copy_removed_at_once(tmp_path: Path) -> None:
    """G2: the copy an automatic association leaves goes at once, unless a link still uses it."""
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[conv("c1", msg("c1h", ROOT, "human", ["photo.png", "photo.png"]))]), site)
    write(dl / "photo.png", b"v1")
    update(site, [dl])
    a = assoc(site, "c1")
    c1 = a["c1h/file/photo.png"]["copy"]
    assert a["c1h/file/photo.png#2"]["copy"] == c1
    userfiles.associate(Archive(site), site, "c1", "c1h/file/photo.png#2", "path", path=str(dl / "photo.png"))
    write(dl / "photo.png", b"v2", age=-200)
    update(site, [dl])
    a = assoc(site, "c1")
    c2 = a["c1h/file/photo.png"]["copy"]
    assert c2 != c1 and (site / c2).read_bytes() == b"v2"
    assert a["c1h/file/photo.png#2"]["how"] == "user" and (site / c1).read_bytes() == b"v1"  # the user's choice keeps it
    write(dl / "photo.png", b"v3", age=-400)
    update(site, [dl])
    c3 = assoc(site, "c1")["c1h/file/photo.png"]["copy"]
    assert (site / c3).read_bytes() == b"v3" and (site / c1).exists()
    assert not (site / c2).exists() and not (site / c2).parent.exists()  # no other link used it: removed with its folder
    assert userfiles.orphans(Archive(site), site) == []


def test_orphans_listed_and_removed(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    created = msg("a1", "c1h", "assistant", content=[
        {"type": "tool_use", "name": "create_file", "input": {"path": OUT + "f.py", "file_text": "x = 1\n"}},
        {"type": "tool_use", "name": "present_files", "input": {"filepaths": [OUT + "f.py"]}}])
    build_site(ExportData(conversations=[{**simple(), "chat_messages": [*simple()["chat_messages"], created]}]), site)
    write(site / "files" / "c1" / "photo.png", b"old format")  # a copy of the earlier program
    write(dl / "photo.png", b"a")
    write(dl / "photo (1).png", b"b")
    update(site, [dl])
    first = assoc(site, "c1")["c1h/file/photo.png"]["copy"]
    userfiles.associate(Archive(site), site, "c1", "c1h/file/photo.png", "path", path=str(dl / "photo (1).png"))
    build_site_from_archive(Archive(site), site)
    found = userfiles.orphans(Archive(site), site)
    assert sorted(rel for rel, _ in found) == sorted([first, "files/c1/photo.png"])
    claude_copy = next((site / "files").rglob("f.py"))
    assert claude_copy.relative_to(site).as_posix() not in [rel for rel, _ in found]
    assert userfiles.remove_orphans(Archive(site), site) == (2, 2 + len("old format") - 1)
    assert not (site / first).exists() and not (site / first).parent.exists()  # empty folder removed
    assert claude_copy.exists() and (site / assoc(site, "c1")["c1h/file/photo.png"]["copy"]).exists()
    assert userfiles.orphans(Archive(site), site) == []
    # a page not rendered by this version yet: its copies of Claude's files are not known, so kept
    data = userfiles.load(site)
    del data["claude"]["c1"]
    userfiles.save(site, data)
    write(site / "files" / "c1" / "_claude" / "0123456789ab" / "ancien.py", b"x")
    assert userfiles.orphans(Archive(site), site) == []


def test_earlier_state_dropped(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build_site(ExportData(conversations=[simple()]), site)
    (site / "archive" / "files.json").write_text(json.dumps({"names": {}, "found": {"c1": {"photo.png": {
        "copy": "files/c1/photo.png", "state": "ok"}}}}), encoding="utf-8")
    data = userfiles.load(site)
    assert data["format"] == 2 and data["assoc"] == {}


def test_same_name_in_two_conversations(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[simple("c1", ["image.png"]), simple("c2", ["image.png"])]), site)
    write(dl / "image.png", b"img")
    assert update(site, [dl]) == 2
    userfiles.associate(Archive(site), site, "c1", "c1h/file/image.png", "none")
    assert assoc(site, "c2")["c2h/file/image.png"]["status"] == "auto"
    assert "sûrement fausse" not in page(site, "c2")  # two conversations: not versions of one file


def test_folders_setting_and_command_line(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[simple()]), site)
    write(dl / "x" / "photo.png", b"img")
    try:
        settings.set_file_folders(site, [str(tmp_path / "absent")])
        raise AssertionError("missing folder accepted")
    except ValueError:
        pass
    assert settings.set_file_folders(site, [str(dl), str(dl)]) == [dl.resolve()]
    main(["-o", str(site), "--sans-navigateur"])  # a run of the program looks for the files
    copy = assoc(site, "c1")["c1h/file/photo.png"]["copy"]
    assert f'<img src="../{copy}"' in page(site, "c1")
    settings.set_file_folders(site, None)
    assert not settings.file_folders_set(site)


def _post(server, path: str, body, tok: str | None, ctype="application/json"):
    port = server.server_address[1]
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Host": f"127.0.0.1:{port}", "Content-Type": ctype}
    if tok:
        headers["X-CEV-Token"] = tok
    c.request("POST", path, body=body if isinstance(body, bytes) else json.dumps(body).encode(), headers=headers)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def test_server_routes(tmp_path: Path) -> None:
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[simple()]), site)
    write(dl / "photo.png", b"img")
    write(dl / "photo (1).png", b"autre")
    update(site, [dl])
    server = make_server(site, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = {"page": "c1", "link": "c1h/file/photo.png", "action": "path", "path": str(dl / "photo (1).png")}
        assert _post(server, "/__cev__/link", body, None)[0] == 403
        tok = token(server)
        assert _post(server, "/__cev__/link", {**body, "link": "c1h/file/autre.png"}, tok)[0] == 404
        assert _post(server, "/__cev__/link", {**body, "page": "c9"}, tok)[0] == 404
        assert _post(server, "/__cev__/link", {**body, "action": "oui"}, tok)[0] == 400
        assert _post(server, "/__cev__/link", {**body, "path": "/etc/passwd"}, tok)[0] == 404  # not offered by the menu
        assert "Associé automatiquement" in box(page(site, "c1"), "c1h/file/photo.png")
        assert _post(server, "/__cev__/link", body, tok)[0] == 200
        b = box(page(site, "c1"), "c1h/file/photo.png")  # the page is regenerated at once
        assert 'data-how="user"' in b and "Associé automatiquement" not in b

        # a file chosen in the browser ("Autre fichier…")
        q = "/__cev__/link-file?page=c1&link=" + "c1h%2Ffile%2Fphoto.png" + "&name=mon%20image.png"
        assert _post(server, q, b"envoi", None, "application/octet-stream")[0] == 403
        assert _post(server, q, b"envoi", tok, "application/octet-stream")[0] == 200
        e = assoc(site, "c1")["c1h/file/photo.png"]
        assert (site / e["copy"]).read_bytes() == b"envoi" and e["upload"] == "mon image.png" and e["how"] == "user"
        assert not list((site / "archive" / "depot").glob("*")) if (site / "archive" / "depot").exists() else True

        # cleaning: the copies no link uses any more
        status, data = request(server, "GET", "/__cev__/orphans", {"X-CEV-Token": tok})
        listed = json.loads(data)
        assert status == 200 and len(listed["files"]) == 2 and listed["total"] == len(b"img") + len(b"autre")
        assert request(server, "GET", "/__cev__/orphans", {})[0] == 403
        status, data = _post(server, "/__cev__/orphans", {}, tok)
        assert status == 200 and json.loads(data) == {"removed": 2, "size": 8, "site_size": backup.site_size(site)}
        assert json.loads(request(server, "GET", "/__cev__/orphans", {"X-CEV-Token": tok})[1])["files"] == []

        assert _post(server, "/__cev__/settings", {"file_folders": [str(tmp_path / "absent")]}, tok)[0] == 400
        status, answer = _post(server, "/__cev__/settings", {"file_folders": [str(dl)]}, tok)
        assert status == 200 and json.loads(answer)["file_folders"] == [str(dl.resolve())]
    finally:
        server.shutdown()
        server.server_close()


def test_menu_and_cleaning_in_a_browser(tmp_path: Path) -> None:
    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    site, dl = tmp_path / "site", tmp_path / "dl"
    build_site(ExportData(conversations=[_versions_and_edit()]), site)
    write(dl / "photo.png", b"v2")
    write(dl / "photo (1).png", b"v1", age=100)
    update(site, [dl])
    other = write(tmp_path / "ailleurs" / "choisie.png", b"choisie")
    server = make_server(site, 0, launcher=Path(__file__).resolve().parents[1] / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_api.sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # browser not installed
                pytest.skip(f"Chromium unavailable: {exc}")
            pg = browser.new_context(locale="fr-FR").new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "conversations/c1.html")
            pg.wait_for_selector("html.cev-server")
            box2 = pg.locator('[data-link="h2/file/photo.png"]')
            assert "sûrement fausse" in box2.inner_text()
            box2.locator(".cf-link").click()
            menu = box2.locator(".cf-menu")
            assert menu.is_visible() and menu.locator(".cf-opt").count() == 2
            assert "actuel" in menu.locator(".cf-cur").inner_text() and "photo.png" in menu.locator(".cf-cur").inner_text()
            assert menu.locator(".cf-auto").count() == 0  # automatic: nothing to go back to
            pg.keyboard.press("Escape")
            assert box2.locator(".cf-menu").count() == 0
            box2.locator(".cf-link").click()
            with pg.expect_navigation():
                menu.locator(".cf-opt", has_text="photo (1).png").click()  # a renamed copy
            box2 = pg.locator('[data-link="h2/file/photo.png"]')
            assert box2.get_attribute("data-how") == "user" and box2.locator(".cf-info, .cf-warn").count() == 0
            assert "sûrement fausse" not in pg.locator('[data-link="h1/file/photo.png"]').inner_text()

            box1 = pg.locator('[data-link="h1/file/photo.png"]')
            box1.locator(".cf-link").click()
            with pg.expect_navigation():
                box1.locator(".cf-menu input[type=file]").set_input_files(str(other))  # "Autre fichier…"
            e = assoc(site, "c1")["h1/file/photo.png"]
            assert (site / e["copy"]).read_bytes() == b"choisie" and e["upload"] == "choisie.png"
            box1 = pg.locator('[data-link="h1/file/photo.png"]')
            box1.locator(".cf-link").click()
            assert box1.locator(".cf-auto").count() == 1
            with pg.expect_navigation():
                box1.locator(".cf-none").click()
            assert "Aucun fichier associé" in pg.locator('[data-link="h1/file/photo.png"]').inner_text()

            pg.goto(base + "index.html")
            pg.wait_for_selector("#tab-data:visible")
            pg.click("#tab-data")
            pg.click("#admin-clean")
            pg.wait_for_selector("#clean-delete")
            assert "1 fichier inutilisé" in pg.locator("#clean-panel").inner_text()
            # a frame at the bottom of the data frame, after the others, with its title and its cross
            assert pg.evaluate("() => { const ids = [...document.querySelectorAll('#admin-bar .admin-bar > *')].map(e => e.id);"
                               " return ids.indexOf('clean-panel') === ids.length - 3 && ids[ids.length - 2] === 'annot-panel' && ids[ids.length - 1] === 'uninstall-panel' && ids.indexOf('admin-panel') >= 0; }")
            assert "Libérer de la place" in pg.inner_text("#clean-panel .clean-head")
            before = int(pg.get_attribute("#dash-tiles", "data-size"))
            assert before == backup.site_size(site)  # measured by the server when the index opens
            pg.click("#clean-delete")
            pg.wait_for_function("() => document.getElementById('clean-panel').textContent.includes('Opération terminée')")
            assert "✓ Opération terminée : 1 fichier supprimé" in pg.inner_text("#clean-body")
            after = int(pg.get_attribute("#dash-tiles", "data-size"))  # the overview follows the cleaning
            assert after == backup.site_size(site) < before
            pg.wait_for_timeout(1000)
            assert pg.is_visible("#clean-panel")  # stays until closed
            pg.click("#clean-close")
            assert pg.is_hidden("#clean-panel") and pg.get_attribute("#admin-clean", "aria-expanded") == "false"
            pg.click("#admin-clean")  # opened again: nothing left
            pg.wait_for_function("() => document.getElementById('clean-body').textContent.includes('rien à supprimer')")
            assert userfiles.orphans(Archive(site), site) == []
            # "Rechercher maintenant": closing its log reloads the index and leaves the other frames open (11/11)
            pg.click("#files-search")
            pg.wait_for_function("() => /Opération( non)? terminée/.test(document.getElementById('admin-log').textContent)")
            assert 'non terminée' not in pg.inner_text('#admin-log')
            with pg.expect_navigation():
                pg.click("#admin-close")
            pg.wait_for_selector("#clean-panel:not([hidden])")
            assert pg.is_hidden("#admin-panel")
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
