"""The topics in a real browser (Chromium through Playwright; skipped when it is not installed)."""

import json
import threading
import zipfile
from pathlib import Path

import pytest

from claude_export_viewer import topics
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM

ROOT = "00000000-0000-4000-8000-000000000000"
NAMES = ["Intégrales de Lévy", "Alpha-stables", "Grippe saisonnière", "Recette de crêpes", "Poker ICM"]


def conv(i: int, name: str) -> dict:
    day = f"2026-10-{10 + i:02d}T10:00:00Z"
    return {"uuid": f"c{i}", "name": name, "created_at": day, "updated_at": day,
            "chat_messages": [{"uuid": f"m{i}", "parent_message_uuid": ROOT, "sender": "human",
                               "content": [{"type": "text", "text": "x"}]}]}


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser not installed
            pytest.skip(f"Chromium unavailable: {exc}")
        pg = browser.new_context(locale="fr-FR", viewport={"width": 1000, "height": 800}).new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        yield pg
        browser.close()


def visible(pg) -> list[str]:
    return pg.eval_on_selector_all(".conversation-item",
                                   "els => els.filter(e => e.style.display !== 'none').map(e => e.dataset.uuid).sort()")


def cell(uuid: str) -> str:
    return f'.conversation-item[data-uuid="{uuid}"] .topic-cell'


def test_choose_filter_rename_delete(tmp_path: Path, page) -> None:
    z = tmp_path / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv(i, n) for i, n in enumerate(NAMES, 1)]))
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-20"])
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pg = page
    try:
        pg.goto(site.joinpath("index.html").as_uri())  # as a file: nothing to change
        pg.click("#tab-filters")  # 14/11: the filters in their tab
        assert pg.locator(".topic-select").count() == 0 and pg.is_visible("#filter-topic")  # shown before any topic
        assert pg.eval_on_selector_all("#filter-topic option", "o => o.map(x => x.textContent)") == [
            "Toutes les rubriques", "Sans rubrique"]  # read only: no "Nouvelle rubrique…"

        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.click("#tab-filters")  # 14/11: the filters in their tab
        pg.wait_for_selector(".topic-select", state="attached")  # P7: an empty menu shows under the mouse
        assert pg.locator(".topic-select").count() == 5
        # a topic created from the filter: the filter stays on what it showed
        pg.wait_for_function("() => document.getElementById('filter-topic').options.length === 3")
        assert pg.eval_on_selector_all("#filter-topic option", "o => o.map(x => x.textContent)") == [
            "Toutes les rubriques", "Sans rubrique", "Nouvelle rubrique…"]
        pg.select_option("#filter-topic", " ")
        pg.select_option("#filter-topic", label="Nouvelle rubrique…")
        assert pg.input_value("#filter-topic") == " " and pg.is_hidden("#filter-topic")
        pg.fill(".filter-topic-new input", "math")
        pg.press(".filter-topic-new input", "Enter")
        pg.wait_for_function("() => [...document.getElementById('filter-topic').options].some(o => o.value === 'math')")
        assert topics.load(site) == {"topics": ["math"], "assign": {}}
        assert pg.is_visible("#filter-topic") and pg.locator(".filter-topic-new").count() == 0
        assert pg.input_value("#filter-topic") == " " and len(visible(pg)) == 5
        pg.select_option("#filter-topic", label="Nouvelle rubrique…")
        pg.press(".filter-topic-new input", "Escape")  # given up: nothing created
        assert pg.is_visible("#filter-topic") and topics.load(site)["topics"] == ["math"]
        pg.select_option("#filter-topic", "")
        # a closed menu holds only its value; it is completed when it opens (mouse or keyboard)
        assert pg.eval_on_selector_all(cell("c1") + " option", "o => o.length") == 1
        pg.dispatch_event(cell("c1") + " select", "mousedown")
        assert pg.eval_on_selector_all(cell("c1") + " option", "o => o.map(x => x.textContent)") == [
            "Rubrique…", "math", "Nouvelle rubrique…"]  # (math: created from the filter)

        def choose(uuid: str, **option) -> None:
            pg.hover(cell(uuid))  # P7: an empty menu shows under the mouse
            pg.focus(cell(uuid) + " select")  # (the menu is completed when it opens)
            pg.select_option(cell(uuid) + " select", **option)

        def new(uuid: str, name: str) -> None:
            choose(uuid, label="Nouvelle rubrique…")
            pg.fill(cell(uuid) + " input", name)
            pg.press(cell(uuid) + " input", "Enter")

        def topic_is(uuid: str, name: str) -> None:
            pg.wait_for_function(f"(document.querySelector('[data-uuid={uuid}]').dataset.topic || '') === {json.dumps(name)}")

        new("c1", "  math ")
        topic_is("c1", "math")
        choose("c2", value="math")
        topic_is("c2", "math")
        new("c3", "Médecine")
        topic_is("c3", "Médecine")
        new("c5", "MATH")  # the existing topic
        topic_is("c5", "math")
        choose("c5", value="")
        topic_is("c5", "")
        assert topics.load(site) == {"topics": ["math", "Médecine"], "assign": {"c1": "math", "c2": "math", "c3": "Médecine"}}

        options = pg.eval_on_selector_all("#filter-topic option", "o => o.map(x => x.textContent)")
        assert options == ["Toutes les rubriques", "Sans rubrique", "math", "Médecine", "Nouvelle rubrique…"]
        pg.select_option("#filter-topic", "math")
        assert visible(pg) == ["c1", "c2"]
        for order in ("name-asc", "messages-desc", "date-asc"):  # sorting keeps the filter
            pg.select_option("#sort-by", order)
            assert visible(pg) == ["c1", "c2"]
        pg.select_option("#filter-topic", " ")
        assert visible(pg) == ["c4", "c5"] and pg.inner_text("#result-count") == "2 sur 5 conversations"
        pg.select_option("#filter-topic", "")
        assert visible(pg) == ["c1", "c2", "c3", "c4", "c5"]

        pg.select_option("#filter-topic", "math")
        pg.reload()
        pg.click("#tab-filters")  # 14/11: the filters in their tab
        pg.wait_for_selector(".topic-select", state="attached")  # P7: an empty menu shows under the mouse
        assert pg.input_value("#filter-topic") == "math" and visible(pg) == ["c1", "c2"]

        if pg.is_hidden("#topics-manage"):
            pg.click("#tab-data")  # 14/11: in the tab of the data
        pg.click("#topics-manage")
        pg.locator("#topics-list li", has_text="math").get_by_role("button", name="Renommer").click()
        pg.fill("#topics-list input", "Mathématiques")
        pg.press("#topics-list input", "Enter")
        topic_is("c1", "Mathématiques")
        assert pg.input_value("#filter-topic") == "Mathématiques" and visible(pg) == ["c1", "c2"]

        pg.locator("#topics-list li", has_text="Médecine").get_by_role("button", name="Supprimer").click()
        pg.locator("#topics-list li:has(.topics-confirm)").get_by_role("button", name="Supprimer").click()
        topic_is("c3", "")
        assert topics.load(site) == {"topics": ["Mathématiques"], "assign": {"c1": "Mathématiques", "c2": "Mathématiques"}}

        pg.click("#tab-filters")
        pg.select_option("#filter-topic", "")  # (c4 is hidden by the filter)
        pg.select_option("#lang-select", "ja")
        pg.hover(cell("c4"))
        pg.focus(cell("c4") + " select")
        assert pg.eval_on_selector_all(cell("c4") + " option", "o => o.map(x => x.textContent)") == [
            "カテゴリー…", "Mathématiques", "新しいカテゴリー…"]
        pg.select_option("#lang-select", "fr")

        pg.goto(site.joinpath("index.html").as_uri())  # as a file again: read only, filter works
        pg.click("#tab-filters")  # 14/11: the filters in their tab
        pg.wait_for_selector(".topic-badge")
        assert pg.locator(".topic-select").count() == 0
        pg.select_option("#filter-topic", "Mathématiques")
        assert visible(pg) == ["c1", "c2"]
        assert pg.errors == []
    finally:
        server.shutdown()


def test_settings_frame_buttons_open_and_close(tmp_path: Path, page) -> None:
    z = tmp_path / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv(1, "Une")]))
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-20"])
    dl = tmp_path / "Téléchargements"
    dl.mkdir()
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    server.ctx.downloads = lambda: dl
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pg = page
    try:
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        # 14/11: the frame of the data is a tab, shown with the server, closed while the overview is open; in it,
        # first the frame of the import (dashes), then the buttons and the folders, at once
        pg.wait_for_selector("#tab-data:visible")
        assert pg.is_hidden("#admin-import") and pg.get_attribute("#tab-overview", "aria-selected") == "true"
        pg.click("#tab-data")
        first = pg.eval_on_selector("#admin-bar .admin-bar", "e => e.firstElementChild.id")
        assert first == "admin-import" and pg.is_visible("#admin-folders") and pg.is_hidden("#overview")
        assert "Dernier export importé : " in pg.inner_text("#admin-import") and "Nouvel export : " in pg.inner_text("#admin-import")
        pg.wait_for_selector("#admin-downloads:visible")
        pg.wait_for_selector("#topics-manage:not([hidden])")
        # everything sits in the frame, every setting is a button
        inside = pg.eval_on_selector_all("#admin-bar #admin-import, #admin-bar #topics-manage, #admin-bar #dl-change, "
                                         "#admin-bar #topics-manager, #admin-bar #admin-panel", "e => e.length")
        assert inside == 5
        assert pg.eval_on_selector_all("#admin-bar button.dl-link", "e => e.length") == 0

        def state(button: str, box: str) -> tuple:
            return pg.is_visible(box), pg.get_attribute(button, "aria-expanded")

        for button, box, cross in (("#topics-manage", "#topics-manager", "#topics-close"),
                                   ("#dl-change", "#dl-form", None)):
            pg.click(button)
            assert state(button, box) == (True, "true")
            pg.click(button)  # a second click closes it
            assert state(button, box) == (False, "false")
            if cross:
                pg.click(button)
                pg.click(cross)
                assert state(button, box) == (False, "false")

        # 14/11: no manifest in the downloads: the frame of the import opens the window to choose the files, taken
        # as if dropped
        log_done = "document.getElementById('admin-log').innerText.includes('notes.txt')"
        with pg.expect_file_chooser() as chooser:
            pg.click("#admin-import")
        assert chooser.value.is_multiple()
        chooser.value.set_files(files=[{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"x"}])
        pg.wait_for_function(log_done)
        assert state("#admin-import", "#admin-panel") == (True, "true")
        pg.click("#admin-import")  # a second click closes the log
        assert state("#admin-import", "#admin-panel") == (False, "false")
        (dl / "manifest-1.json").write_text("{}", encoding="utf-8")  # unreadable: not a manifest, the window again
        with pg.expect_file_chooser() as chooser:
            pg.click("#admin-import")
        chooser.value.set_files(files=[{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"x"}])
        pg.wait_for_function(log_done)
        pg.click("#admin-close")  # the cross is kept
        assert state("#admin-import", "#admin-panel") == (False, "false")
        assert pg.errors == []
    finally:
        server.shutdown()
