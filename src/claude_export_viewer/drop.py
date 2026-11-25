"""Files dropped on the index (manifest and/or export ZIPs), received by the local server.

1. The page sends each file in pieces (POST /__cev__/upload): they are written in
   ``archive/depot/<id>/`` under a temporary name, renamed when complete, with the date of the
   original file (so that "a ZIP older than the manifest belongs to an earlier export" still
   holds).
2. POST /__cev__/import-dropped starts the job (one job at a time: never during an import or a
   backup), which checks what was dropped, stores it in ``archive/exports/`` and runs the
   usual import:
   - a manifest (with or without ZIPs): everything goes into the folder of that export, where
     the guided download looks first; ZIPs the manifest does not list are left out;
   - ZIPs without manifest: one export, dated from the data; the same name twice ("x.zip" and
     "x (1).zip") means two exports mixed: refused, one export at a time;
   - two manifests: refused; anything else (not a ZIP, not a manifest): left out.
The staging folder is removed at the end, and when the server starts (an interrupted drop).
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from . import fetch

DEPOT = "depot"
PART = ".partiel"
MAX_FILES = 30
MAX_SIZE = 8 * 1024**3  # bytes per file
RESERVE = 512 * 1024**2  # bytes always left free on the disk (review of 21/11, B5): the import needs room after it
_ID = re.compile(r"[a-z0-9]{8,32}")
_NAME = re.compile(r"[\w .,()+\-]{1,150}\.(?:zip|json)", re.IGNORECASE)
_COPY = re.compile(r" ?\(\d+\)(?=\.[^.]+$)")  # "x (1).zip" -> "x.zip"


class DropError(ValueError):
    """A refused piece or drop; ``key`` is the i18n key of the message (with ``params``)."""

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.key, self.params = key, params


def depot_dir(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / DEPOT


def staging(site_dir: Path, drop_id: str) -> Path:
    if not isinstance(drop_id, str) or not _ID.fullmatch(drop_id):
        raise DropError("drop.bad_request")
    return depot_dir(site_dir) / drop_id


def clean_all(site_dir: Path) -> None:
    """Remove every staging folder (at server start: drops interrupted earlier)."""
    shutil.rmtree(depot_dir(site_dir), ignore_errors=True)


def _free(folder: Path) -> int:
    """Free bytes on the disk of ``folder`` (or of its first existing parent)."""
    folder = Path(folder).resolve()
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    return shutil.disk_usage(folder).free


def receive(site_dir: Path, drop_id: str, name: str, offset: int, chunk, length: int,
            last: bool, mtime: float | None) -> int:
    """Append ``length`` bytes read from ``chunk`` (a file object) at ``offset`` of the file
    being received; when ``last``, the file is complete. Returns its size so far."""
    folder = staging(site_dir, drop_id)
    name = name or ""
    if "/" in name or "\\" in name or not _NAME.fullmatch(name):  # a bare file name only
        raise DropError("drop.bad_name", name=name)
    if folder.is_dir() and name not in {p.name.removesuffix(PART) for p in folder.iterdir()} \
            and len(list(folder.iterdir())) >= MAX_FILES:
        raise DropError("drop.too_many", n=MAX_FILES)
    part = folder / (name + PART)
    have = part.stat().st_size if part.exists() else 0
    if offset == 0 and have:  # sent again from the start
        part.unlink()
        have = 0
    if offset != have:
        raise DropError("drop.bad_offset")
    if have + length > MAX_SIZE:
        raise DropError("drop.too_big", name=name)
    if length and _free(site_dir) < length + RESERVE:  # a full disk: refused before, not cut in the middle
        part.unlink(missing_ok=True)
        raise DropError("drop.no_space", name=name, reserve=RESERVE // 1024**2)
    folder.mkdir(parents=True, exist_ok=True)
    with part.open("ab") as f:
        left = length
        while left:
            data = chunk.read(min(left, 1 << 20))
            if not data:
                raise DropError("drop.bad_request")
            f.write(data)
            left -= len(data)
    size = have + length
    if last:
        final = folder / name
        os.replace(part, final)
        if mtime:
            os.utime(final, (mtime, mtime))
    return size


def _is_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            z.namelist()
        return True
    except (OSError, zipfile.BadZipFile):
        return False


def _store(files: list[Path], folder: Path) -> list[Path]:
    """Move the files into ``folder`` (a file of the same name is replaced: the dropped one is
    what the user wants); their dates are kept."""
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        target = folder / f.name
        os.replace(f, target)
        out.append(target)
    return out


def plan(site_dir: Path, drop_id: str, say) -> list[str] | None:
    """Check the dropped files and store them in the archive; returns the arguments of the
    import to run (before ``-o``), or None when there is nothing to import. ``say(key, **args)``."""
    folder = staging(site_dir, drop_id)
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.endswith(PART)) if folder.is_dir() else []
    manifests, zips = [], []
    for f in files:
        m = fetch.read_manifest(f) if f.suffix.lower() == ".json" else None
        if m is not None:
            manifests.append((f, m))
            say("drop.manifest", name=f.name)
        elif f.suffix.lower() == ".zip" and _is_zip(f):
            zips.append(f)
            say("drop.zip", name=f.name)
        else:
            say("drop.not_export", name=f.name)
    if len(manifests) > 1:
        say("drop.two_manifests")
        return None
    if manifests:
        path, manifest = manifests[0]
        export_dir = Path(site_dir) / "archive" / "exports" / manifest.folder_name
        patterns = [fetch._name_pattern(mf.filename) for mf in manifest.files]
        listed = [z for z in zips if any(p.match(z.name) for p in patterns)]
        for z in zips:
            if z not in listed:
                say("drop.not_in_manifest", name=z.name)
        stored = _store([path, *listed], export_dir)
        return [str(stored[0])]
    if not zips:
        say("drop.nothing")
        return None
    seen: dict[str, str] = {}
    for z in zips:
        base = _COPY.sub("", z.name).lower()
        if base in seen:
            say("drop.mixed", name=seen[base], other=z.name)
            return None
        seen[base] = z.name
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stored = _store(zips, Path(site_dir) / "archive" / "exports" / f"depot-{stamp}")
    return [str(p) for p in stored]
