"""Uninstalling CEV (AF-m1, 14/11): button "Désinstaller…" of the index (server.uninstall_job) and ``--desinstaller``.

First the copies the user ticks, in a dated folder "CEV-sauvegarde-AAAA-MM-JJ" of the downloads (never inside what is
removed): the exports as claude.ai gave them, the ZIP of the whole site (``--restaurer`` puts it back: nothing to
import again), the ZIP of all the conversations in Markdown (readable without CEV), the program in a ZIP (to install
it again without Internet), and a LISEZMOI.txt saying how to install everything again. Then everything CEV wrote is
removed: the site with its archive, the program, the icon (menu, desktop), Piper and its voices, the sounds read
aloud. What the browser keeps for the pages (choices of display) is cleared by the page itself; the other ports
(another launch) are named to the user.

``--restaurer ZIP``: the ZIP of a site (backup.make_backup) unpacked into a site folder holding no archive yet.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__, allexport, backup, codecache, desktop, install, speech, system
from .i18n import t

COPIES = ("exports", "site", "markdown", "program")


class UninstallError(Exception):
    """A copy that failed (nothing is removed then) or a folder refused (``key``: i18n key)."""

    def __init__(self, key: str, **args: Any) -> None:
        super().__init__(key)
        self.key, self.args_ = key, args


def size_of(path: Path) -> int:
    path = Path(path)
    if path.is_file() or path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                continue
    return total


def _inside(path: Path, folder: Path) -> bool:
    path, folder = Path(path).resolve(), Path(folder).resolve()
    return path == folder or folder in path.parents


def program_dir() -> Path:
    """The folder of the program running (the one holding claude-export-viewer.py)."""
    return Path(__file__).resolve().parents[2]


def _icon_files(home: Path) -> list[Path]:
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        roaming = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        menu = roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        desk = system.windows_shell_folder("Desktop") or home / "Desktop"
        names = {desktop._file_name(t("desktop.name", lang)) + ".lnk" for lang in ("fr", "en", "de", "es", "it", "nl",
                                                                                   "pt", "pl", "ru", "ja", "ko", "zh")}
        names |= {"Archives Claude.lnk", "Claude Archives.lnk"}  # the former names (up to 2026.11.14)
        return [local / "claude-export-viewer", *(f / n for f in (menu, desk) for n in sorted(names))]
    files = [home / ".local/share/icons/hicolor/scalable/apps/claude-export-viewer.svg",
             home / ".local/share/applications" / desktop.DESKTOP_NAME]
    folder = desktop._desktop_folder(home)
    if folder:
        files.append(folder / desktop.DESKTOP_NAME)
    return files


def targets(site_dir: Path, program: Path | None = None, home: Path | None = None) -> list[dict[str, Any]]:
    """What will be removed: [{"key", "path", "size"}], only what exists. The program folder only when it is a CEV
    one and holds neither the home folder nor the site."""
    site_dir = Path(site_dir).resolve()
    home = (home or Path.home()).resolve()
    program = (program or program_dir()).resolve()
    out: list[dict[str, Any]] = [{"key": "site", "path": site_dir}]
    if (program / install.LAUNCHER).is_file() and program != home and not _inside(site_dir, program) \
            and not _inside(program, site_dir):
        out.append({"key": "program", "path": program})
    out += [{"key": "icon", "path": p} for p in _icon_files(home)]
    out.append({"key": "piper", "path": speech.folder(site_dir)})
    out.append({"key": "sounds", "path": speech.cache_dir()})
    out.append({"key": "cache", "path": codecache.path()})  # the colours of the code kept (15/11)
    seen, kept = set(), []
    for e in out:
        p = Path(e["path"])
        if (p.exists() or p.is_symlink()) and str(p) not in seen and p.resolve() != home:
            seen.add(str(p))
            kept.append({**e, "path": p, "size": size_of(p)})
    return kept


def copies_dir(site_dir: Path, today: date | None = None) -> Path:
    """Where the copies go by default: a dated folder in the downloads (the one of the backups)."""
    return backup.destination(site_dir) / f"CEV-sauvegarde-{(today or date.today()).isoformat()}"


def copy_sizes(site_dir: Path, program: Path | None = None) -> dict[str, int]:
    """The size of what each copy takes (before compression): exports, site, program; markdown: the conversations."""
    site_dir = Path(site_dir).resolve()
    program = (program or program_dir()).resolve()
    return {"exports": size_of(site_dir / "archive" / "exports"), "site": backup.site_size(site_dir),
            "markdown": size_of(site_dir / "archive" / "conversations"),
            "program": size_of(program) if (program / install.LAUNCHER).is_file() else 0}


def check_dest(dest: Path, site_dir: Path, program: Path | None = None) -> Path:
    """The folder of the copies, refused inside what is removed."""
    dest = Path(dest).expanduser()
    if not dest.is_absolute():
        raise UninstallError("uninstall.dest_relative", path=str(dest))
    for e in targets(site_dir, program):
        if _inside(dest, e["path"]):
            raise UninstallError("uninstall.dest_inside", path=str(dest), removed=str(e["path"]))
    return dest


def _zip_program(program: Path, dest: Path) -> Path:
    """The program in a ZIP laid out as the one given out (a folder claude-export-viewer/): --installer from it."""
    target = dest / f"claude-export-viewer-{__version__}.zip"
    part = target.with_name(target.name + backup.PART)
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(program):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".ruff_cache", ".git"))
            for name in sorted(files):
                if not name.endswith(".pyc"):
                    f = Path(root) / name
                    z.write(f, Path("claude-export-viewer") / f.relative_to(program))
    os.replace(part, target)
    return target


def make_copies(archive: Any, site_dir: Path, dest: Path, what: list[str], say: Callable[[str, dict], None],
                program: Path | None = None, lang: str | None = None) -> list[Path]:
    """The copies ticked, in ``dest`` (created), then LISEZMOI.txt. An error stops everything (UninstallError):
    nothing is removed without its copies."""
    site_dir = Path(site_dir).resolve()
    program = (program or program_dir()).resolve()
    dest = check_dest(dest, site_dir, program)
    written: list[Path] = []
    if not what:
        return written
    try:
        dest.mkdir(parents=True, exist_ok=True)
        if "exports" in what and (site_dir / "archive" / "exports").is_dir():
            say("uninstall.copy_exports", {"path": str(dest / "exports-claude.ai")})
            shutil.copytree(site_dir / "archive" / "exports", dest / "exports-claude.ai", dirs_exist_ok=True)
            written.append(dest / "exports-claude.ai")
        if "site" in what:  # checked before anything is removed (15/11): every conversation is in it
            site_zip = backup.make_backup(site_dir, dest, say=say)
            if backup_count(site_zip) != len(archive.conversations):
                raise UninstallError("uninstall.copy_incomplete", path=str(site_zip), n=backup_count(site_zip),
                                     total=len(archive.conversations))
            say("uninstall.copy_checked", {"path": str(site_zip), "n": len(archive.conversations)})
            written.append(site_zip)
        if "markdown" in what:
            written.append(allexport.build_all(archive, site_dir, dest, lang, say=say))
        if "program" in what and (program / install.LAUNCHER).is_file():
            say("uninstall.copy_program", {"path": str(dest)})
            written.append(_zip_program(program, dest))
        readme = dest / t("uninstall.readme_file", lang)
        names = {p.name for p in written}
        site_zip = next((p.name for p in written if p.name.startswith(site_dir.name + "-") and "markdown" not in p.name),
                        f"{site_dir.name}-AAAA-MM-JJ.zip")
        readme.write_text(t("uninstall.readme", lang, folder=str(dest), site=str(site_dir), site_zip=site_zip,
                            version=__version__, files="\n".join(f"  - {n}" for n in sorted(names))) + "\n",
                          encoding="utf-8")
        written.append(readme)
    except (OSError, backup.BackupError) as exc:
        raise UninstallError("uninstall.copy_failed", error=str(exc)) from exc
    return written


def remove(entries: list[dict[str, Any]], say: Callable[[str, dict], None]) -> list[str]:
    """Remove what targets() listed; returns the paths that could not be removed (reported, the others go on)."""
    failed = []
    for e in entries:
        p = Path(e["path"])
        try:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
            say("uninstall.removed", {"path": str(p)})
        except OSError as exc:
            failed.append(str(p))
            say("uninstall.remove_failed", {"path": str(p), "error": str(exc)})
    if sys.platform != "win32":
        try:
            import subprocess

            subprocess.run(["update-desktop-database", str(Path.home() / ".local/share/applications")],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    return failed


# --- Restoring a backup ----------------------------------------------------------------


def backup_root(zip_path: Path) -> str | None:
    """The folder at the root of a ZIP of a site (backup.make_backup: "<site>/archive/etat.json"), else None."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
    except (OSError, zipfile.BadZipFile):
        return None
    for n in names:
        parts = n.split("/")
        if len(parts) == 3 and parts[1] == "archive" and parts[2] == "etat.json":
            return parts[0]
    return None


_BACKUP_NAME = re.compile(r".+-\d{4}-\d{2}-\d{2}( \(\d+\))?\.zip$")


def backup_count(zip_path: Path) -> int:
    """The conversations a ZIP of a site holds (its archive/etat.json), 0 when it is not one or cannot be read."""
    root = backup_root(zip_path)
    if root is None:
        return 0
    try:
        with zipfile.ZipFile(zip_path) as z:
            state = json.loads(z.read(f"{root}/archive/etat.json").decode("utf-8"))
        return len(state.get("conversations") or {})
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return 0


def find_backup(site_dir: Path) -> Path | None:
    """The backup to offer on the welcome of an empty Library (15/11): among the ZIPs of a site in the downloads
    and their "CEV-sauvegarde-…" folders, the one holding the most conversations (the most recent among equals);
    never one without conversation (a backup of an empty or test Library). None when there is none."""
    try:
        folder = backup.destination(site_dir)
    except backup.BackupError:
        return None
    if not folder.is_dir():
        return None
    found = [(backup_count(z), z.stat().st_mtime, z) for z in [*folder.glob("*.zip"), *folder.glob("CEV-sauvegarde-*/*.zip")]
             if _BACKUP_NAME.match(z.name) and "-markdown-" not in z.name and not z.name.startswith("claude-export-viewer-")]
    found = [f for f in found if f[0] > 0]
    return max(found, key=lambda f: (f[0], f[1]))[2] if found else None


def restore(zip_path: Path, site_dir: Path, say: Callable[[str, dict], None] | None = None) -> int:
    """Unpack the ZIP of a site into ``site_dir``, which must hold no conversation yet (the few files of such a
    Library, pages made by the program and settings, are replaced by those of the backup); returns the number of
    files. The pages are made again by the program afterwards.

    Review of 21/11 (A2): the state of the archive (archive/etat.json) is written last, each file through a
    temporary one, and every conversation it lists must then have its file. Cut before the end, or incomplete, the
    Library stays without conversation (an incomplete state is renamed etat.json.incomplet), so the restore can
    be made again."""
    from .archive import Archive

    zip_path, site_dir = Path(zip_path).expanduser().resolve(), Path(site_dir).resolve()
    root = backup_root(zip_path)
    if root is None:
        raise UninstallError("restore.not_backup", path=str(zip_path))
    expected = backup_count(zip_path)
    if not expected:  # (15/11) a backup of an empty Library: nothing to put back
        raise UninstallError("restore.empty", path=str(zip_path))
    if Archive(site_dir).conversations:  # (its state file may hold settings only: the downloads folder…)
        raise UninstallError("restore.not_empty", path=str(site_dir))
    state_name = f"{root}/archive/etat.json"
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        members = [i for i in z.infolist() if i.filename.startswith(root + "/") and not i.is_dir()]
        members.sort(key=lambda i: i.filename == state_name)  # the state last (a stable sort keeps the rest)
        for info in members:
            target = (site_dir / info.filename[len(root) + 1:]).resolve()
            if not _inside(target, site_dir):
                continue  # a name going out of the folder: ignored
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".restauration.tmp")
            with z.open(info) as src, open(tmp, "wb") as out:
                shutil.copyfileobj(src, out)
            os.replace(tmp, target)
            n += 1
    archive = Archive(site_dir)
    got = sum(1 for m in archive.conversations.values() if archive.raw_file(m).is_file())
    if got != expected or got != len(archive.conversations):
        state = site_dir / "archive" / "etat.json"
        if state.is_file():
            os.replace(state, state.with_name("etat.json.incomplet"))
        raise UninstallError("restore.incomplete", path=str(zip_path), n=got, total=expected)
    if say:
        say("restore.done", {"n": n, "path": str(site_dir), "conversations": got})
    return n
