"""Markdown version of a conversation, offered by the ".md" export button.

Content: the text exchanged (and the artifacts Claude produced) along the main
branch; every other version of the conversation is placed where it forks off,
inside a quote block (a frame in Writer or Word) whose labels are in italics.
Thinking blocks, tool calls and tool results are left out.

The Markdown uses only common syntax (headings, quotes, fenced code, $…$
formulas), readable by Typora, Obsidian, Zettlr, and convertible by Pandoc.

Labels ("You", "Other version", dates…) go through a translator ``tr``: the
program's own (``i18n.t``) for files it writes, or ``marker`` for the Markdown
embedded in the pages, whose markers ⟦cev:key:{args}⟧ are replaced by the
browser in the language chosen in the index (static/i18n.js).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from . import dates, i18n, tree
from .models import Attachment, ChatMessage, FileRef, TextContent, ToolUseContent

Translator = Callable[..., str]

_CODE_TYPES = {
    "application/vnd.ant.code": "",
    "application/vnd.ant.mermaid": "mermaid",
    "text/html": "html",
    "application/vnd.ant.react": "jsx",
    "image/svg+xml": "svg",
}


def marker(key: str, **args: Any) -> str:
    """A label left for the browser to translate: ⟦cev:key:{args}⟧."""
    if not args:
        return f"\u27e6cev:{key}\u27e7"
    payload = json.dumps({k: i18n._js_arg(v) for k, v in args.items()}, ensure_ascii=False)
    payload = payload.replace("\u27e7", "\\u27e7")  # a "⟧" in a title must not end the marker
    return f"\u27e6cev:{key}:{payload}\u27e7"


def _fence(text: str, lang: str = "") -> str:
    longest = max((len(m) for m in re.findall(r"`{3,}", text)), default=2)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{text.rstrip()}\n{ticks}"


def _artifact(block: ToolUseContent, tr: Translator) -> str:
    ai = block.artifact_input
    if ai is None or ai.command not in ("create", "rewrite") or not ai.content:
        return ""
    title = "**" + (tr("md.artifact", title=ai.title) if ai.title else tr("md.artifact_untitled")) + "**"
    kind = ai.type or ""
    if kind in _CODE_TYPES:
        return f"{title}\n\n{_fence(ai.content, ai.language or _CODE_TYPES[kind])}"
    return f"{title}\n\n{ai.content.strip()}"


def message_body(msg: ChatMessage, tr: Translator = i18n.t) -> str:
    parts: list[str] = []
    names = [a.file_name for a in msg.attachments if isinstance(a, Attachment) and a.file_name]
    names += [f.file_name for f in msg.files if isinstance(f, FileRef) and f.file_name]
    if names:
        parts.append("*" + tr("md.attachments", names=", ".join(names)) + "*")
    for block in msg.content:
        if isinstance(block, TextContent) and block.text.strip():
            parts.append(block.text.strip())
        elif isinstance(block, ToolUseContent) and block.is_artifact:
            art = _artifact(block, tr)
            if art:
                parts.append(art)
    return "\n\n".join(parts)


def _speaker(msg: ChatMessage, tr: Translator) -> str:
    if msg.sender == "human":
        return tr("md.you")
    if msg.sender == "assistant":
        return "Claude"
    return msg.sender.capitalize() or "?"


def _quote(text: str, levels: int = 1) -> str:
    prefix = "> " * levels
    return "\n".join((prefix + line) if line else prefix.rstrip() for line in text.split("\n"))


def conversation_markdown(
    title: str,
    created: datetime | None,
    items: list[tree.Item],
    to_message: Any,
    deleted_since: str = "",
    frame_levels: int = 1,
    versions: bool = True,
    tr: Translator = i18n.t,
) -> str:
    """``frame_levels``: quote levels per frame (2 doubles the indent in Writer and Word).

    ``deleted_since``: ISO date of the export the conversation is missing from.
    ``versions=False`` keeps only the main thread: other versions and parts deleted
    on claude.ai are left out (and the header says so when there were any; without
    any, the text is exactly the same as with ``versions=True``).
    """
    main = tree.main_path(items)

    def render_item(item: tree.Item) -> str:
        msg = to_message(item.payload)
        if msg is None:
            return ""
        body = message_body(msg, tr)
        if not body:
            return ""
        # Inside a frame, speakers are in italics too, to tell them from the main thread.
        stars = "**" if any(x is item for x in main) else "***"
        head = f"{stars}{_speaker(msg, tr)}{stars}"
        if msg.created_at:
            head += " — " + tr("md.when", date=msg.created_at)
        return f"{head}\n\n{body}"

    omitted = 0

    def render_branch(branch: tree.Branch) -> str:
        nonlocal omitted
        if not versions:
            omitted += 1
            return ""
        if branch.removed:
            label = tr("md.removed_part", n=branch.size)
        else:
            label = tr("md.alt_version", n=branch.size)
            started = dates.parse(branch.first.created)
            if started:
                label += tr("md.started", date=started)
        inner = "\n\n".join(p for p in branch.content if p)
        block = f"*{label}*" + (f"\n\n{inner}" if inner else "")
        return _quote(block, frame_levels)

    pieces, _ = tree.render(items, render_item, render_branch)
    lines = [f"# {title or tr('web.untitled')}", ""]
    meta = []
    if created:
        meta.append(tr("md.conversation_of", date=created))
    meta.append(tr("md.exported") + (tr("md.main_only") if omitted else ""))
    lines.append("*" + " · ".join(meta) + "*")
    if deleted_since:
        lines += ["", "*" + tr("md.deleted", date=i18n.Day(deleted_since)) + "*"]
    lines.append("")
    body = "\n\n---\n\n".join(p for p in pieces if p)
    return "\n".join(lines) + "\n---\n\n" + body + "\n"


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def export_filename(title: str, created: datetime | None, lang: str | None = None) -> str:
    untitled = i18n.t("web.untitled", lang)
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or untitled)
    clean = re.sub(r"\s+", " ", clean).strip()[:80] or untitled
    prefix = created.astimezone().strftime("%Y-%m-%d ") if created and created.tzinfo else (
        created.strftime("%Y-%m-%d ") if created else "")
    if not prefix and clean.split(".")[0].upper() in _WINDOWS_RESERVED:
        clean += "_"  # "CON.md", "NUL.md"… cannot be created on Windows
    return f"{prefix}{clean}.md"


def main_filename(filename: str, lang: str | None = None) -> str:
    """File name of a "main thread only" export: "2026-10-20 Title.md" -> "2026-10-20 Title (main thread).md"."""
    suffix = i18n.t("md.main_suffix", lang)
    stem, dot, ext = filename.rpartition(".")
    return f"{stem}{suffix}.{ext}" if dot else filename + suffix


def embed(markdown: str, filename: str, markdown_main: str | None = None) -> str:
    """JSON safe to put inside <script type="application/json">.

    ``markdown_main`` (main thread only) is stored only when it differs, i.e. when
    the conversation has other versions or deleted parts; the page then adds the
    translated " (main thread)" suffix to the file name.
    """
    payload = {"filename": filename, "markdown": markdown}
    if markdown_main is not None and markdown_main != markdown:
        payload["markdown_main"] = markdown_main
    data = json.dumps(payload, ensure_ascii=False)
    return data.replace("<", "\\u003c")
