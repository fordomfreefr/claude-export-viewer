"""Phase E of 2026-10-29: links between conversations, notes, highlighted passages
(archive/annotations.json; browser tests skipped without Chromium)."""

from __future__ import annotations

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
LONG = "Remplissage de la réponse.\n\n" * 30


def _conv(uuid: str, name: str, day: int, *texts: str) -> dict:
    msgs, parent = [], ROOT
    for i, text in enumerate(texts):
        mid = f"{uuid}-{i}"
        msgs.append({"uuid": mid, "parent_message_uuid": parent, "sender": "human" if i % 2 == 0 else "assistant",
                     "created_at": f"2026-10-{day:02d}T10:0{i}:00Z", "content": [{"type": "text", "text": text}]})
        parent = mid
    return {"uuid": uuid, "name": name, "created_at": f"2026-10-{day:02d}T10:00:00Z", "chat_messages": msgs}


def _site(tmp: Path) -> Path:
    z = tmp / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([
            _conv("c1", "Noyer", 10, "Comment greffer un noyer ?", "La greffe en fente se fait au printemps. " + LONG,
                  "Et le semis ?", "Le semis donne un arbre variable."),
            _conv("c2", "Poker", 11, "Stratégie ICM", "L'ICM évalue les jetons."),
            _conv("c3", "Lois stables", 12, "Paramètre alpha",
                  "Alpha règle les queues.\n\n- premier point\n- second point\n\n| a | b |\n|---|---|\n| un | deux |\n| trois | quatre |")]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-22"])
    return site


def test_links_notes_marks_on_the_server(tmp_path: Path) -> None:
    site = _site(tmp_path)
    load_raw = Archive(site).load_raw
    ch = lambda **r: annotations.change(site, r, load_raw)  # noqa: E731
    ch(action="link", a="c1", b="c2")
    state = ch(action="link", a="c2", b="c3")
    assert state["links"] == {"c1": ["c2"], "c2": ["c1", "c3"], "c3": ["c2"]}  # both ways, not transitive
    assert state["convs"]["c3"][0] == "Lois stables" and state["convs"]["c3"][1].endswith(".html")
    for bad in ({"a": "c1", "b": "c1"}, {"a": "c1", "b": "c9"}):
        with pytest.raises(annotations.AnnotationError):
            ch(action="link", **bad)
    assert ch(action="unlink", a="c3", b="c2")["links"] == {"c1": ["c2"], "c2": ["c1"]}
    assert ch(action="clear_links", conversation="c2")["links"] == {}
    # notes: on your messages only; empty removes
    assert ch(action="note", conversation="c1", message="c1-0", text=" ma note ")["notes"]["c1"]["c1-0"]["text"] == "ma note"
    assert ch(action="note", conversation="c1", message="c1-1", text="sur Claude")["notes"]["c1"]["c1-1"]["text"] == "sur Claude"
    with pytest.raises(annotations.AnnotationError):
        ch(action="note", conversation="c1", message="nope", text="x")
    ch(action="note", conversation="c1", message="c1-1", text="")
    assert ch(action="note", conversation="c1", message="c1-0", text="")["notes"] == {}
    # highlighted passages
    p = {"message": "c1-1", "s": 3, "q": "greffe"}
    assert ch(action="mark", conversation="c1", passages=[p])["marks"] == {"c1": {"c1-1": [{"s": 3, "q": "greffe"}]}}
    assert ch(action="unmark", conversation="c1", passages=[p])["marks"] == {}
    ch(action="mark", conversation="c1", passages=[p])
    assert ch(action="clear_marks", conversation="c1")["marks"] == {}
    assert '"convs"' in (site / "annotations-data.js").read_text(encoding="utf-8")


def _select(pg, uuid: str, text: str, end_uuid: str = "", end_text: str = "") -> None:
    """Select ``text`` in a message (up to ``end_text`` of another one when given)."""
    pg.evaluate("""([a, ta, b, tb]) => {
      const node = (u, t) => { const w = document.createTreeWalker(document.querySelector('.message[data-uuid="' + u + '"]'), NodeFilter.SHOW_TEXT);
        while (w.nextNode()) { const i = w.currentNode.nodeValue.indexOf(t); if (i >= 0) return [w.currentNode, i]; } };
      const [n1, i1] = node(a, ta); const [n2, i2] = b ? node(b, tb) : [n1, i1];
      const r = document.createRange(); r.setStart(n1, i1); r.setEnd(n2, i2 + (b ? tb : ta).length);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.dispatchEvent(new Event('selectionchange'));
    }""", [uuid, text, end_uuid, end_text])
    pg.wait_for_timeout(250)


def test_phase_e_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        item = '.conversation-item[data-uuid="{}"]'
        pg.goto(base + "index.html")
        # E1: a conversation dragged onto another one links them, both ways, not transitive
        pg.drag_and_drop(item.format("c1") + " a", item.format("c2") + " a")
        pg.wait_for_selector(item.format("c1") + " .link-count")
        pg.drag_and_drop(item.format("c3") + " a", item.format("c2") + " a")
        pg.wait_for_function("document.querySelector('" + item.format("c3") + " .link-count') !== null")
        counts = {c: " ".join(pg.inner_text(item.format(c) + " .link-count").split()) for c in ("c1", "c2", "c3")}
        assert counts == {"c1": "· 1", "c2": "· 2", "c3": "· 1"}, counts
        page_of = {c: pg.get_attribute(item.format(c) + " a", "href") for c in ("c1", "c2")}
        pg.goto(base + page_of["c2"])
        pg.click("#link-list > summary")
        assert pg.inner_text("#link-list > summary").strip() == "Liens (2)"
        assert [x.strip() for x in pg.locator("#link-list .fav-item:not(.series-here) .fav-excerpt").all_inner_texts()] == ["Noyer", "Lois stables"]
        pg.locator("#link-list .fav-item:not(.series-here)").nth(1).locator(".fav-remove").click()
        pg.wait_for_function("document.querySelectorAll('#link-list .fav-item:not(.series-here)').length === 1")
        pg.click("#link-list .fav-item a")
        pg.wait_for_url("**" + page_of["c1"].removeprefix("conversations"))
        # E2: a note on your message and one on Claude's, each under its bubble
        pg.click('.message[data-uuid="c1-0"] .note-btn')
        assert pg.locator('.message[data-uuid="c1-0"] > .cev-note .cev-note-label').is_visible()  # title kept while writing
        assert pg.locator(".cev-note-erase").count() == 0  # nothing to erase yet
        pg.fill(".cev-note-edit", "Greffer en avril")
        pg.click(".cev-note-save")
        pg.wait_for_selector('.message[data-uuid="c1-0"] > .cev-note .cev-note-text')
        pg.click('.message[data-uuid="c1-1"] .note-btn')
        pg.fill(".cev-note-edit", "À vérifier")
        pg.keyboard.press("Control+Enter")
        pg.wait_for_selector('.message[data-uuid="c1-1"] > .cev-note .cev-note-text')
        assert annotations.load(site)["notes"]["c1"] == {"c1-0": annotations.load(site)["notes"]["c1"]["c1-0"],
                                                         "c1-1": annotations.load(site)["notes"]["c1"]["c1-1"]}
        human, claude = pg.locator('.message[data-uuid="c1-0"] > .cev-note'), pg.locator('.message[data-uuid="c1-1"] > .cev-note')
        # the grip of the free corner: the left for yours (its right edge stays), the right for Claude's
        def drag(note, dx: int, dy: int = 0) -> tuple:
            note.evaluate("e => e.scrollIntoView({ block: 'center' })")
            before = note.bounding_box()
            g = note.locator(".cev-note-grip").bounding_box()
            pg.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
            pg.mouse.down()
            pg.mouse.move(g["x"] + g["width"] / 2 + dx, g["y"] + g["height"] / 2 + dy, steps=5)
            pg.mouse.up()
            return before, note.bounding_box()
        box, wider = drag(human, -120)
        assert human.locator(".cev-note-grip").bounding_box()["x"] < box["x"] + 25  # on the left
        assert wider["width"] > box["width"] + 100 and abs(wider["x"] + wider["width"] - box["x"] - box["width"]) < 2
        box, wider = drag(claude, 120)
        assert wider["width"] > box["width"] + 100 and abs(wider["x"] - box["x"]) < 2
        assert pg.locator('.message[data-uuid="c1-1"] > .cev-note .cev-note-edit').count() == 0  # not opened by the drag
        # the frame "Notes (2)", in the order of the conversation; its cross erases a note
        pg.click("#note-list > summary")
        assert pg.inner_text("#note-list > summary").strip() == "Notes (2)"
        assert [x.strip() for x in pg.locator("#note-list .fav-excerpt").all_inner_texts()] == ["Greffer en avril", "À vérifier"]
        pg.locator("#note-list .fav-item").nth(1).locator(".fav-remove").click()
        pg.wait_for_function("document.querySelectorAll('#note-list .fav-item').length === 1")
        assert claude.count() == 0
        # "Effacer" while writing
        pg.click('.message[data-uuid="c1-1"] .note-btn')
        pg.fill(".cev-note-edit", "temporaire")
        pg.click(".cev-note-save")
        pg.wait_for_selector('.message[data-uuid="c1-1"] > .cev-note .cev-note-text')
        pg.click('.message[data-uuid="c1-1"] > .cev-note')
        pg.click(".cev-note-erase")
        pg.wait_for_selector('.message[data-uuid="c1-1"] > .cev-note', state="detached")
        assert list(annotations.load(site)["notes"]["c1"]) == ["c1-0"]
        # 11/11 (the charter): undo / redo by steps of typing, saved by a click elsewhere
        pg.click('.message[data-uuid="c1-1"] .note-btn')
        assert pg.locator(".cev-note-head .cev-note-undo").is_disabled()
        pg.keyboard.type("un")
        pg.wait_for_timeout(700)
        pg.keyboard.type(" deux")
        pg.click(".cev-note-undo")
        assert pg.input_value(".cev-note-edit") == "un"
        pg.click(".cev-note-redo")
        assert pg.input_value(".cev-note-edit") == "un deux" and pg.locator(".cev-note-redo").is_disabled()
        pg.click("h1")
        pg.wait_for_selector('.message[data-uuid="c1-1"] > .cev-note .cev-note-text')
        assert annotations.load(site)["notes"]["c1"]["c1-1"]["text"] == "un deux"
        # a long note (more than 7 s of reading) is erased only after "Oui"
        pg.click('.message[data-uuid="c1-1"] > .cev-note')
        pg.fill(".cev-note-edit", " ".join(["mot"] * 30))
        pg.keyboard.press("Control+Enter")
        pg.wait_for_selector('.message[data-uuid="c1-1"] > .cev-note .cev-note-text')
        pg.click('.message[data-uuid="c1-1"] > .cev-note')
        pg.click(".cev-note-erase")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector('.message[data-uuid="c1-1"] > .cev-note', state="detached")
        assert list(annotations.load(site)["notes"]["c1"]) == ["c1-0"]
        # E3: highlight a selection, then remove it by selecting it again
        mark = pg.locator('#page-nav [data-go="mark"]')
        off = lambda: "off" in (mark.get_attribute("class") or "")  # never disabled: the wheel reaches it (11/11)
        assert off()
        _select(pg, "c1-1", "greffe en fente")
        pg.wait_for_function("!document.querySelector('#page-nav [data-go=mark]').classList.contains('off')")
        mark.click()
        pg.wait_for_selector("mark.cev-hl")
        assert "".join(pg.locator("mark.cev-hl").all_inner_texts()) == "greffe en fente"
        assert annotations.load(site)["marks"]["c1"]["c1-1"][0]["q"] == "greffe en fente"
        pg.reload()
        pg.wait_for_selector("mark.cev-hl")
        _select(pg, "c1-1", "en fente")  # part of the highlighted passage
        mark.click()
        pg.wait_for_selector("mark.cev-hl", state="detached")
        assert annotations.load(site)["marks"] == {}
        # colours (11/11): the wheel over the button chooses one (a box of 5 squares, the current one ringed)
        mark.hover()
        pg.mouse.wheel(0, -100)
        pg.wait_for_selector('.nav-hl-box:not([hidden]) .hl-sq.on[data-c="g"]')
        _select(pg, "c1-1", "greffe en fente")
        mark.click()
        pg.wait_for_selector("mark.cev-hl.hl-g")
        assert annotations.load(site)["marks"]["c1"]["c1-1"][0]["c"] == "g"
        mark.hover()
        pg.mouse.wheel(0, 100)  # back to yellow: a part of the green passage selected makes it yellow, whole
        _select(pg, "c1-1", "en fente")
        mark.click()
        pg.wait_for_selector("mark.cev-hl.hl-g", state="detached")
        (m,) = annotations.load(site)["marks"]["c1"]["c1-1"]
        assert m["q"] == "greffe en fente" and "c" not in m
        _select(pg, "c1-1", "en fente")  # same colour: removed
        mark.click()
        pg.wait_for_selector("mark.cev-hl", state="detached")
        assert annotations.load(site)["marks"] == {}
        _select(pg, "c1-2", "le semis", "c1-3", "Le semis")  # over two messages: one passage in each
        mark.click()
        pg.wait_for_function("document.querySelectorAll('mark.cev-hl').length >= 2")
        assert set(annotations.load(site)["marks"]["c1"]) == {"c1-2", "c1-3"}
        # a highlighting over two list items and over table cells keeps the list and the table
        pg.goto(base + "index.html")
        page_c3 = pg.get_attribute(item.format("c3") + " a", "href")
        pg.goto(base + page_c3)
        before = pg.evaluate("[...document.querySelectorAll('.message li, .message td')].map(e => Math.round(e.getBoundingClientRect().height))")
        _select(pg, "c3-1", "premier", "c3-1", "second point")
        mark.click()
        pg.wait_for_selector("mark.cev-hl")
        _select(pg, "c3-1", "un", "c3-1", "quatre")
        mark.click()
        pg.wait_for_function("[...document.querySelectorAll('mark.cev-hl')].some(m => m.textContent === 'quatre')")
        assert pg.locator("ul > mark, ol > mark, table > mark, tbody > mark, thead > mark, tr > mark").count() == 0
        assert pg.evaluate("[...document.querySelectorAll('.message tr')].map(r => r.children.length)") == [2, 2, 2]
        after = pg.evaluate("[...document.querySelectorAll('.message li, .message td')].map(e => Math.round(e.getBoundingClientRect().height))")
        assert after == before
        # the index: the notes and passages counted; the note is searched; all passages removed at once
        pg.goto(base + "index.html")
        pg.click("#tab-filters")  # 14/11: the filters in their tab
        assert " ".join(pg.inner_text(item.format("c1") + " .note-count").split()) == "· 1"
        assert " ".join(pg.inner_text(item.format("c1") + " .mark-count").split()) == "· 2"
        # plain icons on the index, brick (the accent) on hover
        icon = pg.locator(item.format("c1") + " .note-count .annot-n")
        muted = pg.locator(item.format("c1") + " .conversation-meta").evaluate("e => getComputedStyle(e).color")
        assert icon.evaluate("e => getComputedStyle(e).color") == muted
        icon.hover()
        assert icon.evaluate("e => getComputedStyle(e).color") == pg.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()").replace("#c96442", "rgb(201, 100, 66)")
        pg.fill("#content-search", "avril")
        pg.wait_for_timeout(700)
        assert pg.locator(".conversation-item:visible").count() == 1 and pg.locator(item.format("c1")).is_visible()
        pg.fill("#content-search", "")
        pg.click(item.format("c1") + " .mark-count .annot-clear")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector(item.format("c1") + " .mark-count", state="detached")
        assert annotations.load(site)["marks"].get("c1") is None and pg.url.endswith("index.html")
        # every note at once, after "Oui", as for the other icons
        pg.click(item.format("c1") + " .note-count .annot-clear")
        assert "« Noyer »" in pg.inner_text(".cev-confirm-text")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector(item.format("c1") + " .note-count", state="detached")
        assert annotations.load(site)["notes"] == {}
        # a release over the dashed conversation links them even when no "drop" comes (some systems)
        pg.evaluate("""() => { const dt = new DataTransfer(), a = document.querySelector('[data-uuid="c1"] a'),
            b = document.querySelector('[data-uuid="c3"] a'), ev = (el, t) => el.dispatchEvent(new DragEvent(t,
            { bubbles: true, cancelable: true, dataTransfer: dt, clientY: 300 }));
          ev(a, 'dragstart'); ev(b, 'dragover'); ev(a, 'dragend'); }""")
        pg.wait_for_function("document.querySelector('" + item.format("c3") + " .link-count') !== null")
        assert "c3" in annotations.load(site)["links"]["c1"]
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


def test_annotations_in_the_exports(tmp_path: Path) -> None:
    import io
    import shutil

    from claude_export_viewer import i18n, office_export
    i18n.set_language("fr")
    site = _site(tmp_path)
    archive = Archive(site)
    annotations.change(site, {"action": "note", "conversation": "c1", "message": "c1-0", "text": "Greffer en avril"},
                       archive.load_raw)
    annotations.change(site, {"action": "mark", "conversation": "c1",
                              "passages": [{"message": "c1-1", "s": 3, "q": "greffe en fente"},
                                           {"message": "c1-2", "s": 3, "q": "le semis"}]}, archive.load_raw)
    annot = office_export.annotations_of(site, "c1")
    md = office_export.convert_archived(archive, "c1", "md", annot=annot).data.decode("utf-8")
    assert "La ==greffe en fente== se fait" in md and "Et ==le semis== ?" in md
    # the note under its message (yours here), before Claude's answer
    assert md.index("Comment greffer") < md.index("> **Note :**\\\n> Greffer en avril") < md.index("La ==greffe")
    plain = office_export.convert_archived(archive, "c1", "md").data.decode("utf-8")
    assert "==" not in plain and "Greffer en avril" not in plain  # box unchecked: none
    if not shutil.which("pandoc"):
        return
    txt = office_export.convert_archived(archive, "c1", "txt", annot=annot).data.decode("utf-8")
    assert "La greffe en fente se fait" in txt and "Greffer en avril" in txt and "==greffe" not in txt
    odt = zipfile.ZipFile(io.BytesIO(office_export.convert_archived(archive, "c1", "odt", annot=annot).data))
    content = odt.read("content.xml").decode("utf-8")
    assert '<text:span text:style-name="CEV_Surligne">greffe en fente</text:span>' in content
    assert 'style:name="CEV_Surligne"' in content and "" not in content
    assert odt.infolist()[0].filename == "mimetype" and odt.infolist()[0].compress_type == zipfile.ZIP_STORED
    docx = zipfile.ZipFile(io.BytesIO(office_export.convert_archived(archive, "c1", "docx", annot=annot).data))
    assert '<w:highlight w:val="yellow" />' in docx.read("word/document.xml").decode("utf-8")
