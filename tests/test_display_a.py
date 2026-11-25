"""Phase A of 2026-10-29: the user's text as typed, thinking summaries, pasted texts,
claude.ai's instructions in the user's message, cut replies, the drop hint."""

from __future__ import annotations

from typing import Any

from claude_export_viewer import i18n
from claude_export_viewer.html_builder import render_archived_conversation
from claude_export_viewer.markdown_export import message_body
from claude_export_viewer.models import parse_message

ROOT = "00000000-0000-4000-8000-000000000000"


def _msg(i: int, sender: str, content: list[dict[str, Any]], parent: int | None = None, **kw: Any) -> dict[str, Any]:
    return {"uuid": f"m{i}", "parent_message_uuid": f"m{parent}" if parent is not None else ROOT,
            "sender": sender, "created_at": f"2026-10-01T10:0{i}:00Z", "content": content, **kw}


def _page(*msgs: dict[str, Any]) -> str:
    raw = {"uuid": "c1", "name": "Essai", "created_at": "2026-10-01T10:00:00Z",
           "updated_at": "2026-10-01T10:09:00Z", "chat_messages": list(msgs)}
    return "\n".join(render_archived_conversation(raw, files={})[1])


def test_user_text_as_typed() -> None:
    typed = "ligne 1\nligne 2\n\n    indenté\n```\npas du code\n```\n*pas en italique*"
    page = _page(_msg(0, "human", [{"type": "text", "text": typed}]),
                 _msg(1, "assistant", [{"type": "text", "text": "*italique*"}], parent=0))
    assert '<div class="content-text plain-text">ligne 1\nligne 2\n\n    indenté\n```' in page
    assert "<em>pas en italique</em>" not in page and "<pre" not in page
    assert "<em>italique</em>" in page  # Claude's answer: still Markdown


def test_thinking_summaries_without_text() -> None:
    think = {"type": "thinking", "thinking": "", "summaries": [{"summary": "Explication des méthodes"},
                                                               {"summary": "Comparaison du semis"}]}
    page = _page(_msg(0, "human", [{"type": "text", "text": "q"}]),
                 _msg(1, "assistant", [think, {"type": "thinking", "thinking": "", "summaries": []},
                                       {"type": "text", "text": "r"}], parent=0))
    assert page.count('class="thinking"') == 1  # nothing for the one without text or summary
    assert "<summary>Comparaison du semis</summary>" in page
    assert "<li>Explication des méthodes</li><li>Comparaison du semis</li>" in page


def test_pasted_text() -> None:
    i18n.set_language("fr")
    human = _msg(0, "human", [{"type": "text", "text": "voici"}],
                 attachments=[{"file_name": "", "file_type": "txt", "file_size": 40515, "extracted_content": "x" * 40515}],
                 files=[{"file_name": ""}])
    page = _page(human)
    assert "Texte collé" in page and "Sans nom" not in page and "Fichier inconnu" not in page
    assert "40515" in page  # "Voir le contenu" kept
    assert "Texte collé" in message_body(parse_message(human))


def test_user_resources_hidden_by_default() -> None:
    # claude.ai's instructions in the user's message: grouped, and hidden by the style sheet
    from pathlib import Path
    css = (Path(i18n.__file__).parent / "static" / "style.css").read_text(encoding="utf-8")
    assert "body:not(.cev-show-resources) .messages .cev-resources," in css  # B4: every message


def test_cut_reply_marked() -> None:
    i18n.set_language("fr")
    page = _page(_msg(0, "human", [{"type": "text", "text": "q"}]),
                 _msg(1, "assistant", [{"type": "text", "text": "réponse complète"}], parent=0),
                 _msg(2, "assistant", [], parent=1, text=""),
                 _msg(3, "human", [{"type": "text", "text": "suite"}], parent=2))
    assert page.count("cev-cut") == 1 and page.count("Message interrompu ou compaction") == 1
    assert page.index("réponse complète") < page.index("cev-cut") < page.index("Message interrompu") < page.index("suite")
    assert "\x00" not in page


def test_drop_hint_rich_in_every_language() -> None:
    for lang in i18n.LANGUAGES:  # 14/11: the frame of the import names the manifest and the ZIPs, its title in bold
        text = i18n.catalog(lang)["web.drop.zone"]
        assert text.startswith("[b]") and text.count("[b]") == text.count("[/b]") == 1, lang
        assert "manifest.json" in text and "ZIP" in text, lang
        assert "[b]claude.ai[/b]" in i18n.catalog(lang)["web.drop.how"], lang
        assert "[b]claude.ai[/b]" in i18n.catalog(lang)["web.drop.how_new"], lang  # once an export is imported
    assert i18n.rich("[v]a[/v] <x> [b]b[/b]") == '<span class="hint-verb">a</span> &lt;x&gt; <b>b</b>'


def test_user_text_exported_as_typed() -> None:
    import shutil
    import subprocess

    import pytest

    from claude_export_viewer.markdown_export import typed
    from claude_export_viewer.office_export import PANDOC_INPUT
    exe = shutil.which("pandoc")
    if not exe:
        pytest.skip("pandoc absent")
    text = "a *b* [c](d) \\(e\\) l'été -- \"q\"\n\n    indenté\n```\n1. non\n@x $y$ &amp;\n===\n: z"
    out = subprocess.run([exe, "-f", PANDOC_INPUT, "-t", "plain", "--wrap=none"], input=typed(text),
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert [x.rstrip() for x in out.replace("\u00a0", " ").rstrip("\n").split("\n")] == text.split("\n")


def test_lists_of_the_user_have_a_hanging_indent(tmp_path) -> None:
    """L1: in your bubbles, a line starting with "1.", "2)", "-", "*" or "•" wraps under its text, as on
    claude.ai; the text stays exactly as typed (copy, search, highlighter)."""
    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    from .helpers import ExportData, build_site
    long = "mot " * 60
    text = f"Voici :\n1. {long}\n2) deux\n\n- a\n* b\n• c\nfin"
    out = tmp_path / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "L", "chat_messages": [
        {"uuid": "m0", "sender": "human", "text": text, "content": [{"type": "text", "text": text}]}]}]), out)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser not installed
            pytest.skip(f"Chromium unavailable: {exc}")
        pg = browser.new_page(viewport={"width": 1000, "height": 800})
        pg.goto((out / "conversations" / "c1.html").as_uri())
        box = pg.locator(".message-human .plain-text")
        assert box.evaluate("e => e.textContent") == text                  # the very same characters
        item = pg.locator(".li-line").first
        x = item.evaluate("""e => { const r = document.createRange(), t = e.lastChild;
            const first = e.firstChild.getBoundingClientRect().left;  // the marker
            r.setStart(t, 0); r.setEnd(t, t.length); const rects = [...r.getClientRects()];
            return [first, rects[0].left, rects[rects.length - 1].left, rects.length]; }""")
        marker, text_start, wrapped, n = x
        assert n > 1 and abs(wrapped - text_start) < 3 and wrapped > marker + 5  # wraps under its text
        gaps = box.evaluate("""e => { const lh = parseFloat(getComputedStyle(e).lineHeight), top = e.getBoundingClientRect().top;
            const r = [...e.querySelectorAll('.li-line')].map(x => x.getBoundingClientRect());
            return [(r[0].top - top) / lh, (r[2].top - r[1].bottom) / lh, (r[3].top - r[2].bottom) / lh]; }""")
        assert [round(g) for g in gaps] == [1, 1, 0]                        # "Voici :" above, one blank line, none
        browser.close()
