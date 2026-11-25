"""D1 of 2026-10-29: the .txt export (Pandoc, plain text), with lines of separation."""

from __future__ import annotations

import shutil

import pytest

from claude_export_viewer import i18n, office_export, tree
from claude_export_viewer.markdown_export import conversation_markdown
from claude_export_viewer.models import parse_message

ROOT = "00000000-0000-4000-8000-000000000000"


def _msg(uuid: str, parent: str, sender: str, minute: int, content: list) -> dict:
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender,
            "created_at": f"2026-10-23T08:{minute:02d}:00Z", "content": content}


def _text(versions: bool = True) -> str:
    if not shutil.which("pandoc"):
        pytest.skip("pandoc absent")
    i18n.set_language("fr")
    msgs = [_msg("1", ROOT, "human", 53, [{"type": "text", "text": "Estime $\\alpha$\n  ligne 2"}]),
            _msg("2", "1", "assistant", 54, [{"type": "thinking", "thinking": "réflexion secrète"},
                                             {"type": "text", "text": "On a $x^2 \\le \\alpha$."}]),
            _msg("2b", "1", "assistant", 50, [{"type": "text", "text": "Première réponse"}]),
            _msg("3", "2", "human", 55, [{"type": "text", "text": "Merci"}]),
            _msg("4", "3", "assistant", 56, [{"type": "text", "text": "De rien"}])]
    raw = {"uuid": "c", "name": "Essai", "chat_messages": msgs}
    md = conversation_markdown("Essai", None, tree.items_from_raw(raw), parse_message, versions=versions, for_text=True)
    data, _ = office_export.run_pandoc(office_export.prepare_for_pandoc(md), "txt", ("--wrap=none",))
    return office_export.separate(data.decode("utf-8"))


def test_text_export() -> None:
    lines = _text().split("\n")
    q, a = "=" * 40, "-" * 40
    main = [x for x in lines if x and not x.startswith("  ")]  # the frame of the other version: indented
    order = [x for x in main if x in (q, a) or x.startswith(("Vous —", "Claude —"))]
    assert order == [q, "Vous — 23/10/2026 à 10:53", a, "Claude — 23/10/2026 à 10:54",
                     q, "Vous — 23/10/2026 à 10:55", a, "Claude — 23/10/2026 à 10:56"]
    text = "\n".join(lines)
    assert "Estime $\\alpha$\n  ligne 2" in text  # your text as typed
    assert "On a x² ≤ α." in text.replace("\u2004", " ")  # formula made readable by Pandoc (thin spaces)
    assert "réflexion secrète" not in text and "CEVTEXTSEP" not in text
    assert "  Première réponse" in text  # the other version, indented in its frame
    assert "Première réponse" not in _text(versions=False)
