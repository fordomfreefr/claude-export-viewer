"""Hiding Claude's answers on a conversation page, in a real browser (skipped without Chromium)."""

from pathlib import Path

from .helpers import ExportData, build_site
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def _msg(uuid: str, parent: str, sender: str, text: str) -> dict:
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender, "created_at": "2026-09-06T10:19:00Z",
            "content": [{"type": "text", "text": text}]}


def _site(tmp: Path) -> Path:
    msgs = [_msg("q1", ROOT, "human", "Question un"), _msg("a1", "q1", "assistant", "Réponse un"),
            _msg("a1b", "q1", "assistant", "Autre réponse un"),  # retried: a frame "other version"
            _msg("q2", "a1", "human", "Question deux"), _msg("a2", "q2", "assistant", "Réponse deux"),
            _msg("q3", "a2", "human", "Question trois sans réponse")]
    # a1 more recent than a1b: the main branch goes through a1
    msgs[1]["created_at"] = "2026-09-06T10:20:00Z"
    out = tmp / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai", "chat_messages": msgs}]), out)
    return out


def visible(pg, text: str) -> bool:
    return pg.get_by_text(text, exact=True).first.is_visible()


def test_fold_answers(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    url = (_site(tmp_path) / "conversations" / "c1.html").as_uri()
    pg.set_viewport_size({"width": 1366, "height": 800})  # 1000 px: the two columns of buttons cover the arrows
    pg.goto(url)
    assert pg.locator(".fold-one").count() == 2  # not on the last message, which has no answer
    assert visible(pg, "Réponse un") and visible(pg, "Réponse deux")

    pg.locator(".message-human .fold-one").nth(1).click()  # the answer to question two only
    assert visible(pg, "Réponse un") and not visible(pg, "Réponse deux") and visible(pg, "Question deux")
    assert pg.get_attribute("#fold-all", "aria-pressed") == "false"

    pg.click("#fold-all")  # every answer: only your messages remain
    for q in ("Question un", "Question deux", "Question trois sans réponse"):
        assert visible(pg, q)
    assert not visible(pg, "Réponse un") and not visible(pg, "Réponse deux")
    assert pg.locator(".cev-folded").filter(has_text="Autre réponse un").count() == 1  # the frame too
    assert pg.get_attribute("#fold-all", "aria-pressed") == "true"
    assert pg.get_attribute("#fold-all", "title") == "Afficher toutes les réponses de Claude"

    pg.locator(".message-human .fold-one").first.click()  # show one answer
    assert visible(pg, "Réponse un") and not visible(pg, "Réponse deux")

    pg.reload()  # kept while the tab is open
    assert visible(pg, "Réponse un") and not visible(pg, "Réponse deux")

    pg.emulate_media(media="print")  # printing shows everything
    assert visible(pg, "Réponse deux") and not pg.locator("#fold-all").is_visible()
    pg.emulate_media(media="screen")

    pg.click("#fold-all")  # not all hidden: hides all
    pg.click("#fold-all")  # all hidden: shows all
    assert visible(pg, "Réponse un") and visible(pg, "Réponse deux")
    assert pg.errors == []


def test_copy_message_and_keys(tmp_path: Path, page) -> None:  # noqa: F811
    import threading
    from claude_export_viewer.server import make_server
    pg = page
    site = tmp_path / "site"
    long = "Ligne de réponse.\n\n" * 60
    msgs = [_msg("q1", ROOT, "human", "Calculer $\\int_0^1 x^2\\,dx$ **vite**"), _msg("a1", "q1", "assistant", long),
            _msg("q2", "a1", "human", "Question deux"), _msg("a2", "q2", "assistant", long),
            _msg("q3", "a2", "human", "Question trois"), _msg("a3", "q3", "assistant", long)]
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai", "chat_messages": msgs}]), site)
    server = make_server(site, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        pg.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
        pg.goto(base + "/conversations/c1.html")
        assert pg.locator(".copy-msg").count() == 6
        pg.locator(".message-human .copy-msg").first.click()
        pg.wait_for_function("navigator.clipboard.readText().then(t => t.length > 0)")
        assert pg.evaluate("navigator.clipboard.readText()") == "Calculer $\\int_0^1 x^2\\,dx$ **vite**"
        assert "copied" in pg.locator(".message-human .copy-msg").first.get_attribute("class")

        def top(i: int) -> float:
            return pg.locator(".messages > .message-human").nth(i).evaluate("e => e.getBoundingClientRect().top")

        def arrived(i: int) -> None:  # the end of the smooth scrolling, not a fixed wait (AF-f6)
            pg.wait_for_function(
                "i => Math.abs(document.querySelectorAll('.messages > .message-human')[i].getBoundingClientRect().top) < 3",
                arg=i)

        steps = (("ArrowRight", 0), ("ArrowRight", 1), ("ArrowRight", 2), ("ArrowLeft", 1), ("n", 1), ("ArrowLeft", 0))
        for key, i in steps:  # first: the first message to the top; N: not a key any more
            pg.keyboard.press(key)
            arrived(i)
        pg.click('#page-nav [data-go="next"]')  # the Next / Back buttons
        arrived(1)
        pg.click('#page-nav [data-go="back"]')
        arrived(0)

        assert pg.get_attribute('#page-nav [data-go="next"]', "title") == "Votre message suivant '6'"
        assert pg.get_attribute('#page-nav [data-go="top"]', "title") == "Haut de page '7'"

        def numpad5(key: str) -> None:  # 5 of the numeric keypad, off ("Clear") or on ("5")
            pg.evaluate("k => document.dispatchEvent(new KeyboardEvent('keydown', {key: k, code: 'Numpad5', bubbles: true}))", key)

        middle = pg.evaluate("Math.round((document.documentElement.scrollHeight - innerHeight) / 2)")
        pg.wait_for_function("new Promise(r => { const y = scrollY; setTimeout(() => r(scrollY === y), 150); })")
        before = pg.evaluate("scrollY")  # settled (the arrival above may still nudge a pixel or two)
        numpad5("5")  # keypad on: the digit is left alone
        pg.wait_for_timeout(300)
        assert pg.evaluate("scrollY") == before
        numpad5("Clear")
        pg.wait_for_function("m => Math.abs(scrollY - m) < 3", arg=middle)
        # the jump keeps aiming until it settles: wait for the real end before moving (its aim would pull back)
        pg.wait_for_function("new Promise(r => { const y = scrollY; setTimeout(() => r(scrollY === y), 150); })")
        pg.evaluate("scrollTo(0, 0)")

        y0 = pg.evaluate("scrollY")  # slow continuous scrolling
        pg.click('#page-nav [data-go="scroll"]')
        pg.wait_for_timeout(1000)
        y1 = pg.evaluate("scrollY")
        assert 15 < y1 - y0 < 60  # speed 5: 32 px/s
        pg.keyboard.press("+")
        pg.keyboard.press("+")
        assert pg.inner_text("#nav-speed") == "Vitesse 7 / 9"
        pg.wait_for_timeout(1000)
        y2 = pg.evaluate("scrollY")
        assert 50 < y2 - y1 < 95  # speed 7: 70 px/s
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(150)
        y3 = pg.evaluate("scrollY")
        pg.wait_for_timeout(400)
        assert pg.evaluate("scrollY") == y3 and pg.get_attribute('#page-nav [data-go="scroll"]', "aria-pressed") == "false"
        pg.reload()
        pg.click('#page-nav [data-go="scroll"]')
        assert pg.inner_text("#nav-speed") == "Vitesse 7 / 9"  # speed kept
        pg.click('#page-nav [data-go="scroll"]')
        pg.evaluate("scrollTo(0, 0)")
        pg.keyboard.press("m")  # hides all the answers
        assert pg.locator(".cev-folded").count() == 3
        pg.keyboard.press("?")
        assert pg.locator(".keys-help").is_visible() and "Votre message suivant (pavé numérique désactivé)" in pg.inner_text(".keys-help")
        pg.keyboard.press("Escape")
        assert not pg.locator(".keys-help").is_visible()
        pg.keyboard.press("m")
        assert pg.locator(".cev-folded").count() == 0
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


def test_theme_music_and_labels(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    site = _site(tmp_path)
    pg.goto((site / "conversations" / "c1.html").as_uri())
    # "Moi" / "Claude" before the date of each message
    assert pg.locator(".message-human .message-who").first.inner_text() == "Moi"
    assert pg.locator(".message-assistant .message-who").first.text_content() == "Claude"
    # a short page: the theme and the music work, the scrolling buttons stay in place, greyed
    assert pg.locator('#page-nav [data-go="theme"]').is_visible()
    assert pg.locator('#page-nav [data-go="music"]').is_visible()
    top = pg.locator('#page-nav [data-go="top"]')
    # (22/11) greyed but its title shown on hover: a click does nothing (nav.js)
    assert top.is_visible() and top.evaluate("e => getComputedStyle(e).opacity") == "0.35"
    pg.evaluate("window.scrollTo(0, 0)")
    pg.click('#page-nav [data-go="middle"]')  # (top: disabled at the top of the page)
    assert pg.evaluate("window.scrollY") == 0
    theme = '#page-nav [data-go="theme"]'
    bg = "getComputedStyle(document.documentElement).backgroundColor"
    assert pg.get_attribute(theme, "title") == "Thème : système" and pg.evaluate("document.documentElement.dataset.theme") == "light"  # the system (light here), 14/11
    light = pg.evaluate(bg)
    pg.click(theme)
    assert pg.get_attribute(theme, "title") == "Thème : clair" and pg.evaluate(bg) == light
    pg.click(theme)
    assert pg.get_attribute(theme, "title") == "Thème : sombre" and pg.evaluate(bg) != light  # counter-check: really dark
    pg.reload()
    assert pg.evaluate("document.documentElement.dataset.theme") == "dark" and pg.get_attribute(theme, "data-mode") == "dark"
    pg.click(theme)  # back to the system's
    assert pg.evaluate("document.documentElement.dataset.theme") == "light" and pg.evaluate(bg) == light
    # the music: on / off, volume by the wheel or + / - over the note, kept
    music = '#page-nav [data-go="music"]'
    pg.click(music)
    assert pg.get_attribute(music, "aria-pressed") == "true" and pg.get_attribute(music, "title").startswith("Couper")
    pg.hover(music)
    pg.mouse.wheel(0, -100)
    assert pg.inner_text("#nav-volume") == "Volume 4 / 7"
    pg.keyboard.press("-")
    pg.keyboard.press("-")
    assert pg.inner_text("#nav-volume") == "Volume 2 / 7"
    pg.click(music)
    assert pg.get_attribute(music, "aria-pressed") == "false"
    pg.reload()
    pg.hover(music)
    pg.keyboard.press("+")
    assert pg.inner_text("#nav-volume") == "Volume 3 / 7"  # kept: 2 + 1
    # the wheel over the play button changes the speed of the scrolling
    pg.evaluate("document.body.style.minHeight = '5000px'")
    pg.wait_for_timeout(200)
    pg.hover('#page-nav [data-go="scroll"]')
    pg.mouse.wheel(0, -100)
    assert pg.inner_text("#nav-speed") == "Vitesse 6 / 9"
    assert not pg.errors


def test_index_frame_and_buttons(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    site = _site(tmp_path)
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "dl-system" not in html and "(dossier du système)" not in html
    frame = pg.locator(".filter-frame")
    pg.goto((site / "index.html").as_uri())
    pg.click("#tab-filters")  # 14/11: the filters in their tab
    # one frame: both search boxes and the sort menu, rows split by a thin line
    for el in ("#search", "#content-search", "#sort-by"):
        assert frame.locator(el).count() == 1, el
    assert pg.locator(".filter-row").nth(1).evaluate("e => getComputedStyle(e).borderTopStyle") == "solid"
    assert pg.locator('#page-nav [data-go="theme"]').is_visible()  # also on the index
    assert pg.locator('#page-nav [data-go="find"]').count() == 0  # the index has its own search
    pg.goto((site / "conversations" / "c1.html").as_uri())
    # the way back to the index: the round button "Vers le sommaire" (C1), no longer a link at the top
    assert pg.locator(".back-link").count() == 0 and pg.locator('#page-nav [data-go="index"]').is_visible()
    assert not pg.errors


def test_print_ink(tmp_path: Path, page) -> None:  # noqa: F811
    """Printing (11/11): bubbles without fill, Claude's frame thin black, notes in black, even in the dark theme."""
    pg = page
    pg.goto((_site(tmp_path) / "conversations" / "c1.html").as_uri())
    pg.evaluate("""() => { document.documentElement.setAttribute('data-theme', 'dark');
      const n = document.createElement('div'); n.className = 'cev-note'; n.id = 'n';
      n.innerHTML = '<span class="cev-note-label">Note</span><div class="cev-note-text">Texte</div>';
      document.querySelector('.message-assistant').appendChild(n); }""")
    style = "(s) => { const e = document.querySelector(s), c = getComputedStyle(e); return [c.backgroundColor, c.borderTopColor, c.color]; }"
    pg.emulate_media(media="print")
    human, claude = pg.evaluate(style, ".message-human .message-bubble"), pg.evaluate(style, ".message-assistant .message-bubble")
    assert human[0] == claude[0] == "rgba(0, 0, 0, 0)"
    assert claude[1] == "rgb(0, 0, 0)" and human[1] != "rgb(0, 0, 0)"   # yours keeps its blue frame
    assert pg.evaluate(style, "#n .cev-note-text")[2] == "rgb(0, 0, 0)"
    assert pg.errors == []
