"""HTML of one message: Markdown (mistune), formulas, code (Pygments), artifacts, attachments, other blocks."""

from __future__ import annotations

import functools
import html
import re
from typing import Any
from urllib.parse import quote

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from . import attachments, userfiles
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
    pill = f'<span class="attachment-pill">{name} ({details})</span>'
    original = attachments.found(att.file_name)
    # the original document found on the computer: its name, then the icon opening it
    parts.append(_userfile(att.file_name, original, pill) if original else pill)

    text = att.extracted_content
    if text:
        saved = attachments.save(att.file_name or "document", text)
        if saved and not original:  # the whole text as a file: opened with the program of the computer
            parts.append(_open_link(saved.href.removeprefix("../")))
        n = len(text)
        long_doc = n > attachments.LONG
        summary_key = "web.attachment.view_long" if long_doc else "web.attachment.view"
        details = [f'<details class="attachment-content">{html_text(summary_key, "summary", n=n)}']
        if long_doc or (saved and saved.text_only):
            notes = []
            if long_doc:
                notes.append(html_text("web.attachment.long", n=n))
            if saved and saved.text_only:
                notes.append(html_text("web.attachment.text_only"))
            if saved:
                notes.append(html_text("web.attachment.path") + f' <code translate="no">{html.escape(str(saved.path))}</code>')
            details.append('<p class="attachment-note">' + " ".join(notes) + "</p>")
        details.append(f'<pre translate="no">{html.escape(text)}</pre></details>')
        parts.append("".join(details))

    parts.append("</div>")
    return "".join(parts)


def _open_link(rel: str) -> str:
    """Icon opening a file of the site (``rel``: URL path from the site folder) with the program of the computer."""
    rel = html.escape(rel)
    return (
        f'<a class="attachment-open" href="../{rel}" data-open="{rel}" target="_blank"'
        f' title="{html.escape(t("web.attachment.open"))}" data-i18n-attr="title:web.attachment.open">'
        '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M14 3h7v7M21 3l-9 9'
        'M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg></a>'
    )


def _userfile(name: str, entry: dict, pill: str = "") -> str:
    """A file of the conversation found on the user's computer (copied into the site)."""
    rel = quote(entry["copy"])
    ext = name.rpartition(".")[2].lower() if "." in name else ""
    out = [f'<div class="userfile" data-file="{html.escape(name)}">']
    if ext in userfiles.IMAGES:
        out.append(f'<a class="userfile-image" href="../{html.escape(rel)}" target="_blank">'
                   f'<img src="../{html.escape(rel)}" alt="{html.escape(name)}" loading="lazy"></a>')
    pill = pill or f'<span class="file-pill">{html.escape(name)}</span>'
    out.append(f'<div class="userfile-bar">{pill}{_open_link(rel)}')
    if entry.get("state") != "ok":
        out.append(
            '<span class="userfile-check">'
            + html_text("web.userfile.found", "span")
            + f' <code translate="no">{html.escape(entry.get("source", ""))}</code> '
            + html_text("web.userfile.question", "span")
            + f' <button type="button" class="userfile-yes" data-action="ok">{html_text("web.userfile.yes")}</button>'
            + f'<button type="button" class="userfile-no" data-action="reject">{html_text("web.userfile.no")}</button>'
            + "</span>"
        )
    else:  # accepted: the answer can be changed (the question comes back)
        out.append('<span class="userfile-accepted">'
                   f'<button type="button" class="userfile-edit" data-action="undo">{html_text("web.userfile.edit")}</button>'
                   "</span>")
    out.append("</div></div>")
    return "".join(out)


def _render_file(f: FileRef) -> str:
    entry = attachments.found(f.file_name)
    if entry:
        return _userfile(f.file_name, entry)
    name = html.escape(f.file_name) if f.file_name else html_text("web.unknown_file")
    return f'<span class="file-pill">{name}</span>'


_PILL = ' class="file-pill"'


def _render_unknown(block: UnknownContent) -> str:
    kind = block.original_type or "?"
    if kind == "document":
        pill = html_text("web.document_attached", "span", _PILL)
        return f'<div class="unknown-block">{pill}</div>'
    if kind == "injected_prompt_block":
        if not block.text.strip() or not attachments.first_injected(block.source, block.text.strip()):
            return ""  # the same instructions repeated by claude.ai: shown once per page
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


_COPY_SVG = ('<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/>'
             '<path d="M5 15V5a2 2 0 0 1 2-2h8"/></svg>')


def render_message(msg: ChatMessage, markdown: str = "") -> str:
    """Render a full chat message to HTML (``markdown``: its text, copied by the icon after the date)."""
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

    # Files created by Claude that the user saved, found on the computer
    created = [(n, e) for n in userfiles.created_names([b.model_dump(mode="json") for b in msg.content])
               if (e := attachments.found(n))]
    if created:
        parts.append('<div class="files created-files">' + "".join(_userfile(n, e) for n, e in created) + "</div>")

    rendered = "\n".join(p for p in parts if p)

    sender = _SAFE_CLASS.sub("", msg.sender.lower()) or "unknown"
    copy = ""
    if markdown.strip():
        copy = (f'<button type="button" class="copy-msg" title="{html.escape(t("web.copy_msg"))}"'
                f' data-i18n-attr="title:web.copy_msg" data-md="{html.escape(markdown)}">{_COPY_SVG}</button>')
    date = html_date(msg.created_at, with_time=True) if msg.created_at else ""
    time_html = f'<div class="message-time">{date}{copy}</div>\n' if date or copy else ""
    return (
        f'<div class="message message-{sender}">\n{time_html}'
        f'<div class="message-bubble">\n{rendered}\n</div>\n</div>'
    )
