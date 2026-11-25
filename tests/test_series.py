"""AE-m3 (16-18/11): suites — a link with a direction (annotations "series", in the order set by the user), made
and ordered in "Liens" by dragging (an empty place shows where a row goes); lines "Suite : fil k sur n" on the
pages; the index unchanged."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from claude_export_viewer import annotations
from claude_export_viewer.archive import Archive
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_annotations_e import _site
from .test_topics_browser import page  # noqa: F401 - fixture


def test_series_on_the_server(tmp_path: Path) -> None:
    site = _site(tmp_path)
    load_raw = Archive(site).load_raw
    ch = lambda **r: annotations.change(site, r, load_raw)  # noqa: E731
    ch(action="link", a="c1", b="c2")
    ch(action="link", a="c2", b="c3")
    state = ch(action="series_set", here="c2", order=["c3", "c1", "c2"])  # the order set by the user, not the dates
    assert state["series"] == [["c3", "c1", "c2"]] and set(state["convs"]) == {"c1", "c2", "c3"}
    assert "series_ordered" not in state
    assert state["links"] == {"c1": ["c2", "c3"], "c2": ["c1", "c3"], "c3": ["c1", "c2"]}  # a suite links its conversations
    assert ch(action="series_set", here="c2", order=["c1", "c2"])["series"] == [["c1", "c2"]]  # c3 out
    assert ch(action="series_set", here="c3", order=["c3", "c1"])["series"] == [["c3", "c1"]]  # c1 moved: c2 alone, no suite
    assert ch(action="series_set", here="c3", order=["c3"])["series"] == []
    assert ch(action="link", a="c1", b="c2")["links"]["c3"] == ["c1", "c2"]  # taken out, links kept
    ch(action="series_set", here="c1", order=["c1", "c2", "c3"])
    state = ch(action="unlink", a="c1", b="c3")  # two of one suite unlinked: c3 leaves the suite
    assert state["series"] == [["c1", "c2"]] and "c3" not in state["links"]["c1"]
    ch(action="series_set", here="c2", order=["c1", "c2"])
    assert ch(action="clear_links", conversation="c1")["series"] == []  # no link: no suite
    for bad in ({"here": "c1", "order": ["c1", "c1"]}, {"here": "c1", "order": ["c1", "c9"]}, {"here": "c1", "order": "c2"}):
        with pytest.raises(annotations.AnnotationError):
            ch(action="series_set", **bad)
    assert annotations._clean_series([["b", "a"], ["b", "c"], ["d"], "x"]) == [["b", "a"]]


def test_suites_of_before_put_in_the_order_of_the_dates(tmp_path: Path) -> None:
    site = _site(tmp_path)
    path = site / "archive" / "annotations.json"
    path.write_text(json.dumps({"series": [["c3", "c1", "c2"]]}), encoding="utf-8")  # 16-17/11: kept sorted, any order
    dates = {u: m["created_at"] for u, m in Archive(site).conversations.items()}
    assert annotations.load(site)["series"] == [sorted(["c1", "c2", "c3"], key=lambda u: dates[u])]
    assert annotations.load(site)["links"]["c1"] == ["c2", "c3"]  # the links missing made
    annotations.save(site, annotations.load(site))
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "series": [["c3", "c1", "c2"]]}), encoding="utf-8")
    assert annotations.load(site)["series"] == [["c3", "c1", "c2"]]  # once ordered, the order stays


def _drag(pg, source: str, target: str, below: bool = False) -> None:
    """A row dragged with the mouse onto the upper (or lower) part of another row (or anywhere)."""
    a, b = pg.locator(source).bounding_box(), pg.locator(target).bounding_box()
    pg.mouse.move(a["x"] + 30, a["y"] + a["height"] / 2)
    pg.mouse.down()
    pg.mouse.move(a["x"] + 40, a["y"] + a["height"] / 2 + 8, steps=3)
    y = b["y"] + b["height"] * (0.8 if below else 0.2)
    pg.mouse.move(b["x"] + 30, y, steps=8)
    assert pg.locator(".series-slot").count() == 1  # the empty place
    pg.mouse.up()


def test_series_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    load_raw = Archive(site).load_raw
    annotations.change(site, {"action": "link", "a": "c1", "b": "c3"}, load_raw)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        item = '.conversation-item[data-uuid="{}"]'
        pg.goto(base + "index.html")
        href = {c: pg.get_attribute(item.format(c) + " a", "href") for c in ("c1", "c2", "c3")}
        links = "#link-list li[data-other='{}']"
        nums = lambda: [x.get_attribute("data-other") for x in pg.locator("#link-list .series-items > li").all()]  # noqa: E731
        # one link only (c3 → c1): "ce fil" among the links; c1 put below it: the suite c3, c1
        pg.goto(base + href["c3"])
        pg.click("#link-list > summary")
        pg.wait_for_selector("#link-list .series-hint")
        assert [x.strip() for x in pg.locator("#link-list .fav-excerpt").all_inner_texts()] == ["Noyer", "Lois stables — cette conversation"]
        assert pg.locator("#link-list .series-here .fav-remove").count() == 0
        _drag(pg, links.format("c1"), "#link-list .series-here", below=True)
        pg.wait_for_selector("#link-list .series-box")
        assert nums() == ["c3", "c1"]  # the place set, not the dates (c1 is older)
        assert "Suite : conversation 1 sur 2" in pg.locator(".series-line").first.inner_text()
        # out of the suite by its cross: it stays a link
        pg.locator(links.format("c1") + " .fav-remove").click()
        pg.wait_for_function("!document.querySelector('#link-list .series-box')")
        assert pg.locator("#link-list > .link-items > li[data-other='c1']").count() == 1
        # two links: c1 put above c3 makes the suite c1, c3, then c2 (a link) put between them
        annotations.change(site, {"action": "link", "a": "c2", "b": "c3"}, load_raw)
        pg.reload()
        pg.click("#link-list > summary")
        pg.wait_for_selector("#link-list .series-hint")
        _drag(pg, links.format("c1"), "#link-list .series-here")
        pg.wait_for_selector("#link-list .series-box")
        assert nums() == ["c1", "c3"]
        _drag(pg, links.format("c2"), links.format("c3"))
        pg.wait_for_function("document.querySelectorAll('#link-list .series-items > li').length === 3")
        assert nums() == ["c1", "c2", "c3"]
        assert pg.inner_text("#link-list > summary").strip() == "Liens (2)"
        # the order changed in the frame: c3 ("ce fil") put first
        _drag(pg, "#link-list .series-here", links.format("c1"))
        pg.wait_for_function("document.querySelector('#link-list .series-items > li').dataset.other === 'c3'")
        assert nums() == ["c3", "c1", "c2"]
        # the same suite, in the same order, on the page of c2; its lines follow that order
        pg.goto(base + href["c2"])
        pg.wait_for_selector("#link-list .series-box", state="attached")
        top, bottom = pg.locator(".series-line").first, pg.locator(".series-line").last
        assert "Suite : conversation 3 sur 3" in top.inner_text() and "← Noyer" in top.inner_text()
        assert "Conversation suivante" not in bottom.inner_text()
        # out of the frame by dragging: it stays a link
        pg.click("#link-list > summary")
        _drag(pg, links.format("c1"), ".messages")
        pg.wait_for_function("document.querySelectorAll('#link-list .series-items > li').length === 2")
        assert [x for x in Archive(site).conversations] and annotations.load(site)["series"] == [["c3", "c2"]]
        # the index is unchanged: no line gathers a suite
        pg.goto(base + "index.html")
        pg.wait_for_selector(item.format("c1"))
        assert all(pg.is_visible(item.format(c)) for c in ("c1", "c2", "c3")) and pg.locator(".series-badge").count() == 0
        assert not pg.errors
    finally:
        server.shutdown()
        server.server_close()


def test_moved_from_another_suite_asks_first(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    load_raw = Archive(site).load_raw
    ch = lambda **r: annotations.change(site, r, load_raw)  # noqa: E731
    ch(action="link", a="c1", b="c2")
    ch(action="link", a="c2", b="c3")
    ch(action="series_set", here="c1", order=["c1", "c2"])
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        pg.goto(base + "index.html")
        pg.goto(base + pg.get_attribute('.conversation-item[data-uuid="c3"] a', "href"))
        pg.click("#link-list > summary")
        pg.wait_for_selector("#link-list .series-here")
        _drag(pg, "#link-list li[data-other='c2']", "#link-list .series-here")
        pg.wait_for_selector(".cev-confirm-no")
        pg.click(".cev-confirm-no")  # No: nothing changes
        assert annotations.load(site)["series"] == [["c1", "c2"]]
        _drag(pg, "#link-list li[data-other='c2']", "#link-list .series-here")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector("#link-list .series-box")
        assert annotations.load(site)["series"] == [["c2", "c3"]]  # c2 left its suite (c1 alone: no more suite)
        assert not pg.errors
    finally:
        server.shutdown()
        server.server_close()
