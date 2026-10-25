"""Streaming loader for Claude.ai data exports.

Accepts any mix of:
  - export ZIP files (the old single ZIP, or the newer split ZIPs such as
    ``conversations-000.zip``, ``projects-000.zip``...),
  - folders where those ZIPs were extracted,
  - individual ``.json`` / ``.jsonl`` files.

Conversations are read and yielded one at a time, so memory use stays small
whatever the size of the export.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any

from pydantic import ValidationError

from . import dates
from .i18n import t
from .models import Conversation, User

_CHUNK = 1 << 20  # 1 MiB
_ONE_DAY = timedelta(days=1)
_JSON_SUFFIXES = (".json", ".jsonl")


# --- Streaming JSON ----------------------------------------------------------


def _skip_ws(f: IO[str], buf: str, pos: int, extra: str = "") -> tuple[str, int, bool]:
    """Skip whitespace (and ``extra`` characters); refill the buffer as needed."""
    skip = " \t\r\n" + extra
    while True:
        while pos < len(buf) and buf[pos] in skip:
            pos += 1
        if pos < len(buf):
            return buf, pos, False
        chunk = f.read(_CHUNK)
        if not chunk:
            return "", 0, True
        buf, pos = chunk, 0


def _iter_array(f: IO[str], buf: str, pos: int) -> Iterator[Any]:
    """Yield the elements of a JSON array one by one. ``buf[pos]`` follows '['."""
    decoder = json.JSONDecoder()
    eof = False
    while True:
        buf, pos, eof_ws = _skip_ws(f, buf, pos, ",")
        if eof_ws or buf[pos] == "]":
            return
        want = _CHUNK
        while True:
            try:
                obj, end = decoder.raw_decode(buf, pos)
                break
            except json.JSONDecodeError:
                if eof:
                    raise
                chunk = f.read(want)
                if not chunk:
                    eof = True
                buf, pos = buf[pos:] + chunk, 0
                want = max(_CHUNK, len(buf))  # geometric growth: linear total cost
        yield obj
        buf, pos = buf[end:], 0


def iter_json_items(f: IO[str]) -> Iterator[Any]:
    """Yield the top-level items of a JSON array, a JSONL file, or a single JSON value.

    Arrays and JSONL are streamed. A single object spread over several lines
    has to be loaded whole; if it only wraps a list (``{"conversations": [...]}``)
    the list items are yielded, otherwise the object itself (a project file
    written over several lines, with its list of documents, is one item).
    """
    buf, pos, eof = _skip_ws(f, "", 0)
    if eof:
        return
    if buf[pos] == "[":
        yield from _iter_array(f, buf, pos + 1)
        return
    first_line_end = buf.find("\n", pos)
    while first_line_end < 0:
        chunk = f.read(_CHUNK)
        if not chunk:
            first_line_end = len(buf)
            break
        buf += chunk
        first_line_end = buf.find("\n", pos)
    head = buf[pos:first_line_end]
    try:
        first = json.loads(head)
    except json.JSONDecodeError:
        whole = json.loads(buf[pos:] + f.read())
        if isinstance(whole, dict) and len(whole) == 1 and isinstance(next(iter(whole.values())), list):
            yield from next(iter(whole.values()))
            return
        yield whole
        return
    # JSONL (or a one-line JSON document)
    yield first
    lines = buf[first_line_end:].split("\n")
    pending = lines.pop()  # possibly a partial line, completed by the next read
    for line in lines:
        yield from _jsonl_line(line)
    for line in f:
        yield from _jsonl_line(pending + line)
        pending = ""
    yield from _jsonl_line(pending)


def _jsonl_line(line: str) -> Iterator[Any]:
    line = line.strip()
    if line:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            warn(t("warn.bad_json_line"))


def _looks_like_conversation(obj: Any) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("chat_messages"), list)


# --- Locating the files of an export -----------------------------------------


@dataclass
class Source:
    """A JSON/JSONL document found in the inputs (on disk or inside a ZIP)."""

    label: str
    name: str  # base file name, lower case
    open: Callable[[], AbstractContextManager[IO[str]]]
    timestamp: datetime | None = None  # date stored in the ZIP for this member
    folder: str = ""  # name of the folder holding the file, lower case (e.g. "projects")
    origin: Path | None = None  # file on disk (the ZIP itself for a ZIP member)

    @property
    def kind(self) -> str:
        n = self.name
        if "manifest" in n:
            return "manifests"
        if "conversation" in n:
            return "conversations"
        if n.startswith("users") or n.startswith("user."):
            return "users"
        # Newer exports store one file per project: projects/<id>.json
        if "project" in n or self.folder == "projects":
            return "projects"
        return "other"


def _text(stream: IO[bytes]) -> IO[str]:
    return io.TextIOWrapper(stream, encoding="utf-8", errors="replace")


class _ZipMember:
    def __init__(self, zip_path: Path, member: str) -> None:
        self.zip_path, self.member = zip_path, member

    @contextmanager
    def __call__(self) -> Iterator[IO[str]]:
        with zipfile.ZipFile(self.zip_path) as zf, zf.open(self.member) as raw, _text(raw) as stream:
            yield stream


def _sources_in_zip(path: Path) -> list[Source]:
    out = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(_JSON_SUFFIXES):
                continue
            parts = info.filename.lower().split("/")
            base, folder = parts[-1], (parts[-2] if len(parts) > 1 else "")
            try:
                stamp: datetime | None = datetime(*info.date_time)
            except ValueError:
                stamp = None
            out.append(
                Source(f"{path.name}:{info.filename}", base, _ZipMember(path, info.filename), stamp, folder, path)
            )
    return out


def find_sources(inputs: Iterable[Path]) -> list[Source]:
    sources: list[Source] = []
    for p in inputs:
        p = Path(p).expanduser()
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and (child.suffix.lower() in _JSON_SUFFIXES or child.suffix.lower() == ".zip"):
                    sources.extend(find_sources([child]))
        elif p.suffix.lower() == ".zip":
            try:
                sources.extend(_sources_in_zip(p))
            except zipfile.BadZipFile:
                warn(t("warn.bad_zip", name=p.name))
        elif p.suffix.lower() in _JSON_SUFFIXES:
            # An extracted file keeps the date stored in the ZIP as its modification time.
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            sources.append(
                Source(
                    p.name,
                    p.name.lower(),
                    lambda p=p: p.open("r", encoding="utf-8", errors="replace"),
                    mtime,
                    p.parent.name.lower(),
                    p,
                )
            )
    return sources


# --- Warnings ----------------------------------------------------------------

_warnings: dict[str, int] = {}


def warn(message: str) -> None:
    _warnings[message] = _warnings.get(message, 0) + 1


def pop_warnings() -> dict[str, int]:
    out = dict(_warnings)
    _warnings.clear()
    return out


# --- Public API --------------------------------------------------------------


@dataclass
class ExportSources:
    conversations: list[Source] = field(default_factory=list)
    users: list[Source] = field(default_factory=list)
    projects: list[Source] = field(default_factory=list)
    manifests: list[Source] = field(default_factory=list)


def classify(inputs: Iterable[Path]) -> ExportSources:
    found = ExportSources()
    others = []
    for s in find_sources(inputs):
        if s.kind == "other":
            others.append(s)
        else:
            getattr(found, s.kind).append(s)
    if not found.conversations:
        # Unknown naming scheme: keep any file whose first item is a conversation.
        for s in others:
            try:
                with s.open() as f:
                    first = next(iter_json_items(f), None)
            except (json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, OSError):
                continue
            if _looks_like_conversation(first):
                found.conversations.append(s)
    return found


def _iter_raw(sources: list[Source]) -> Iterator[Any]:
    for s in sources:
        try:
            with s.open() as f:
                yield from iter_json_items(f)
        except (json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, OSError) as exc:
            warn(t("warn.read_interrupted", source=s.label, error=type(exc).__name__))


def _load_list(sources: list[Source], model: Any) -> list[Any]:
    out = []
    for raw in _iter_raw(sources):
        try:
            out.append(model.model_validate(raw))
        except ValidationError:
            warn(t("warn.bad_item", kind=model.__name__))
    return out


def iter_conversation_records(sources: list[Source]) -> Iterator[tuple[dict[str, Any], Conversation]]:
    """Yield (raw dict, validated conversation) one at a time; unreadable ones and duplicates are skipped.

    The raw dict is what the archive keeps, so that nothing of the export is lost.
    """
    seen: set[str] = set()
    for n, raw in enumerate(_iter_raw(sources)):
        if not isinstance(raw, dict):
            warn(t("warn.not_a_conversation"))
            continue
        if not raw.get("uuid"):
            raw = {**raw, "uuid": f"conversation-{n}"}
        try:
            convo = Conversation.model_validate(raw)
        except ValidationError:
            warn(t("warn.bad_conversation"))
            continue
        if convo.uuid in seen:
            continue
        seen.add(convo.uuid)
        yield raw, convo


# --- Export date -------------------------------------------------------------


@dataclass
class ExportDate:
    value: datetime  # timezone-aware (UTC)
    source: str  # where the date comes from, shown to the user ("manifeste fourni"...)


def manifest_date(found: ExportSources) -> datetime | None:
    """Creation date written in the export manifest, if exactly one manifest was given."""
    found_dates: set[datetime] = set()
    for s in found.manifests:
        try:
            with s.open() as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data.get("created_at") and "data_files" in data:
            try:
                found_dates.add(dates.utc(datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))))
            except ValueError:
                pass
    if len(found_dates) > 1:
        warn(t("warn.several_manifests"))
        return None
    return next(iter(found_dates), None)


def zip_date(found: ExportSources) -> datetime | None:
    """Date stored in the ZIP for the conversations file(s), when it looks plausible."""
    stamps = [dates.utc(s.timestamp) for s in found.conversations if s.timestamp]
    if not stamps:
        return None
    stamp = max(stamps)
    if stamp.year < 2023 or stamp > datetime.now(timezone.utc) + _ONE_DAY:
        return None
    return stamp


def _parse_dt(value: Any) -> datetime | None:
    d = dates.parse(value)
    return dates.utc(d) if d is not None else None


def data_date(found: ExportSources) -> datetime | None:
    """Most recent date found in the conversations: an export is always created after it."""
    latest: datetime | None = None
    for c in _iter_raw(found.conversations):
        if not isinstance(c, dict):
            continue
        for value in (c.get("updated_at"), c.get("created_at")):
            d = _parse_dt(value)
            if d and (latest is None or d > latest):
                latest = d
    return latest


def nearby_manifest_date(found: ExportSources, not_before: datetime | None) -> tuple[datetime, str] | None:
    """Manifest lying next to the conversations file, matching this export.

    Several manifests may sit in the same folder (one per export). The export
    was created after its most recent message, so the right manifest is the
    first one created at or after ``not_before``.
    """
    folders = {s.origin.parent for s in found.conversations if s.origin is not None}
    candidates = []
    for folder in folders:
        for path in folder.glob("*manifest*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or "data_files" not in data:
                continue
            d = _parse_dt(data.get("created_at"))
            if d and (not_before is None or d >= not_before):
                candidates.append((d, path.name))
    return min(candidates) if candidates else None


def load_users(sources: ExportSources) -> list[User]:
    return _load_list(sources.users, User)


def load_project_names(sources: ExportSources) -> dict[str, str]:
    """Only uuid -> name (projects can embed large documents we do not need)."""
    names = {}
    for raw in _iter_raw(sources.projects):
        if isinstance(raw, dict) and raw.get("uuid"):
            names[str(raw["uuid"])] = str(raw.get("name") or "")
    return names


def print_warnings(stream: IO[str] = sys.stderr) -> None:
    for message, count in pop_warnings().items():
        print("  " + t("cli.warning", message=message) + (f" (×{count})" if count > 1 else ""), file=stream)
