"""Plan view of a conversation (AE-c1, maquette B3 v2, step 1): static/plan.js + plan.css, titles of the
bubbles (annotations "titles"), in the exports with the box "Annotations" (browser tests skipped without
Chromium)."""

from __future__ import annotations

import json
import threading
import zipfile
from pathlib import Path

import pytest

from claude_export_viewer import annotations, office_export
from claude_export_viewer.archive import Archive
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"
LONG = " ".join(f"Phrase numéro {i} pour allonger la réponse." for i in range(60))
CODE = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(15)) + "\ngirafe = 1\n```"
LONG2 = " ".join(f"Phrase numéro {i} pour allonger la réponse." for i in range(30)) + " Le zèbre est ici. " + LONG


def _m(uuid: str, parent: str, sender: str, time: str, *content: dict) -> dict:
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender,
            "created_at": f"2026-10-31T{time}:00Z", "content": list(content)}


def _t(text: str) -> dict:
    return {"type": "text", "text": text}


def _site(tmp: Path) -> Path:
    # q2b (14:09) is edited from q2a (14:02): two versions at a1, the most recent one followed; a3 is an
    # interrupted reply (thinking only, hidden with the resources): q3 and q4 are one block
    msgs = [
        {**_m("q1", ROOT, "human", "09:12", _t("Première question\nsur plusieurs\nlignes\net encore une")),
         "attachments": [{"file_name": "a.txt", "extracted_content": "a"}, {"file_name": "b.txt", "extracted_content": "b"}]},
        _m("a1", "q1", "assistant", "09:13", {"type": "thinking", "thinking": "Je réfléchis."}, _t(LONG + "\n\n" + CODE)),
        _m("q2a", "a1", "human", "14:02", _t("Version une")),
        _m("a2a", "q2a", "assistant", "14:03", _t("Réponse à la version une")),
        _m("q2b", "a1", "human", "14:09", _t("Version deux")),
        _m("a2b", "q2b", "assistant", "14:10", _t("Réponse à la version deux. " + LONG2)),
        _m("q3", "a2b", "human", "15:00", _t("Question interrompue")),
        _m("a3", "q3", "assistant", "15:00", {"type": "thinking", "thinking": "Je commence…"}),
        _m("q4", "a3", "human", "15:01", _t("Question reprise")),
        _m("a4", "q4", "assistant", "15:02", _t("Réponse reprise")),
    ]
    z = tmp / "p.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([{"uuid": "c1", "name": "Plan", "created_at": "2026-10-31T09:12:00Z",
                                                       "chat_messages": msgs}]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-11-01"])
    return site


def test_titles_are_annotations_and_go_in_the_exports(tmp_path: Path) -> None:
    site = _site(tmp_path)
    ch = lambda **r: annotations.change(site, r, Archive(site).load_raw)  # noqa: E731
    state = ch(action="title", conversation="c1", message="q1", text="  Le   titre\n de la question ")
    assert state["titles"] == {"c1": {"q1": {"text": "Le titre de la question", "updated": state["titles"]["c1"]["q1"]["updated"]}}}
    assert state["notes"] == {}  # a title is not a note
    with pytest.raises(annotations.AnnotationError):
        ch(action="title", conversation="c1", message="nope", text="x")
    ch(action="note", conversation="c1", message="q1", text="Ma note")
    archive = Archive(site)
    with_annot, _ = office_export.archived_markdown(archive, "c1", annot=office_export.annotations_of(site, "c1"))
    assert "> **Titre :** Le titre de la question\n\n" in with_annot
    assert with_annot.index("Le titre de la question") < with_annot.index("Première question") < with_annot.index("Ma note")
    without, _ = office_export.archived_markdown(archive, "c1")
    assert "Le titre" not in without and "Ma note" not in without
    assert ch(action="title", conversation="c1", message="q1", text=" ")["titles"] == {}  # empty: removed
    assert "titles" in json.loads((site / "archive" / "annotations.json").read_text(encoding="utf-8"))


def test_no_plan_view(tmp_path: Path, page) -> None:  # noqa: F811
    """17/11 (AE-c1): the plan view removed — the switch "Lecture · Structure"; a view "plan" kept by the browser
    opens the reading."""
    site = _site(tmp_path)
    pg = page
    pg.add_init_script("try { localStorage.setItem('cev-view', 'plan'); } catch (e) {}")
    pg.goto((site / "conversations" / "c1.html").as_uri())
    pg.wait_for_selector(".plan-view")
    assert [o.get_attribute("data-v") for o in pg.locator(".plan-view .plan-opt").all()] == ["reading", "structure"]
    assert pg.get_attribute(".plan-view .plan-opt.on", "data-v") == "reading"
    assert not pg.evaluate("document.documentElement.classList.contains('cev-plan')")
    assert pg.locator(".plan-show, #plan-fold, .plan-strip, .plan-fork").count() == 0
    pg.click(".plan-view", position={"x": 4, "y": 6})  # on the title: the next view
    assert pg.evaluate("document.documentElement.classList.contains('cev-structure')")
    pg.click(".plan-view", position={"x": 4, "y": 6})
    assert pg.get_attribute(".plan-view .plan-opt.on", "data-v") == "reading" and not pg.errors


def test_titles_frame_and_reading_lines(tmp_path: Path, page) -> None:  # noqa: F811
    """The frame "Titres (n)" as "Notes (n)", in the order of the page; "Lignes" in the reading and the
    structure, a setting of their own (the plan keeps its own)."""
    site = _site(tmp_path)
    ch = lambda **r: annotations.change(site, r, Archive(site).load_raw)  # noqa: E731
    ch(action="title", conversation="c1", message="q3", text="Suite")
    ch(action="title", conversation="c1", message="a1", text="Réponse longue")
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        url = f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html"
        pg.goto(url)
        entry = '.message[data-uuid="{}"]'
        shown = lambda sel: pg.eval_on_selector(sel, "e => e.checkVisibility()")  # noqa: E731
        height = lambda u: pg.eval_on_selector(entry.format(u) + " > .message-bubble", "b => b.clientHeight")  # noqa: E731
        # the frame: its count, the titles in the order of the page (a1 before q3), a cross removes one
        label = lambda: " ".join(pg.inner_text("#title-list > summary").split())  # noqa: E731
        assert label() == "Titres (2)" and "has-titles" in pg.get_attribute("#title-list", "class")
        pg.click("#title-list > summary")
        assert pg.eval_on_selector_all("#title-list .fav-excerpt", "l => l.map(e => e.textContent)") == ["Réponse longue", "Suite"]
        assert pg.get_attribute("#title-list li:first-child a", "href") == "#msg=a1"
        pg.click("#title-list li:first-child .fav-remove")
        pg.wait_for_function("document.querySelectorAll('#title-list .fav-excerpt').length === 1")
        assert label() == "Titres (1)" and list(annotations.load(site)["titles"]["c1"]) == ["q3"]
        assert pg.locator(entry.format("a1") + " > .cev-title").count() == 0
        # Lignes in the reading: Tout at first (nothing cut, no arrow), then 1, 3
        reading = height("a1")
        assert pg.get_attribute("html", "data-read-lines") == "all" and not shown(entry.format("a1") + " .plan-dn")
        pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
        pg.click(".plan-lines > span:not(.plan-opt)")
        fade = "e => getComputedStyle(e, '::after').content"
        assert pg.get_attribute("html", "data-read-lines") == "1" and height("a1") < reading
        assert not shown(entry.format("a1") + " .code-block") and shown(entry.format("a1") + " .plan-dn")
        assert pg.eval_on_selector(entry.format("a1") + " > .message-bubble", fade) == "none"  # no fade at 1 line
        pg.click(".plan-lines > span:not(.plan-opt)")
        pg.wait_for_function(f"document.querySelector('{entry.format('a1')}').classList.contains('plan-cut')")
        assert pg.eval_on_selector(entry.format("a1") + " > .message-bubble", fade) == '""'
        assert pg.eval_on_selector(entry.format("q4") + " > .message-bubble", fade) == "none"  # short: not cut
        # the arrow and the icons of what it holds, after the date: the whole bubble, then cut again
        dn = entry.format("a1") + " > .message-time > .plan-dn"
        three = height("a1")
        pg.click(dn + " > svg")
        assert shown(entry.format("a1") + " .code-block") and height("a1") > three
        pg.click(dn + " > svg")
        assert height("a1") == three
        assert pg.eval_on_selector_all(entry.format("q1") + " .plan-ic", "l => l.map(i => i.title)") == ["2 pièces jointes"]
        # kept by the browser; the search opens the cut bubble of the passage found
        pg.goto(url + "?q=girafe")
        pg.wait_for_selector(entry.format("a1") + ".plan-flip")
        assert shown(entry.format("a1") + " .code-block")
        pg.goto(url)
        assert "cev-read-cut" in pg.get_attribute("html", "class") and height("a1") == three
        # the plan: its own 3 lines; the structure: the bubbles shown cut as the reading
        pg.click('.plan-view .plan-opt[data-v="structure"]')
        pg.click('.st-row[data-uuid="q1"]')
        assert shown(entry.format("a1")) and height("a1") == three and shown(entry.format("a1") + " .plan-dn")
        pg.click('.plan-view .plan-opt[data-v="reading"]')
        pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (after the reload above)
        pg.click(".plan-lines > span:not(.plan-opt)")
        pg.click(".plan-lines > span:not(.plan-opt)")  # 5, Tout: as before
        assert height("a1") == reading and not shown(entry.format("a1") + " .plan-dn")
        assert "cev-read-cut" not in pg.get_attribute("html", "class")
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


# --- Structure view (structure.js): a thread shaped like "Test ALPHA question" ---------------------------------
def _alpha_site(tmp: Path) -> Path:
    spec = [  # uuid, parent, sender, minute (the followed thread ends with the most recent message)
        ("qa0", ROOT, "human", "33:00"), ("aa0", "qa0", "assistant", "33:10"),
        ("q1", ROOT, "human", "34:00"), ("a1", "q1", "assistant", "34:10"),
        ("q2", "a1", "human", "35:00"), ("a2x", "q2", "assistant", "35:10"), ("a2y", "q2", "assistant", "36:00"),
        ("a2", "q2", "assistant", "36:30"),
        ("q3", "a2", "human", "39:00"), ("a3a", "q3", "assistant", "39:10"), ("a3b", "q3", "assistant", "41:00"),
        ("q3b0", "a3b", "human", "41:10"), ("a3b0x", "q3b0", "assistant", "41:20"), ("a3b0", "q3b0", "assistant", "42:00"),
        ("q3b1", "a3b", "human", "42:10"), ("a3b1x", "q3b1", "assistant", "42:20"), ("a3b1", "q3b1", "assistant", "43:00"),
        ("q3b2", "a3b1", "human", "43:10"), ("a3b2", "q3b2", "assistant", "43:20"),
        ("q3b3", "a3b2", "human", "45:00"), ("a3b3", "q3b3", "assistant", "45:10"),
        ("a3", "q3", "assistant", "46:00"),
        ("q4", "a3", "human", "48:00"), ("a4", "q4", "assistant", "48:10"),
        ("q5", "a4", "human", "49:00"), ("a5", "q5", "assistant", "49:10"),
        ("a5b", "a5", "assistant", "49:30"),  # an answer going on after an interrupted one
    ]
    msgs = [{"uuid": u, "parent_message_uuid": p, "sender": s, "created_at": f"2026-10-23T17:{t}Z",
             "content": [_t(f"Texte de {u}")]} for u, p, s, t in spec]
    z = tmp / "alpha.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([{"uuid": "c2", "name": "Test ALPHA", "created_at": "2026-10-23T17:33:00Z",
                                                       "chat_messages": msgs}]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-11-01"])
    return site


def test_structure_view_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = _alpha_site(tmp_path)
    ch = lambda **r: annotations.change(site, r, Archive(site).load_raw)  # noqa: E731
    ch(action="title", conversation="c2", message="q3b1", text="Les flèches")
    pg = page
    pg.goto((site / "conversations" / "c2.html").as_uri())
    pg.click('.plan-view .plan-opt[data-v="structure"]')
    assert pg.evaluate("document.documentElement.classList.contains('cev-structure')")
    assert not pg.is_visible(".messages") and pg.is_visible(".st-panel")
    rows = pg.eval_on_selector_all(".st-row", "l => l.map(r => r.querySelector('.st-num').textContent + ' ' + r.querySelector('.st-text').textContent)")
    assert rows == ["0.1 Texte de qa0", "1 Texte de q1", "2 Texte de q2", "2.1 autre réponse de Claude",
                    "2.2 autre réponse de Claude", "3 Texte de q3", "3.1 autre réponse de Claude",
                    "3.2 autre réponse de Claude", "3.2.1 Les flèches", "3.2.1.1 autre réponse de Claude",
                    "3.2.2 Texte de q3b2", "3.2.3 Texte de q3b3", "3.2.0.1 Texte de q3b0",
                    "3.2.0.1.1 autre réponse de Claude", "4 Texte de q4", "5 Texte de q5"], rows  # 18/11: as drawn
    assert pg.eval_on_selector('.st-row[data-uuid="q3b1"] .st-text', "e => e.tagName") == "B"  # a title, in bold
    pos = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.st-svg circle')].map(c => "
                      "[c.dataset.uuid, [+c.getAttribute('cx'), +c.getAttribute('cy')]]))")
    # the versions of one question / one answer in one column, one under the other
    assert pos["qa0"][0] == pos["q1"][0] and pos["a2x"][0] == pos["a2y"][0] == pos["a2"][0]
    assert pos["q3b0"][0] == pos["q3b1"][0] and pos["a3a"][0] == pos["a3b"][0] == pos["a3"][0]
    assert pos["q1"][1] < pos["qa0"][1] and pos["a2"][1] < pos["a2x"][1] < pos["a2y"][1]
    # no crossing: the branch leaving furthest right (3.2.1.1) is nearer than the one leaving before (3.2.0.1)
    assert pos["q3b1"][1] < pos["a3b1x"][1] < pos["q3b0"][1] < pos["a3b0x"][1]
    # the mouse over a line: its date, and its point lit; over a point: its line lit
    when = pg.inner_text('.message[data-uuid="q3b1"] > .message-time time')
    assert when and pg.get_attribute('.st-row[data-uuid="q3b1"]', "title") == when
    assert pg.text_content('.st-svg circle[data-uuid="q3b1"] > title') == when
    pg.hover('.st-row[data-uuid="q3b1"]')
    assert "st-hi" in pg.get_attribute('.st-svg circle[data-uuid="q3b1"]', "class")
    pg.hover('.st-svg circle[data-uuid="q2"]')
    assert "st-hi" in pg.get_attribute('.st-row[data-uuid="q2"]', "class")
    assert "st-hi" not in pg.get_attribute('.st-svg circle[data-uuid="q3b1"]', "class")
    # a click on a question: it and its answer under the list, after a line, as in the reading view (even in
    # another version); the other answers folded in their frames
    assert not pg.is_visible(".st-sep")
    pg.click('.st-row[data-uuid="q3b1"]')
    shown = "[...document.querySelectorAll('.message[data-uuid]')].filter(m => m.checkVisibility()).map(m => m.dataset.uuid)"
    frames = ("[...document.querySelectorAll('details.removed-part')].filter(d => d.checkVisibility())"
              ".map(d => d.querySelector('.message').dataset.uuid + (d.open ? ' ouvert' : ' replié'))")
    assert pg.evaluate(shown) == ["q3b1", "a3b1"] and pg.is_visible(".st-sep")
    assert pg.evaluate(frames) == ["a3b ouvert", "a3b1x replié"]  # the frame of 3.2 on the way (its line hidden)
    assert pg.is_visible('.message[data-uuid="q3b1"] > .message-bubble') and pg.is_visible('.message[data-uuid="q3b1"] .fav-star')
    assert not pg.is_visible(".removed-part > summary")
    assert "st-sel" in pg.get_attribute('.st-row[data-uuid="q3b1"]', "class")
    pg.click('.st-svg circle[data-uuid="a2x"]')  # a point of an answer: its question with it
    assert pg.evaluate(shown) == ["q2", "a2x"] and pg.evaluate(frames) == ["a2x ouvert", "a2y replié"]
    pg.click('.st-svg circle[data-uuid="q2"]')  # its question: the followed answer, the two others folded
    assert pg.evaluate(shown) == ["q2", "a2"] and pg.evaluate(frames) == ["a2x replié", "a2y replié"]
    pg.click('.removed-part.st-alt > summary')  # a folded answer can be opened
    assert pg.evaluate(shown) == ["q2", "a2x", "a2"]
    # kept by the browser
    pg.reload()
    assert pg.is_visible(".st-panel") and pg.locator(".st-row").count() == 16
    pg.click('.plan-view .plan-opt[data-v="reading"]')
    assert pg.is_visible(".messages") and not pg.is_visible(".st-panel")
    assert pg.errors == []


def test_titles_in_the_reading_view(tmp_path: Path, page) -> None:  # noqa: F811
    """A title is entered in the reading view too, and the list of the structure view shows it; your bubbles of
    another version: the blue frame without the fill."""
    site = _alpha_site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c2.html")
        q1 = '.message[data-uuid="q1"]'
        pg.click(q1 + " .plan-add-title")
        pg.fill(".cev-title-edit", "Titre en lecture")
        pg.press(".cev-title-edit", "Enter")
        pg.wait_for_selector(q1 + " > .cev-title:not(:has(input))")
        assert pg.inner_text(q1 + " > .cev-title") == "Titre en lecture"
        assert annotations.load(site)["titles"]["c2"]["q1"]["text"] == "Titre en lecture"
        # 14/11: the T icon stays, coloured; its click writes the title again, its second click saves; nothing moves
        t_icon = q1 + " .plan-add-title"
        assert pg.is_visible(t_icon) and "has-title" in pg.get_attribute(t_icon, "class")
        rect = "e => { const r = e.getBoundingClientRect(); return [r.top, r.height]; }"
        before = pg.eval_on_selector(q1 + " > .cev-title", rect)
        pg.click(t_icon)
        assert pg.eval_on_selector(q1 + " > .cev-title", rect) == before and pg.is_visible(q1 + " .cev-title-edit")
        pg.fill(".cev-title-edit", "Titre repris")
        pg.click(t_icon)
        pg.wait_for_selector(q1 + " > .cev-title:not(:has(input))")
        assert pg.inner_text(q1 + " > .cev-title") == "Titre repris" and pg.eval_on_selector(q1 + " > .cev-title", rect) == before
        for _ in range(50):
            if annotations.load(site)["titles"]["c2"]["q1"]["text"] == "Titre repris":
                break
            pg.wait_for_timeout(100)
        assert annotations.load(site)["titles"]["c2"]["q1"]["text"] == "Titre repris"
        # "Masquer les titres": unchecked at the opening, hides the titles; the T icon shows them again
        assert not pg.is_checked("#hide-titles")
        pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
        pg.check("#hide-titles")
        assert not pg.is_visible(q1 + " > .cev-title")
        pg.click(t_icon)
        assert not pg.is_checked("#hide-titles") and pg.is_visible(q1 + " .cev-title-edit")
        pg.press(".cev-title-edit", "Escape")
        # the head of a note does not move when its tools come
        pg.click(q1 + " .note-btn")
        pg.fill(".cev-note-edit", "Une note")
        pg.click(q1 + " .note-btn")
        pg.wait_for_selector(q1 + " > .cev-note .cev-note-text")
        line = q1 + " > .cev-note .cev-note-head"
        head = pg.eval_on_selector(line, "e => e.getBoundingClientRect().height")
        pg.click(q1 + " > .cev-note .cev-note-text")
        pg.wait_for_selector(q1 + " > .cev-note .cev-note-edit")
        assert pg.eval_on_selector(line, "e => e.getBoundingClientRect().height") == head
        top = lambda sel: pg.eval_on_selector(sel, "e => e.getBoundingClientRect().top")  # noqa: E731
        assert top(q1 + " > .message-time") < top(q1 + " > .cev-title") < top(q1 + " > .message-bubble")
        # the fill and the frame of your bubble: two distinct blues; another version: the frame only
        style = "e => { const c = getComputedStyle(e); return [c.backgroundColor, c.borderTopColor]; }"
        fill, frame = pg.eval_on_selector(q1 + " > .message-bubble", style)
        assert fill != frame and fill != "rgba(0, 0, 0, 0)"
        assert pg.eval_on_selector('.message[data-uuid="qa0"] > .message-bubble', style) == ["rgba(0, 0, 0, 0)", frame]
        pg.click('.plan-view .plan-opt[data-v="structure"]')
        assert pg.inner_text('.st-row[data-uuid="q1"] b.st-text') == "Titre repris"
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


def test_moves_and_links_are_annotations(tmp_path: Path) -> None:
    site = _alpha_site(tmp_path)
    ch = lambda **r: annotations.change(site, r, Archive(site).load_raw)  # noqa: E731
    moves = lambda st: st["moves"].get("c2", {})  # noqa: E731
    assert moves(ch(action="move", conversation="c2", message="q4", target="q2", how="under")) == {"q4": {"to": "q2", "how": "under"}}
    for bad in ({"message": "q4", "target": "q4", "how": "under"}, {"message": "nope", "target": "q2", "how": "under"},
                {"message": "q4", "target": "nope", "how": "after"}, {"message": "q4", "target": "q2", "how": "sideways"},
                {"message": "q4", "target": "q2", "how": "cut"}):
        with pytest.raises(annotations.AnnotationError):
            ch(action="move", conversation="c2", **bad)
    # after the answer it follows on claude.ai: back in place
    assert moves(ch(action="move", conversation="c2", message="q4", target="a3", how="after")) == {}
    assert moves(ch(action="move", conversation="c2", message="q4", target="a2", how="after")) == {"q4": {"to": "a2", "how": "after"}}
    assert moves(ch(action="move", conversation="c2", message="q4", how="cut")) == {"q4": {"to": None, "how": "cut"}}
    st = ch(action="bend", conversation="c2", message="q4", bend=-30)
    assert moves(st)["q4"]["bend"] == -30
    state = ch(action="relation", conversation="c2", a="q3", b="q4", dir="to")
    assert state["relations"] == {"c2": [{"a": "q3", "b": "q4", "dir": "to"}]}
    ch(action="bend", conversation="c2", a="q3", b="q4", bend=40)
    state = ch(action="relation", conversation="c2", a="q3", b="q4", dir="both")  # one link per pair, its curve kept
    assert state["relations"] == {"c2": [{"a": "q3", "b": "q4", "dir": "both", "bend": 40.0}]}
    with pytest.raises(annotations.AnnotationError):
        ch(action="relation", conversation="c2", a="q3", b="q4", dir="sideways")
    # "Annuler": back step by step, the history kept in the archive (10 changes at most)
    state = ch(action="undo_structure", conversation="c2")
    assert state["relations"] == {"c2": [{"a": "q3", "b": "q4", "dir": "to", "bend": 40.0}]}
    ch(action="undo_structure", conversation="c2")
    ch(action="undo_structure", conversation="c2")
    assert moves(ch(action="undo_structure", conversation="c2")) == {"q4": {"to": None, "how": "cut"}}
    for k in range(15):
        ch(action="bend", conversation="c2", message="q4", bend=k)
    assert len(annotations.load(site)["structure_history"]["c2"]) == annotations.STRUCTURE_UNDO
    assert "structure_history = " not in (site / annotations.DATA_JS).read_text(encoding="utf-8")
    state = ch(action="reset_structure", conversation="c2")
    assert state["moves"] == {} and state["relations"] == {}
    assert moves(ch(action="undo_structure", conversation="c2"))["q4"]["bend"] == 14  # even a reset can be taken back


def test_logical_order_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = _alpha_site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.set_viewport_size({"width": 1200, "height": 900})
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c2.html")
        pg.click('.plan-view .plan-opt[data-v="structure"]')
        pg.wait_for_selector(".st-reset", state="detached")  # nothing to reset nor to undo yet
        node = '.st-svg [data-uuid="{}"]'

        def centre(u: str) -> tuple[float, float]:
            b = pg.locator(node.format(u)).bounding_box()
            return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

        def drag(a: str | tuple[float, float], b: str | tuple[float, float], shift: bool = False) -> None:
            (x1, y1) = centre(a) if isinstance(a, str) else a
            (x2, y2) = centre(b) if isinstance(b, str) else b
            if shift:
                pg.keyboard.down("Shift")
            pg.mouse.move(x1, y1)
            pg.mouse.down()
            pg.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=4)
            pg.mouse.move(x2, y2, steps=4)
            pg.mouse.up()
            if shift:
                pg.keyboard.up("Shift")

        moves = lambda: annotations.load(site)["moves"].get("c2", {})  # noqa: E731
        changed = lambda: pg.wait_for_function("window.CEV_ANNOTATIONS && true")  # noqa: E731
        positions = ("Object.fromEntries([...document.querySelectorAll('.st-svg [data-uuid]')].map(c => "
                     "{ const b = c.getBBox(); return [c.dataset.uuid, [b.x + b.width / 2, b.y + b.height / 2]]; }))")
        shown = "[...document.querySelectorAll('.message[data-uuid]')].filter(m => m.checkVisibility()).map(m => m.dataset.uuid)"
        # a click on a question: the question and all its answers (here an interrupted one and its sequel)
        pg.click(node.format("q5"))
        assert pg.evaluate(shown) == ["q5", "a5", "a5b"]
        pg.click(node.format("a5b"))
        assert pg.evaluate(shown) == ["q5", "a5", "a5b"]
        pg.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        drag("q4", "q2")  # actual order: a question does not move
        pg.wait_for_timeout(300)
        assert moves() == {}
        pg.click(".st-order .plan-opt[data-v='logic']")
        # onto a question: under it, the lowest lane, its line curved from the answer before (not through 4)
        drag("q4", "q2")
        pg.wait_for_function("document.querySelector('.st-row[data-uuid=\"q4\"] .st-tag') !== null")
        assert moves() == {"q4": {"to": "q2", "how": "under"}}
        pos = pg.evaluate(positions)
        assert pos["q4"][0] == pos["q2"][0] and pos["q5"][1] == pos["q4"][1]
        assert pos["q4"][1] > max(y for u, (_, y) in pos.items() if u not in ("q4", "a4", "q5", "a5", "a5b"))
        assert pg.locator('.st-curve[data-kind="move"] .st-join').count() == 1
        rows = pg.eval_on_selector_all(".st-row", "l => l.map(r => r.dataset.uuid)")
        assert rows[rows.index("q4") + 1] == "q5" and rows.index("q4") > rows.index("q2")  # 18/11: another version of 2
        indent = lambda u: pg.eval_on_selector(f'.st-row[data-uuid="{u}"]', "r => r.style.paddingLeft")  # noqa: E731
        assert indent("q4") == indent("q2")
        assert pg.inner_text('.st-row[data-uuid="q4"] .st-tag') == "déplacée sous 2"
        # its handle bends the line, kept; a double click on it: the automatic curve
        handle = pg.locator('.st-curve[data-kind="move"] .st-handle')
        pg.hover('.st-curve[data-kind="move"] .st-curve-hit', force=True)
        hb = handle.bounding_box()
        drag((hb["x"] + 5, hb["y"] + 5), (hb["x"] - 40, hb["y"] + 5))
        pg.wait_for_function("((window.CEV_ANNOTATIONS.moves || {}).c2 || {}).q4 && 'bend' in window.CEV_ANNOTATIONS.moves.c2.q4")
        assert isinstance(moves()["q4"]["bend"], float)
        pg.hover('.st-curve[data-kind="move"] .st-curve-hit', force=True)
        handle.dblclick()
        pg.wait_for_function("!('bend' in window.CEV_ANNOTATIONS.moves.c2.q4)")
        # a question cannot go under what follows it
        drag("q2", "q3")
        pg.wait_for_timeout(300)
        assert moves() == {"q4": {"to": "q2", "how": "under"}}
        # onto the answer it followed: back in its place, on its line
        drag("q4", "a3")
        pg.wait_for_function("!document.querySelector('.st-row[data-uuid=\"q4\"] .st-tag')")
        assert moves() == {}
        # onto another answer: after it; what followed that answer becomes another version, below
        drag("q4", "a2")
        pg.wait_for_function("document.querySelector('.st-row[data-uuid=\"q4\"] .st-tag') !== null")
        assert moves() == {"q4": {"to": "a2", "how": "after"}}
        assert pg.inner_text('.st-row[data-uuid="q4"] .st-tag') == "à la suite de R2"
        pos = pg.evaluate(positions)
        assert pos["q4"][1] == pos["a2"][1] and pos["q4"][0] == pos["q3"][0] and pos["q3"][1] > pos["q4"][1]
        # a double click: from that question to the end of its branch, in the order shown
        pg.dblclick(node.format("q1"))
        assert pg.evaluate(shown) == ["q1", "a1", "q2", "a2", "q4", "a4", "q5", "a5", "a5b"]
        pg.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        pg.wait_for_timeout(500)
        # ✂ on the line coming to a question: the part stays alone, without its line
        pg.hover(f'.st-cut[data-cut="q5"] .st-cut-hit', force=True)
        pg.click('.st-cut[data-cut="q5"] .st-scissors')
        pg.wait_for_function("((window.CEV_ANNOTATIONS.moves || {}).c2 || {}).q5")
        assert moves()["q5"] == {"to": None, "how": "cut"}
        assert pg.inner_text('.st-row[data-uuid="q5"] .st-tag') == "coupée"
        # a logical link: Shift + drag; a click on it: → ← ↔, then removed
        drag("q3", "q4", shift=True)
        pg.wait_for_function("document.querySelector('.st-row[data-uuid=\"q3\"] .st-lk') !== null")
        assert pg.inner_text('.st-row[data-uuid="q3"] .st-lk') == "→ 4" and pg.inner_text('.st-row[data-uuid="q4"] .st-lk') == "← 3"
        for way in ("back", "both", None):
            pg.locator(".st-rel-hit").dispatch_event("click")
            pg.wait_for_function("(w) => { const r = ((window.CEV_ANNOTATIONS.relations || {}).c2 || [])[0]; return w ? r && r.dir === w : !r; }",
                                 arg=way)
        # "Annuler": back step by step (the link, then the cut…)
        pg.click(".st-back")
        pg.wait_for_function("((window.CEV_ANNOTATIONS.relations || {}).c2 || [])[0]?.dir === 'both'")
        for _ in range(4):
            pg.click(".st-back")
            pg.wait_for_timeout(150)
        pg.wait_for_function("!((window.CEV_ANNOTATIONS.moves || {}).c2 || {}).q5")
        assert moves() == {"q4": {"to": "a2", "how": "after"}}
        # ↺ puts a question back; "Réinitialisation" (after Oui) removes everything
        pg.click('.st-row[data-uuid="q4"] .st-undo')
        pg.wait_for_function("!document.querySelector('.st-row[data-uuid=\"q4\"] .st-tag')")
        assert moves() == {}
        pg.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        pg.wait_for_timeout(300)
        drag("q4", "q2")
        pg.wait_for_selector('.st-row[data-uuid="q4"] .st-tag')
        pg.click(".st-reset:not(.st-back)")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector('.st-row[data-uuid="q4"] .st-tag', state="detached")
        assert moves() == {}
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


def test_cut_then_moves_in_the_structure(tmp_path: Path, page) -> None:  # noqa: F811
    """The user's sequences on "Test ALPHA" (11/11): cut Q1–Q2, Q3 onto R1 (✂ on its new line), then Q5 under Q2
    (cut too: no line from R1); a cut part at the left of the list."""
    site = _alpha_site(tmp_path)
    ch = lambda **r: annotations.change(site, r, Archive(site).load_raw)  # noqa: E731
    ch(action="move", conversation="c2", message="q2", how="cut")
    ch(action="move", conversation="c2", message="q3", how="after", target="a1")
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.set_viewport_size({"width": 1200, "height": 900})
        url = f"http://127.0.0.1:{server.server_address[1]}/conversations/c2.html"
        pg.goto(url)
        pg.click('.plan-view .plan-opt[data-v="structure"]')
        pg.click('.st-order .plan-opt[data-v="logic"]')
        pg.wait_for_selector('.st-row[data-uuid="q3"] .st-tag')
        assert pg.locator('.st-cut[data-cut="q3"]').count() == 1      # the line R1 – Q3 can be cut
        assert pg.locator('.st-cut[data-cut="q2"]').count() == 0      # no line: nothing to cut
        ch(action="move", conversation="c2", message="q5", how="under", target="q2")
        pg.goto(url)
        pg.wait_for_selector('.st-row[data-uuid="q5"] .st-tag')
        to = lambda u: pg.evaluate("u => { const c = document.querySelector('.st-svg [data-uuid=\"' + u + '\"]'); "  # noqa: E731
                                   "return [...document.querySelectorAll('.st-svg line.st-main, .st-svg line.st-alt')]"
                                   ".filter(l => l.getAttribute('x2') == c.getAttribute('cx') && l.getAttribute('y2') == c.getAttribute('cy')).length; }", u)
        assert to("q2") == to("q5") == 0                                 # no line to Q2 nor to Q5
        assert pg.locator('.st-curve[data-kind="move"]').count() == 0   # Q5 cut as Q2, no curve from R1
        pad = lambda u: pg.eval_on_selector(f'.st-row[data-uuid="{u}"]', "e => e.style.paddingLeft")  # noqa: E731
        assert pad("q2") == pad("q5") == pad("q1") == "0px"            # cut parts at the left
    finally:
        server.shutdown()


def test_structure_numbers_in_the_reading(tmp_path: Path, page) -> None:  # noqa: F811
    """18/11 (AE-c1): on the line of each bubble, its direct relations in the drawing (the order chosen in the
    structure view): "[before] ← [itself] → [other answers] [questions after]", drawn as the points; a click goes
    to that bubble; the logical links in green; "Masquer les numéros" hides them, their place kept."""
    site = _alpha_site(tmp_path)
    ch = lambda **r: annotations.change(site, r, Archive(site).load_raw)  # noqa: E731
    ch(action="relation", conversation="c2", a="q3", b="q5", dir="to")
    ch(action="move", conversation="c2", message="q4", target="a2", how="after")
    pg = page
    pg.goto((site / "conversations" / "c2.html").as_uri())
    badge = '.message[data-uuid="{}"] > .message-time > .st-badge'
    pg.wait_for_selector(badge.format("q3"), state="attached")
    text = lambda u: pg.eval_on_selector(badge.format(u), "b => [...b.querySelectorAll('.st-pill, .st-arrow, .st-cut, "  # noqa: E731
                                         ".st-badge-link')].map(e => e.textContent).join(' ')")
    # the real order
    assert text("q1") == "1 → 2" and text("q2") == "1 ← 2 → 2.1 2.2 3"
    assert text("q3") == "2 ← 3 → 3.1 3.2 4 → 5" and text("q4") == "3 ← 4 → 5"  # (→ 5: the logical link, green)
    assert text("a3a") == "3 ← 3.1" and text("a2") == "R2"
    cls = lambda u, n: pg.eval_on_selector(f'{badge.format(u)} .st-pill:nth-child({n})', "e => e.className")  # noqa: E731
    assert cls("q2", 1) == "st-pill" and "st-ans" in pg.eval_on_selector(badge.format("q2") + " .st-after > :first-child", "e => e.className")
    pg.evaluate("window.scrollTo(0, 0)")
    pg.click(badge.format("q4") + " button.st-pill")
    pg.wait_for_selector('.message[data-uuid="q3"].st-flash')
    # the logical order (the move of 4 after R2): 2 ← 4 → 5, 3 then after R2 too
    # 22/11: "Vue" on the line of the title: it does not move; the bar of the structure only in the structure view
    x = lambda: pg.evaluate("(() => { const l = document.querySelector('.plan-view').getBoundingClientRect(); "  # noqa: E731
                            "return [l.left, l.top + window.scrollY]; })()")
    before = x()
    assert not pg.locator("#plan-bar").is_visible()
    pg.click('.plan-view .plan-opt[data-v="structure"]')
    assert x() == before
    assert pg.locator("#plan-bar > .st-bar .st-order").is_visible()  # "Ordre" at the end of the line of "Vue"
    assert pg.locator("#plan-bar .st-help").count() == 0  # "Comment réorganiser" at the top of the panel, on the left
    pg.click('.st-order .plan-opt[data-v="logic"]')
    # in the structure view, a pill shows that question as a click in the list does
    pg.click('.st-row[data-uuid="q4"]')
    pg.wait_for_selector('.message[data-uuid="q4"].st-shown')
    pg.click(badge.format("q4") + " button.st-pill:not(.st-self)")
    pg.wait_for_selector('.message[data-uuid="q2"].st-shown')
    pg.click('.plan-view .plan-opt[data-v="reading"]')
    assert not pg.locator("#plan-bar > .st-bar").is_visible() and x() == before
    assert text("q4") == "2 ← 4 → 5" and text("q2") == "1 ← 2 → 2.1 2.2 4 3"
    where = ("m => { const t = m.querySelector(':scope > .message-time time').getBoundingClientRect(); "
             "return [m.getBoundingClientRect().top + window.scrollY, t.left, m.querySelector(':scope > .message-time').offsetHeight]; }")
    pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles; before measuring)
    top = pg.eval_on_selector('.message[data-uuid="a4"]', where)
    pg.check("#hide-numbers")
    assert not pg.is_visible(badge.format("q1"))
    assert pg.eval_on_selector('.message[data-uuid="a4"]', where) == top  # the place kept: nothing moves
    pg.uncheck("#hide-numbers")
    assert pg.is_visible(badge.format("q1")) and not pg.errors


def test_structure_list_follows_the_drawing(tmp_path: Path, page) -> None:  # noqa: F811
    """18/11: the list under the drawing, in its order and with its indents (the user's example): the starts of the
    thread in the order asked; several questions after one answer one step to the right each, in the order of the
    drawing; a question alone after an answer the same step; the other answers of a question one step to the right."""
    site = _alpha_site(tmp_path)
    annotations.change(site, {"action": "move", "conversation": "c2", "message": "q4", "target": "a2", "how": "after"},
                       Archive(site).load_raw)
    pg = page
    pg.add_init_script("try { localStorage.setItem('cev-view', 'structure'); localStorage.setItem('cev-struct-order', 'logic'); } catch (e) {}")
    pg.goto((site / "conversations" / "c2.html").as_uri())
    pg.wait_for_selector(".st-row")
    rows = pg.eval_on_selector_all(".st-row", "l => l.map(r => parseInt(r.style.paddingLeft) / 22 + ' ' + r.querySelector('.st-num').textContent)")
    assert rows == ["0 0.1", "0 1", "0 2", "1 2.1", "1 2.2", "1 4", "1 5", "1 3", "2 3.1", "2 3.2", "3 3.2.1", "4 3.2.1.1",
                    "3 3.2.2", "3 3.2.3", "3 3.2.0.1", "4 3.2.0.1.1"]
