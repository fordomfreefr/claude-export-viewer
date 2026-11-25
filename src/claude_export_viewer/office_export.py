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

from . import created, i18n, system, tree
from .markdown_export import (ODT_OFF, ODT_ON, TEXT_A, TEXT_Q, conversation_markdown, export_filename, main_filename,
                              message_markdown, message_suffix)
from .models import Conversation, parse_message

FORMATS = {"md": "markdown", "odt": "odt", "docx": "docx", "txt": "plain"}
PANDOC_INPUT = "markdown+tex_math_dollars+tex_math_single_backslash"
# "==passage==": highlighted, only when the export has highlighted passages (else "a == b == c"
# written by Claude would be)
MARKED_INPUT = PANDOC_INPUT + "+mark"
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


def run_pandoc(markdown: str, fmt: str, extra: tuple[str, ...] = (), marked: bool = False) -> tuple[bytes, list[str]]:
    exe = pandoc_path()
    if exe is None:
        raise PandocMissing(i18n.t("office.no_pandoc", install=system.pandoc_hint()))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"conversation.{fmt}"
        try:
            proc = subprocess.run(
                [exe, "-f", MARKED_INPUT if marked else PANDOC_INPUT, "-t", FORMATS[fmt], *extra, "-o", str(out)],
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


def annotations_of(site_dir: Path, uuid: str) -> dict[str, Any]:
    """The notes, titles and highlighted passages of a conversation, as the export takes them."""
    from . import annotations
    data = annotations.load(site_dir)
    return {"notes": {m: e["text"] for m, e in data["notes"].get(uuid, {}).items()},
            "titles": {m: e["text"] for m, e in data["titles"].get(uuid, {}).items()},
            "marks": {m: [x["q"] for x in v] for m, v in data["marks"].get(uuid, {}).items()}}


def archived_markdown(archive: Any, uuid: str, frame_levels: int = 1, versions: bool = True,
                      lang: str | None = None, for_text: bool = False, links: Any = None,
                      annot: dict[str, Any] | None = None, odt: bool = False,
                      message: str | None = None, part: int | None = None) -> tuple[str, str]:
    """Markdown of an archived conversation (labels in ``lang``) and its file name (without extension).

    ``versions=False``: main thread only (file name ending with " (main thread)", translated).
    ``message``: that message only (its uuid; KeyError when the conversation does not hold it).
    A very long conversation (shown in parts, html_builder.plan_of) is exported one part at a time, never whole in
    memory: ``part`` (from 0; the first when not given), or the part holding ``message``; the file name says it.
    """
    from . import html_builder
    parts = html_builder.plan_of(archive, uuid)
    if parts is None:
        return markdown_of_raw(archive, uuid, archive.load_raw(uuid), None, "", frame_levels, versions, lang,
                               for_text, links, annot, odt, message)
    n = len(parts.plan.ranges)
    wanted = parts.plan.part_of.get(message, 0) if message is not None else (
        part if isinstance(part, int) and 0 <= part < n else 0)
    chunks = html_builder.iter_part_raws(archive, uuid, parts)
    try:
        for k, raw, leaf in chunks:
            if k == wanted:
                return markdown_of_raw(archive, uuid, raw, leaf, part_suffix(k, n, lang), frame_levels, versions,
                                       lang, for_text, links, annot, odt, message)
    finally:
        chunks.close()  # its temporary files removed
    raise KeyError(message or uuid)


def part_suffix(k: int, n: int, lang: str | None = None) -> str:
    """" (partie 3 sur 12)": the end of the file name of a part of a very long conversation."""
    return " " + i18n.t("export.part_suffix", lang, k=k + 1, n=n)


def markdown_of_raw(archive: Any, uuid: str, raw: dict[str, Any], leaf: str | None, suffix: str,
                    frame_levels: int = 1, versions: bool = True, lang: str | None = None, for_text: bool = False,
                    links: Any = None, annot: dict[str, Any] | None = None, odt: bool = False,
                    message: str | None = None) -> tuple[str, str]:
    """archived_markdown of ``raw`` (the conversation, or one part of it whose main branch ends at ``leaf``)."""
    convo = Conversation.model_validate({**raw, "chat_messages": []})
    items = tree.items_from_raw(raw)
    if leaf is not None:
        last = next((i for i in items if i.key == leaf), None)
        if last is not None:
            last.forced = True
    if message is not None:
        item = next((i for i in items if i.key == message), None)
        msg = parse_message(item.payload) if item is not None else None
        if msg is None:
            raise KeyError(message)
        a = annot or {}
        md = message_markdown(convo.name, convo.created_at, msg, tr=lambda key, **args: i18n.t(key, lang, **args),
                              files=created.reconstruct(raw).get(message), for_text=for_text, links=links,
                              note=(a.get("notes") or {}).get(message), mtitle=(a.get("titles") or {}).get(message),
                              marks=(a.get("marks") or {}).get(message), odt=odt)
        name = export_filename(convo.name, convo.created_at, lang).removesuffix(".md")
        return md, name + message_suffix(msg.created_at, lang)
    info = archive.display_info(archive.conversations[uuid])
    md = conversation_markdown(convo.name + suffix, convo.created_at, items, parse_message,
                               info["deleted_since"], frame_levels, versions,
                               tr=lambda key, **args: i18n.t(key, lang, **args), files=created.reconstruct(raw),
                               for_text=for_text, links=links, notes=(annot or {}).get("notes"),
                               titles=(annot or {}).get("titles"), marks=(annot or {}).get("marks"), odt=odt)
    name = export_filename(convo.name, convo.created_at, lang)
    return md, (name if versions else main_filename(name, lang)).removesuffix(".md") + suffix


def convert_archived(archive: Any, uuid: str, fmt: str, versions: bool = True, lang: str | None = None,
                     links: Any = None, annot: dict[str, Any] | None = None, message: str | None = None,
                     part: int | None = None) -> Converted:
    """``links``: the names of the files become links (the ZIP of an export, zipexport.Bundle);
    ``annot``: your notes and highlighted passages, included (annotations_of)."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    md, base = archived_markdown(archive, uuid, 1 if fmt in ("md", "txt") else OFFICE_FRAME_LEVELS, versions, lang,
                                 for_text=fmt == "txt", links=links, annot=annot, odt=fmt == "odt", message=message,
                                 part=part)
    if fmt == "md":
        return Converted(md.encode("utf-8"), base + ".md", [])
    if fmt == "txt":
        data, warnings = run_pandoc(prepare_for_pandoc(md, lang), fmt, ("--wrap=none",), marked=bool(annot and annot.get("marks")))
        return Converted(separate(data.decode("utf-8")).encode("utf-8"), f"{base}.txt", warnings)
    data, warnings = run_pandoc(prepare_for_pandoc(md, lang), fmt, marked=bool(annot and annot.get("marks")))
    if fmt == "odt" and annot and annot.get("marks"):
        data = odt_highlights(data)
    return Converted(data, f"{base}.{fmt}", warnings)


_HL_STYLE = ('<style:style style:name="CEV_Surligne" style:family="text">'
             '<style:text-properties fo:background-color="#ffe94d"/></style:style>')


def odt_highlights(data: bytes) -> bytes:
    """The marks of the highlighted passages (markdown_export.ODT_ON / ODT_OFF) of an .odt made
    yellow spans; if the result were not valid XML, only the marks are taken off."""
    import io
    import zipfile
    from xml.dom import minidom
    src = zipfile.ZipFile(io.BytesIO(data))
    content = src.read("content.xml").decode("utf-8")
    if ODT_ON not in content:
        return data
    new = content.replace(ODT_ON, '<text:span text:style-name="CEV_Surligne">').replace(ODT_OFF, "</text:span>")
    new = new.replace("<office:automatic-styles>", "<office:automatic-styles>" + _HL_STYLE, 1)
    new = new.replace("<office:automatic-styles/>", "<office:automatic-styles>" + _HL_STYLE + "</office:automatic-styles>", 1)
    try:
        minidom.parseString(new.encode("utf-8"))
    except Exception:  # noqa: BLE001 - a passage over a formatting: plain text rather than a broken file
        new = content.replace(ODT_ON, "").replace(ODT_OFF, "")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            body = new.encode("utf-8") if info.filename == "content.xml" else src.read(info.filename)
            z.writestr(info, body, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED)
    return out.getvalue()


_MARK = re.compile(r"^([ \t]*)(" + TEXT_Q + "|" + TEXT_A + r")[ \t]*$", re.M)


_LEAD_NBSP = re.compile("^([ \t]*)(\u00a0+)", re.M)


def separate(text: str) -> str:
    """The markers of the .txt export (markdown_export.TEXT_Q / TEXT_A) as lines of separation:
    "=====" before each of your messages (between two blocks question / answer), "-----" between a
    question and its answer; inside a frame of other versions, with the indent of the frame."""
    text = _MARK.sub(lambda m: m.group(1) + ("=" if m.group(2) == TEXT_Q else "-") * 40, text)
    # the non-breaking spaces that kept the indent and the empty lines of your text: plain spaces
    return _LEAD_NBSP.sub(lambda m: m.group(1) + " " * len(m.group(2)), text)


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

