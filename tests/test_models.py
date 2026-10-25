from pydantic import TypeAdapter

from claude_export_viewer.models import (
    Attachment,
    ChatMessage,
    ContentBlock,
    Conversation,
    FileRef,
    TextContent,
    ThinkingContent,
    ThinkingSummary,
    TokenBudgetContent,
    ToolResultContent,
    ToolUseContent,
    User,
)


def test_user_parsing() -> None:
    data = {"uuid": "abc-123", "full_name": "Test User", "email_address": "test@example.com"}
    user = User.model_validate(data)
    assert user.uuid == "abc-123"
    assert user.full_name == "Test User"


def test_unknown_user_fields_are_ignored() -> None:
    data = {"uuid": "abc", "full_name": "Test", "email_address": "t@t.com", "verified_phone_number": "+1234"}
    user = User.model_validate(data)
    assert user.full_name == "Test" and not hasattr(user, "verified_phone_number")


def test_text_content_discriminator() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python({"type": "text", "text": "Hello world", "citations": []})
    assert isinstance(block, TextContent)
    assert block.text == "Hello world"


def test_thinking_content_discriminator() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python(
        {
            "type": "thinking",
            "thinking": "Let me think...",
            "summaries": [{"summary": "Thinking about it"}],
        }
    )
    assert isinstance(block, ThinkingContent)
    assert block.thinking == "Let me think..."
    assert len(block.summaries) == 1
    assert isinstance(block.summaries[0], ThinkingSummary)


def test_tool_use_content_artifact() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python(
        {
            "type": "tool_use",
            "id": "tu-1",
            "name": "artifacts",
            "input": {
                "command": "create",
                "id": "my-artifact",
                "type": "text/markdown",
                "title": "My Doc",
                "content": "# Hello",
            },
        }
    )
    assert isinstance(block, ToolUseContent)
    assert block.is_artifact is True
    ai = block.artifact_input
    assert ai is not None
    assert ai.command == "create"
    assert ai.title == "My Doc"


def test_tool_use_content_non_artifact() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python(
        {
            "type": "tool_use",
            "id": "tu-2",
            "name": "web_search",
            "input": {"query": "test"},
            "message": "Searching the web",
        }
    )
    assert isinstance(block, ToolUseContent)
    assert block.is_artifact is False
    assert block.artifact_input is None


def test_tool_use_nullable_id() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python({"type": "tool_use", "id": None, "name": "test", "input": {}})
    assert isinstance(block, ToolUseContent)
    assert block.id is None


def test_tool_result_content() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python(
        {
            "type": "tool_result",
            "tool_use_id": "tu-1",
            "name": "web_search",
            "content": "some result",
            "is_error": False,
        }
    )
    assert isinstance(block, ToolResultContent)
    assert block.content == "some result"


def test_tool_result_display_content_dict() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python(
        {
            "type": "tool_result",
            "tool_use_id": "tu-1",
            "name": "web_fetch",
            "display_content": {"type": "rich_link", "link": {"url": "https://example.com"}},
        }
    )
    assert isinstance(block, ToolResultContent)
    assert isinstance(block.display_content, dict)


def test_token_budget_content() -> None:
    adapter = TypeAdapter(ContentBlock)
    block = adapter.validate_python({"type": "token_budget"})
    assert isinstance(block, TokenBudgetContent)


def test_chat_message_parsing() -> None:
    data = {
        "uuid": "msg-1",
        "text": "Hello",
        "content": [{"type": "text", "text": "Hello"}],
        "sender": "human",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": None,
        "attachments": [{"file_name": "doc.pdf", "file_size": 1024, "file_type": "pdf", "extracted_content": "text"}],
        "files": [{"file_name": "image.png"}],
    }
    msg = ChatMessage.model_validate(data)
    assert msg.sender == "human"
    assert len(msg.content) == 1
    assert isinstance(msg.content[0], TextContent)
    assert len(msg.attachments) == 1
    assert isinstance(msg.attachments[0], Attachment)
    assert len(msg.files) == 1
    assert isinstance(msg.files[0], FileRef)


def test_conversation_parsing() -> None:
    data = {
        "uuid": "conv-1",
        "name": "Test Conversation",
        "summary": "",
        "created_at": "2026-01-01T12:00:00Z",
        "updated_at": "2026-01-01T13:00:00Z",
        "account": {"uuid": "acct-1"},
        "chat_messages": [
            {
                "uuid": "msg-1",
                "text": "Hi",
                "content": [{"type": "text", "text": "Hi"}],
                "sender": "human",
                "attachments": [],
                "files": [],
            },
            {
                "uuid": "msg-2",
                "text": "Hello!",
                "content": [{"type": "text", "text": "Hello!"}],
                "sender": "assistant",
                "attachments": [],
                "files": [],
            },
        ],
    }
    convo = Conversation.model_validate(data)
    assert convo.name == "Test Conversation"
    assert len(convo.chat_messages) == 2
    assert convo.chat_messages[0].sender == "human"
    assert convo.chat_messages[1].sender == "assistant"


def test_conversation_with_project_uuid() -> None:
    data = {
        "uuid": "conv-2",
        "name": "Project Chat",
        "account": {"uuid": "acct-1"},
        "project_uuid": "proj-1",
        "chat_messages": [],
    }
    convo = Conversation.model_validate(data)
    assert convo.project_uuid == "proj-1"


def test_conversation_without_project_uuid() -> None:
    convo = Conversation(uuid="conv-3", name="No Project")
    assert convo.project_uuid is None


# --- Tolerance to unexpected export content ---


def test_unknown_block_types_do_not_fail() -> None:
    from claude_export_viewer.models import ChatMessage, TextContent, UnknownContent

    msg = ChatMessage.model_validate(
        {
            "sender": "assistant",
            "content": [
                {"type": "image", "source": {}},
                {"type": "server_tool_use", "name": "web_search", "input": {"query": "lois normales"}},
                {"type": "text", "text": "ok"},
            ],
        }
    )
    kinds = [type(b) for b in msg.content]
    assert kinds == [UnknownContent, UnknownContent, TextContent]
    assert msg.content[0].original_type == "image"
    assert "lois normales" in msg.content[1].text


def test_lenient_fields() -> None:
    from claude_export_viewer.models import Conversation

    c = Conversation.model_validate(
        {
            "uuid": "c1",
            "name": None,
            "created_at": "not a date",
            "account": "weird",
            "chat_messages": [
                {"sender": "system", "attachments": [{"file_name": "a.txt", "file_size": None}, "junk"]},
                42,
            ],
        }
    )
    assert c.name == ""
    assert c.created_at is None
    assert c.account is None
    assert len(c.chat_messages) == 1
    assert c.chat_messages[0].sender == "system"
    assert c.chat_messages[0].uuid == ""
    assert c.chat_messages[0].attachments[0].file_size == 0
