"""Markdown export of a conversation ("Exporter en .md")."""

import json
import re
from pathlib import Path

from claude_export_viewer import tree
from claude_export_viewer.markdown_export import conversation_markdown, embed, export_filename
from claude_export_viewer.models import Conversation, parse_message
from tests.helpers import ExportData, build_site, raw

ROOT = "00000000-0000-4000-8000-000000000000"


def convo() -> Conversation:
    return Conversation.model_validate({
        "uuid": "c", "name": "Estimation : taux/an ?", "created_at": "2026-10-23T08:53:17Z",
        "chat_messages": [
            {"uuid": "1", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-10-23T08:53:17Z",
             "content": [{"type": "text", "text": "Estime $\\alpha$"}], "attachments": [{"file_name": "taux.ods"}]},
            {"uuid": "2", "parent_message_uuid": "1", "sender": "assistant", "created_at": "2026-10-23T08:54:00Z",
             "content": [{"type": "thinking", "thinking": "RÉFLEXION"},
                         {"type": "text", "text": "Voici :\n\n```python\nprint('ok')\n```"},
                         {"type": "tool_use", "name": "web_search", "input": {"query": "x"}},
                         {"type": "tool_result", "name": "web_search", "content": "RÉSULTAT"},
                         {"type": "tool_use", "name": "artifacts", "input": {
                             "command": "create", "id": "a", "type": "application/vnd.ant.code",
                             "language": "basic", "title": "Module", "content": "Function F()\nEnd Function"}}]},
            {"uuid": "2b", "parent_message_uuid": "1", "sender": "assistant", "created_at": "2026-10-23T08:53:30Z",
             "content": [{"type": "text", "text": "Première réponse abandonnée"}]},
        ],
    })


def markdown(versions: bool = True) -> str:
    c = convo()
    return conversation_markdown(c.name, c.created_at, tree.items_from_raw(raw(c)), parse_message,
                                 versions=versions)


def test_main_thread_text_artifacts_and_attachments() -> None:
    md = markdown()
    assert md.startswith("# Estimation : taux/an ?\n")
    assert "**Vous** — " in md and "**Claude** — " in md
    assert "Estime $\\alpha$" in md  # formulas kept as LaTeX
    assert "```python\nprint('ok')\n```" in md
    assert "**Artefact : Module**" in md and "```basic\nFunction F()\nEnd Function\n```" in md
    assert "*Pièces jointes : taux.ods*" in md


def test_thinking_and_tool_results_are_left_out() -> None:
    md = markdown()
    assert "RÉFLEXION" not in md and "RÉSULTAT" not in md and "web_search" not in md


def test_other_versions_are_framed_in_italics_at_their_fork() -> None:
    md = markdown()
    frame = re.search(r"((?:^>.*\n)+)", md, flags=re.M).group(1)
    assert frame.startswith("> *Autre version — 1 message, commencée le 23/10/2026")
    assert "> ***Claude***" in frame and "> Première réponse abandonnée" in frame
    # the frame comes after the question and before the kept answer
    assert md.index("Estime") < md.index("Première réponse") < md.index("Voici :")


def test_filename_and_safe_embedding() -> None:
    assert export_filename("Estimation : taux/an ?", convo().created_at).endswith(" Estimation taux an.md")
    data = embed("a </script><script>alert(1)</script> b", "x.md")
    assert "<" not in data
    assert json.loads(data)["markdown"] == "a </script><script>alert(1)</script> b"


def test_page_offers_the_export_button(tmp_path: Path) -> None:
    build_site(ExportData(conversations=[convo()]), tmp_path)
    page = (tmp_path / "conversations" / "c.html").read_text(encoding="utf-8")
    assert 'id="export-md"' in page and 'src="../export.js"' in page
    payload = re.search(r'<script type="application/json" id="cev-markdown">(.*?)</script>', page, re.S).group(1)
    assert json.loads(payload)["filename"].endswith("Estimation taux an.md")
    assert (tmp_path / "export.js").is_file()


def test_archived_page_offers_it_too(tmp_path: Path) -> None:
    import zipfile

    from claude_export_viewer.cli import main

    z = tmp_path / "c.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([convo().model_dump(mode="json")]))
    main([str(z), "-o", str(tmp_path / "site"), "--date-export", "2026-10-23"])
    page = (tmp_path / "site" / "conversations" / "c.html").read_text(encoding="utf-8")
    payload = re.search(r'id="cev-markdown">(.*?)</script>', page, re.S).group(1)
    assert "Première réponse abandonnée" in json.loads(payload)["markdown"]


# --- "Inclure les autres versions" unchecked: main thread only ---------------


def test_main_thread_only_leaves_out_other_versions() -> None:
    full, main = markdown(), markdown(versions=False)
    assert "Première réponse abandonnée" in full
    assert "Première réponse abandonnée" not in main and "Autre version" not in main and "\n>" not in main
    assert "fil principal seulement" in main and "fil principal seulement" not in full
    # everything of the main thread is still there, in the same order
    for kept in ("Estime $\\alpha$", "Voici :", "**Artefact : Module**", "taux.ods"):
        assert kept in main
    assert main.index("Estime") < main.index("Voici :")


def test_main_thread_only_is_identical_without_branches() -> None:
    c = convo()
    linear = {**raw(c), "chat_messages": [m for m in raw(c)["chat_messages"] if m["uuid"] != "2b"]}
    items = tree.items_from_raw(linear)
    a = conversation_markdown(c.name, c.created_at, items, parse_message)
    b = conversation_markdown(c.name, c.created_at, items, parse_message, versions=False)
    assert a == b
    assert "markdown_main" not in json.loads(embed(a, "x.md", b))


def test_same_items_can_be_rendered_twice() -> None:
    c = convo()
    items = tree.items_from_raw(raw(c))
    first = conversation_markdown(c.name, c.created_at, items, parse_message)
    conversation_markdown(c.name, c.created_at, items, parse_message, versions=False)
    assert conversation_markdown(c.name, c.created_at, items, parse_message) == first
    assert first.count("Première réponse abandonnée") == 1


def test_page_embeds_both_variants_and_the_checkbox(tmp_path: Path) -> None:
    build_site(ExportData(conversations=[convo()]), tmp_path)
    page = (tmp_path / "conversations" / "c.html").read_text(encoding="utf-8")
    assert '<input type="checkbox" id="export-versions" checked>' in page
    assert "Inclure les autres versions et les parties supprimées" in page
    payload = json.loads(re.search(r'id="cev-markdown">(.*?)</script>', page, re.S).group(1))
    assert "Première réponse abandonnée" in payload["markdown"]
    assert "Première réponse abandonnée" not in payload["markdown_main"]
    assert payload["filename"].endswith("Estimation taux an.md")  # the page adds the translated suffix
    assert "\u27e6cev:md.main_only\u27e7" in payload["markdown_main"]  # labels left for the browser
