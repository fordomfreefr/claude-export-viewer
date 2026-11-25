"""Favorite messages: archive/annotations.json, the server, the pages (browser tests skipped
without Chromium)."""

import json
import threading
import zipfile
from pathlib import Path

import pytest

from claude_export_viewer import annotations
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"
LONG = "Remplissage de la réponse.\n\n" * 60


def _site(tmp: Path) -> Path:
    msgs = [{"uuid": "q1", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-10-20T10:00:00Z",
             "content": [{"type": "text", "text": "Quelle est la loi   stable ?"}]},
            {"uuid": "a1", "parent_message_uuid": "q1", "sender": "assistant", "created_at": "2026-10-20T10:01:00Z",
             "content": [{"type": "text", "text": LONG + "Fin de la réponse un."}]},
            {"uuid": "q2", "parent_message_uuid": "a1", "sender": "human", "created_at": "2026-10-20T10:02:00Z",
             "content": [{"type": "text", "text": "Deuxième question " + "x" * 300}]},
            {"uuid": "a2", "parent_message_uuid": "q2", "sender": "assistant", "created_at": "2026-10-20T10:03:00Z",
             "content": [{"type": "text", "text": LONG}]}]
    other = {"uuid": "c2", "name": "Autre", "created_at": "2026-10-21T10:00:00Z",
             "chat_messages": [{"uuid": "z1", "parent_message_uuid": ROOT, "sender": "human",
                                "content": [{"type": "text", "text": "Rien"}]}]}
    z = tmp / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([
            {"uuid": "c1", "name": "Lois stables", "created_at": "2026-10-20T10:00:00Z", "chat_messages": msgs}, other]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-22"])
    return site


def test_change_and_checks(tmp_path: Path) -> None:
    site = _site(tmp_path)
    assert (site / "annotations-data.js").read_text(encoding="utf-8") == ('window.CEV_ANNOTATIONS = {"favorites": {}, "links": {}, "series": [], '
                                                                        '"notes": {}, "titles": {}, "marks": {}, "moves": {}, "relations": {}, "structure_history": {}, "convs": {}};\n')
    load_raw = Archive(site).load_raw
    state = annotations.change(site, {"action": "favorite", "conversation": "c1", "message": "q1", "on": True}, load_raw)
    entry = state["favorites"]["c1"]["q1"]
    assert entry["sender"] == "human" and entry["date"].startswith("2026-10-20T10:00:00")
    assert entry["excerpt"] == "Quelle est la loi stable ?"  # spaces collapsed
    long = annotations.change(site, {"action": "favorite", "conversation": "c1", "message": "q2", "on": True},
                              load_raw)["favorites"]["c1"]["q2"]["excerpt"]
    assert len(long) == annotations.EXCERPT and long.endswith("…")
    # kept in the archive, and in the script read by the pages
    saved = json.loads((site / "archive" / "annotations.json").read_text(encoding="utf-8"))
    assert set(saved["favorites"]["c1"]) == {"q1", "q2"}
    assert '"q2"' in (site / "annotations-data.js").read_text(encoding="utf-8")
    # refused: a message or a conversation not in the archive, a broken request; nothing changed
    for bad, key in (({"conversation": "c1", "message": "nope", "on": True}, "web.fav.unknown_message"),
                     ({"conversation": "c9", "message": "q1", "on": True}, "web.fav.unknown_message"),
                     ({"conversation": "c1", "message": "q1", "on": "oui"}, "web.fav.bad_request"),
                     ({"conversation": "c1", "message": "z1", "on": True}, "web.fav.unknown_message")):
        with pytest.raises(annotations.AnnotationError) as err:
            annotations.change(site, {"action": "favorite", **bad}, load_raw)
        assert err.value.key == key, bad
    assert set(annotations.load(site)["favorites"]["c1"]) == {"q1", "q2"}
    # removed; the last one removes the conversation
    annotations.change(site, {"action": "favorite", "conversation": "c1", "message": "q1", "on": False}, load_raw)
    state = annotations.change(site, {"action": "favorite", "conversation": "c1", "message": "q2", "on": False}, load_raw)
    assert state["favorites"] == {}
    # a rebuild of the site keeps them
    annotations.change(site, {"action": "favorite", "conversation": "c1", "message": "a1", "on": True}, load_raw)
    main(["-o", str(site)])
    assert '"a1"' in (site / "annotations-data.js").read_text(encoding="utf-8")
    # a broken file: no favorite, no crash
    (site / "archive" / "annotations.json").write_text("{cassé", encoding="utf-8")
    assert annotations.load(site)["favorites"] == {}


def test_favorites_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    pg = page
    star = '.message[data-uuid="{}"] > .message-time > .fav-star'
    try:
        # as a file: read only
        pg.goto((site / "conversations").joinpath(next(p.name for p in (site / "conversations").glob("*.html")
                                                        if "Lois" in p.read_text(encoding="utf-8"))).as_uri())
        page_name = pg.url.rsplit("/", 1)[1]
        assert pg.get_attribute(star.format("q1"), "title").startswith("Favoris : ouvrir la Bibliothèque")
        pg.click(star.format("q1"))
        assert pg.locator(".message.cev-fav").count() == 0

        pg.goto(base + "conversations/" + page_name)
        pg.wait_for_function("document.querySelector('.fav-star').title === 'Ajouter aux favoris'")
        assert pg.inner_text("#fav-list > summary").strip() == "Favoris (0)"  # shown even without favorite
        bubble = '.message[data-uuid="{}"] > .message-bubble'
        before = pg.eval_on_selector(bubble.format("q1"), "e => getComputedStyle(e).boxShadow")
        pg.click(star.format("q1"))
        pg.wait_for_selector('.message[data-uuid="q1"].cev-fav')
        assert pg.get_attribute(star.format("q1"), "aria-pressed") == "true"
        assert pg.get_attribute(star.format("q1"), "title") == "Retirer des favoris"
        shadow = pg.eval_on_selector(bubble.format("q1"), "e => getComputedStyle(e).boxShadow")
        border = pg.eval_on_selector(bubble.format("q1"), "e => getComputedStyle(e).borderTopColor")
        assert shadow != before and border == "rgb(22, 196, 90)"  # light theme: neon green
        assert pg.locator(".message.cev-fav").count() == 1  # only this message changed
        pg.click(star.format("a1"))
        pg.wait_for_selector('.message[data-uuid="a1"].cev-fav')
        # dark theme: a vivid tint of each frame
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        assert pg.eval_on_selector(bubble.format("q1"), "e => getComputedStyle(e).borderTopColor") == "rgb(77, 168, 255)"
        assert pg.eval_on_selector(bubble.format("a1"), "e => getComputedStyle(e).borderTopColor") == "rgb(242, 242, 242)"
        pg.evaluate("document.documentElement.removeAttribute('data-theme')")
        # kept in the archive: still there after a reload, and on the page opened as a file
        pg.reload()
        pg.wait_for_selector('.message[data-uuid="a1"].cev-fav')
        # AF-f3 (14/11): the dark theme written once, for [data-theme="dark"]: the theme of the system is put there
        # and followed while the page is open
        bg = "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
        pg.emulate_media(color_scheme="dark")
        pg.wait_for_function("document.documentElement.dataset.theme === 'dark'")
        assert pg.evaluate(bg) == "#1a1a1a"
        pg.emulate_media(color_scheme="light")
        pg.wait_for_function("document.documentElement.dataset.theme === 'light'")
        assert pg.evaluate(bg) != "#1a1a1a"
        assert set(json.loads((site / "archive" / "annotations.json").read_text(encoding="utf-8"))["favorites"]["c1"]) == {"q1", "a1"}

        # the frame "Favoris (n)" of the page: the list, a link to the message, removal
        assert pg.inner_text("#fav-list > summary").strip() == "Favoris (2)"
        assert "has-favs" in pg.get_attribute("#fav-list", "class")  # yellow star
        pg.click("#fav-list > summary")
        items = pg.locator(".fav-item")
        assert items.count() == 2 and "Quelle est la loi stable ?" in items.nth(0).inner_text()
        assert items.nth(0).locator("b").inner_text() == "Moi" and items.nth(1).locator("b").inner_text() == "Claude"
        items.nth(1).locator("a").click()  # the long answer: the page goes down to it
        pg.wait_for_url("**#msg=a1")
        pg.wait_for_timeout(800)
        assert pg.evaluate("scrollY") > 300  # counter-check: not left at the top of the page
        pg.evaluate("scrollTo(0, 0)")
        items.nth(1).locator("a").click()  # the same link again (no change of address): goes there again
        pg.wait_for_timeout(800)
        assert pg.evaluate("scrollY") > 300
        # the halo is not cut: the frame of a favorite is always painted whole
        assert pg.eval_on_selector('.message[data-uuid="q1"]', "e => getComputedStyle(e).contentVisibility") == "visible"
        assert pg.eval_on_selector('.message[data-uuid="q2"]', "e => getComputedStyle(e).contentVisibility") == "auto"
        # the index: no list of favorites, their number in the line of information
        pg.goto(base + "index.html")
        assert pg.locator("#fav-list").count() == 0
        meta = '.conversation-item[data-uuid="{}"] .conversation-meta'
        assert pg.inner_text(meta.format("c1")).replace("  ", " ").endswith("· 2") and pg.locator(meta.format("c1") + " .fav-count svg").count() == 1
        assert pg.locator(meta.format("c2") + " .fav-count").count() == 0  # none: no star
        # removal from the frame of the page
        pg.goto(base + "conversations/" + page_name)
        pg.click("#fav-list > summary")
        pg.wait_for_selector(".fav-remove")
        pg.locator(".fav-item").nth(0).locator(".fav-remove").click()
        pg.wait_for_function("document.querySelectorAll('.fav-item').length === 1")
        assert pg.inner_text("#fav-list > summary").strip() == "Favoris (1)"
        assert pg.locator('.message[data-uuid="q1"].cev-fav').count() == 0  # its frame too
        pg.locator(".fav-item").nth(0).locator(".fav-remove").click()
        pg.wait_for_selector("#fav-list .fav-none")
        assert pg.inner_text("#fav-list > summary").strip() == "Favoris (0)" and "has-favs" not in pg.get_attribute("#fav-list", "class")
        assert pg.inner_text("#fav-list .fav-none") == "Aucun favori : cliquer sur l'étoile d'un message"
        pg.click(star.format("q1"))
        pg.wait_for_selector('.message[data-uuid="q1"].cev-fav')
        # as a file: the frame and the count, without removal buttons
        pg.goto((site / "conversations" / page_name).as_uri())
        assert pg.inner_text("#fav-list > summary").strip() == "Favoris (1)" and pg.locator(".fav-remove").count() == 0
        pg.goto((site / "index.html").as_uri())
        assert pg.inner_text(meta.format("c1")).replace("  ", " ").endswith("· 1")
        assert pg.locator(".fav-clear").count() == 0  # as a file: the star does nothing
        # C4: served, a click on the star of the index removes every favorite of the conversation,
        # after "Oui" in the confirmation box; "Non": nothing removed, the link not followed
        pg.goto(base + "index.html")
        clear = meta.format("c1") + " .fav-clear"
        pg.click(clear)
        assert pg.locator("dialog.cev-confirm").is_visible()
        assert "« Lois stables »" in pg.inner_text(".cev-confirm-text")
        pg.click(".cev-confirm-no")
        assert pg.locator("dialog.cev-confirm").count() == 0 and pg.url.endswith("index.html")
        assert annotations.load(site)["favorites"]["c1"]
        pg.click(clear)
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector(meta.format("c1") + " .fav-count", state="detached")
        assert annotations.load(site)["favorites"] == {} and pg.url.endswith("index.html")
        assert not pg.errors
    finally:
        server.shutdown()
        server.server_close()
