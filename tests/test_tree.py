"""Branches of a conversation (edited messages, retried answers).

The fixture reproduces the shape of a real test conversation (26 messages)
exported from claude.ai on 2026-10-23: an edited first message, an answer
retried twice, an edited question, and a retry from higher up.
"""

import re

from claude_export_viewer.html_builder import render_archived_conversation
from claude_export_viewer.models import Conversation
from tests.helpers import raw


def render_conversation(convo: Conversation):
    """Pieces of the page and main branch, as the site renders an archived conversation."""
    validated, pieces = render_archived_conversation(raw(convo))
    return pieces, validated.chat_messages

ROOT = "00000000-0000-4000-8000-000000000000"

# (id, parent, sender, time, text) — same tree as the real export
SHAPE = [
    ("h1", ROOT, "human", "17:33:47", "Bonsoir ORIGINAL"),
    ("a1", "h1", "assistant", "17:33:54", "Bonsoir"),
    ("h2", ROOT, "human", "17:34:42", "EDIT-ALPHA"),
    ("a2", "h2", "assistant", "17:34:50", "Réponse ALPHA"),
    ("h3", "a2", "human", "17:35:34", "BRAVO"),
    ("a3a", "h3", "assistant", "17:35:37", "BRAVO réponse 1"),
    ("a3b", "h3", "assistant", "17:36:32", "BRAVO réponse 2"),
    ("a3c", "h3", "assistant", "17:36:52", "BRAVO réponse 3"),
    ("h4", "a3c", "human", "17:39:24", "Je ne peux pas supprimer"),
    ("a4a", "h4", "assistant", "17:39:41", "Réponse 4a"),
    ("a4b", "h4", "assistant", "17:41:11", "Réponse 4b"),
    ("h5a", "a4b", "human", "17:41:42", "Flèches ?"),
    ("a5a1", "h5a", "assistant", "17:41:49", "Réponse 5a1"),
    ("a5a2", "h5a", "assistant", "17:42:16", "Réponse 5a2"),
    ("h5b", "a4b", "human", "17:42:45", "Flèches, suis-je bête ?"),
    ("a5b1", "h5b", "assistant", "17:42:52", "Réponse 5b1"),
    ("a5b2", "h5b", "assistant", "17:43:10", "Réponse 5b2"),
    ("h6", "a5b2", "human", "17:43:39", "Le fonctionnement a changé"),
    ("a6", "h6", "assistant", "17:43:52", "Réponse 6"),
    ("h7", "a6", "human", "17:45:31", "Interface différente"),
    ("a7", "h7", "assistant", "17:45:37", "Réponse 7"),
    ("a4c", "h4", "assistant", "17:46:57", "Réponse 4c"),
    ("h8", "a4c", "human", "17:48:17", "Anciens échanges invisibles"),
    ("a8", "h8", "assistant", "17:48:31", "Réponse 8"),
    ("h9", "a8", "human", "17:49:31", "Fin du test"),
    ("a9", "h9", "assistant", "17:49:35", "Dernière réponse"),
]


def conversation() -> Conversation:
    return Conversation.model_validate(
        {
            "uuid": "test",
            "chat_messages": [
                {
                    "uuid": i,
                    "parent_message_uuid": p,
                    "sender": s,
                    "created_at": f"2026-10-23T{t}Z",
                    "content": [{"type": "text", "text": txt}],
                }
                for i, p, s, t, txt in SHAPE
            ],
        }
    )


def test_main_branch_is_the_path_to_the_latest_message() -> None:
    _, main = render_conversation(conversation())
    assert [m.uuid for m in main] == ["h2", "a2", "h3", "a3c", "h4", "a4c", "h8", "a8", "h9", "a9"]


def test_other_branches_are_framed_where_they_fork() -> None:
    pieces, _ = render_conversation(conversation())
    page = "".join(pieces)
    titles = re.findall(r">Autre version — (\d+) messages?", page)
    # top-level frames: 2 (edited first message), 1 + 1 (retries of BRAVO), 1 + 11 (under h4);
    # nested inside the 11-message frame: 3 (h5a branch) and 1 (a5b1 retry);
    # nested inside the 3-message frame: 1 (h5a was answered twice: a5a1, a5a2)
    assert sorted(map(int, titles)) == [1, 1, 1, 1, 1, 2, 3, 11]
    # every message is on the page exactly once
    for _, _, _, _, txt in SHAPE:
        assert page.count(f">{txt}<") == 1, txt
    # order: edited first message frame, then main start; retries of BRAVO before the kept answer
    pos = lambda t: page.index(f">{t}<")  # noqa: E731
    assert pos("Bonsoir ORIGINAL") < pos("EDIT-ALPHA") < pos("BRAVO")
    assert pos("BRAVO") < pos("BRAVO réponse 1") < pos("BRAVO réponse 2") < pos("BRAVO réponse 3")
    assert pos("Je ne peux pas supprimer") < pos("Réponse 4a") < pos("Réponse 4b") < pos("Réponse 4c")
    assert pos("Réponse 4c") < pos("Fin du test") < pos("Dernière réponse")
    # times of branch starts are shown
    assert "commencée le 23/10/2026" in page


def test_linear_export_without_parent_ids_is_unchanged() -> None:
    convo = Conversation.model_validate(
        {
            "uuid": "lin",
            "chat_messages": [
                {"uuid": f"m{i}", "sender": "human" if i % 2 == 0 else "assistant",
                 "content": [{"type": "text", "text": f"msg {i}"}]}
                for i in range(4)
            ],
        }
    )
    pieces, main = render_conversation(convo)
    assert [m.uuid for m in main] == ["m0", "m1", "m2", "m3"]
    assert "Autre version" not in "".join(pieces)


def test_index_counts_main_branch(tmp_path) -> None:
    from tests.helpers import ExportData, build_site

    build_site(ExportData(conversations=[conversation()]), tmp_path)
    assert "10 messages" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "10 messages" in (tmp_path / "conversations" / "test.html").read_text(encoding="utf-8")
