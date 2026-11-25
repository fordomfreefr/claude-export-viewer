"""A rewrite of an artifact keeps the type, title and language of its creation (seen on the user's
archive: "Évaluation des mains au poker avec pokerstove", the rewrite holds only id and content)."""
from claude_export_viewer import tree
from claude_export_viewer.html_builder import render_archived_conversation
from claude_export_viewer.markdown_export import conversation_markdown
from claude_export_viewer.models import parse_message

CODE = '#!/usr/bin/env python3\n# commentaire\nimport subprocess\n'


def _art(**inp):
    return {"type": "tool_use", "name": "artifacts", "input": inp}


def test_rewrite_inherits_type_title_language():
    create = _art(id="w", type="application/vnd.ant.code", title="PokerStove Wrapper", command="create",
                  content=CODE, language="python")
    rewrite = _art(id="w", command="rewrite", content=CODE + "# v2\n")
    raw = {"uuid": "c", "name": "t", "chat_messages": [
        {"uuid": "h", "sender": "human", "text": "q", "content": [{"type": "text", "text": "q"}],
         "created_at": "2025-12-21T08:18:00Z", "parent_message_uuid": "00000000-0000-4000-8000-000000000000"},
        {"uuid": "a", "sender": "assistant", "text": "r", "created_at": "2025-12-21T08:19:00Z",
         "parent_message_uuid": "h",
         "content": [{"type": "text", "text": "r"}, create, {"type": "text", "text": "Étape 5"}, rewrite]}]}
    _, pages = render_archived_conversation(raw)
    html = "".join(pages)
    after = html.split("Étape 5</p>")[-1]            # the rewrite, in the bubble
    assert "PokerStove Wrapper" in after
    assert '<span class="c1"># v2</span>' in after   # highlighted as Python, not Markdown
    assert "input" in raw["chat_messages"][1]["content"][3] and "type" not in rewrite["input"]  # raw untouched
    md = conversation_markdown("t", None, tree.items_from_raw(raw), parse_message)
    assert md.count("```python") == 2 and md.count("PokerStove Wrapper") == 2   # the .md export too


def test_injected_instructions_go_to_claude():
    """claude.ai files its instructions in the user's message ("Cultiver un noyer au jardin"): they are
    shown in each reply of Claude to it, after its opening thinking; without a reply they stay in the
    user's message."""
    inj = {"type": "injected_prompt_block", "prompt": "Consigne zanzibar", "injection_source": "date_note"}
    root = "00000000-0000-4000-8000-000000000000"
    raw = {"uuid": "c", "name": "t", "chat_messages": [
        {"uuid": "h", "sender": "human", "text": "q", "created_at": "2026-10-10T16:20:00Z",
         "parent_message_uuid": root, "content": [{"type": "text", "text": "q"}, inj]},
        {"uuid": "a", "sender": "assistant", "text": "r", "created_at": "2026-10-10T16:21:00Z",
         "parent_message_uuid": "h", "content": [{"type": "thinking", "thinking": "réflexion"},
                                                 {"type": "text", "text": "r"}]},
        {"uuid": "h2", "sender": "human", "text": "q2", "created_at": "2026-10-10T16:22:00Z",
         "parent_message_uuid": "a", "content": [{"type": "text", "text": "q2"}, inj]}]}
    _, pages = render_archived_conversation(raw)
    html = "".join(pages)
    human, claude, last = (html.split(f'data-uuid="{u}"')[1].split("data-uuid=")[0] for u in ("h", "a", "h2"))
    assert "zanzibar" not in human and "zanzibar" in claude and "zanzibar" in last
    assert claude.index("réflexion") < claude.index("zanzibar") < claude.index("<p>r</p>")
    assert raw["chat_messages"][0]["content"][1] is inj   # raw untouched


def _m(uuid, parent, sender, at, content, text=""):
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender, "created_at": at,
            "text": text, "content": content}


def test_cut_replies():
    """Replies of Claude without text, as in the user's archive (interrupted or compaction, the export does
    not tell): one mark, the thinking kept, the whole message hidden with claude.ai's resources."""
    root = "00000000-0000-4000-8000-000000000000"
    think = {"type": "thinking", "thinking": "", "summaries": [{"summary": "Calculant la moyenne"}]}
    tool = {"type": "tool_use", "name": "bash_tool", "input": {"command": "ls"}}
    q = lambda u, p, at: _m(u, p, "human", at, [{"type": "text", "text": "q " + u}], "q " + u)
    raw = {"uuid": "c", "name": "t", "chat_messages": [
        q("q1", root, "2026-06-14T10:49:32Z"),
        _m("dij", "q1", "assistant", "2026-06-14T10:49:34Z", []),                         # nothing
        q("q2", "dij", "2026-06-14T10:53:48Z"),
        _m("hull", "q2", "assistant", "2026-06-14T10:54:00Z", [think]),                   # thinking only
        q("q3", "hull", "2026-06-14T10:55:00Z"),
        _m("py", "q3", "assistant", "2026-06-14T10:56:00Z", [{"type": "text", "text": ""}]),  # empty text
        q("q4", "py", "2026-06-14T10:57:00Z"),
        _m("tool", "q4", "assistant", "2026-06-14T10:58:00Z", [tool])]}                  # a tool: normal
    html = "".join(render_archived_conversation(raw)[1])
    bubble = lambda u: html.split(f'data-uuid="{u}"')[1].split("data-uuid=")[0]
    for u in ("dij", "hull", "py"):
        assert f'message-assistant cev-cut" data-uuid="{u}"' in html and 'class="cut-note"' in bubble(u), u
    assert "Calculant la moyenne" in bubble("hull")
    assert "cev-cut" not in html.split('data-uuid="tool"')[0][-80:] and "cut-note" not in bubble("tool")


def test_long_code_folded():
    """A code frame of more than 10 lines is folded to its first lines (text and artifacts); not the
    files of Claude, already in a closed frame, nor the code inside an artifact (its header folds)."""
    from claude_export_viewer.renderer import code_block
    ten, eleven = "\n".join(map(str, range(10))), "\n".join(map(str, range(11)))
    assert "cev-long" not in code_block(ten + "\n", "python")
    assert "cev-long" in code_block(eleven, "python") and "fold-icon" in code_block(eleven, "python")
    assert "cev-long" not in code_block(eleven, "python", foldable=False)
    art = _art(id="x", type="application/vnd.ant.code", title="T", command="create", content=eleven, language="python")
    raw = {"uuid": "c", "name": "t", "chat_messages": [
        {"uuid": "a", "sender": "assistant", "text": "r", "content": [{"type": "text", "text": "r"}, art]}]}
    html = "".join(render_archived_conversation(raw)[1])
    assert html.count("cev-long") == 1 and 'class="artifact cev-long"' in html
