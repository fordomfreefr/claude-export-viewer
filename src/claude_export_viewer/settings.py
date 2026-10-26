"""Settings kept with the archive (archive/settings.json): the downloads folder.

The import button and the guided download look for the manifest and the ZIP
files in the downloads folder of the system. A browser may save them elsewhere
(its own "save files to" setting): that folder can be set here, from the index
page or with --telechargements, and is then searched first.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import fetch

FILE = "settings.json"


def _path(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FILE


def load(site_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads(_path(site_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(site_dir: Path, data: dict[str, Any]) -> None:
    path = _path(site_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def downloads_folder(site_dir: Path) -> Path | None:
    """The folder set by the user, if any and if it still exists."""
    value = load(site_dir).get("downloads")
    if not value or not isinstance(value, str):
        return None
    folder = Path(value)
    return folder if folder.is_dir() else None


def set_downloads_folder(site_dir: Path, value: str) -> Path | None:
    """Remember the downloads folder ("" goes back to the folder of the system).

    Raises ValueError if the folder does not exist.
    """
    data = load(site_dir)
    value = (value or "").strip()
    if not value:
        data.pop("downloads", None)
        save(site_dir, data)
        return None
    folder = Path(value).expanduser()
    if not folder.is_dir():
        raise ValueError(value)
    folder = folder.resolve()
    data["downloads"] = str(folder)
    save(site_dir, data)
    return folder


def search_folders(site_dir: Path) -> list[Path]:
    """Where to look for a manifest: the folder set by the user first, then the system's."""
    out: list[Path] = []
    for folder in [downloads_folder(site_dir), *fetch.user_download_dirs()]:
        if folder is not None and all(folder.resolve() != f.resolve() for f in out):
            out.append(folder)
    return out or [Path.home()]


def file_folders(site_dir: Path) -> list[Path]:
    """Where the files of the conversations are looked for (default: the downloads folders)."""
    value = load(site_dir).get("file_folders")
    if not isinstance(value, list):
        return [f for f in search_folders(site_dir) if f != Path.home()] or search_folders(site_dir)
    return [Path(v) for v in value if isinstance(v, str) and v]


def file_folders_set(site_dir: Path) -> bool:
    """True when the user chose the folders (False: the default is used)."""
    return isinstance(load(site_dir).get("file_folders"), list)


def set_file_folders(site_dir: Path, values: list[str] | None) -> list[Path]:
    """Remember the folders (None goes back to the default). Raises ValueError(folder) for a missing one."""
    data = load(site_dir)
    if values is None:
        data.pop("file_folders", None)
        save(site_dir, data)
        return file_folders(site_dir)
    out: list[Path] = []
    for value in values:
        value = (value or "").strip()
        if not value:
            continue
        folder = Path(value).expanduser()
        if not folder.is_dir():
            raise ValueError(value)
        folder = folder.resolve()
        if folder not in out:
            out.append(folder)
    data["file_folders"] = [str(f) for f in out]
    save(site_dir, data)
    return out
