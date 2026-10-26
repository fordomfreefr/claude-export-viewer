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
        pg.wait_for_timeout(200)
        assert pg.evaluate("navigator.clipboard.readText()") == "Calculer $\\int_0^1 x^2\\,dx$ **vite**"
        assert "copied" in pg.locator(".message-human .copy-msg").first.get_attribute("class")

        def top(i: int) -> float:
            return pg.locator(".messages > .message-human").nth(i).evaluate("e => e.getBoundingClientRect().top")

        steps = (("ArrowRight", 0), ("ArrowRight", 1), ("ArrowRight", 2), ("ArrowLeft", 1), ("n", 1), ("ArrowLeft", 0))
        for key, i in steps:  # first: the first message to the top; N: not a key any more
            pg.keyboard.press(key)
            pg.wait_for_timeout(900)  # smooth scrolling
            assert abs(top(i)) < 3, (key, i)
        pg.click('#page-nav [data-go="next"]')  # the Next / Back buttons
        pg.wait_for_timeout(900)
        assert abs(top(1)) < 3
        pg.click('#page-nav [data-go="back"]')
        pg.wait_for_timeout(900)
        assert abs(top(0)) < 3

        assert pg.get_attribute('#page-nav [data-go="next"]', "title") == "Votre message suivant '6'"
        assert pg.get_attribute('#page-nav [data-go="top"]', "title") == "Haut de page '7'"

        def numpad5(key: str) -> None:  # 5 of the numeric keypad, off ("Clear") or on ("5")
            pg.evaluate("k => document.dispatchEvent(new KeyboardEvent('keydown', {key: k, code: 'Numpad5', bubbles: true}))", key)
            pg.wait_for_timeout(400)

        middle = pg.evaluate("Math.round((document.documentElement.scrollHeight - innerHeight) / 2)")
        before = pg.evaluate("scrollY")
        numpad5("5")  # keypad on: the digit is left alone
        assert pg.evaluate("scrollY") == before
        numpad5("Clear")
        assert abs(pg.evaluate("scrollY") - middle) < 3
        pg.evaluate("scrollTo(0, 0)")

        y0 = pg.evaluate("scrollY")  # slow continuous scrolling
        pg.click('#page-nav [data-go="scroll"]')
        pg.wait_for_timeout(1000)
        y1 = pg.evaluate("scrollY")
        assert 15 < y1 - y0 < 60  # speed 3: 32 px/s
        pg.keyboard.press("+")
        pg.keyboard.press("+")
        assert pg.inner_text("#nav-speed") == "Vitesse 5 / 7"
        pg.wait_for_timeout(1000)
        y2 = pg.evaluate("scrollY")
        assert 50 < y2 - y1 < 95  # speed 5: 70 px/s
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        y3 = pg.evaluate("scrollY")
        pg.wait_for_timeout(500)
        assert pg.evaluate("scrollY") == y3 and pg.get_attribute('#page-nav [data-go="scroll"]', "aria-pressed") == "false"
        pg.reload()
        pg.click('#page-nav [data-go="scroll"]')
        assert pg.inner_text("#nav-speed") == "Vitesse 5 / 7"  # speed kept
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
