"""Tolerant Pydantic models of the conversations of a Claude.ai export."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator, model_validator

# --- Tolerant base -----------------------------------------------------------
#
# Claude exports evolve over time. Every model below is lenient: unknown keys
# are ignored, ``null`` values fall back to the field default, and unparseable
# dates become ``None``. Malformed content blocks, attachments or files are
# converted or dropped instead of aborting the whole export.

_DATETIME = TypeAdapter(datetime)


def _lenient_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return _DATETIME.validate_python(value)
    except ValidationError:
        return None


class TolerantModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


def _lenient_list(model: type[BaseModel], items: Any) -> list[Any]:
    """Validate each item separately and silently drop the invalid ones."""
    if not isinstance(items, list):
        return []
    out: list[Any] = []
    for item in items:
        if isinstance(item, model):
            out.append(item)
            continue
        try:
            out.append(model.model_validate(item))
        except ValidationError:
            pass
    return out


# --- Users ---


class User(TolerantModel):
    uuid: str
    full_name: str = ""
    email_address: str = ""


# --- Content Blocks ---


class TextContent(TolerantModel):
    type: Literal["text"] = "text"
    text: str = ""
    citations: list[Any] = []


class ThinkingSummary(TolerantModel):
    summary: str = ""


class ThinkingContent(TolerantModel):
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    summaries: list[ThinkingSummary] = []
    cut_off: bool = False
    alternative_display_type: str | None = None

    @field_validator("summaries", mode="before")
    @classmethod
    def _summaries(cls, v: Any) -> list[Any]:
        return _lenient_list(ThinkingSummary, v)


class ArtifactInput(TolerantModel):
    command: str = "create"
    id: str = ""
    type: str | None = None
    title: str | None = None
    language: str | None = None
    content: str | None = None
    old_str: str | None = None
    new_str: str | None = None
    version_uuid: str | None = None


class ToolUseContent(TolerantModel):
    type: Literal["tool_use"] = "tool_use"
    id: str | None = None
    name: str = ""
    input: dict[str, Any] | ArtifactInput = Field(default_factory=dict)
    message: str | None = None
    integration_name: str | None = None
    display_content: str | dict[str, Any] | list[Any] | None = None

    @property
    def is_artifact(self) -> bool:
        return self.name == "artifacts"

    @property
    def artifact_input(self) -> ArtifactInput | None:
        if not self.is_artifact:
            return None
        if isinstance(self.input, ArtifactInput):
            return self.input
        try:
            return ArtifactInput.model_validate(self.input)
        except ValidationError:
            return None


class ToolResultContent(TolerantModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str | None = None
    name: str = ""
    content: Any = None
    is_error: bool = False
    structured_content: dict[str, Any] | None = None
    message: str | None = None
    integration_name: str | None = None
    display_content: str | dict[str, Any] | list[Any] | None = None


class TokenBudgetContent(TolerantModel):
    type: Literal["token_budget"] = "token_budget"


class UnknownContent(TolerantModel):
    """A content block whose type this tool does not know (image, web search, ...)."""

    type: Literal["unknown"] = "unknown"
    original_type: str = ""
    text: str = ""
    source: str = ""  # injected_prompt_block: where the instructions came from


ContentBlock = Annotated[
    TextContent | ThinkingContent | ToolUseContent | ToolResultContent | TokenBudgetContent | UnknownContent,
    Field(discriminator="type"),
]

_KNOWN_BLOCK_TYPES = {"text", "thinking", "tool_use", "tool_result", "token_budget", "unknown"}
_BLOCK_ADAPTER: TypeAdapter[Any] = TypeAdapter(ContentBlock)


def _extract_text(value: Any, limit: int = 4000) -> str:
    """Best-effort extraction of human-readable text from an arbitrary block."""
    parts: list[str] = []

    def walk(v: Any, depth: int) -> None:
        if depth > 6 or sum(len(p) for p in parts) > limit:
            return
        if isinstance(v, str):
            if v.strip():
                parts.append(v)
        elif isinstance(v, dict):
            for key in ("text", "title", "url", "query", "content", "summary"):
                if key in v:
                    walk(v[key], depth + 1)
        elif isinstance(v, list):
            for x in v:
                walk(x, depth + 1)

    if isinstance(value, dict):
        for key in ("text", "content", "title", "url", "input", "summary"):
            if key in value:
                walk(value[key], 0)
    text = "\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n..."


def parse_content_blocks(blocks: Any) -> list[Any]:
    """Validate content blocks one by one; unknown or broken ones become UnknownContent."""
    if not isinstance(blocks, list):
        return []
    out: list[Any] = []
    for b in blocks:
        if isinstance(b, BaseModel):
            out.append(b)
            continue
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        if btype in _KNOWN_BLOCK_TYPES:
            try:
                out.append(_BLOCK_ADAPTER.validate_python(b))
                continue
            except ValidationError:
                pass
        if btype == "injected_prompt_block":
            # Instructions added automatically by claude.ai (not written by the user)
            src = b.get("injection_source")
            if isinstance(src, dict):
                src = src.get("type") or src.get("name") or ""
            prompt = b.get("prompt")
            out.append(
                UnknownContent(
                    original_type="injected_prompt_block",
                    text=prompt if isinstance(prompt, str) else _extract_text(b),
                    source=str(src or ""),
                )
            )
            continue
        out.append(UnknownContent(original_type=str(btype or "?"), text=_extract_text(b)))
    return out


# --- Attachments & Files ---


class Attachment(TolerantModel):
    file_name: str = ""
    file_size: int = 0
    file_type: str = ""
    extracted_content: str = ""

    @field_validator("file_size", mode="before")
    @classmethod
    def _size(cls, v: Any) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0


class FileRef(TolerantModel):
    file_name: str = ""


# --- Messages & Conversations ---


class ChatMessage(TolerantModel):
    uuid: str = ""
    parent_message_uuid: str | None = None
    text: str = ""
    content: list[ContentBlock] = []
    sender: str = "unknown"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[Attachment] = []
    files: list[FileRef] = []

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _dates(cls, v: Any) -> datetime | None:
        return _lenient_datetime(v)

    @field_validator("content", mode="before")
    @classmethod
    def _content(cls, v: Any) -> list[Any]:
        return parse_content_blocks(v)

    @field_validator("attachments", mode="before")
    @classmethod
    def _attachments(cls, v: Any) -> list[Any]:
        return _lenient_list(Attachment, v)

    @field_validator("files", mode="before")
    @classmethod
    def _files(cls, v: Any) -> list[Any]:
        return _lenient_list(FileRef, v)

    @model_validator(mode="after")
    def _fallback_text(self) -> ChatMessage:
        # Older exports may only fill ``text``; show it if no block has text.
        if self.text and not any(isinstance(b, TextContent) and b.text for b in self.content):
            self.content = [TextContent(text=self.text), *self.content]
        return self


class AccountRef(TolerantModel):
    uuid: str = ""


class Conversation(TolerantModel):
    uuid: str
    name: str = ""
    summary: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    account: AccountRef | None = None
    project_uuid: str | None = None
    chat_messages: list[ChatMessage] = []

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _dates(cls, v: Any) -> datetime | None:
        return _lenient_datetime(v)

    @field_validator("account", mode="before")
    @classmethod
    def _account(cls, v: Any) -> Any:
        return v if isinstance(v, (dict, AccountRef)) else None

    @field_validator("chat_messages", mode="before")
    @classmethod
    def _messages(cls, v: Any) -> list[Any]:
        return _lenient_list(ChatMessage, v)


# --- Helpers ---


def parse_message(raw: Any) -> ChatMessage | None:
    """A validated message, or None if it cannot be read."""
    if isinstance(raw, ChatMessage):
        return raw
    try:
        return ChatMessage.model_validate(raw)
    except (ValueError, TypeError):
        return None


def is_empty_conversation(convo: Conversation) -> bool:
    """True when no message contains conversation text.

    Deleted conversations stay in the export either completely empty or with
    leftovers only (an attached image or file, an empty reply...): attachments,
    files, tool calls and thinking blocks alone do not make a conversation.
    """
    return not any(isinstance(b, TextContent) and b.text.strip() for m in convo.chat_messages for b in m.content)
