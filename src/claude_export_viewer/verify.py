"""AE-m10 (15/11): "Vérifier l'archive" — every file of archive/ read again; what is unreadable or missing said.

What is checked:

- ``etat.json`` (the list of the conversations): readable, else nothing more can be checked (a backup brings it back);
- each conversation of it: its ``conversations/<name>.jsonl.gz (or the former .json.gz)`` present, decompressed (the gzip check sum) and read
  as JSON, of the same uuid;
- the JSON files of the user (annotations, rubriques, fichiers, réglages, states of the annotations kept) and those
  already set aside as unreadable (``jsonfile.damaged``);
- the libraries kept (``cdn/``, ``esm/``): their index readable, each file it names present;
- the exports kept (``exports/**``): every ZIP read in full (the check sum of each file), the JSON files read.

A conversation unreadable or missing can be **repaired** from the exports kept (``repair``): every version found there
is merged as an import does (the version of the export the archive showed, else the latest; the messages of the
others kept as "removed on claude.ai"). Messages only the lost file held (from an export not kept) cannot come back.

``say(key, args)`` gets every line (i18n keys ``verify.*``); the CLI prints them, the server puts them in the log.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import dates, jsonfile
from .i18n import t
from .archive import Archive, ArchiveError, _hash, merge_versions, read_raw_file
from .loader import FUTURE_MARGIN, classify, export_date, iter_conversation_records, pop_left_out, pop_warnings

Say = Callable[[str, dict[str, Any]], None]
USER_FILES = ("annotations.json", "topics.json", "files.json", "settings.json")
REPAIRABLE_MARK = "\x1fCEV-REPAIRABLE "  # "<mark> n": read by the server (the button "Réparer" of the page)


@dataclass
class Report:
    problems: int = 0
    broken: dict[str, str] = field(default_factory=dict)  # uuid -> name: conversations unreadable or missing
    repairable: list[str] = field(default_factory=list)  # those found in the exports kept
    counts: dict[str, int] = field(default_factory=lambda: {"conversations": 0, "zips": 0, "files": 0})
    redate: dict[str, str] = field(default_factory=dict)  # export date in the future -> date to give it (ISO)

    @property
    def n_repairable(self) -> int:
        return len(self.repairable) + len(self.redate)


def _when(d: datetime | None) -> str:
    return d.strftime(t("fmt.date") + " %H:%M") if d else t("cli.import.date_unknown")


def _from_export(archive: Archive, day: str) -> list[dict[str, Any]]:
    """The conversations an export brought or saw (its date among their first, last or shown export)."""
    return [m for m in archive.conversations.values()
            if day in (m.get("first_seen"), m.get("last_seen"), m.get("version_export"))]


def _future_exports(archive: Archive, rep: Report, problem: Callable[..., None], say: Say,
                    now: datetime | None = None) -> None:
    """Review of 21/11: an export dated after the computer's clock (a date typed wrong, a manifest made up) freezes the
    archive: it stays the latest export, every later one is taken for older. Repairable when its newest conversation
    is not in the future itself: the export takes that date (an export is always made after its newest conversation;
    the clock is not used for the new date). When the newest conversation is in the future too, the clock is probably
    wrong: nothing is repaired."""
    now = now or datetime.now(timezone.utc)
    for e in archive.state.get("exports", []):
        when = dates.parse(e.get("date"))
        if when is None or dates.utc(when) <= now + FUTURE_MARGIN:
            continue
        stamps = [dates.parse(m.get(k)) for m in _from_export(archive, e["date"]) for k in ("updated_at", "created_at")]
        newest = max((dates.utc(x) for x in stamps if x), default=None)
        problem("verify.future_export", export=_when(dates.utc(when)), clock=_when(now), newest=_when(newest))
        if newest is not None and newest <= now + FUTURE_MARGIN:
            rep.redate[e["date"]] = dates.iso_utc(newest)
            say("verify.future_export_repair", {"newest": _when(newest)})
        else:
            say("verify.future_export_clock", {})


def redate(site_dir: Path, mapping: dict[str, str], say: Say) -> int:
    """Give the exports of ``mapping`` (old ISO date -> new) their new date, in the list of the exports and in the
    conversations. A conversation last seen in such an export may have been seen in the later ones too (that was not
    kept): it is taken as alive until the next import tells. Returns the number of exports redated; the caller holds
    the lock."""
    archive = Archive(site_dir)
    done = 0
    for e in archive.state.get("exports", []):
        if e.get("date") in mapping:
            e["redated_from"], e["date"] = e["date"], mapping[e["date"]]
            done += 1
    archive.state["exports"].sort(key=lambda e: e["date"])
    latest = archive.latest_export
    for old, new in mapping.items():
        n = 0
        for meta in archive.conversations.values():
            hit = False
            if meta.get("first_seen") == old:
                meta["first_seen"], hit = new, True
            if meta.get("version_export") == old:
                meta["version_export"], hit = new, True
            if meta.get("last_seen") == old:
                meta["last_seen"], hit = max(new, latest or new), True
            n += hit
        say("verify.redated", {"old": _when(dates.parse(old)), "new": _when(dates.parse(new)), "n": n})
    archive.save()
    return done


def _json_ok(path: Path) -> str | None:
    """None when the file is read as JSON, else the error."""
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return str(exc)
    return None


def _zip_error(path: Path) -> tuple[str, str] | None:
    """(i18n key, detail) when the ZIP cannot be read in full."""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError) as exc:
        return "verify.zip_unreadable", str(exc)
    return ("verify.zip_damaged", bad) if bad else None


def export_folders(site_dir: Path) -> list[Path]:
    root = Path(site_dir) / "archive" / "exports"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def _versions(site_dir: Path, uuids: set[str]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Every version of these conversations in the exports kept: uuid -> [(ISO date of the export, raw)]."""
    found: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for folder in export_folders(site_dir):
        try:
            sources = classify([folder])
            if not sources.conversations:
                continue
            d = dates.iso_utc(export_date(sources).value)
            for raw, convo in iter_conversation_records(sources.conversations):
                if convo.uuid in uuids:
                    found.setdefault(convo.uuid, []).append((d, raw))
        except (OSError, ValueError, zipfile.BadZipFile, EOFError):
            continue  # a damaged export: said by check()
        finally:
            pop_left_out()
            pop_warnings()
    return found


def check(site_dir: Path, say: Say) -> Report:
    site_dir = Path(site_dir)
    folder = site_dir / "archive"
    rep = Report()

    def problem(key: str, **args: Any) -> None:
        rep.problems += 1
        say(key, args)

    say("verify.start", {"path": str(folder)})
    try:
        archive: Archive | None = Archive(site_dir)
    except ArchiveError as exc:
        archive = None
        problem("verify.state_unreadable", path=str(folder / "etat.json"), error=str(exc))
    if archive is not None:
        _future_exports(archive, rep, problem, say)
        for uuid, meta in archive.conversations.items():
            rep.counts["conversations"] += 1
            name = meta.get("name") or uuid
            path = archive.raw_file(meta)
            if not path.is_file():
                rep.broken[uuid] = name
                problem("verify.conv_missing", name=name, file=path.name)
                continue
            try:
                raw = read_raw_file(path)  # (either form: the lines of 2026.11.21.7 or the former whole JSON)
            except (OSError, ValueError, EOFError, KeyError, TypeError, AttributeError) as exc:
                rep.broken[uuid] = name
                problem("verify.conv_unreadable", name=name, file=path.name, error=str(exc))
                continue
            if not isinstance(raw, dict) or raw.get("uuid") != uuid:
                rep.broken[uuid] = name
                problem("verify.conv_unreadable", name=name, file=path.name, error="uuid")
    paths = [folder / n for n in USER_FILES] + sorted((folder / "annotations-copies").glob("*.json"))
    for path in paths:
        if path.is_file():
            rep.counts["files"] += 1
            error = _json_ok(path)
            if error:
                problem("verify.file_unreadable", path=str(path), error=error)
    for name in jsonfile.damaged(site_dir):
        problem("verify.file_damaged", path=str(folder / name))
    _check_libraries(folder, rep, problem)
    zips = sorted((folder / "exports").rglob("*.zip")) if (folder / "exports").is_dir() else []
    for path in zips:
        rep.counts["zips"] += 1
        say("verify.reading", {"path": path.relative_to(folder).as_posix()})
        err = _zip_error(path)
        if err:
            problem(err[0], path=str(path), detail=err[1])
    for path in sorted((folder / "exports").rglob("*.json")) if (folder / "exports").is_dir() else []:
        rep.counts["files"] += 1
        error = _json_ok(path)
        if error:
            problem("verify.file_unreadable", path=str(path), error=error)
    if rep.broken:
        versions = _versions(site_dir, set(rep.broken))
        rep.repairable = [u for u in rep.broken if u in versions]
    if not rep.problems:
        say("verify.ok", dict(rep.counts))
    else:
        say("verify.found", {"n": rep.problems})
        if rep.repairable:
            say("verify.repairable", {"n": len(rep.repairable)})
        lost = len(rep.broken) - len(rep.repairable)
        if lost:
            say("verify.not_repairable", {"n": lost})
    return rep


def _check_libraries(folder: Path, rep: Report, problem: Callable[..., None]) -> None:
    for sub, files_of in (("cdn", lambda v: [v.get("file")]),
                          ("esm", lambda v: [hashlib.sha256(u.encode("utf-8")).hexdigest()[:16] + ".js"
                                             for u in v.get("modules") or [] if isinstance(u, str)])):
        index = folder / sub / "index.json"
        if not index.is_file():
            continue
        rep.counts["files"] += 1
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problem("verify.file_unreadable", path=str(index), error=str(exc))
            continue
        for key, value in (data.items() if isinstance(data, dict) else []):
            if not isinstance(value, dict):
                continue
            for name in files_of(value):
                if isinstance(name, str) and name and not (folder / sub / name).is_file():
                    problem("verify.lib_missing", name=str(key), path=str(folder / sub / name))


def repair(site_dir: Path, uuids: list[str], say: Say) -> int:
    """The conversations given made again from the exports kept; returns how many were. The caller holds the lock."""
    archive = Archive(site_dir)
    wanted = {u for u in uuids if u in archive.conversations}
    versions = _versions(site_dir, wanted)
    done = 0
    for uuid in sorted(wanted, key=lambda u: archive.conversations[u].get("name") or u):
        meta = archive.conversations[uuid]
        found = sorted(versions.get(uuid) or [], key=lambda v: v[0])
        if not found:
            say("verify.repair_none", {"name": meta.get("name") or uuid})
            continue
        shown = [v for v in found if v[0] == meta.get("version_export")] or [found[-1]]
        d0, merged = shown[-1]
        display_hash = _hash(merged)
        for d, raw in found:
            if (d, raw) is not shown[-1]:
                merged, _ = merge_versions(merged, raw, d)
        meta.update(hash=display_hash, version_export=d0)
        archive._store_merged(meta, merged)
        done += 1
        say("verify.repaired", {"name": meta.get("name") or uuid, "n": len(found)})
    archive.save()
    return done


def run(site_dir: Path, say: Say, repair_now: bool | Callable[[int], bool] = False) -> Report:
    """check(), then repair() and redate() when asked (``repair_now`` True, or a question given the number
    repairable)."""
    rep = check(site_dir, say)
    if rep.n_repairable:
        ask = repair_now(rep.n_repairable) if callable(repair_now) else repair_now
        if ask:
            if rep.redate:
                redate(site_dir, rep.redate, say)
            if rep.repairable:
                repair(site_dir, rep.repairable, say)
    return rep
