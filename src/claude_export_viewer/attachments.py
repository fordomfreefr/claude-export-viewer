"""Text of the documents joined to the messages, saved as files in the site folder.

The export holds only the text extracted from a joined document, not the file.
Each text is written to ``attachments/<conversation>/<name>``, so that it can be
opened with the program of the computer (local server) or downloaded. The
original extension is kept for text formats; other documents (.pdf, .docx…)
get ``.txt`` added, since only their text is available.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

FOLDER = "attachments"
CREATED = "_claude"  # files/<conversation>/_claude/<content>/<name>: files created by Claude (created.py)
LONG = 3000  # characters: beyond, the page warns before showing the text

TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "rst", "csv", "tsv", "json", "jsonl", "xml", "yaml", "yml", "toml", "ini", "cfg",
    "log", "tex", "bib", "py", "js", "ts", "html", "htm", "css", "c", "h", "cpp", "hpp", "java", "rs", "go",
    "rb", "php", "sh", "bash", "sql", "r", "m", "jl", "kt", "swift", "pl", "lua", "bas", "vb", "srt",
}


@dataclass
class Saved:
    href: str  # relative to a conversation page
    path: Path  # absolute
    text_only: bool  # the original was not a text file: only its text is kept


@dataclass
class Context:
    site_dir: Path
    key: str  # conversation page name without .html
    used: set[str] = field(default_factory=set)
    injected: set[tuple[str, str]] = field(default_factory=set)
    links: dict[str, dict] = field(default_factory=dict)  # link id -> what the page shows of it (userfiles.views)
    created: set[str] = field(default_factory=set)  # copies written for the files created by Claude


_ctx: Context | None = None


def begin(site_dir: Path, key: str) -> None:
    """Called before rendering a conversation page."""
    global _ctx
    _ctx = Context(Path(site_dir).resolve(), key)


def set_links(links: dict[str, dict]) -> None:
    """The links of the conversation and their association (userfiles.views)."""
    if _ctx is not None:
        _ctx.links = links


def site_file(rel: str) -> Path | None:
    """A file of the site folder (a copy of a link), during a page rendering."""
    return _ctx.site_dir / rel if _ctx is not None else None


def link(link_id: str) -> dict | None:
    """What the page shows of a link (None outside a page rendering)."""
    return _ctx.links.get(link_id) if _ctx is not None else None


def created_copies() -> list[str]:
    """The copies written for the files created by Claude during this rendering."""
    return sorted(_ctx.created) if _ctx is not None else []


def end() -> None:
    global _ctx
    _ctx = None


def first_injected(source: str, text: str) -> bool:
    """False for a block of instructions identical to one already shown on the page."""
    if _ctx is None:
        return True
    if (source, text) in _ctx.injected:
        return False
    _ctx.injected.add((source, text))
    return True


def _file_name(name: str) -> tuple[str, bool]:
    from .userfiles import short_name
    clean = short_name(re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .") or "document")
    ext = clean.rpartition(".")[2].lower() if "." in clean else ""
    if ext in TEXT_EXTENSIONS:
        return clean, False
    return clean + ".txt", True


def save(name: str, text: str) -> Saved | None:
    """Write the text (once per name in the conversation); None outside a page rendering."""
    if _ctx is None:
        return None
    file_name, text_only = _file_name(name)
    stem, dot, ext = file_name.rpartition(".")
    candidate, n = file_name, 1
    while candidate.lower() in _ctx.used:  # same name twice in one conversation
        n += 1
        candidate = f"{stem} ({n}).{ext}" if dot else f"{file_name} ({n})"
    _ctx.used.add(candidate.lower())
    path = _ctx.site_dir / FOLDER / _ctx.key / candidate
    data = text.encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
    except OSError:  # (review of 21/11) one file that cannot be written: shown without its file, the page made all the same
        return None
    return Saved(f"../{FOLDER}/{quote(_ctx.key)}/{quote(candidate)}", path, text_only)


def save_created(name: str, text: str) -> str | None:
    """Write a file created by Claude into the site, once per content (several versions of a name
    keep apart, the same content handed over twice is written once); its path from the site folder,
    or None outside a page rendering."""
    if _ctx is None:
        return None
    from .userfiles import FOLDER as FILES, safe_name
    data = text.encode("utf-8")
    rel = f"{FILES}/{_ctx.key}/{CREATED}/{hashlib.sha256(data).hexdigest()[:12]}/{safe_name(name)}"
    path = _ctx.site_dir / rel
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
    except OSError:  # (review of 21/11) as in save()
        return None
    _ctx.created.add(rel)
    return rel


def resolve(site_dir: Path, relative: str) -> Path | None:
    """The file named by a page (``attachments/…`` or ``files/…``), only if it is inside those folders."""
    bases = [(Path(site_dir) / folder).resolve() for folder in (FOLDER, "files")]
    try:
        path = (Path(site_dir) / relative).resolve()
    except (OSError, ValueError):
        return None
    if not any(base in path.parents for base in bases) or not path.is_file():
        return None
    return path
