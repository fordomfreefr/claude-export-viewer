"""Cumulative local archive of Claude conversations.

Each export from claude.ai is a snapshot of the account at one moment. The
archive merges successive exports so that nothing is ever lost:

- every conversation is identified by its uuid (no duplicates);
- the archived copy is replaced only by a version coming from an export at
  least as recent as the one it came from (importing an old export later never
  overwrites newer content);
- a conversation that had text and is missing from the latest export, or is
  present there but emptied, is kept and marked "deleted on claude.ai";
- that mark is recomputed at every run: if the conversation shows up again in
  a later export, the mark disappears. Nothing is ever deleted from the archive.

Layout (inside the site folder)::

    archive/
        etat.json                  metadata of every conversation and export
        conversations/<id>.json.gz raw conversation as found in the export
        LISEZMOI.txt
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import os
import re
import shutil
import tempfile
import time
import zlib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import dates
from .i18n import Day, t
from .loader import FUTURE_MARGIN, ExportDate
from .models import Conversation, is_empty_conversation
from .tree import count_main
from .tree import skeleton as tree_skeleton
from .tree import (
    EXTRA_KEY,
    LAST_SEEN,
    LEGACY_REMOVED_KEY,
    LINEAR_PARENT,
    extra_messages,
    has_text,
    items_from_raw,
    main_path,
    message_key,
)

FORMAT = 1
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9_.-]")

_README = """\
Ce dossier contient la copie de toutes vos conversations Claude importées,
y compris celles supprimées depuis sur claude.ai.

NE PAS LE SUPPRIMER : c'est à partir de lui que le site est (re)construit.
Pour sauvegarder vos conversations, il suffit de copier ce dossier.

This folder holds the copy of every imported Claude conversation, including
those deleted from claude.ai since. Do not delete it: the site is built from it.
"""


IMPORT_MARK = "import-en-cours.json"  # written when an import starts, removed once its state is saved
LOCK_FILE = "verrou"  # locked while a program writes the archive or the site (ArchiveLock)


class ArchiveBusy(Exception):
    """Another program is writing the archive (ArchiveLock with ``wait=False``)."""


class ArchiveLock:
    """Exclusive lock of the archive between programs (two imports, an import and a rebuild…): the
    second one waits, or gets ArchiveBusy. The system releases it when the program ends, even killed, so
    it never stays behind. Not re-entrant: taken by the callers (cli, server), never by the builder."""

    def __init__(self, site_dir: Path) -> None:
        self.path = Path(site_dir) / "archive" / LOCK_FILE
        self._f: Any = None

    def _try(self) -> bool:
        try:
            if os.name == "nt":
                import msvcrt
                self._f.seek(0)
                msvcrt.locking(self._f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def acquire(self, wait: bool = True, on_wait: Any = None) -> ArchiveLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a+b")  # noqa: SIM115 - kept open while locked
        if self._try():
            return self
        if not wait:
            self._f.close()
            self._f = None
            raise ArchiveBusy
        if on_wait:
            on_wait()
        while not self._try():
            time.sleep(0.5)
        return self

    def release(self) -> None:
        if self._f is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._f.seek(0)
                msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._f.close()
        self._f = None

    def __enter__(self) -> ArchiveLock:
        return self.acquire()

    def __exit__(self, *exc: Any) -> None:
        self.release()


class ArchiveError(Exception):
    """The archive cannot be read (its message is meant for the user)."""


DISK_RESERVE = 512 * 1024**2  # bytes an import always leaves free (as drop.RESERVE): stopped before a full disk


class DiskFull(ArchiveError):
    """An import stopped because the disk would be (nearly) full: the archive is left as by an import cut short."""


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# --- One conversation on disk (step 2 of the reading in pieces, 21/11) -------------------------------------------
# conversations/<name>.jsonl.gz: line 1 {"cev": 2, "meta": {…}} (every field in its order, the lists of RAW_LISTS
# as [] at their place), then one line [key, element] per element of those lists (the messages, the messages kept
# from earlier exports). Read and written line by line: a conversation is never needed whole in memory. The former
# <name>.json.gz (the whole JSON) is still read; a conversation goes to the new form when it is written again.

RAW_SUFFIX, LEGACY_SUFFIX = ".jsonl.gz", ".json.gz"
TEMP_DIR = "temporaire"  # in archive/: the temporary files of an import (emptied at the start of each, not backed up)
RAW_FORMAT = 2


def _raw_lists() -> tuple[str, ...]:
    return ("chat_messages", EXTRA_KEY, LEGACY_REMOVED_KEY)


def write_raw(path: Path, raw: dict[str, Any]) -> None:
    """Write a conversation in the form of the lines above, through a temporary file (never half written)."""
    lists = _raw_lists()
    meta = {k: ([] if k in lists and isinstance(v, list) else v) for k, v in raw.items()}
    tmp = path.with_name(path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        f.write(json.dumps({"cev": RAW_FORMAT, "meta": meta}, ensure_ascii=False, separators=(",", ":")) + "\n")
        for key in lists:
            if isinstance(raw.get(key), list):
                for item in raw[key]:
                    f.write(json.dumps([key, item], ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def iter_raw_file(path: Path) -> Iterator[tuple[Any, ...]]:
    """("meta", fields) then ("item", key, element) one by one; the former whole form is given the same way."""
    try:
        yield from _iter_raw_file(path)
    except (EOFError, zlib.error) as exc:  # a gzip cut short or damaged: a ValueError too (25/11)
        raise ValueError(f"conversation : fichier tronqué ou abîmé ({exc})") from None


def _iter_raw_file(path: Path) -> Iterator[tuple[Any, ...]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        if not path.name.endswith(RAW_SUFFIX):  # the former form: one JSON document
            raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("conversation : objet JSON attendu")
            lists = [k for k in _raw_lists() if isinstance(raw.get(k), list)]
            yield ("meta", {k: ([] if k in lists else v) for k, v in raw.items()})
            for key in lists:
                for item in raw[key]:
                    yield ("item", key, item)
            return
        head = json.loads(f.readline())
        if not isinstance(head, dict) or head.get("cev") != RAW_FORMAT or not isinstance(head.get("meta"), dict):
            raise ValueError("conversation : en-tête illisible")
        lists = {k for k, v in head["meta"].items() if v == []}  # before the caller fills the meta (read_raw_file)
        yield ("meta", head["meta"])
        for n, line in enumerate(f, 2):
            # (25/11, Gemini audit) a damaged line is always a ValueError: never a TypeError of the unpacking (a number,
            # a list of 3) or an AttributeError later (a key whose value in the header is not an empty list)
            try:
                key, item = json.loads(line)
            except (ValueError, TypeError):
                raise ValueError(f"conversation : ligne {n} illisible") from None
            if not isinstance(key, str) or key not in lists:
                raise ValueError(f"conversation : liste inconnue {key!r}")
            yield ("item", key, item)


def read_raw_file(path: Path) -> dict[str, Any]:
    """The conversation whole (as stored before 2026.11.21.7)."""
    raw: dict[str, Any] = {}
    for ev in iter_raw_file(path):
        if ev[0] == "meta":
            raw = ev[1]
        else:
            raw[ev[1]].append(ev[2])
    return raw


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class RawSpool:
    """Step 3a of the reading in pieces (21/11): a conversation received field by field and message by message (the
    Events of loader), its messages written at once to a temporary file, never whole in memory. Gives the same hash
    as _hash(the conversation whole) — so that an unchanged conversation is still seen unchanged — and writes the file
    of the archive (write_raw's form) by copying the temporary one. The messages are kept with their keys sorted (the
    form the hash needs; the order of the keys of a message has no meaning). Use as a context manager."""

    MEMORY = 8 << 20  # characters kept in memory; beyond, the messages go to a temporary file (a long conversation)

    def __init__(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.path: Path | None = None
        self._out: Any = None
        self._mem: list[str] | None = []  # the lines, while the conversation is small (as fast as before, measured)
        self._size = 0
        self.meta: dict[str, Any] = {}
        self.lists: list[str] = []  # the keys streamed, in their order
        self.count = 0
        self.skeleton: list[tuple[str, ...]] = []  # tree.skeleton of each message (dict) of chat_messages (3c)

    def field(self, key: str, value: Any) -> None:
        self.meta[key] = value

    def start(self, key: str) -> None:
        self.meta[key] = []
        if key not in self.lists:
            self.lists.append(key)

    def item(self, key: str, value: Any) -> None:
        line = json.dumps(key, ensure_ascii=False) + "\t" + _canon(value) + "\n"
        if self._mem is not None:
            self._mem.append(line)
            self._size += len(line)
            if self._size > self.MEMORY:  # too long to keep: to the disk from now on
                self.folder.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix="conversation-", suffix=".tmp", dir=self.folder)
                self.path, self._out = Path(name), os.fdopen(fd, "w", encoding="utf-8")
                self._out.writelines(self._mem)
                self._mem = None
        else:
            self._out.write(line)
        self.count += 1
        if key == "chat_messages" and isinstance(value, dict):
            self.skeleton.append(tree_skeleton(value))

    @classmethod
    def from_raw(cls, folder: Path, raw: dict[str, Any]) -> "RawSpool":
        """A spool filled from a conversation already whole (the import given (raw, conversation) pairs)."""
        spool = cls(folder)
        for key, value in raw.items():
            if key in _raw_lists() and isinstance(value, list):
                spool.start(key)
                for item in value:
                    spool.item(key, item)
            else:
                spool.field(key, value)
        return spool

    def items(self, key: str) -> Iterator[Any]:
        """The elements of ``key`` decoded, in their order (a value of ``meta`` when it was not streamed)."""
        if key in self.lists and self.meta.get(key) == []:
            return (json.loads(text) for text in self._items(key))
        value = self.meta.get(key)
        return iter(value if isinstance(value, list) else [])

    def _items(self, key: str) -> Iterator[str]:
        """The canonical texts of the elements of ``key``, in their order (the temporary file read again)."""
        tag = json.dumps(key, ensure_ascii=False) + "\t"
        if self._mem is not None:
            for line in list(self._mem):
                if line.startswith(tag):
                    yield line[len(tag):-1]
            return
        self._out.flush()
        with self.path.open(encoding="utf-8") as f:  # (a handle of its own: several readings may go on at once)
            for line in f:
                if line.startswith(tag):
                    yield line[len(tag):-1]

    def hash(self) -> str:
        """_hash of the conversation whole, computed by reading the temporary file again."""
        h = hashlib.sha256()
        h.update(b"{")
        for n, key in enumerate(sorted(self.meta)):
            h.update(((("," if n else "") + json.dumps(key, ensure_ascii=False) + ":")).encode("utf-8"))
            if key in self.lists and self.meta[key] == []:
                h.update(b"[")
                for i, text in enumerate(self._items(key)):
                    h.update(((("," if i else "") + text)).encode("utf-8"))
                h.update(b"]")
            else:
                h.update(_canon(self.meta[key]).encode("utf-8"))
        h.update(b"}")
        return h.hexdigest()[:24]

    def write(self, path: Path) -> None:
        """The file of the archive (write_raw's form), through a temporary file, line by line."""
        tmp = path.with_name(path.name + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
            f.write(json.dumps({"cev": RAW_FORMAT, "meta": self.meta}, ensure_ascii=False, separators=(",", ":")) + "\n")
            for key in self.lists:
                if self.meta.get(key) == []:
                    for text in self._items(key):
                        f.write("[" + json.dumps(key, ensure_ascii=False) + "," + text + "]\n")
        os.replace(tmp, path)

    def close(self) -> None:
        if self._out is not None:
            self._out.close()
        if self.path is not None:
            self.path.unlink(missing_ok=True)
        self._mem = None

    def __enter__(self) -> "RawSpool":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class StoredConversation:
    """A conversation of the archive read again line by line, as often as needed (3d): ``meta`` its fields,
    ``items(key)`` the elements of one of its lists."""

    def __init__(self, path: Path) -> None:
        self.path = path
        events = iter_raw_file(path)
        self.meta = next(events)[1]
        events.close()

    def items(self, key: str) -> Iterator[Any]:
        if self.meta.get(key) != []:
            value = self.meta.get(key)
            yield from (value if isinstance(value, list) else [])
            return
        for ev in iter_raw_file(self.path):
            if ev[0] == "item" and ev[1] == key:
                yield ev[2]


def _extras_of(conv: Any) -> Iterator[dict[str, Any]]:
    """tree.extra_messages, element by element."""
    for m in conv.items(EXTRA_KEY):
        if isinstance(m, dict):
            yield m
    for group in conv.items(LEGACY_REMOVED_KEY):
        if not isinstance(group, dict):
            continue
        previous = group.get("after")
        for m in group.get("messages") or []:
            if isinstance(m, dict):
                yield {**m, LINEAR_PARENT: m.get(LINEAR_PARENT, previous), LAST_SEEN: group.get("export")}
                previous = message_key(m)


class MessageSource:
    """The messages of a conversation by uuid, for the annotations (favorites, notes, marks, structure; 21/11): an
    ordinary conversation is read whole as before; a very long one (a stored file of BIG_FILE or more) is read once,
    line by line, into a small index kept for the next changes: uuid -> parent, sender, date and the beginning of its
    text (what an excerpt shows). annotations.find_message takes it in place of the conversation."""

    BIG_FILE = 512 << 10
    TEXT = 4000  # characters of text kept per message of a long conversation (an excerpt is much shorter)
    _cache: dict[tuple[str, int, int], dict[str, dict[str, Any]]] = {}

    def __init__(self, path: Path) -> None:
        self.path = path
        self._index: dict[str, dict[str, Any]] | None = None

    def _build(self) -> dict[str, dict[str, Any]]:
        st = self.path.stat()
        key = (str(self.path), st.st_mtime_ns, st.st_size)
        if key in MessageSource._cache:
            return MessageSource._cache[key]
        stored = StoredConversation(self.path)
        big = st.st_size >= self.BIG_FILE
        index: dict[str, dict[str, Any]] = {}
        for m in itertools.chain(stored.items("chat_messages"), _extras_of(stored)):
            if not isinstance(m, dict) or not isinstance(m.get("uuid"), str) or m["uuid"] in index:
                continue
            if big:
                blocks = m.get("content") if isinstance(m.get("content"), list) else []
                text = " ".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
                m = {k: m.get(k) for k in ("uuid", "parent_message_uuid", "sender", "created_at")} | {
                    "text": str(m.get("text") or "")[:self.TEXT], "content": [{"type": "text", "text": text[:self.TEXT]}]}
            index[m["uuid"]] = m
        if big:  # the last two long conversations kept (an ordinary one is read again: fast)
            while len(MessageSource._cache) >= 2:
                MessageSource._cache.pop(next(iter(MessageSource._cache)))
            MessageSource._cache[key] = index
        return index

    def find(self, uuid: str) -> dict[str, Any] | None:
        if self._index is None:
            self._index = self._build()
        return self._index.get(uuid)


@dataclass
class Merged:
    """A merge written to a temporary file (3d): what _store_merged needs, without the conversation whole."""
    path: Path
    added: int
    removed_hash: str
    removed_messages: int
    n_messages: int


def merge_stream(current: Any, other: Any, other_date: str, folder: Path) -> Merged:
    """merge_versions(current, other, other_date) for conversations read element by element (a RawSpool, a
    StoredConversation): the same merged conversation, written to a temporary file of ``folder`` (moved into place
    by the caller, or removed); in memory only the keys of the messages and the skeletons."""
    cur_keys: set[str] = set()
    cur_skeleton: list[tuple[str, ...]] = []
    for m in current.items("chat_messages"):
        if isinstance(m, dict):
            cur_keys.add(message_key(m))
            cur_skeleton.append(tree_skeleton(m))
    fd, name = tempfile.mkstemp(prefix="extras-", suffix=".tmp", dir=folder)
    extras_path = Path(name)
    known: set[str] = set()
    extra_skeleton: list[tuple[str, ...]] = []
    removed = hashlib.sha256(b'{"r":[')
    added = n = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            def keep(m: dict[str, Any]) -> None:
                nonlocal n
                text = _canon(m)
                out.write(text + "\n")
                removed.update(((("," if n else "") + text)).encode("utf-8"))
                extra_skeleton.append(tree_skeleton(m, extra=True))
                n += 1
            for m in itertools.chain(_extras_of(other), _extras_of(current)):
                k = message_key(m)
                if k not in cur_keys and k not in known:
                    keep(m)
                    known.add(k)
            linear = not any(m.get("parent_message_uuid") for m in other.items("chat_messages") if isinstance(m, dict))
            previous: str | None = None
            for m in other.items("chat_messages"):
                if not isinstance(m, dict):
                    continue
                k = message_key(m)
                if k not in cur_keys and k not in known:
                    kept = {**m, LAST_SEEN: other_date}
                    if linear:
                        kept[LINEAR_PARENT] = previous
                    keep(kept)
                    known.add(k)
                    added += has_text(m)
                previous = k
        removed.update(b"]}")
        meta = {k: v for k, v in current.meta.items() if k not in (EXTRA_KEY, LEGACY_REMOVED_KEY)}
        if n:
            meta[EXTRA_KEY] = []
        fd2, name2 = tempfile.mkstemp(prefix="merged-", suffix=RAW_SUFFIX, dir=folder)
        os.close(fd2)
        merged_path = Path(name2)
        with gzip.open(merged_path, "wt", encoding="utf-8", compresslevel=6) as f:
            f.write(json.dumps({"cev": RAW_FORMAT, "meta": meta}, ensure_ascii=False, separators=(",", ":")) + "\n")
            if meta.get("chat_messages") == []:
                for m in current.items("chat_messages"):
                    f.write("[\"chat_messages\"," + json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "]\n")
            with extras_path.open(encoding="utf-8") as extras:
                for line in extras:
                    f.write("[" + json.dumps(EXTRA_KEY) + "," + line[:-1] + "]\n")
    finally:
        extras_path.unlink(missing_ok=True)
    return Merged(merged_path, added, removed.hexdigest()[:24] if n else "", n, count_main(cur_skeleton, extra_skeleton))


def _hash(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


# --- Messages that vanished from a conversation ---------------------------------
#
# The export holds every branch of a conversation, so editing or retrying on
# claude.ai loses nothing. Should messages still disappear from a later export,
# the archive keeps them (under tree.EXTRA_KEY, with the date of the last export
# holding them) and the page shows them where they belong in the tree, in a
# frame labelled "removed on claude.ai".


def merge_versions(current: dict[str, Any], other: dict[str, Any], other_date: str) -> tuple[dict[str, Any], int]:
    """``current`` (version to display) plus the messages of ``other`` it does not contain.

    ``other`` comes from the export dated ``other_date``. Returns the merged
    conversation and the number of newly kept messages that hold text.
    """
    cur_keys = {message_key(m) for m in current.get("chat_messages") or [] if isinstance(m, dict)}
    extras: list[dict[str, Any]] = []
    known: set[str] = set()
    for m in [*extra_messages(other), *extra_messages(current)]:
        k = message_key(m)
        if k not in cur_keys and k not in known:
            extras.append(m)
            known.add(k)

    added = 0
    other_msgs = [m for m in other.get("chat_messages") or [] if isinstance(m, dict)]
    linear = not any(m.get("parent_message_uuid") for m in other_msgs)
    previous: str | None = None
    for m in other_msgs:
        k = message_key(m)
        if k not in cur_keys and k not in known:
            kept = {**m, LAST_SEEN: other_date}
            if linear:
                kept[LINEAR_PARENT] = previous
            extras.append(kept)
            known.add(k)
            added += has_text(m)
        previous = k

    merged = {k: v for k, v in current.items() if k not in (EXTRA_KEY, LEGACY_REMOVED_KEY)}
    if extras:
        merged[EXTRA_KEY] = extras
    return merged, added


def visible_count(raw: dict[str, Any]) -> int:
    """Messages on the main branch (what the page shows outside the frames)."""
    return len(main_path(items_from_raw(raw)))


@dataclass
class ImportStats:
    export_date: str = ""
    export_source: str = ""
    is_latest: bool = True
    seen: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_empty: int = 0
    emptied: int = 0  # present in the export but emptied, archived copy kept
    with_removed_parts: int = 0  # conversations where removed messages were kept
    newly_deleted: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    suspicious: bool = False  # many conversations vanished at once: a file may be missing
    incomplete: bool = False  # a file of conversations could not be read to its end (audit A1)
    newest: datetime | None = None  # the newest conversation of the export (updated_at, created_at)
    date_before_newest: bool = False  # the export date before its newest conversation: wrong (harmless, told)


class Archive:
    def __init__(self, site_dir: Path) -> None:
        self.dir = Path(site_dir) / "archive"
        self.raw_dir = self.dir / "conversations"
        self.state_path = self.dir / "etat.json"
        self._imported: str | None = None  # date of the export imported, until save()
        if self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ArchiveError(t("archive.unreadable", path=self.state_path, error=exc)) from None
        else:
            self.state = {"format": FORMAT, "exports": [], "conversations": {}, "users": {}, "projects": {}}

    # --- state helpers -------------------------------------------------------

    @property
    def conversations(self) -> dict[str, dict[str, Any]]:
        return self.state["conversations"]

    @property
    def exists(self) -> bool:
        return self.state_path.exists()

    @property
    def interrupted_import(self) -> dict[str, Any] | None:
        """The import started and never finished ({"date", "label"}), else None: importing the same
        export again completes the archive (tests/test_interrupted_import.py)."""
        try:
            mark = json.loads((self.dir / IMPORT_MARK).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return mark if isinstance(mark, dict) and isinstance(mark.get("date"), str) else None

    @property
    def latest_export(self) -> str | None:
        dates = [e["date"] for e in self.state["exports"] if not e.get("incomplete")]
        return max(dates) if dates else None

    def deleted_since(self, meta: dict[str, Any]) -> str | None:
        """ISO date of the first export the conversation is missing from, or None if it is alive."""
        if not meta.get("had_text"):
            return None
        latest = self.latest_export
        if latest is None or meta["last_seen"] >= latest:
            return None
        later = [e["date"] for e in self.state["exports"] if e["date"] > meta["last_seen"] and not e.get("incomplete")]
        return min(later) if later else latest

    def _deleted_set(self) -> set[str]:
        return {u for u, m in self.conversations.items() if self.deleted_since(m)}

    def _new_filename(self, uuid: str) -> str:
        used = {m["filename"] for m in self.conversations.values()}
        base = _UNSAFE_FILENAME.sub("_", uuid)[:100] or "conversation"
        name, i = base, 2
        while f"{name}.html" in used:
            name, i = f"{base}_{i}", i + 1
        return f"{name}.html"

    def raw_path(self, meta: dict[str, Any]) -> Path:
        """The file of a conversation in the current form (written there); see raw_file for reading."""
        return self.raw_dir / (meta["filename"].removesuffix(".html") + RAW_SUFFIX)

    def raw_file(self, meta: dict[str, Any]) -> Path:
        """The file holding the conversation: the current form, else the former one (not written again yet)."""
        path = self.raw_path(meta)
        if path.is_file():
            return path
        legacy = path.with_name(path.name.removesuffix(RAW_SUFFIX) + LEGACY_SUFFIX)
        return legacy if legacy.is_file() else path

    def load_raw(self, uuid: str) -> dict[str, Any]:
        return self._load_meta_raw(self.conversations[uuid])

    def stored(self, uuid: str) -> "StoredConversation":
        return StoredConversation(self.raw_file(self.conversations[uuid]))

    def iter_messages(self, uuid: str) -> Iterator[Any]:
        """The messages, then the extra messages (tree.extra_messages), one by one: never the conversation whole."""
        stored = self.stored(uuid)
        return itertools.chain(stored.items("chat_messages"), _extras_of(stored))

    def find_message(self, uuid: str, key: str) -> dict[str, Any] | None:
        """The message of key ``key`` (tree.message_key), read line by line; None when absent."""
        return next((m for m in self.iter_messages(uuid) if isinstance(m, dict) and message_key(m) == key), None)

    def message_source(self, uuid: str) -> "MessageSource":
        """What the annotations need of a conversation (KeyError when unknown): see MessageSource."""
        return MessageSource(self.raw_file(self.conversations[uuid]))

    def iter_raw(self, uuid: str) -> Iterator[tuple[Any, ...]]:
        """The conversation line by line (see iter_raw_file), without loading it whole."""
        return iter_raw_file(self.raw_file(self.conversations[uuid]))

    def _load_meta_raw(self, meta: dict[str, Any]) -> dict[str, Any]:
        return read_raw_file(self.raw_file(meta))

    def _store_merged(self, meta: dict[str, Any], merged: dict[str, Any]) -> None:
        extras = merged.get(EXTRA_KEY) or []
        meta["removed_hash"] = _hash({"r": extras}) if extras else ""
        meta["removed_messages"] = len(extras)
        meta["n_messages"] = visible_count(merged)
        self._store_raw(meta, merged)

    @property
    def temp_dir(self) -> Path:
        return self.dir / TEMP_DIR

    @staticmethod
    def _spools(records: Iterable[Any], folder: Path) -> Iterator[tuple[Any, Conversation, bool]]:
        """(spool, conversation, has_text) from loader.iter_conversation_spools, or made from (raw, conversation)
        pairs (the conversation already whole: tests, older callers)."""
        for rec in records:
            if len(rec) == 3:
                yield rec
                continue
            raw, convo = rec
            with RawSpool.from_raw(folder, raw) as spool:
                yield spool, convo, not is_empty_conversation(convo)

    def _install(self, meta: dict[str, Any], got: Merged) -> None:
        """A merge written by merge_stream put in place of the conversation (what _store_merged does)."""
        path = self.raw_path(meta)
        os.replace(got.path, path)
        path.with_name(path.name.removesuffix(RAW_SUFFIX) + LEGACY_SUFFIX).unlink(missing_ok=True)
        meta["removed_hash"], meta["removed_messages"], meta["n_messages"] = got.removed_hash, got.removed_messages, got.n_messages

    def _store_raw(self, meta: dict[str, Any], raw: dict[str, Any]) -> None:
        path = self.raw_path(meta)
        write_raw(path, raw)
        path.with_name(path.name.removesuffix(RAW_SUFFIX) + LEGACY_SUFFIX).unlink(missing_ok=True)  # the former form

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        readme = self.dir / "LISEZMOI.txt"
        if not readme.exists():
            readme.write_text(_README, encoding="utf-8")
        data = json.dumps(self.state, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        _atomic_write(self.state_path, data)
        mark = self.interrupted_import
        if self._imported is not None and mark and mark["date"] == self._imported:
            (self.dir / IMPORT_MARK).unlink(missing_ok=True)  # that import is complete now
        self._imported = None

    # --- import --------------------------------------------------------------

    def import_export(
        self,
        records: Iterable[Any],  # (spool, conversation, has_text) from loader.iter_conversation_spools, or (raw, conversation)
        export_date: ExportDate,
        label: str = "",
        skip_empty: bool = True,
        users: dict[str, str] | None = None,
        projects: dict[str, str] | None = None,
        read_ok: Callable[[], bool] | None = None,
    ) -> ImportStats:
        """Merge the conversations of one export. ``read_ok()``, asked once they are all read, says whether every
        file of conversations was read to its end; if not (audit A1, option b of 21/11), what was read is kept but
        the export is recorded as incomplete: it is not the latest export and marks no conversation as deleted."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        d = dates.iso_utc(export_date.value)
        if self.interrupted_import is None or self.interrupted_import["date"] == d:
            # an earlier cut import stays marked until that export is imported again
            _atomic_write(self.dir / IMPORT_MARK, json.dumps({"date": d, "label": label}, ensure_ascii=False).encode("utf-8"))
        self._imported = d
        latest_before = self.latest_export
        stats = ImportStats(export_date=d, export_source=export_date.source)
        stats.is_latest = latest_before is None or d >= latest_before
        deleted_before = self._deleted_set()
        alive_before = len(self.conversations) - len(deleted_before)

        temp = self.temp_dir
        shutil.rmtree(temp, ignore_errors=True)  # what an import cut short left
        temp.mkdir(parents=True, exist_ok=True)
        for spool, convo, has_text in self._spools(records, temp):
            stats.seen += 1
            if shutil.disk_usage(self.raw_dir).free < DISK_RESERVE:  # (review of 21/11) before writing anything more
                raise DiskFull(t("cli.import.no_space", reserve=DISK_RESERVE // 1024**2))
            for when in (convo.updated_at, convo.created_at):
                w = dates.utc(when) if when else None
                if w and (stats.newest is None or w > stats.newest):
                    stats.newest = w
            meta = self.conversations.get(convo.uuid)

            if not has_text:
                if meta is not None and meta.get("had_text"):
                    stats.emptied += 1  # deleted shell: keep the archived copy, do not mark as seen
                    continue
                if skip_empty:
                    stats.skipped_empty += 1
                    continue

            h = spool.hash()  # (step 3d, 21/11: the conversation is never whole in memory; the same hash as _hash)
            extra_sk = [tree_skeleton(m, extra=True) for m in _extras_of(spool)] \
                if EXTRA_KEY in spool.lists or LEGACY_REMOVED_KEY in spool.lists else []
            info = {
                "name": convo.name,
                "created_at": convo.created_at.isoformat() if convo.created_at else "",
                "updated_at": convo.updated_at.isoformat() if convo.updated_at else "",
                "account_uuid": convo.account.uuid if convo.account else "",
                "project_uuid": convo.project_uuid or "",
                "n_messages": count_main(spool.skeleton, extra_sk),
            }
            if meta is None:
                meta = {
                    **info,
                    "filename": self._new_filename(convo.uuid),
                    "hash": h,
                    "had_text": has_text,
                    "first_seen": d,
                    "last_seen": d,
                    "version_export": d,
                }
                self.conversations[convo.uuid] = meta
                path = self.raw_path(meta)
                spool.write(path)
                path.with_name(path.name.removesuffix(RAW_SUFFIX) + LEGACY_SUFFIX).unlink(missing_ok=True)
                stats.new += 1
                continue

            if h == meta["hash"]:
                stats.unchanged += 1
            elif d >= meta["version_export"]:
                # Newer version: it becomes the displayed one, the vanished messages are kept.
                got = merge_stream(spool, StoredConversation(self.raw_file(meta)), meta["version_export"], temp)
                meta.update(info, hash=h, version_export=d)
                self._install(meta, got)
                stats.updated += 1
                stats.with_removed_parts += bool(got.added)
            else:
                # Older export: nothing is overwritten, but messages the archive never saw are kept.
                got = merge_stream(StoredConversation(self.raw_file(meta)), spool, d, temp)
                if got.added:
                    self._install(meta, got)
                    stats.with_removed_parts += 1
                else:
                    got.path.unlink()
                stats.unchanged += 1
            meta["first_seen"] = min(meta["first_seen"], d)
            meta["last_seen"] = max(meta["last_seen"], d)
            meta["had_text"] = meta.get("had_text", False) or has_text

        stats.incomplete = read_ok is not None and not read_ok()
        # an export is made after its newest conversation: a date before it is wrong; harmless (the export is only
        # taken for older than it is: nothing overwritten, no conversation marked deleted because of it), told
        stats.date_before_newest = stats.newest is not None and stats.newest > export_date.value + FUTURE_MARGIN
        # Record the export (re-importing the same export does not duplicate it)
        exports = [e for e in self.state["exports"] if e["date"] != d]
        entry = {
            "date": d,
            "source": export_date.source,
            "label": label,
            "conversations": stats.seen,
            "imported_at": dates.iso_utc(datetime.now(timezone.utc)),
        }
        if stats.incomplete:
            entry["incomplete"] = True
        exports.append(entry)
        self.state["exports"] = sorted(exports, key=lambda e: e["date"])

        for key, names in (("users", users or {}), ("projects", projects or {})):
            target = self.state[key]
            for uuid, name in names.items():
                if stats.is_latest or uuid not in target:
                    target[uuid] = name

        deleted_after = self._deleted_set()
        stats.newly_deleted = sorted(deleted_after - deleted_before)
        stats.restored = sorted(deleted_before - deleted_after)
        if stats.is_latest and not stats.incomplete and len(stats.newly_deleted) > max(5, 0.25 * alive_before):
            stats.suspicious = True
        return stats

    # --- display helpers -----------------------------------------------------

    def display_info(self, meta: dict[str, Any]) -> dict[str, Any]:
        """Dates of exports shown on the pages: ISO days ("" when not applicable)."""
        deleted = self.deleted_since(meta)
        return {
            "deleted_since": Day(deleted[:10]) if deleted else "",
            "version_export": Day(meta["version_export"][:10]) if meta.get("version_export") else "",
        }
