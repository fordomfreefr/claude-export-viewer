"""Export of a conversation to LibreOffice (.odt) or Word (.docx), through Pandoc.

The conversion starts from the same Markdown as the "Exporter en .md" button.
Pandoc turns the LaTeX formulas into native equations of the target office
suite. Pandoc is optional: without it, these exports are simply unavailable.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import i18n, system, tree
from .markdown_export import conversation_markdown, export_filename, main_filename
from .models import Conversation, parse_message

FORMATS = {"md": "markdown", "odt": "odt", "docx": "docx"}
PANDOC_INPUT = "markdown+tex_math_dollars+tex_math_single_backslash"
_TEXT_COMMANDS = ("textbf", "textit", "emph", "texttt", "textsf", "textrm", "underline")


class PandocMissing(RuntimeError):
    pass


def pandoc_path() -> str | None:
    return shutil.which("pandoc")


# --- Preparing formulas for Pandoc -------------------------------------------
#
# Pandoc's formula reader rejects text commands nested inside \text{...}, e.g.
#     \text{ a un \textbf{maximum} en }
# KaTeX accepts it. The same display is obtained with
#     \text{ a un }\textbf{maximum}\text{ en }


def _group(s: str, i: int) -> int:
    """Index just after the brace group starting at s[i] == '{' (or -1 if unbalanced)."""
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


_NESTED = re.compile(r"\\(" + "|".join(_TEXT_COMMANDS) + r")\s*\{")


def _split_text_group(content: str) -> str:
    """Rewrite the inside of one \\text{...} group; returns the replacement for the whole group."""
    out: list[str] = []
    pos = 0
    plain_start = 0
    while True:
        m = _NESTED.search(content, pos)
        if not m:
            break
        end = _group(content, m.end() - 1)
        if end < 0:
            break
        if m.start() > plain_start:
            out.append("\\text{" + content[plain_start:m.start()] + "}")
        out.append(content[m.start():end])
        plain_start = pos = end
    if not out:
        return "\\text{" + content + "}"
    if plain_start < len(content):
        out.append("\\text{" + content[plain_start:] + "}")
    return "".join(out)


def _fix_formula_text(segment: str) -> str:
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"\\text\s*\{", segment):
        if m.start() < pos:
            continue
        end = _group(segment, m.end() - 1)
        if end < 0:
            continue
        out.append(segment[pos:m.start()])
        out.append(_split_text_group(segment[m.end():end - 1]))
        pos = end
    out.append(segment[pos:])
    return "".join(out)


# --- Images -------------------------------------------------------------------
#
# Pandoc fetches the target of a Markdown image to embed it in the document:
# "![x](/home/me/file)" in a conversation would put that file of this computer
# into the .docx, and "![x](https://…)" would make a network request. Images
# are therefore turned into plain links before the conversion (the export never
# held the pictures anyway).

_IMAGE = re.compile(r"(?<!\\)!\[")
_INLINE_CODE = re.compile(r"(`+)[^`]*?\1")


def _neutralize_images(text: str, label: str) -> str:
    replace = "[" + label.replace("\\", "\\\\")
    out, pos = [], 0
    for m in _INLINE_CODE.finditer(text):
        out.append(_IMAGE.sub(replace, text[pos:m.start()]))
        out.append(m.group(0))  # code spans are left as they are
        pos = m.end()
    out.append(_IMAGE.sub(replace, text[pos:]))
    return "".join(out)


def prepare_for_pandoc(markdown: str, lang: str | None = None) -> str:
    """Formula fixes and image neutralization ("![x](y)" -> "[Image: x](y)"), outside fenced code blocks."""
    label = i18n.t("office.image", lang, label="")
    parts = re.split(r"(^(?:> ?)*`{3,}.*$[\s\S]*?^(?:> ?)*`{3,}[ \t]*$)", markdown, flags=re.M)
    return "".join(p if i % 2 else _neutralize_images(_fix_formula_text(p), label) for i, p in enumerate(parts))


# --- Conversion --------------------------------------------------------------


@dataclass
class Converted:
    data: bytes
    filename: str
    warnings: list[str]


def run_pandoc(markdown: str, fmt: str) -> tuple[bytes, list[str]]:
    exe = pandoc_path()
    if exe is None:
        raise PandocMissing(i18n.t("office.no_pandoc", install=system.pandoc_hint()))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"conversation.{fmt}"
        try:
            proc = subprocess.run(
                [exe, "-f", PANDOC_INPUT, "-t", FORMATS[fmt], "-o", str(out)],
                input=markdown.encode("utf-8"),
                capture_output=True,
                timeout=300,
                **system.no_window(),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(i18n.t("office.timeout")) from None
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(i18n.t("office.failed", error=proc.stderr.decode("utf-8", "replace").strip()[:500]))
        warnings = [line for line in proc.stderr.decode("utf-8", "replace").splitlines() if "WARNING" in line]
        return out.read_bytes(), warnings


OFFICE_FRAME_LEVELS = 2  # frames indented twice as much in Writer / Word


def archived_markdown(archive: Any, uuid: str, frame_levels: int = 1, versions: bool = True,
                      lang: str | None = None) -> tuple[str, str]:
    """Markdown of an archived conversation (labels in ``lang``) and its file name (without extension).

    ``versions=False``: main thread only (file name ending with " (main thread)", translated).
    """
    raw = archive.load_raw(uuid)
    convo = Conversation.model_validate({**raw, "chat_messages": []})
    info = archive.display_info(archive.conversations[uuid])
    md = conversation_markdown(convo.name, convo.created_at, tree.items_from_raw(raw), parse_message,
                               info["deleted_since"], frame_levels, versions,
                               tr=lambda key, **args: i18n.t(key, lang, **args))
    name = export_filename(convo.name, convo.created_at, lang)
    return md, (name if versions else main_filename(name, lang)).removesuffix(".md")


def convert_archived(archive: Any, uuid: str, fmt: str, versions: bool = True, lang: str | None = None) -> Converted:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    md, base = archived_markdown(archive, uuid, 1 if fmt == "md" else OFFICE_FRAME_LEVELS, versions, lang)
    if fmt == "md":
        return Converted(md.encode("utf-8"), base + ".md", [])
    data, warnings = run_pandoc(prepare_for_pandoc(md, lang), fmt)
    return Converted(data, f"{base}.{fmt}", warnings)


# --- Finding a conversation (command line) -----------------------------------


def find_conversations(archive: Any, query: str) -> list[tuple[str, dict[str, Any]]]:
    """Exact identifier first; otherwise conversations whose title contains the query (case-insensitive)."""
    convs = archive.conversations
    if query in convs:
        return [(query, convs[query])]
    by_file = [(u, m) for u, m in convs.items() if m.get("filename", "").removesuffix(".html") == query]
    if by_file:
        return by_file
    q = query.casefold().strip()
    return [(u, m) for u, m in convs.items() if q and q in (m.get("name") or "").casefold()]

