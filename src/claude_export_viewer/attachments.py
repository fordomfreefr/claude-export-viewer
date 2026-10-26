"""Text of the documents joined to the messages, saved as files in the site folder.

The export holds only the text extracted from a joined document, not the file.
Each text is written to ``attachments/<conversation>/<name>``, so that it can be
opened with the program of the computer (local server) or downloaded. The
original extension is kept for text formats; other documents (.pdf, .docx…)
get ``.txt`` added, since only their text is available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

FOLDER = "attachments"
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
    found: dict[str, dict] = field(default_factory=dict)  # the user's files found on the computer (userfiles)


_ctx: Context | None = None


def begin(site_dir: Path, key: str, found: dict[str, dict] | None = None) -> None:
    """Called before rendering a conversation page."""
    global _ctx
    _ctx = Context(Path(site_dir).resolve(), key, found=found or {})


def found(name: str) -> dict | None:
    """The user's copy of a file of this conversation, if found on the computer."""
    return _ctx.found.get(name) if _ctx is not None and name else None


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
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .") or "document"
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
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
    return Saved(f"../{FOLDER}/{quote(_ctx.key)}/{quote(candidate)}", path, text_only)


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
