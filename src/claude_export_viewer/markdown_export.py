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

from . import created, dates, i18n, tree
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
    payload = i18n.dumps({k: i18n._js_arg(v) for k, v in args.items()})
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


def _created(p: created.Presented, tr: Translator, href: str | None = None) -> str:
    """A file handed over by Claude: its content as a code block (or its name only); ``href``: a link
    on its name (the ZIP of an export)."""
    if p.text is None:
        return "*" + tr("md.created_absent", name=_named_link(p.name, href)) + "*"
    head = tr("md.created", name=_named_link(p.name, href))
    if p.versions > 1:
        head += " " + tr("md.created_version", n=p.version, total=p.versions)
    out = f"**{head}**"
    if not p.complete:
        out += "\n\n*" + tr("md.created_incomplete") + "*"
    return out + "\n\n" + _fence(p.text, created.language(p.name))


_TYPED_ESC = re.compile(r"""([\\`*_{}<>#+\-.!|~^$@=&"':])""")
_NBSP = "\u00a0"


def typed(text: str) -> str:
    """The user's text as Markdown that shows it as typed (no Markdown of its own, as on claude.ai):
    punctuation escaped, every line kept (hard breaks), leading spaces and empty lines kept."""
    lines = []
    for line in text.strip("\n").split("\n"):
        line = _TYPED_ESC.sub(r"\\\1", line.rstrip()).replace("[", "&#91;").replace("]", "&#93;")
        lead = len(line) - len(line.lstrip(" \t"))
        indent = line[:lead].replace("\t", "    ").replace(" ", _NBSP)
        lines.append(indent + line[lead:] or _NBSP)
    return "\\\n".join(lines)


# A file linked from an export (the ZIP of an export, zipexport.py):
# links(message uuid, kind, name, rank of that name, text known from the export or None) -> href or None
Linker = Callable[[str, str, str, int, "str | None"], "str | None"]


def _named_link(label: str, href: str | None) -> str:
    if not href:
        return label
    return "[" + re.sub(r"([\\\[\]])", r"\\\1", label) + "](<" + href + ">)"


# Highlighted passages in an export: "==text==" (Markdown read by Pandoc with +mark, Obsidian,
# Typora); for an .odt, two characters Pandoc keeps as they are, made a yellow span afterwards
# (office_export.odt_highlights).
ODT_ON, ODT_OFF = "\ue000", "\ue001"


def _escape_typed(line: str) -> str:
    return _TYPED_ESC.sub(r"\\\1", line).replace("[", "&#91;").replace("]", "&#93;")


def highlight(text: str, quotes: list[str], user: bool = False, odt: bool = False) -> str:
    """``text`` with each passage of ``quotes`` highlighted where it is found as is (a passage over
    several lines: each line); ``user``: ``text`` is the user's text made by :func:`typed`. A passage
    crossing formatting (bold, a link…) is not found: left plain."""
    on, off = (ODT_ON, ODT_OFF) if odt else ("==", "==")
    for q in quotes:
        start = 0
        for line in (x.strip() for x in q.split("\n")):
            if not line:
                continue
            needle = _escape_typed(line) if user else line
            i = text.find(needle, start)
            if i < 0:
                continue
            text = text[:i] + on + needle + off + text[i + len(needle):]
            start = i + len(on) + len(needle) + len(off)
    return text


def message_body(msg: ChatMessage, tr: Translator = i18n.t, files: list[created.Presented] | None = None,
                 as_typed: bool = True, links: Linker | None = None, marks: list[str] | None = None,
                 odt: bool = False) -> str:
    """Markdown of a message (``files``: the files it hands over, from created.reconstruct;
    ``as_typed``: the user's text kept as typed, see :func:`typed`; False: the raw text, for the copy;
    ``links``: the names of the files become links, see Linker)."""
    parts: list[str] = []
    ranks: dict[tuple[str, str], int] = {}

    def link(kind: str, name: str, text: str | None) -> str | None:
        if links is None:
            return None
        ranks[(kind, name)] = ranks.get((kind, name), 0) + 1
        return links(msg.uuid, kind, name, ranks[(kind, name)], text)

    names = [_named_link(a.file_name or tr("web.pasted_text"),
                         link("attachment", a.file_name or tr("web.pasted_text") + ".txt", a.extracted_content or None))
             for a in msg.attachments if isinstance(a, Attachment)]
    names += [_named_link(f.file_name, link("file", f.file_name, None))
              for f in msg.files if isinstance(f, FileRef) and f.file_name]
    if names:
        parts.append("*" + tr("md.attachments", names=", ".join(names)) + "*")
    for block in msg.content:
        if isinstance(block, TextContent) and block.text.strip():
            user = as_typed and msg.sender == "human"
            text = typed(block.text) if user else block.text.strip()
            parts.append(highlight(text, marks, user, odt) if marks else text)
        elif isinstance(block, ToolUseContent) and block.is_artifact:
            art = _artifact(block, tr)
            if art:
                parts.append(art)
    parts += [_created(p, tr, link("created", p.name, p.text if p.complete else None)) for p in files or []]
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


TEXT_Q = "CEVTEXTSEPQ"  # before your message in the .txt export: a line "====="
TEXT_A = "CEVTEXTSEPA"  # before Claude's: a line "-----"


def conversation_markdown(
    title: str,
    created: datetime | None,
    items: list[tree.Item],
    to_message: Any,
    deleted_since: str = "",
    frame_levels: int = 1,
    versions: bool = True,
    tr: Translator = i18n.t,
    files: dict[str, list[created.Presented]] | None = None,
    for_text: bool = False,
    links: Linker | None = None,
    notes: dict[str, str] | None = None,
    titles: dict[str, str] | None = None,
    marks: dict[str, list[str]] | None = None,
    odt: bool = False,
    kept: dict[str, str] | None = None,
) -> str:
    """``frame_levels``: quote levels per frame (2 doubles the indent in Writer and Word).

    ``for_text``: for the .txt export (office_export): speakers not in bold, each message preceded
    by a marker paragraph (TEXT_Q before yours, TEXT_A before Claude's) that becomes a line of
    separation once the text is out of Pandoc, instead of the horizontal rules.

    ``deleted_since``: ISO date of the export the conversation is missing from.
    ``versions=False`` keeps only the main thread: other versions and parts deleted
    on claude.ai are left out (and the header says so when there were any; without
    any, the text is exactly the same as with ``versions=True``).

    ``files``: created.reconstruct of the conversation (the files Claude handed over).

    ``notes`` (message uuid -> note) and ``marks`` (message uuid -> highlighted passages): the
    annotations, when the export includes them, a note under its message; ``titles`` (message uuid ->
    title of the plan view): above its message, with the notes; ``odt``: highlighting
    for an .odt.

    ``kept``: the messages already written by another call with the same ``items`` and arguments
    (except ``versions``), filled by this one: the page writes both versions without doing it twice.
    """
    main = tree.main_path(items)
    in_main = {id(x) for x in main}

    def render_item(item: tree.Item) -> str:
        if kept is None:
            return write_item(item)
        if item.key not in kept:
            kept[item.key] = write_item(item)
        return kept[item.key]

    def write_item(item: tree.Item) -> str:
        msg = to_message(item.payload)
        if msg is None:
            return ""
        body = message_body(msg, tr, (files or {}).get(item.key), links=links,
                            marks=(marks or {}).get(item.key), odt=odt)
        if notes and item.key in notes:  # the note of the message, under it
            body += "\n\n" + _quote("**" + tr("md.note") + "**\\\n" + typed(notes[item.key]))
        if titles and item.key in titles and body:  # the title of the message, above it
            body = _quote("**" + tr("md.title") + "** " + typed(titles[item.key])) + "\n\n" + body
        if not body:
            return ""
        # Inside a frame, speakers are in italics too, to tell them from the main thread.
        stars = "" if for_text else "**" if id(item) in in_main else "***"
        head = f"{stars}{_speaker(msg, tr)}{stars}"
        if msg.created_at:
            head += " — " + tr("md.when", date=msg.created_at)
        if for_text:
            return f"{TEXT_Q if msg.sender == 'human' else TEXT_A}\n\n{head}\n\n{body}"
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
    if for_text:
        return "\n".join(lines) + "\n" + "\n\n".join(p for p in pieces if p) + "\n"
    body = "\n\n---\n\n".join(p for p in pieces if p)
    return "\n".join(lines) + "\n---\n\n" + body + "\n"


def message_markdown(
    title: str,
    created: datetime | None,
    msg: ChatMessage,
    tr: Translator = i18n.t,
    files: list[created.Presented] | None = None,
    for_text: bool = False,
    links: Linker | None = None,
    note: str | None = None,
    mtitle: str | None = None,
    marks: list[str] | None = None,
    odt: bool = False,
) -> str:
    """Markdown of ONE message (PT-m1, 08/11): the title of the conversation, then the message as in
    :func:`conversation_markdown` (its title and note when the annotations are included)."""
    body = message_body(msg, tr, files, links=links, marks=marks, odt=odt)
    if note:
        body += "\n\n" + _quote("**" + tr("md.note") + "**\\\n" + typed(note))
    if mtitle and body:
        body = _quote("**" + tr("md.title") + "** " + typed(mtitle)) + "\n\n" + body
    stars = "" if for_text else "**"
    head = f"{stars}{_speaker(msg, tr)}{stars}"
    if msg.created_at:
        head += " — " + tr("md.when", date=msg.created_at)
    meta = []
    if created:
        meta.append(tr("md.conversation_of", date=created))
    meta.append(tr("md.exported") + tr("md.one_message"))
    top = f"# {title or tr('web.untitled')}\n\n*" + " · ".join(meta) + "*\n"
    if for_text:
        return f"{top}\n{TEXT_Q if msg.sender == 'human' else TEXT_A}\n\n{head}\n\n{body}\n"
    return f"{top}\n---\n\n{head}\n\n{body}\n"


def message_suffix(when: datetime | None, lang: str | None = None) -> str:
    """" (message 2026-11-08 14h03)": what the file name of one message adds (the browser makes the same)."""
    stamp = when.astimezone().strftime("%Y-%m-%d %Hh%M") if when and when.tzinfo else (
        when.strftime("%Y-%m-%d %Hh%M") if when else "")
    return re.sub(r"\s+([)）])", r"\1", i18n.t("md.message_suffix", lang, when=stamp))  # no date: " (message)"


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
