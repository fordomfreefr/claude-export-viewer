"""Backup of the whole site folder in one dated ZIP (button "Sauvegarder" of the index, or
``--sauvegarder``): the archive, the user's additions (topics, favorites…) and the pages, so
that the ZIP, unpacked anywhere, opens at once (index.html) and can replace the folder.

The ZIP goes to the downloads folder chosen on the index, else the system's, never inside
the site folder (each backup would hold the previous ones). It is written under a temporary
name and renamed at the end: a ZIP with the final name is always complete. Files already
compressed (.zip, .gz…) are stored as they are (compressing them again gains nothing).
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

from . import fetch, settings

PART = ".partiel"
_STORED = {".zip", ".gz", ".woff2", ".woff", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".odt", ".docx"}


class BackupError(Exception):
    """No folder where the backup may go (``key``: i18n key)."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _inside(path: Path, folder: Path) -> bool:
    path, folder = path.resolve(), folder.resolve()
    return path == folder or folder in path.parents


def destination(site_dir: Path) -> Path:
    """Where the backup goes: the downloads folder chosen on the index, else the system's
    (the first one not inside the site folder)."""
    for folder in [settings.downloads_folder(site_dir), *fetch.user_download_dirs()]:
        if folder is not None and folder.is_dir() and not _inside(folder, site_dir):
            return folder
    raise BackupError("backup.no_folder")


def site_size(site_dir: Path) -> int:
    """Size in bytes of what a backup holds (the files being dropped left out)."""
    return sum(f.stat().st_size for f in _files(site_dir) if f.is_file())


def last_backup(site_dir: Path) -> float | None:
    """Date (timestamp) of the most recent backup ZIP of this site in the backup folder, if any."""
    try:
        folder = destination(site_dir)
    except BackupError:
        return None
    dates = [f.stat().st_mtime for f in folder.glob(f"{Path(site_dir).resolve().name}-*.zip")
             if f.is_file() and "-markdown-" not in f.name]  # (the Markdown export is no backup)
    return max(dates, default=None)


def _files(site_dir: Path) -> list[Path]:
    out = []
    depot = (Path(site_dir) / "archive" / "depot").resolve()  # files of a drop being received
    opened = (Path(site_dir) / "extras" / "artifacts").resolve()  # versions of artifacts opened: extracted again
    temp = (Path(site_dir) / "archive" / "temporaire").resolve()  # temporary files of an import (archive.TEMP_DIR)
    for root, dirs, files in os.walk(site_dir):
        dirs[:] = sorted(d for d in dirs if (Path(root) / d).resolve() not in (depot, opened, temp))
        for name in sorted(files):
            if name.endswith((".tmp", PART)) or (name == "verrou" and Path(root).name == "archive"):
                continue  # a file being written; the lock (unreadable on Windows while held)
            out.append(Path(root) / name)
    return out


def make_backup(site_dir: Path, dest: Path | None = None, today: date | None = None,
                say: Callable[[str, dict], None] | None = None) -> Path:
    """Write <dest>/<site folder name>-YYYY-MM-DD.zip (" (2)", " (3)"… if it exists) and return it.
    ``say(key, args)`` reports the steps."""
    site_dir = Path(site_dir).resolve()
    dest = destination(site_dir) if dest is None else Path(dest)
    if _inside(dest, site_dir):
        raise BackupError("backup.no_folder")
    stem = f"{site_dir.name}-{(today or date.today()).isoformat()}"
    target, n = dest / f"{stem}.zip", 1
    while target.exists():
        n += 1
        target = dest / f"{stem} ({n}).zip"
    files = _files(site_dir)
    if say:
        say("backup.start", {"n": len(files), "size": _mb(sum(f.stat().st_size for f in files)), "path": str(target)})
    part = target.with_name(target.name + PART)
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in files:
                try:
                    kind = zipfile.ZIP_STORED if f.suffix.lower() in _STORED else zipfile.ZIP_DEFLATED
                    z.write(f, Path(site_dir.name) / f.relative_to(site_dir), compress_type=kind)
                except FileNotFoundError:
                    continue  # removed meanwhile (a page rewritten)
        os.replace(part, target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if say:
        say("backup.done", {"path": str(target), "size": _mb(target.stat().st_size)})
    return target


def _mb(size: int) -> str:
    return f"{size / 1e6:.1f}"
