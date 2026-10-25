"""HTML of one message: Markdown (mistune), formulas, code (Pygments), artifacts, attachments, other blocks."""

from __future__ import annotations

import functools
import html
import re
from typing import Any

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from .i18n import html_date, html_text, t
from .math_plugin import latex_math
from .models import (
    Attachment,
    ChatMessage,
    FileRef,
    TextContent,
    ThinkingContent,
    TokenBudgetContent,
    ToolResultContent,
    ToolUseContent,
    UnknownContent,
)

# --- Markdown renderer with Pygments code highlighting ---

_pygments_formatter = HtmlFormatter(nowrap=True)


@functools.lru_cache(maxsize=64)
def _lexer_for(lang: str) -> Any:
    # Building a lexer is costly; one instance per language can be reused.
    return get_lexer_by_name(lang, stripall=True)


def _language_label(lang: str | None) -> str:
    """Human-readable language name ("python" -> "Python"), or "" if unknown."""
    if not lang:
        return ""
    try:
        return _lexer_for(lang.lower()).name
    except Exception:
        return lang


def code_block(code: str, lang: str | None) -> str:
    """A code frame with a header: language on the left, "Copy" button on the right (code.js)."""
    highlighted = _highlight_code(code, lang)
    lang_class = f' class="language-{html.escape(lang)}"' if lang else ""
    label = html.escape(_language_label(lang))
    return (
        '<div class="code-block">'
        '<div class="code-header">'
        f'<span class="code-lang">{label}</span>'
        + html_text("web.copy", "button", f' type="button" class="copy-btn" title="{html.escape(t("web.copy_title"))}"'
                    ' data-i18n-attr="title:web.copy_title"')
        + "</div>"
        f"<pre class='highlight' translate='no'><code{lang_class}>{highlighted}</code></pre>"
        "</div>"
    )


def _highlight_code(code: str, lang: str | None) -> str:
    # Without a language, the code is shown as plain text: guessing the language
    # is slow on long blocks and often wrong.
    if not lang:
        return html.escape(code)
    try:
        lexer = _lexer_for(lang.lower())
    except Exception:
        return html.escape(code)
    return highlight(code, lexer, _pygments_formatter)


class _HighlightRenderer(mistune.HTMLRenderer):
    """Extends the default HTML renderer to use Pygments for code blocks."""

    def block_code(self, code: str, info: str | None = None, **attrs: Any) -> str:
        lang = info.split()[0] if info else None
        return code_block(code, lang) + "\n"

    def link(self, text: str, url: str, title: str | None = None) -> str:
        # safe_url() neutralises javascript:, vbscript:, data: (non image) and file: links
        safe = self.safe_url(url)
        title_attr = f' title="{html.escape(title)}"' if title else ""
        return f'<a href="{safe}"{title_attr} target="_blank" rel="noopener noreferrer">{text}</a>'

    def image(self, text: str, url: str, title: str | None = None) -> str:
        # An archive read offline must not load pictures from the Internet (nor
        # files of this computer): a Markdown image is shown as a link.
        label = text or html.escape(url)
        return self.link(f"[{html_text('web.image_link', label='')}{label}]", url, title)


_md = mistune.create_markdown(
    renderer=_HighlightRenderer(),
    plugins=["strikethrough", "table", latex_math],
)


def render_markdown(text: str) -> str:
    """Render markdown text to HTML."""
    return _md(text)


# --- Content block renderers ---


def _render_text(block: TextContent) -> str:
    if not block.text:
        return ""
    return f'<div class="content-text">{render_markdown(block.text)}</div>'


def _render_thinking(block: ThinkingContent) -> str:
    if not block.thinking:
        return ""
    if block.summaries:
        summary = f"<summary>{html.escape(block.summaries[-1].summary)}</summary>"
    else:
        summary = html_text("web.thinking", "summary")
    return (
        f'<details class="thinking">'
        f"{summary}"
        f'<div class="thinking-content">{render_markdown(block.thinking)}</div>'
        f"</details>"
    )


# Artifact type → label (a translation key, or a name that needs none)
_ARTIFACT_TYPE_LABELS: dict[str, str] = {
    "text/markdown": "web.artifact.document",
    "text/html": "HTML",
    "application/vnd.ant.code": "Code",
    "application/vnd.ant.react": "web.artifact.react",
    "application/vnd.ant.mermaid": "web.artifact.mermaid",
    "image/svg+xml": "SVG",
}


def _render_artifact(block: ToolUseContent) -> str:
    ai = block.artifact_input
    if ai is None:
        return ""

    # Only render create/rewrite commands (they have full content)
    if ai.command not in ("create", "rewrite"):
        return ""

    title = html.escape(ai.title) if ai.title else html_text("web.untitled")
    artifact_type = ai.type or ""
    type_label = _ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type)
    type_html = html_text(type_label) if type_label.startswith("web.") else html.escape(type_label)
    content = ai.content or ""

    # Render content based on type
    if artifact_type in ("text/markdown",):
        rendered = render_markdown(content)
    elif artifact_type in ("application/vnd.ant.code", "application/vnd.ant.mermaid"):
        lang = ai.language or ""
        rendered = code_block(content, lang or None)
    elif artifact_type in ("text/html", "application/vnd.ant.react", "image/svg+xml"):
        # Show as highlighted code — rendering raw HTML/React would be unsafe
        lang = "html" if artifact_type != "application/vnd.ant.react" else "jsx"
        rendered = code_block(content, lang)
    else:
        rendered = render_markdown(content)

    return (
        f'<div class="artifact">'
        f'<div class="artifact-header">'
        f'<span class="artifact-title">{title}</span>'
        f'<span class="artifact-type">{type_html}</span>'
        f"</div>"
        f'<div class="artifact-content">{rendered}</div>'
        f"</div>"
    )


def _render_tool_use(block: ToolUseContent) -> str:
    if block.is_artifact:
        return _render_artifact(block)

    summary = (f"<summary>{html.escape(block.message)}</summary>" if block.message
               else html_text("web.tool_used", "summary", name=block.name))
    tool = html_text("web.tool", "div", ' class="tool-name"', name=block.name)
    return f'<details class="tool-use">{summary}{tool}</details>'


def _render_tool_result(block: ToolResultContent) -> str:
    # Skip artifact results (usually just "OK")
    if block.name == "artifacts":
        return ""

    content_text = ""
    if isinstance(block.content, str):
        content_text = block.content
    elif isinstance(block.content, list):
        parts = []
        for item in block.content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        content_text = "\n".join(parts)

    if not content_text or len(content_text.strip()) == 0:
        return ""

    # Truncate very long tool results
    truncated = len(content_text) > 2000
    display = html.escape(content_text[:2000]) + ("\n" + html_text("web.truncated") if truncated else "")

    error_class = " tool-error" if block.is_error else ""
    summary = (html_text("web.tool_result", "summary", name=block.name) if block.name
               else html_text("web.tool_result_unnamed", "summary"))
    return (
        f'<details class="tool-result{error_class}">'
        f"{summary}"
        f"<pre>{display}</pre>"
        f"</details>"
    )


def _render_attachment(att: Attachment) -> str:
    name = html.escape(att.file_name) if att.file_name else html_text("web.no_name")
    file_type = html.escape(att.file_type) if att.file_type else html_text("web.file")
    size_kb = att.file_size / 1024 if att.file_size else 0.0
    size = (html_text("web.size_kb", size=float(size_kb)) if size_kb < 1024
            else html_text("web.size_mb", size=float(size_kb / 1024)))

    parts = ['<div class="attachment">']
    details = f"{file_type}, {size}" if att.file_size else file_type
    parts.append(f'<span class="attachment-pill">{name} ({details})</span>')

    if att.extracted_content:
        if len(att.extracted_content) <= 3000:
            preview = att.extracted_content
        else:
            preview = att.extracted_content[:3000] + "\n..."
        parts.append(
            f'<details class="attachment-content">'
            f"{html_text('web.view_content', 'summary')}"
            f"<pre>{html.escape(preview)}</pre>"
            f"</details>"
        )

    parts.append("</div>")
    return "".join(parts)


def _render_file(f: FileRef) -> str:
    name = html.escape(f.file_name) if f.file_name else html_text("web.unknown_file")
    return f'<span class="file-pill">{name}</span>'


_PILL = ' class="file-pill"'


def _render_unknown(block: UnknownContent) -> str:
    kind = block.original_type or "?"
    if kind == "document":
        pill = html_text("web.document_attached", "span", _PILL)
        return f'<div class="unknown-block">{pill}</div>'
    if kind == "injected_prompt_block":
        if not block.text.strip():
            return ""
        summary = (html_text("web.injected_from", "summary", source=block.source) if block.source
                   else html_text("web.injected", "summary"))
        text = block.text if len(block.text) <= 8000 else block.text[:8000] + "\n..."
        return (
            f'<details class="tool-result unknown-block injected">'
            f"{summary}"
            f"<pre>{html.escape(text)}</pre>"
            f"</details>"
        )
    key, args = ("web.image_not_included", {}) if kind == "image" else ("web.content_of_type", {"type": kind})
    if not block.text:
        pill = html_text(key, "span", _PILL, **args)
        return f'<div class="unknown-block">{pill}</div>'
    return (
        f'<details class="tool-result unknown-block">'
        f"{html_text(key, 'summary', **args)}"
        f"<pre>{html.escape(block.text)}</pre>"
        f"</details>"
    )


_SAFE_CLASS = re.compile(r"[^a-z0-9_-]")


def render_message(msg: ChatMessage) -> str:
    """Render a full chat message to HTML."""
    parts: list[str] = []

    # Render attachments first (they appear above the message)
    for att in msg.attachments:
        parts.append(_render_attachment(att))

    # Render file references
    if msg.files:
        file_html = " ".join(_render_file(f) for f in msg.files)
        parts.append(f'<div class="files">{file_html}</div>')

    # Render content blocks
    for block in msg.content:
        if isinstance(block, TextContent):
            parts.append(_render_text(block))
        elif isinstance(block, ThinkingContent):
            parts.append(_render_thinking(block))
        elif isinstance(block, ToolUseContent):
            parts.append(_render_tool_use(block))
        elif isinstance(block, ToolResultContent):
            parts.append(_render_tool_result(block))
        elif isinstance(block, TokenBudgetContent):
            pass  # Skip
        elif isinstance(block, UnknownContent):
            parts.append(_render_unknown(block))

    rendered = "\n".join(p for p in parts if p)

    sender = _SAFE_CLASS.sub("", msg.sender.lower()) or "unknown"
    time_html = f'<div class="message-time">{html_date(msg.created_at, with_time=True)}</div>\n' if msg.created_at else ""
    return (
        f'<div class="message message-{sender}">\n{time_html}'
        f'<div class="message-bubble">\n{rendered}\n</div>\n</div>'
    )
