"""Guided download of a Claude.ai export from its manifest.

The export arrives as a small "manifest" JSON (downloaded from the e-mail
link) listing several ZIP files, each with its own link. Those links only work
in a browser signed in to claude.ai, expire 24 hours after the export is
created and may stop working once used. So this module:

1. picks the most recent manifest in a folder;
2. finds the ZIPs already downloaded (browsers rename duplicates
   "conversations-000 (1).zip"), ignoring files older than the export;
3. opens each missing link in the browser, one at a time, and waits until the
   download is complete before opening the next one;
4. moves the files into ``<site>/archive/exports/<date>/``.

Only links to https://claude.ai/ are ever opened. No credentials are handled:
the download happens in the user's own browser session.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import webbrowser
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import system
from .i18n import t

DEFAULT_CATEGORIES = ("conversations", "projects", "light_metadata")
LINK_LIFETIME = timedelta(hours=24)
_PARTIAL_SUFFIXES = (".crdownload", ".part", ".download", ".partial")


@dataclass
class ManifestFile:
    category: str
    filename: str
    url: str


@dataclass
class Manifest:
    path: Path
    created_at: datetime
    files: list[ManifestFile]

    @property
    def expires_at(self) -> datetime:
        return self.created_at + LINK_LIFETIME

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def folder_name(self) -> str:
        return self.created_at.strftime("%Y-%m-%d_%H%M%S")


def read_manifest(path: Path) -> Manifest | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("data_files"), list):
        return None
    try:
        created = datetime.fromisoformat(str(data.get("created_at")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    files = []
    for f in data["data_files"]:
        if isinstance(f, dict) and f.get("filename") and f.get("export_url"):
            files.append(ManifestFile(str(f.get("category") or ""), Path(str(f["filename"])).name, str(f["export_url"])))
    return Manifest(Path(path), created.astimezone(timezone.utc), files)


def latest_manifest(folder: Path) -> Manifest | None:
    found = [m for m in (read_manifest(p) for p in Path(folder).glob("*manifest*.json")) if m]
    return max(found, key=lambda m: m.created_at) if found else None


def manifest_from_inputs(inputs: list[Path]) -> Manifest | None:
    """Manifest mode: a single folder holding a manifest, or a manifest file."""
    if len(inputs) != 1:
        return None
    p = Path(inputs[0]).expanduser()
    if p.is_dir():
        return latest_manifest(p)
    if p.suffix.lower() == ".json":
        return read_manifest(p)
    return None


_WINDOWS_DOWNLOADS = "{374DE290-123F-4565-9164-39C4925E467B}"  # known folder id of "Downloads"


def _windows_downloads() -> Path | None:
    """Windows: the Downloads folder, wherever the user moved it."""
    return system.windows_shell_folder(_WINDOWS_DOWNLOADS)


def user_download_dirs() -> list[Path]:
    """The user's download folder(s): system setting (XDG on Linux, registry on Windows), then the usual names."""
    folders: list[Path] = []
    if os.name == "nt":
        folder = _windows_downloads()
        if folder:
            folders.append(folder)
    else:
        try:
            out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, encoding="utf-8",
                                 errors="replace", timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                folders.append(Path(out.stdout.strip()))
        except (OSError, subprocess.SubprocessError):
            pass
    # usual names of the folder (xdg-user-dir above normally gives the right one)
    for name in ("Downloads", "Téléchargements", "Descargas", "Scaricati", "Transferências", "Pobrane",
                 "Загрузки", "下载", "ダウンロード", "다운로드"):
        folders.append(Path.home() / name)
    unique: list[Path] = []
    for f in folders:
        if f.is_dir() and f.resolve() != Path.home().resolve() and f.resolve() not in [u.resolve() for u in unique]:
            unique.append(f)
    return unique


def download_folders(manifest: Manifest, extra: Iterable[Path] = ()) -> list[Path]:
    """Where the browser may save the files: the manifest's folder, ``extra`` (the folder set by
    the user) and the user's download folder."""
    unique = [manifest.path.parent]
    for f in [*extra, *user_download_dirs()]:
        if f.resolve() not in [u.resolve() for u in unique]:
            unique.append(f)
    return unique


def _name_pattern(filename: str) -> re.Pattern[str]:
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    # "conversations-000.zip", "conversations-000 (1).zip", "conversations-000(2).zip"
    return re.compile(re.escape(stem) + r"(?: ?\(\d+\))?" + (r"\." + re.escape(ext) if ext else "") + r"$")


def _is_partial(path: Path) -> bool:
    return any(path.with_name(path.name + s).exists() for s in _PARTIAL_SUFFIXES)


def _complete_zip(path: Path) -> bool:
    try:
        if path.stat().st_size == 0 or _is_partial(path):
            return False
        with zipfile.ZipFile(path) as z:
            z.namelist()
        return True
    except (OSError, zipfile.BadZipFile):
        return False


def find_downloaded(mf: ManifestFile, folders: Iterable[Path], not_before: datetime) -> Path | None:
    """Most recent complete copy of ``mf`` downloaded after ``not_before`` (older ones belong to earlier exports)."""
    pattern = _name_pattern(mf.filename)
    limit = not_before.timestamp()
    found = []
    for folder in folders:
        for p in Path(folder).iterdir() if Path(folder).is_dir() else []:
            if p.is_file() and pattern.match(p.name):
                mtime = p.stat().st_mtime
                if mtime >= limit and _complete_zip(p):
                    found.append((mtime, p))
    return max(found)[1] if found else None


def wait_for_download(
    mf: ManifestFile,
    folders: Iterable[Path],
    since: datetime,
    timeout: float,
    poll: float = 1.0,
) -> Path | None:
    """Wait until a complete copy of ``mf`` appears (its size must stay stable between two checks)."""
    folders = list(folders)
    deadline = time.monotonic() + timeout
    last: dict[Path, int] = {}
    while time.monotonic() < deadline:
        path = find_downloaded(mf, folders, since)
        if path is not None:
            size = path.stat().st_size
            if last.get(path) == size:
                return path
            last[path] = size
        time.sleep(poll)
    return None


def safe_link(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and u.hostname == "claude.ai"


def browser_opener(command: str | None) -> Callable[[str], None]:
    if command:
        return lambda url: subprocess.Popen([command, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return lambda url: webbrowser.open(url, new=2)


@dataclass
class FetchResult:
    export_dir: Path
    files: dict[str, list[Path]] = field(default_factory=dict)  # category -> files
    missing: list[str] = field(default_factory=list)
    manifest_copy: Path | None = None


def fetch_export(
    manifest: Manifest,
    site_dir: Path,
    categories: Iterable[str] = DEFAULT_CATEGORIES,
    opener: Callable[[str], None] | None = None,
    folders: list[Path] | None = None,
    timeout: float = 300,
    poll: float = 1.0,
    say: Callable[[str], None] = print,
    manual: bool = False,
) -> FetchResult:
    """Download the wanted files of ``manifest``.

    Automatic mode opens each link in the browser; manual mode only prints it
    (Ctrl + click in most terminals, or copy it into the browser signed in to
    claude.ai). In both modes the link is printed and the download folder is
    watched until the complete file arrives.
    """
    opener = opener or browser_opener(None)
    folders = folders if folders is not None else download_folders(manifest)
    export_dir = Path(site_dir) / "archive" / "exports" / manifest.folder_name
    result = FetchResult(export_dir)
    wanted = [f for f in manifest.files if f.category in set(categories)]
    wanted.sort(key=lambda f: f.category != "conversations")  # the essential one first
    search = [export_dir, *folders]

    total = len(wanted)
    for i, mf in enumerate(wanted, 1):
        head = f"[{i}/{total}] {mf.filename}"
        path = find_downloaded(mf, search, manifest.created_at)
        if path is not None:
            say(t("fetch.already", head=head, name=path.name))
        elif manifest.expired:
            say(t("fetch.expired", head=head))
            result.missing.append(mf.filename)
            continue
        elif not safe_link(mf.url):
            say(t("fetch.refused", head=head))
            result.missing.append(mf.filename)
            continue
        else:
            say(f"\n{head}")
            since = datetime.now(timezone.utc) - timedelta(seconds=2)
            if manual:
                say(t("fetch.open_manually"))
            else:
                opener(mf.url)
                say(t("fetch.opened"))
            say(f"  {mf.url}")
            say(t("fetch.waiting"))
            path = wait_for_download(mf, folders, since, timeout, poll)
            if path is None:
                say(t("fetch.timeout", seconds=f"{timeout:.0f}"))
                result.missing.append(mf.filename)
                continue
            say(t("fetch.received", name=path.name))
        result.files.setdefault(mf.category, []).append(path)

    # Store everything in the archive, under the canonical names.
    export_dir.mkdir(parents=True, exist_ok=True)
    by_name = {mf.filename: mf for mf in wanted}
    for category, paths in result.files.items():
        moved = []
        for p in paths:
            canonical = next((n for n in by_name if _name_pattern(n).match(p.name)), p.name)
            target = export_dir / canonical
            if p.resolve() != target.resolve():
                try:
                    shutil.move(str(p), str(target))
                    p = target
                except OSError as exc:
                    say(t("fetch.cannot_store", name=p.name, error=exc))
            moved.append(p)
        result.files[category] = moved
    manifest_target = export_dir / "manifest.json"
    try:
        if manifest.path.resolve() != manifest_target.resolve():
            shutil.copy2(manifest.path, manifest_target)
            os.remove(manifest.path)
        result.manifest_copy = manifest_target
    except OSError:
        result.manifest_copy = manifest.path
    return result
