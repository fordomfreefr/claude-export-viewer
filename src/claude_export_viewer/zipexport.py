"""The export of a conversation put in a dated ZIP, to send it (by e-mail…): "Titre_AAAA-MM-JJ.zip"
holding the exported file (.md, .odt, .docx or .txt) and, in a folder "fichiers/", the files it
names: the documents joined to the messages (the copy of the file associated on the computer, else
the text the export holds) and the files made by Claude (their content, else the copy associated).
Their names in the export become relative links "fichiers/<nom>", still valid once the ZIP is
unpacked; two files of the same name get a number.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from . import i18n, office_export, userfiles
from .attachments import TEXT_EXTENSIONS


class Bundle:
    """The files joined to an export, and the link of each (markdown_export.Linker)."""

    def __init__(self, site_dir: Path, uuid: str, folder: str) -> None:
        self.site_dir = Path(site_dir)
        self.assoc = userfiles.load(site_dir)["assoc"].get(uuid, {})
        self.folder = folder
        self.files: dict[str, bytes | Path] = {}  # name in the folder -> content or file
        self._seen: dict[tuple[Any, ...], str] = {}

    def _name(self, name: str) -> str:
        clean = userfiles.safe_name(name) or "fichier"
        stem, dot, ext = clean.rpartition(".")
        if not dot:
            stem, ext = clean, ""
        candidate, n = clean, 1
        while candidate.lower() in (k.lower() for k in self.files):
            n += 1
            candidate = f"{stem} ({n}).{ext}" if ext else f"{stem} ({n})"
        return candidate

    def __call__(self, msg: str, kind: str, name: str, rank: int, text: str | None) -> str | None:
        entry = self.assoc.get(userfiles.view_key(msg, kind, name, rank)) or {}
        copy = self.site_dir / entry["copy"] if entry.get("copy") else None
        content: bytes | Path | None = None
        if copy is not None and copy.is_file():
            content = copy  # the user's own file (or the copy chosen for a file of Claude)
        elif text is not None:
            ext = name.rpartition(".")[2].lower() if "." in name else ""
            if kind == "attachment" and ext not in TEXT_EXTENSIONS:
                name += ".txt"  # a document of which the export only holds the text
            content = text.encode("utf-8")
        if content is None:
            return None
        key = (str(content),) if isinstance(content, Path) else (name, content)
        if key not in self._seen:  # the same file named twice: one copy
            stored = self._name(name)
            self.files[stored] = content
            self._seen[key] = stored
        return f"{self.folder}/{self._seen[key]}"


def zip_name(title: str, lang: str | None = None, today: date | None = None) -> str:
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or i18n.t("web.untitled", lang))
    clean = re.sub(r"\s+", " ", clean).strip(" .")[:80] or "conversation"
    return f"{clean}_{(today or date.today()).isoformat()}.zip"


def build(archive: Any, site_dir: Path, uuid: str, fmt: str, versions: bool = True,
          lang: str | None = None, annot: bool = False, part: int | None = None) -> tuple[bytes, str, list[str]]:
    """The ZIP (its bytes, its name, the warnings of Pandoc)."""
    folder = i18n.t("zip.folder", lang)
    bundle = Bundle(site_dir, uuid, folder)
    result = office_export.convert_archived(archive, uuid, fmt, versions, lang, links=bundle,
                                            annot=office_export.annotations_of(site_dir, uuid) if annot else None,
                                            part=part)
    title = (archive.conversations.get(uuid) or {}).get("name") or ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(result.filename, result.data)
        for name, content in bundle.files.items():
            arc = f"{folder}/{name}"
            if isinstance(content, Path):
                z.write(content, arc)
            else:
                z.writestr(arc, content)
    return buf.getvalue(), zip_name(title, lang), result.warnings


def write(data: bytes, folder: Path, name: str) -> Path:
    """Write the ZIP in the folder chosen; an existing file of that name is kept (a number is added)."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(str(folder))
    out = folder / name
    n = 1
    while out.exists():
        n += 1
        out = folder / f"{name[:-4]} ({n}).zip"
    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(out)
    return out
