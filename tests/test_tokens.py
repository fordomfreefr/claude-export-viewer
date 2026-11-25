"""Rough evaluation of the tokens used by a conversation (tokens.py), checked against figures
computed by hand, and its place on the index."""

import json
from pathlib import Path

from claude_export_viewer import i18n, tokens
from claude_export_viewer.tokens import CHARS_PER_TOKEN, evaluate, short

from .helpers import ExportData, build_site

ROOT = "00000000-0000-4000-8000-000000000000"
H = "q" * 35  # 35 characters: 10 tokens
A = "r" * 70  # 20 tokens


def m(uuid: str, parent: str, sender: str, *blocks: dict) -> dict:
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender, "content": list(blocks)}


def text(s: str) -> dict:
    return {"type": "text", "text": s}


def tok(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN)


def test_every_reply_reads_the_conversation_again() -> None:
    msgs = [m("h1", ROOT, "human", text(H)), m("a1", "h1", "assistant", text(A)),
            m("h2", "a1", "human", text(H)), m("a2", "h2", "assistant", text(A))]
    r = evaluate({"chat_messages": msgs})
    assert r["content"] == tok(35 + 70 + 35 + 70) == 60 and r["tools"] == 0
    # a1 reads h1 and writes A; a2 reads h1 a1 h2 and writes A
    assert r["total"] == tok((35 + 70) + (35 + 70 + 35 + 70)) == 90
    # counter-check: twice as long a conversation costs about four times as much (squared)
    long = [m(f"h{i}", f"a{i - 1}" if i else ROOT, "human", text(H)) for i in range(20)]
    long = [x for i, h in enumerate(long) for x in (h, m(f"a{i}", f"h{i}", "assistant", text(A)))]
    t10, t20 = evaluate({"chat_messages": long[:20]})["total"], evaluate({"chat_messages": long})["total"]
    assert 3.5 < t20 / t10 < 4.2


def test_tools_make_the_context_read_again() -> None:
    use = {"type": "tool_use", "name": "web_search", "input": {"query": "x" * 20}}
    use_chars = len(json.dumps(use["input"])) + len("web_search")
    res = {"type": "tool_result", "name": "web_search", "content": [{"type": "text", "text": "w" * 700}]}
    plain = [m("h1", ROOT, "human", text(H)), m("a1", "h1", "assistant", text(A))]
    tooled = [m("h1", ROOT, "human", text(H)), m("a1", "h1", "assistant", use, res, use, res, text(A))]
    p, t = evaluate({"chat_messages": plain}), evaluate({"chat_messages": tooled})
    assert t["tools"] == tok(2 * use_chars + 2 * 700)
    # 3 calls: the context alone, then after each result everything received so far
    read = 35 + (35 + use_chars + 700) + (35 + 2 * use_chars + 2 * 700)
    written = 2 * use_chars + 70
    assert t["total"] == tok(read + written)
    assert t["total"] > 10 * p["total"]  # much hungrier than the same reply without tools


def test_other_versions_and_attachments_count() -> None:
    msgs = [m("h1", ROOT, "human", text(H)), m("a1", "h1", "assistant", text(A)),
            m("a1b", "h1", "assistant", text(A))]  # a retry: read h1 again
    msgs[0]["attachments"] = [{"file_name": "n.txt", "extracted_content": "z" * 350}]
    r = evaluate({"chat_messages": msgs})
    assert r["content"] == tok(35 + 350 + 70 + 70)
    assert r["total"] == tok(2 * (35 + 350 + 70))
    # kept by the archive after their removal on claude.ai: counted too
    r2 = evaluate({"chat_messages": msgs[:2], "_cev_extra_messages": [msgs[2]]})
    assert r2 == r
    assert evaluate({}) == {"v": tokens.VERSION, "content": 0, "tools": 0, "total": 0}
    assert evaluate({"chat_messages": [m("x", "x", "assistant", text(A))]})["total"] == 20  # a loop: no hang


def test_short_form() -> None:
    assert [short(n) for n in (850, 4230, 4250, 482_400, 999_400, 999_600, 1_400_000)] == [
        (850, ""), (4.2, "k"), (4.3, "k"), (482, "k"), (999, "k"), (1.0, "M"), (1.4, "M")]
    assert i18n.t("web.tokens.short", "fr", n=i18n.Tokens(1_400_000)) == "≈ 1,4 M tokens"
    assert i18n.t("web.tokens.short", "en", n=i18n.Tokens(482_400)) == "≈ 482 k tokens"


def test_on_the_index(tmp_path: Path) -> None:
    msgs = [m("h1", ROOT, "human", text(H)), m("a1", "h1", "assistant", text(A))]
    site = tmp_path / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai", "created_at": "2026-10-01T10:00:00Z",
                                          "chat_messages": msgs}]), site)
    html = (site / "index.html").read_text(encoding="utf-8")
    assert '<span class="tok-count"' in html and "≈ 30 tokens" in html
    assert "Évaluation grossière des tokens utilisés : contenu ≈ 30 (dont outils ≈ 0)" in html
    assert '&quot;$tok&quot;: 30' in html  # rewritten by the browser in the chosen language

    page = next((site / "conversations").glob("*.html")).read_text(encoding="utf-8")
    meta = page[page.index('class="meta"'):page.index("</div>", page.index('class="meta"'))]
    assert meta.index("message") < meta.index("≈ 30 tokens")  # on the page too, after the messages
