"""Phase B of 2026-10-29 in a real browser (skipped without Chromium): one way to stop the slow
scrolling, a favorite placed at the top, whole-word search, claude.ai's resources hidden, the
weekly bars sliding."""

from pathlib import Path

from .helpers import ExportData, build_site
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"
LONG = "Remplissage de la réponse.\n\n" * 60


def _msg(uuid: str, parent: str, sender: str, content: list, **kw) -> dict:
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender, "created_at": "2026-09-06T10:19:00Z",
            "content": content, **kw}


def _text(t: str) -> dict:
    return {"type": "text", "text": t}


def _site(tmp: Path) -> Path:
    think = {"type": "thinking", "thinking": "", "summaries": [{"summary": "Réflexion résumée"}]}
    search = [{"type": "tool_use", "name": "web_search", "input": {"query": "noyer"}},
              {"type": "tool_result", "name": "web_search", "content": [{"type": "text", "text": "résultat"}]}]
    msgs = [
        _msg("q1", ROOT, "human", [_text("Un Acer pour placer le café ?"),
                                   {"type": "injected_prompt_block", "prompt": "Consigne de claude.ai",
                                    "injection_source": {"type": "date_note"}}],
             attachments=[{"file_name": "notes.txt", "file_type": "txt", "file_size": 12, "extracted_content": "contenu joint"}]),
        _msg("a1", "q1", "assistant", [think] + search + [_text("Acer, placer, caf. " + LONG)]),
        _msg("a1c", "a1", "assistant", [], text=""),  # compaction
        _msg("q2", "a1c", "human", [_text("Deuxième question")]),
        _msg("a2", "q2", "assistant", [_text(LONG)]),
    ]
    old = {"uuid": "c0", "name": "Ancienne", "created_at": "2024-01-10T10:00:00Z", "updated_at": "2024-01-10T10:00:00Z",
           "chat_messages": [_msg("o1", ROOT, "human", [_text("ancienne question")])]}
    out = tmp / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai", "chat_messages": msgs}, old]), out)
    return out


def test_phase_b_conversation(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    url = (_site(tmp_path) / "conversations" / "c1.html").as_uri()
    pg.goto(url)
    scroll = pg.locator('#page-nav [data-go="scroll"]')

    # B4: claude.ai's folding lines and the compaction hidden by default; the user's file shown
    box = pg.locator("#hide-resources")
    pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
    assert box.is_checked()
    for sel in (".thinking", ".cev-resources", ".cev-cut"):
        assert pg.locator(sel).count() >= 1 and not pg.locator(sel).first.is_visible(), sel
    assert pg.get_by_text("notes.txt").first.is_visible()
    box.uncheck()
    for sel in (".thinking", ".message-assistant .cev-resources", ".cev-cut .cut-note"):
        assert pg.locator(sel).first.is_visible(), sel
    assert pg.locator(".message-human .cev-resources").count() == 0  # 5b: claude.ai's instructions in Claude's reply
    pg.reload()  # 21/11: the choice kept by the browser
    assert not pg.locator("#hide-resources").is_checked() and pg.locator(".thinking").first.is_visible()
    pg.evaluate("document.getElementById('bubbles-tab').open = true")
    pg.locator("#hide-resources").check()
    assert not pg.locator(".thinking").first.is_visible()

    # B1: any action stops the slow scrolling; the theme does not
    scroll.click()
    assert scroll.get_attribute("aria-pressed") == "true"
    pg.click('#page-nav [data-go="theme"]')
    assert scroll.get_attribute("aria-pressed") == "true"
    pg.locator("#hide-resources").click()
    assert scroll.get_attribute("aria-pressed") == "false"
    scroll.click()
    pg.click('#page-nav [data-go="find"]')  # the magnifier
    assert scroll.get_attribute("aria-pressed") == "false"

    # B3: whole words (checked by default), accents count as letters
    pg.fill(".hit-words", "acer")
    pg.press(".hit-words", "Enter")
    assert pg.locator("mark.cev-hit").count() == 2  # "Acer" twice, not "placer"
    pg.fill(".hit-words", "caf")
    pg.press(".hit-words", "Enter")
    assert pg.locator("mark.cev-hit").count() == 1  # "caf.", not "café"
    pg.locator(".hit-whole input").uncheck()
    assert pg.locator("mark.cev-hit").count() == 2
    pg.click('#page-nav [data-go="find"]')

    # B2: a favorite: the start of its message at the top of the window
    pg.goto(url + "#msg=q2")
    pg.wait_for_timeout(900)
    top = pg.evaluate("document.querySelector('.message[data-uuid=\"q2\"]').getBoundingClientRect().top")
    assert 0 <= top <= 12
    assert pg.errors == []


def test_weekly_bars_slide(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    pg.goto((_site(tmp_path) / "index.html").as_uri())
    pg.click(".dash-line")
    first = pg.get_attribute("#dash-bars .dash-bar >> nth=0", "data-key")
    pg.click("#dash-prev")
    pg.wait_for_timeout(100)
    assert pg.locator(".dash-ghost i").count() == 26  # the weeks leaving, during the slide
    pg.wait_for_timeout(600)
    assert pg.locator(".dash-ghost").count() == 0
    assert pg.locator("#dash-bars .dash-bar").count() == 52
    assert pg.get_attribute("#dash-bars .dash-bar >> nth=26", "data-key") == first
    assert pg.errors == []


def test_dates_slide_with_the_bars(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    pg.goto((_site(tmp_path) / "index.html").as_uri())
    pg.click(".dash-line")
    before = pg.locator("#dash-axis > span").all_text_contents()
    pg.click("#dash-prev")
    pg.wait_for_timeout(100)
    ghost = pg.locator(".dash-axis-ghost span")
    assert ghost.all_text_contents() == before  # the former dates, beside the new ones
    assert [ghost.nth(i).evaluate("e => getComputedStyle(e).visibility") for i in range(5)] == ["hidden"] * 3 + ["visible"] * 2
    pg.wait_for_timeout(600)
    assert pg.locator(".dash-axis-ghost").count() == 0
    assert pg.locator("#dash-axis > span").all_text_contents()[2:] != before[2:]
    assert pg.errors == []
