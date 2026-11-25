"""Phase C of 2026-10-29 in a real browser (skipped without Chromium): the arrow of the
Favorites frame, the other versions hidden on the page when the box is unchecked."""

from pathlib import Path

from .test_fold_browser import _site
from .test_topics_browser import page  # noqa: F401 - fixture


def test_favorites_arrow_and_versions_hidden(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    pg.goto((_site(tmp_path) / "conversations" / "c1.html").as_uri())
    # P3 (11/11): the frames of the head are tabs, one open at a time
    pg.click("#fav-list > summary")
    pg.click("#note-list > summary")
    pg.wait_for_function("[...document.querySelectorAll('.fav-tabs > .fav-list[open]')].map(d => d.id).join() === 'note-list'")

    # C3 (21/11: "Masquer : les autres versions et suppressions", the screen only): the other versions hidden on the
    # page and not searched; the box of the export no longer acts on the screen
    frame = pg.locator(".removed-part").first
    assert frame.is_visible()
    pg.click('#page-nav [data-go="find"]')
    pg.fill(".hit-words", "autre")
    pg.press(".hit-words", "Enter")
    assert pg.locator("mark.cev-hit").count() == 1
    pg.evaluate("document.getElementById('export-tab').open = true")  # (22/11: in the tab Exporter)
    pg.locator("#export-main").check()
    assert frame.is_visible()
    pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
    pg.locator("#hide-versions").check()
    assert not frame.is_visible() and frame.evaluate("e => getComputedStyle(e).display") == "none"
    assert pg.locator("mark.cev-hit").count() == 0  # searched again without them
    # (21/11) failed once under the load of the whole suite, never alone: probably the reload coming before Chromium
    # has committed localStorage (a hypothesis, not proved); a user never reloads within milliseconds of a click
    pg.wait_for_timeout(500)
    pg.reload()  # the choices are remembered, each its own
    assert pg.locator("#hide-versions").is_checked() and pg.locator("#export-main").is_checked()
    assert not pg.locator(".removed-part").first.is_visible()
    pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
    pg.locator("#hide-versions").uncheck()
    assert pg.locator(".removed-part").first.is_visible()
    assert pg.errors == []


def test_icons_in_two_frames(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    site = _site(tmp_path)
    pg.goto((site / "conversations" / "c1.html").as_uri())
    assert pg.locator(".back-link").count() == 0 and pg.locator(".convo-title #fold-all").count() == 0

    def place(go: str) -> tuple:
        b = pg.locator("#page-nav .nav-pair" if go == "pair" else f'#page-nav [data-go="{go}"]').bounding_box()
        return round(b["x"]), round(b["y"])

    groups = pg.locator(".nav-group")
    assert groups.count() == 2
    # (22/11) frame above: mark | index ; find | fold ; music | theme ; ‹ | › — frame below: ←|→ ↑ ; (read aloud, served) = ; scrolling ↓
    for frame, rows in ((0, [("mark", "index"), ("find", "fold"), ("music", "theme"), ("hist-back", "hist-forward")]),
                        (1, [("pair", "top"), (None, "middle"), ("scroll", "bottom")])):
        assert pg.locator(f".nav-group >> nth={frame}").locator('[data-go="index"], [data-go="back"]').count() == 1
        for left, right in rows:
            if left:
                assert place(left)[1] == place(right)[1] and place(left)[0] < place(right)[0], (left, right)
    assert place("index")[0] == place("theme")[0] == place("fold")[0] == place("hist-forward")[0]
    assert place("index")[1] < place("fold")[1] < place("music")[1] < place("hist-back")[1] < place("top")[1]  # (22/11)
    # ← | → one round button cut in two, on the place of ←
    assert abs(place("back")[1] - place("next")[1]) <= 1 and place("pair")[0] <= place("back")[0] < place("next")[0]
    assert place("next")[0] < place("top")[0] and not pg.is_visible('#page-nav [data-go="speak"]')  # not served
    pg.click('#page-nav [data-go="index"]')
    pg.wait_for_url("**/index.html")
    # the index: the same frames, without the buttons of the conversations
    assert pg.locator(".nav-group").count() == 2 and pg.locator('#page-nav [data-go="back"]').count() == 0
    # (22/11, Dom) 2x2: music, theme / before, after; below 2x3 as on the pages: top, middle, bottom on the right,
    # the scrolling at the bottom left
    assert place("theme")[1] == place("music")[1] < place("hist-back")[1] == place("hist-forward")[1]
    assert place("music")[0] == place("hist-back")[0] < place("theme")[0] == place("hist-forward")[0]
    assert place("top")[0] == place("middle")[0] == place("bottom")[0] > place("scroll")[0]
    assert place("scroll")[1] == place("bottom")[1] > place("middle")[1] > place("top")[1]
    assert pg.errors == []


def test_buttons_greyed_when_they_have_nothing_to_do(tmp_path: Path, page) -> None:  # noqa: F811
    from .test_favorites import _site as long_site
    pg = page
    site = long_site(tmp_path)
    pg.goto((site / "conversations" / next((site / "conversations").glob("*.html")).name).as_uri())
    pg.wait_for_timeout(200)
    b = {go: pg.locator(f'#page-nav [data-go="{go}"]') for go in ("back", "next", "scroll")}
    assert b["back"].is_disabled() and b["next"].is_enabled() and b["scroll"].is_enabled()  # first message, top
    pg.click('#page-nav [data-go="next"]')  # the first message, at the top: still nothing before it
    pg.wait_for_timeout(900)
    assert b["back"].is_disabled()
    pg.click('#page-nav [data-go="next"]')  # the second one
    pg.wait_for_timeout(900)
    assert b["back"].is_enabled()
    pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")  # the end of the page
    pg.wait_for_timeout(200)
    assert b["next"].is_disabled() and b["scroll"].is_disabled() and b["back"].is_enabled()
    pg.evaluate("window.scrollBy(0, -300)")  # room to go down again
    pg.wait_for_timeout(200)
    assert b["scroll"].is_enabled()
    assert pg.errors == []
