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
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import dates
from .i18n import Day, t
from .loader import ExportDate
from .models import Conversation, is_empty_conversation
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


class ArchiveError(Exception):
    """The archive cannot be read (its message is meant for the user)."""


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


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


class Archive:
    def __init__(self, site_dir: Path) -> None:
        self.dir = Path(site_dir) / "archive"
        self.raw_dir = self.dir / "conversations"
        self.state_path = self.dir / "etat.json"
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
    def latest_export(self) -> str | None:
        dates = [e["date"] for e in self.state["exports"]]
        return max(dates) if dates else None

    def deleted_since(self, meta: dict[str, Any]) -> str | None:
        """ISO date of the first export the conversation is missing from, or None if it is alive."""
        if not meta.get("had_text"):
            return None
        latest = self.latest_export
        if latest is None or meta["last_seen"] >= latest:
            return None
        later = [e["date"] for e in self.state["exports"] if e["date"] > meta["last_seen"]]
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
        return self.raw_dir / (meta["filename"].removesuffix(".html") + ".json.gz")

    def load_raw(self, uuid: str) -> dict[str, Any]:
        return self._load_meta_raw(self.conversations[uuid])

    def _load_meta_raw(self, meta: dict[str, Any]) -> dict[str, Any]:
        with gzip.open(self.raw_path(meta), "rt", encoding="utf-8") as f:
            return json.load(f)

    def _store_merged(self, meta: dict[str, Any], merged: dict[str, Any]) -> None:
        extras = merged.get(EXTRA_KEY) or []
        meta["removed_hash"] = _hash({"r": extras}) if extras else ""
        meta["removed_messages"] = len(extras)
        meta["n_messages"] = visible_count(merged)
        self._store_raw(meta, merged)

    def _store_raw(self, meta: dict[str, Any], raw: dict[str, Any]) -> None:
        data = json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _atomic_write(self.raw_path(meta), gzip.compress(data, compresslevel=6))

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        readme = self.dir / "LISEZMOI.txt"
        if not readme.exists():
            readme.write_text(_README, encoding="utf-8")
        data = json.dumps(self.state, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
        _atomic_write(self.state_path, data)

    # --- import --------------------------------------------------------------

    def import_export(
        self,
        records: Iterable[tuple[dict[str, Any], Conversation]],
        export_date: ExportDate,
        label: str = "",
        skip_empty: bool = True,
        users: dict[str, str] | None = None,
        projects: dict[str, str] | None = None,
    ) -> ImportStats:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        d = dates.iso_utc(export_date.value)
        latest_before = self.latest_export
        stats = ImportStats(export_date=d, export_source=export_date.source)
        stats.is_latest = latest_before is None or d >= latest_before
        deleted_before = self._deleted_set()
        alive_before = len(self.conversations) - len(deleted_before)

        for raw, convo in records:
            stats.seen += 1
            has_text = not is_empty_conversation(convo)
            meta = self.conversations.get(convo.uuid)

            if not has_text:
                if meta is not None and meta.get("had_text"):
                    stats.emptied += 1  # deleted shell: keep the archived copy, do not mark as seen
                    continue
                if skip_empty:
                    stats.skipped_empty += 1
                    continue

            h = _hash(raw)
            info = {
                "name": convo.name,
                "created_at": convo.created_at.isoformat() if convo.created_at else "",
                "updated_at": convo.updated_at.isoformat() if convo.updated_at else "",
                "account_uuid": convo.account.uuid if convo.account else "",
                "project_uuid": convo.project_uuid or "",
                "n_messages": visible_count(raw),
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
                self._store_raw(meta, raw)
                stats.new += 1
                continue

            if h == meta["hash"]:
                stats.unchanged += 1
            elif d >= meta["version_export"]:
                # Newer version: it becomes the displayed one, the vanished messages are kept.
                merged, added = merge_versions(raw, self._load_meta_raw(meta), meta["version_export"])
                meta.update(info, hash=h, version_export=d)
                self._store_merged(meta, merged)
                stats.updated += 1
                stats.with_removed_parts += bool(added)
            else:
                # Older export: nothing is overwritten, but messages the archive never saw are kept.
                merged, added = merge_versions(self._load_meta_raw(meta), raw, d)
                if added:
                    self._store_merged(meta, merged)
                    stats.with_removed_parts += 1
                stats.unchanged += 1
            meta["first_seen"] = min(meta["first_seen"], d)
            meta["last_seen"] = max(meta["last_seen"], d)
            meta["had_text"] = meta.get("had_text", False) or has_text

        # Record the export (re-importing the same export does not duplicate it)
        exports = [e for e in self.state["exports"] if e["date"] != d]
        exports.append(
            {
                "date": d,
                "source": export_date.source,
                "label": label,
                "conversations": stats.seen,
                "imported_at": dates.iso_utc(datetime.now(timezone.utc)),
            }
        )
        self.state["exports"] = sorted(exports, key=lambda e: e["date"])

        for key, names in (("users", users or {}), ("projects", projects or {})):
            target = self.state[key]
            for uuid, name in names.items():
                if stats.is_latest or uuid not in target:
                    target[uuid] = name

        deleted_after = self._deleted_set()
        stats.newly_deleted = sorted(deleted_after - deleted_before)
        stats.restored = sorted(deleted_before - deleted_after)
        if stats.is_latest and len(stats.newly_deleted) > max(5, 0.25 * alive_before):
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
