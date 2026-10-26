"""The user's own copies of the files of the conversations, found on the computer.

The export gives only the names of the images and files sent in a message, of
the documents joined to it (with their text) and of the files created by Claude
(``/mnt/user-data/outputs/…``). Files with exactly the same name are looked for
in the folders chosen by the user (sub-folders included, hidden ones skipped);
when several have that name, the most recent is taken. The file found is copied
into the site (``files/<conversation>/<name>``), so that the page shows it.

A file found automatically may be another file with the same name: the page
asks whether it is the right one. Accepted, it is kept; refused, its copy is
removed and that file (path, size, date) is never proposed again for that name.
Names still missing are looked for again at each run, so files saved later
(for example after going back to an old conversation on claude.ai) complete
the site.

State in ``archive/files.json``::

    {"names": {uuid: {"hash": h, "list": [[kind, name], ...]}},
     "found": {uuid: {name: {"source", "size", "mtime", "copy", "state", "rejected"}}}}
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import system

FILE = "files.json"
FOLDER = "files"
CREATED = re.compile(r"/mnt/user-data/outputs/((?:[^\s\"'<>|\\()\[\]]+/)*([^\s\"'<>|\\/()\[\]]+\.[A-Za-z0-9]{1,8}))")
IMAGES = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"}
_SKIP = {"__pycache__", "node_modules"}


@dataclass(frozen=True)
class Candidate:
    path: Path
    size: int
    mtime: float

    def identity(self) -> list[Any]:
        return [str(self.path), self.size, int(self.mtime)]


# --- names in a conversation ---------------------------------------------------


def created_names(data: Any) -> list[str]:
    """Names of the files created by Claude mentioned in a message (or any JSON data)."""
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    out: list[str] = []
    for m in CREATED.finditer(text):
        if m.group(2) not in out:
            out.append(m.group(2))
    return out


def names_in(raw: dict[str, Any]) -> list[list[str]]:
    """[kind, name] of every file named in a conversation: "file", "attachment" or "created"."""
    out: list[list[str]] = []

    def add(kind: str, name: Any) -> None:
        if isinstance(name, str) and name.strip() and [kind, name] not in out:
            out.append([kind, name])

    for msg in raw.get("chat_messages") or []:
        if not isinstance(msg, dict):
            continue
        for f in msg.get("files") or []:
            if isinstance(f, dict):
                add("file", f.get("file_name"))
        for a in msg.get("attachments") or []:
            if isinstance(a, dict):
                add("attachment", a.get("file_name"))
        for name in created_names(msg.get("content") or []):
            add("created", name)
    return out


# --- state ---------------------------------------------------------------------


def _path(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FILE


def load(site_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads(_path(site_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    for k in ("names", "found"):
        if not isinstance(data.get(k), dict):
            data[k] = {}
    return data


def save(site_dir: Path, data: dict[str, Any]) -> None:
    path = _path(site_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def found_for(data: dict[str, Any], uuid: str) -> dict[str, dict[str, Any]]:
    """The files found for a conversation (accepted or proposed), by name."""
    return {n: e for n, e in data["found"].get(uuid, {}).items() if e.get("copy")}


def signature(data: dict[str, Any], uuid: str) -> str:
    """Changes when what a page shows about the files of its conversation changes."""
    found = found_for(data, uuid)
    return json.dumps({n: [e["copy"], e.get("state")] for n, e in sorted(found.items())}, ensure_ascii=False)


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .") or "file"


# --- search --------------------------------------------------------------------


def _key(name: str) -> str:
    return name.casefold() if system.WINDOWS else name


def scan(folders: Iterable[Path], wanted: set[str], skip: Iterable[Path] = ()) -> dict[str, list[Candidate]]:
    """Files named exactly as one of ``wanted``, in the folders and their sub-folders."""
    keys = {_key(n) for n in wanted}
    skipped = set()
    for p in skip:
        try:
            skipped.add(Path(p).resolve())
        except OSError:
            pass
    out: dict[str, list[Candidate]] = {}
    seen: set[Path] = set()
    for folder in folders:
        try:
            folder = Path(folder).expanduser().resolve()
        except OSError:
            continue
        if not folder.is_dir():
            continue
        for root, dirs, files in os.walk(folder, onerror=lambda e: None):
            base = Path(root)
            if base in seen:
                dirs[:] = []
                continue
            seen.add(base)
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP and (base / d) not in skipped]
            for name in files:
                k = _key(name)
                if k in keys:
                    path = base / name
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    out.setdefault(k, []).append(Candidate(path, st.st_size, st.st_mtime))
    return out


def update(archive: Any, site_dir: Path, folders: list[Path], skip: Iterable[Path] = (),
           say: Callable[[int, int, list[Path]], None] | None = None) -> int:
    """Look for the files still missing and copy those found into the site; returns how many were found."""
    site_dir = Path(site_dir)
    data = load(site_dir)
    names, found_all = data["names"], data["found"]
    for uuid in list(names):
        if uuid not in archive.conversations:
            del names[uuid]
    for uuid, meta in archive.conversations.items():
        cached = names.get(uuid)
        if not cached or cached.get("hash") != meta.get("hash"):
            try:
                names[uuid] = {"hash": meta.get("hash"), "list": names_in(archive.load_raw(uuid))}
            except Exception:  # noqa: BLE001 - an unreadable conversation is reported by the rendering
                names[uuid] = {"hash": None, "list": []}

    missing: list[tuple[str, str]] = []
    for uuid, entry in names.items():
        found = found_all.setdefault(uuid, {})
        for _kind, name in entry["list"]:
            e = found.get(name)
            if e and e.get("copy"):
                if (site_dir / e["copy"]).is_file():
                    continue
                src = Path(e.get("source", ""))
                if src.is_file():  # the copy was removed from the site: copy again
                    _copy(src, site_dir / e["copy"])
                    continue
                e.pop("copy", None)
            missing.append((uuid, name))
    if not missing:
        save(site_dir, data)
        return 0
    folders = [f for f in folders if Path(f).is_dir()]
    if say:
        say(len({n for _, n in missing}), len(missing), folders)
    candidates = scan(folders, {n for _, n in missing}, [site_dir, *skip])
    count = 0
    for uuid, name in missing:
        e = found_all[uuid].setdefault(name, {})
        refused = [list(r) for r in e.get("rejected", [])]
        options = [c for c in candidates.get(_key(name), []) if c.identity() not in refused]
        if not options:
            continue
        best = max(options, key=lambda c: c.mtime)
        key = archive.conversations[uuid]["filename"].removesuffix(".html")
        copy = f"{FOLDER}/{key}/{safe_name(name)}"
        try:
            _copy(best.path, site_dir / copy)
        except OSError:
            continue
        e.update({"source": str(best.path), "size": best.size, "mtime": best.mtime, "copy": copy, "state": "auto"})
        count += 1
    save(site_dir, data)
    return count


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


ACTIONS = ("ok", "reject", "undo")


def decide(site_dir: Path, uuid: str, name: str, action: str) -> bool:
    """The user says whether the file found is the right one: "ok", "reject", or "undo" (the
    question is asked again after a "Yes"); False if there is no such file."""
    data = load(site_dir)
    e = data["found"].get(uuid, {}).get(name)
    if not e or not e.get("copy"):
        return False
    if action == "ok":
        e["state"] = "ok"
    elif action == "undo":
        e["state"] = "auto"
    else:
        e.setdefault("rejected", []).append([e.get("source", ""), e.get("size", 0), int(e.get("mtime", 0))])
        try:
            (Path(site_dir) / e["copy"]).unlink()
        except OSError:
            pass
        for k in ("source", "size", "mtime", "copy", "state"):
            e.pop(k, None)
    save(site_dir, data)
    return True
