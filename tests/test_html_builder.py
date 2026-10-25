from pathlib import Path

from tests.helpers import ExportData, build_site
from claude_export_viewer.models import (
    AccountRef,
    ChatMessage,
    Conversation,
    TextContent,
    User,
)


def test_build_site_creates_output(tmp_path: Path) -> None:
    data = ExportData(
        users=[User(uuid="u1", full_name="Test", email_address="t@t.com")],
        conversations=[
            Conversation(
                uuid="conv-1",
                name="Test Conversation",
                created_at="2026-01-01T00:00:00Z",
                chat_messages=[
                    ChatMessage(
                        uuid="m1",
                        sender="human",
                        content=[TextContent(text="Hello")],
                    ),
                    ChatMessage(
                        uuid="m2",
                        sender="assistant",
                        content=[TextContent(text="Hi there!")],
                    ),
                ],
            ),
        ],
    )

    output_dir = tmp_path / "output"
    build_site(data, output_dir)

    assert (output_dir / "index.html").exists()
    assert (output_dir / "style.css").exists()
    assert (output_dir / "conversations" / "conv-1.html").exists()


def test_build_site_index_content(tmp_path: Path) -> None:
    data = ExportData(
        users=[User(uuid="u1", full_name="Alice Smith", email_address="alice@test.com")],
        conversations=[
            Conversation(
                uuid="c1",
                name="First Chat",
                created_at="2026-01-15T00:00:00Z",
                account=AccountRef(uuid="u1"),
                chat_messages=[
                    ChatMessage(uuid="m1", sender="human", content=[TextContent(text="Hi")]),
                ],
            ),
            Conversation(
                uuid="c2",
                name="Second Chat",
                created_at="2026-01-10T00:00:00Z",
                chat_messages=[
                    ChatMessage(uuid="m2", sender="human", content=[TextContent(text="Hello")]),
                ],
            ),
        ],
    )

    output_dir = tmp_path / "output"
    build_site(data, output_dir)

    index_html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "First Chat" in index_html
    assert "Second Chat" in index_html
    assert "2 conversations" in index_html
    # First Chat should appear before Second Chat (newer first)
    assert index_html.index("First Chat") < index_html.index("Second Chat")
    # With a single user, the user filter and the name on every line would be noise
    assert "Alice Smith" not in index_html and 'id="filter-user"' not in index_html

    data.users.append(User(uuid="u2", full_name="Bob", email_address="bob@test.com"))
    build_site(data, output_dir)
    index_html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "Alice Smith" in index_html and 'id="filter-user"' in index_html
    # Filter controls should be present
    assert 'id="filter-user"' in index_html
    assert 'id="sort-by"' in index_html


def test_build_site_conversation_content(tmp_path: Path) -> None:
    data = ExportData(
        conversations=[
            Conversation(
                uuid="c1",
                name="My Chat",
                created_at="2026-01-15T12:00:00Z",
                chat_messages=[
                    ChatMessage(uuid="m1", sender="human", content=[TextContent(text="What is 2+2?")]),
                    ChatMessage(uuid="m2", sender="assistant", content=[TextContent(text="The answer is **4**.")]),
                ],
            ),
        ],
    )

    output_dir = tmp_path / "output"
    build_site(data, output_dir)

    convo_html = (output_dir / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert "My Chat" in convo_html
    assert "message-human" in convo_html
    assert "message-assistant" in convo_html
    assert "What is 2+2?" in convo_html
    assert "<strong>4</strong>" in convo_html
    assert "../style.css" in convo_html
    assert "../index.html" in convo_html


def test_build_site_empty_conversations(tmp_path: Path) -> None:
    data = ExportData(conversations=[])
    output_dir = tmp_path / "output"
    build_site(data, output_dir)

    assert (output_dir / "index.html").exists()
    index_html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert ">0 conversation</span>" in index_html  # French: 0 is singular


def test_empty_conversations_are_skipped(tmp_path: Path) -> None:
    from claude_export_viewer.models import ThinkingContent, TokenBudgetContent

    data = ExportData(
        conversations=[
            Conversation(uuid="ok", name="", chat_messages=[ChatMessage(sender="human", content=[TextContent(text="Hi")])]),
            Conversation(uuid="deleted", name="", chat_messages=[]),
            Conversation(
                uuid="blank",
                name="",
                chat_messages=[
                    ChatMessage(sender="human", content=[TextContent(text="  \n")]),
                    ChatMessage(sender="assistant", content=[ThinkingContent(thinking="..."), TokenBudgetContent()]),
                ],
            ),
            Conversation(
                uuid="image_only",
                name="",
                chat_messages=[
                    ChatMessage(sender="human", files=[{"file_name": "1788586061966_image.png"}]),
                    ChatMessage(sender="assistant", attachments=[{"file_name": "doc.pdf", "extracted_content": "x"}]),
                ],
            ),
        ]
    )
    out = tmp_path / "out"
    stats = build_site(data, out)
    assert (stats.written, stats.skipped_empty) == (1, 3)
    assert sorted(p.name for p in (out / "conversations").glob("*.html")) == ["ok.html"]
    index_html = (out / "index.html").read_text(encoding="utf-8")
    assert "1 conversation<" in index_html
    for name in ("deleted", "blank", "image_only"):
        assert f"{name}.html" not in index_html
    # "Untitled" conversations that do have messages are kept
    assert "ok.html" in index_html

    kept = build_site(data, tmp_path / "all", skip_empty=False)
    assert (kept.written, kept.skipped_empty) == (4, 0)


def test_copy_script_only_on_pages_with_code(tmp_path: Path) -> None:
    data = ExportData(
        conversations=[
            Conversation(
                uuid="avec",
                chat_messages=[ChatMessage(sender="assistant", content=[TextContent(text="```python\nx = 1\n```")])],
            ),
            Conversation(uuid="sans", chat_messages=[ChatMessage(sender="human", content=[TextContent(text="Salut")])]),
        ]
    )
    out = tmp_path / "out"
    build_site(data, out)
    assert (out / "code.js").is_file()
    assert 'src="../code.js"' in (out / "conversations" / "avec.html").read_text(encoding="utf-8")
    assert "code.js" not in (out / "conversations" / "sans.html").read_text(encoding="utf-8")
