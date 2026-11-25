from claude_export_viewer.models import (
    Attachment,
    ChatMessage,
    FileRef,
    TextContent,
    ThinkingContent,
    ThinkingSummary,
    TokenBudgetContent,
    ToolResultContent,
    ToolUseContent,
)
from claude_export_viewer.renderer import render_markdown, render_message


def test_render_markdown_basic() -> None:
    result = render_markdown("Hello **world**")
    assert "<strong>world</strong>" in result
    assert "<p>" in result


def test_render_markdown_code_block() -> None:
    result = render_markdown("```python\nprint('hello')\n```")
    assert "<pre" in result
    assert "<code" in result


def test_render_markdown_table() -> None:
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    result = render_markdown(md)
    assert "<table>" in result
    assert "<th" in result


def test_render_markdown_link() -> None:
    result = render_markdown("[click](https://example.com)")
    assert 'target="_blank"' in result
    assert 'rel="noopener noreferrer"' in result
    assert 'href="https://example.com"' in result


def test_render_markdown_link_harmful_protocol_neutralised() -> None:
    result = render_markdown("[click](javascript:alert(1)) <script>alert(2)</script>")
    assert "javascript:" not in result
    assert "<script>" not in result


def test_render_message_human() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="human",
        content=[TextContent(text="Hello")],
    )
    result = render_message(msg)
    assert "message-human" in result
    assert "message-bubble" in result
    assert "Hello" in result


def test_render_message_assistant_text() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[TextContent(text="**Bold response**")],
    )
    result = render_message(msg)
    assert "message-assistant" in result
    assert "<strong>Bold response</strong>" in result


def test_render_message_thinking() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ThinkingContent(
                thinking="Let me think about this...",
                summaries=[ThinkingSummary(summary="Considering the options")],
            ),
            TextContent(text="Here's my answer"),
        ],
    )
    result = render_message(msg)
    assert "<details" in result
    assert "thinking" in result
    assert "Considering the options" in result
    assert "Here&#x27;s my answer" in result or "Here's my answer" in result


def test_render_message_thinking_no_summary() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[ThinkingContent(thinking="Thinking...", summaries=[])],
    )
    result = render_message(msg)
    assert "Thinking..." in result


def test_render_message_artifact_create() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ToolUseContent(
                name="artifacts",
                input={
                    "command": "create",
                    "id": "my-doc",
                    "type": "text/markdown",
                    "title": "My Document",
                    "content": "# Hello\n\nThis is a document.",
                },
            ),
        ],
    )
    result = render_message(msg)
    assert "artifact" in result
    assert "My Document" in result
    assert "Document" in result  # type label


def test_render_message_artifact_code() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ToolUseContent(
                name="artifacts",
                input={
                    "command": "create",
                    "id": "code-1",
                    "type": "application/vnd.ant.code",
                    "title": "My Script",
                    "language": "python",
                    "content": "print('hello')",
                },
            ),
        ],
    )
    result = render_message(msg)
    assert "artifact" in result
    assert "My Script" in result
    assert "Code" in result


def test_render_message_artifact_update_skipped() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ToolUseContent(
                name="artifacts",
                input={"command": "update", "id": "my-doc", "old_str": "foo", "new_str": "bar"},
            ),
        ],
    )
    result = render_message(msg)
    assert "artifact-header" not in result


def test_render_message_tool_use_non_artifact() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ToolUseContent(name="web_search", input={"query": "test"}, message="Searching the web"),
        ],
    )
    result = render_message(msg)
    assert "<details" in result
    assert "Searching the web" in result


def test_render_message_tool_result_artifact_skipped() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[ToolResultContent(name="artifacts", content="OK")],
    )
    result = render_message(msg)
    assert "OK" not in result or "tool-result" not in result


def test_render_message_tool_result_with_content() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ToolResultContent(name="web_search", content="Search results here", is_error=False),
        ],
    )
    result = render_message(msg)
    assert "tool-result" in result
    assert "Search results here" in result


def test_render_message_tool_result_error() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[
            ToolResultContent(name="web_fetch", content="403 Forbidden", is_error=True),
        ],
    )
    result = render_message(msg)
    assert "tool-error" in result


def test_render_message_tool_result_empty_skipped() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[ToolResultContent(name="some_tool", content="")],
    )
    result = render_message(msg)
    assert "tool-result" not in result


def test_render_message_token_budget_skipped() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="assistant",
        content=[TokenBudgetContent(), TextContent(text="Response")],
    )
    result = render_message(msg)
    assert "token_budget" not in result
    assert "Response" in result


def test_render_message_attachment() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="human",
        content=[TextContent(text="See attached")],
        attachments=[
            Attachment(file_name="report.docx", file_size=34382, file_type="docx", extracted_content="Some text"),
        ],
    )
    result = render_message(msg)
    assert "attachment-pill" in result
    assert "report.docx" in result
    assert "docx" in result
    assert "33,6 Ko" in result
    assert "Voir le contenu" in result


def test_render_message_files() -> None:
    msg = ChatMessage(
        uuid="m1",
        sender="human",
        content=[TextContent(text="Check these files")],
        files=[FileRef(file_name="image.png"), FileRef(file_name="doc.pdf")],
    )
    result = render_message(msg)
    assert "file-pill" in result
    assert "image.png" in result
    assert "doc.pdf" in result


def test_code_block_has_header_with_language_and_copy_button() -> None:
    result = render_markdown("```python\nx = 1 < 2\n```")
    assert '<div class="code-block">' in result
    assert '<span class="code-lang">Python</span>' in result
    assert 'class="copy-btn"' in result and ">Copier</span></button>" in result
    assert 'class="language-python"' in result
    assert "&lt;" in result  # code still escaped


def test_code_block_unknown_or_missing_language() -> None:
    unknown = render_markdown("```truc\nz\n```")
    assert '<span class="code-lang">truc</span>' in unknown
    assert "<code><code>" not in unknown and '<code class="language-truc"><code>' not in unknown
    plain = render_markdown("```\nbrut\n```")
    assert '<span class="code-lang"></span>' in plain
    assert "brut" in plain


def test_message_shows_local_date_and_time_above_bubble() -> None:
    from datetime import datetime, timezone

    msg = ChatMessage(uuid="m", sender="human", content=[TextContent(text="Salut")],
                      created_at="2026-10-23T17:34:42Z")
    html_out = render_message(msg)
    local = datetime(2026, 10, 23, 17, 34, 42, tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y à %H:%M")
    assert f'data-fmt="datetime">{local}</time><button type="button" class="fav-star"' in html_out  # the star after the date
    assert '<time datetime="2026-10-23T17:34:42+00:00"' in html_out  # reformatted by the browser
    assert html_out.index("message-time") < html_out.index("message-bubble")
    assert '<b class="message-who" data-i18n="web.who.human">Moi</b> <time' in html_out  # "Moi" before the date
    no_date = render_message(ChatMessage(uuid="n", sender="human", content=[TextContent(text="x")]))
    assert "<time" not in no_date and ">Moi</b>" in no_date  # no date: the name only
    answer = render_message(ChatMessage(uuid="a", sender="assistant", content=[TextContent(text="x")]))
    assert ">Claude</b>" in answer and ">Moi<" not in answer


def _blocks_msg(*blocks: dict) -> str:
    from claude_export_viewer.models import parse_message
    msg = parse_message({"uuid": "m", "sender": "assistant", "content": list(blocks)})
    return render_message(msg)


_INJ = {"type": "injected_prompt_block", "prompt": "Mémoire : x", "injection_source": {"type": "memory"}}
_USE = {"type": "tool_use", "name": "web_search", "input": {"query": "q"}}
_RES = {"type": "tool_result", "name": "web_search", "content": "résultat"}
_THINK = {"type": "thinking", "thinking": "je réfléchis"}
_TEXT = {"type": "text", "text": "Réponse"}


def _groups(html_out: str) -> list[str]:
    """The inside of each "Ressources de claude.ai" frame."""
    import re
    out, start = [], '<details class="cev-resources">'
    for m in re.finditer(re.escape(start), html_out):
        depth, i = 1, m.end()
        for tag in re.finditer(r"<(/?)details\b", html_out[i:]):
            depth += -1 if tag.group(1) else 1
            if not depth:
                out.append(html_out[i:i + tag.start()])
                break
    return out


def test_claude_ai_blocks_grouped() -> None:
    out = _blocks_msg(_INJ, _TEXT)
    groups = _groups(out)
    assert len(groups) == 1 and "injected" in groups[0] and "Réponse" not in groups[0]
    assert 'data-i18n="web.resources"' in groups[0] and "Ressources de claude.ai (1)" in groups[0]
    assert out.index("cev-resources") < out.index("Réponse")  # the run stays in its place
    # thinking between two tools: in the frame; before the first or after the last: outside
    out = _blocks_msg(_THINK, _USE, _RES, _THINK, _USE, _RES, _THINK, _TEXT)
    groups = _groups(out)
    assert len(groups) == 1 and "Ressources de claude.ai (4)" in groups[0]
    assert groups[0].count('class="thinking"') == 1 and out.count('class="thinking"') == 3
    # the text ends a run: two frames
    assert len(_groups(_blocks_msg(_USE, _TEXT, _RES))) == 2


def test_claude_ai_blocks_counter_checks() -> None:
    # nothing from claude.ai: no frame (thinking alone, plain text)
    assert "cev-resources" not in _blocks_msg(_THINK, _TEXT)
    assert "cev-resources" not in _blocks_msg(_TEXT)
    # an artifact is Claude's work: it ends the run and stays outside
    art = {"type": "tool_use", "name": "artifacts",
           "input": {"command": "create", "id": "a", "type": "text/markdown", "title": "Doc", "content": "# T"}}
    out = _blocks_msg(_USE, art, _RES)
    groups = _groups(out)
    assert len(groups) == 2 and all("Doc" not in g for g in groups) and "Doc" in out
    # the user's document stays outside
    out = _blocks_msg({"type": "document"}, _USE)
    assert len(_groups(out)) == 1 and "document_attached" not in _groups(out)[0] and "web.document_attached" in out
