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
import re
import sys
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any

from pydantic import ValidationError

from . import dates, system
from .i18n import t
from .models import Conversation, TextContent, User, parse_message

_CHUNK = 1 << 20  # 1 MiB
MAX_ELEMENT: int | None = None  # characters of one value read whole (a message, a field) at most; None: element_limit()
MESSAGE_LIMIT: int | None = None  # set by --limite-message (characters): the user agreed to read bigger messages
_READ_FACTOR = 5  # memory to read one message: about 5 times its text (measured 4.2 to 4.5 for an import)


def element_limit() -> int:
    """The biggest value read whole: MAX_ELEMENT if set (tests), else what the free memory of this computer allows
    (a fifth of it, measured factor), at least 64 MiB characters (review of 21/11: not a fixed figure; a message
    beyond it is set aside without being read whole, and the user is asked)."""
    if MAX_ELEMENT is not None:
        return max(MAX_ELEMENT, MESSAGE_LIMIT or 0)
    free = system.available_memory()
    auto = max(64 << 20, (free or (2 << 30)) // _READ_FACTOR)
    return max(auto, MESSAGE_LIMIT or 0)


def _too_big() -> json.JSONDecodeError:
    return json.JSONDecodeError(f"élément JSON de plus de {element_limit() >> 20} Mio", "", 0)


class TooBig:
    """A value too big to be read whole, gone over without keeping it: ``size`` its characters."""

    def __init__(self, size: int) -> None:
        self.size = size


_too_big_seen: list[int] = []  # the sizes of the values set aside since pop_too_big()


def pop_too_big() -> list[int]:
    out = list(_too_big_seen)
    _too_big_seen.clear()
    return out
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


class Events:
    """One JSON object of an array read field by field (step 1 of the reading in pieces, 21/11): iterating gives
    ("field", key, value) for its fields, in their order, and ("item", key, element) one by one for the elements of
    the lists named in ``streamed`` ("chat_messages"): a conversation is never decoded whole, only each message.
    Must be read to its end before the next element of the array. ``assemble()`` makes the dict back."""

    def __init__(self, reader: "_Reader", streamed: tuple[str, ...]) -> None:
        self._events = reader.object_events(streamed)

    def __iter__(self) -> Iterator[tuple]:
        return self._events

    def assemble(self) -> dict[str, Any]:
        """The object as json.loads would give it: the same keys in the same order; a repeated key keeps its first
        place and its last value."""
        out: dict[str, Any] = {}
        for ev in self._events:
            if (ev[0] == "field" and isinstance(ev[2], TooBig)) or (ev[0] == "item" and isinstance(ev[2], TooBig)):
                continue  # set aside (told after the import)
            if ev[0] == "start":
                out[ev[1]] = []
            elif ev[0] == "item":
                out[ev[1]].append(ev[2])
            else:
                out[ev[1]] = ev[2]
        return out


class _Reader:
    """A text file read by blocks of _CHUNK characters: ``buf``/``pos``, refilled on demand. Strict (audit A1): a file
    cut, a missing or doubled comma, a comma before ']' or '}' raise JSONDecodeError (after the elements read)."""

    def __init__(self, f: IO[str], buf: str = "", pos: int = 0, limit: int | None = None) -> None:
        self.f, self.buf, self.pos = f, buf, pos
        self.limit = limit or element_limit()  # (read once: the free memory is not asked at each message)
        self.decoder = json.JSONDecoder()

    def _more(self, want: int = _CHUNK) -> bool:
        chunk = self.f.read(want)
        if not chunk:
            return False
        self.buf, self.pos = self.buf[self.pos:] + chunk, 0
        return True

    def peek(self) -> str | None:
        """The next character after the blanks (not taken), None at the end of the file."""
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos] in " \t\r\n":
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            self.buf, self.pos = "", 0
            if not self._more():
                return None

    def take(self) -> str:
        c = self.peek()
        if c is None:
            raise json.JSONDecodeError("tableau JSON non terminé", "", 0)
        self.pos += 1
        return c

    def value(self) -> Any:
        """One JSON value decoded whole (a message, a title…); the buffer grows (geometrically: linear total cost)
        until it is complete, never beyond MAX_ELEMENT characters."""
        if self.peek() is None:
            raise json.JSONDecodeError("tableau JSON non terminé", "", 0)
        if self.buf[self.pos] in ",]}:":
            raise json.JSONDecodeError("élément attendu", self.buf, self.pos)
        want = _CHUNK
        while True:
            try:
                v, end = self.decoder.raw_decode(self.buf, self.pos)
                # a number cut by the end of the block ("12345." then "678", "1e" then "5") goes on: read on
                cut = isinstance(v, (int, float)) and not isinstance(v, bool) and (
                    end == len(self.buf) or self.buf[end] in ".eE+-0123456789")
                if not cut or not self._more(want):
                    if end - self.pos > self.limit:  # (decoded within one block: let go all the same)
                        size, self.pos = end - self.pos, end
                        _too_big_seen.append(size)
                        return TooBig(size)
                    self.pos = end
                    return v
            except json.JSONDecodeError:
                if not self._more(want):
                    raise
            if len(self.buf) - self.pos > self.limit:
                return self._skip()  # a message too big for the memory: gone over, set aside (21/11)
            want = max(_CHUNK, len(self.buf))

    _STRUCT = re.compile(r'["\\\[\]{}]')

    def _skip(self) -> TooBig:
        """Go over the value beginning at ``pos`` (an object, an array or a string) to its end, a block at a time,
        keeping nothing of it; the reading goes on after it."""
        depth, in_string, escaped, size = 0, False, False, 0
        while True:
            buf, i = self.buf, self.pos
            n = len(buf)
            while i < n:
                if in_string:
                    if escaped:
                        escaped, i = False, i + 1
                        continue
                    q, b = buf.find('"', i), buf.find("\\", i)
                    if b != -1 and (q == -1 or b < q):
                        escaped, i = True, b + 1
                        continue
                    if q == -1:
                        i = n
                        break
                    in_string, i = False, q + 1
                    if depth == 0:
                        size += i - self.pos
                        self.pos = i
                        _too_big_seen.append(size)
                        return TooBig(size)
                    continue
                m = self._STRUCT.search(buf, i)
                if m is None:
                    i = n
                    break
                c, i = m.group(), m.end()
                if c == '"':
                    in_string = True
                elif c in "[{":
                    depth += 1
                else:
                    depth -= 1
                    if depth == 0:
                        size += i - self.pos
                        self.pos = i
                        _too_big_seen.append(size)
                        return TooBig(size)
            size += n - self.pos
            self.buf, self.pos = "", 0
            chunk = self.f.read(_CHUNK)
            if not chunk:
                raise json.JSONDecodeError("tableau JSON non terminé", "", 0)
            self.buf = chunk

    def array(self, streamed: tuple[str, ...] = ()) -> Iterator[Any]:
        """The elements of an array whose '[' is taken; with ``streamed``, each object is given as Events."""
        if self.peek() == "]":
            self.pos += 1
            return
        while True:
            if streamed and self.peek() == "{":
                events = Events(self, streamed)
                yield events
                for _ in events:  # what the caller did not read
                    pass
            else:
                yield self.value()
            c = self.take()
            if c == "]":
                return
            if c != ",":
                raise json.JSONDecodeError("',' attendue", self.buf, self.pos - 1)

    def object_events(self, streamed: tuple[str, ...]) -> Iterator[tuple]:
        if self.take() != "{":
            raise json.JSONDecodeError("'{' attendue", self.buf, self.pos - 1)
        if self.peek() == "}":
            self.pos += 1
            return
        while True:
            if self.peek() != '"':
                raise json.JSONDecodeError("clé attendue", self.buf, self.pos)
            key = self.value()
            if self.take() != ":":
                raise json.JSONDecodeError("':' attendu", self.buf, self.pos - 1)
            if key in streamed and self.peek() == "[":
                self.pos += 1
                yield ("start", key)
                for item in self.array():
                    yield ("item", key, item)
            else:
                yield ("field", key, self.value())
            c = self.take()
            if c == "}":
                return
            if c != ",":
                raise json.JSONDecodeError("',' attendue", self.buf, self.pos - 1)

    def end(self) -> None:
        if self.peek() is not None:  # after ']': blanks only
            raise json.JSONDecodeError("contenu après le tableau JSON", self.buf, self.pos)


def _iter_array(f: IO[str], buf: str, pos: int, streamed: tuple[str, ...] = (), limit: int | None = None) -> Iterator[Any]:
    """Yield the elements of a JSON array one by one. ``buf[pos]`` follows '['. Strict (audit A1, 21/11): a file cut
    before its ']', a missing or doubled comma, a comma before ']' or anything but blanks after ']' raise
    JSONDecodeError (after the elements already read), so that a cut export is never taken for a complete one."""
    reader = _Reader(f, buf, pos, limit)
    yield from reader.array(streamed)
    reader.end()


def iter_json_items(f: IO[str], streamed: tuple[str, ...] = ()) -> Iterator[Any]:
    """Yield the top-level items of a JSON array, a JSONL file, or a single JSON value.

    Arrays and JSONL are streamed. A single object spread over several lines
    has to be loaded whole; if it only wraps a list (``{"conversations": [...]}``)
    the list items are yielded, otherwise the object itself (a project file
    written over several lines, with its list of documents, is one item).
    """
    limit = element_limit()
    buf, pos, eof = _skip_ws(f, "", 0)
    if eof:
        return
    if buf[pos] == "[":
        yield from _iter_array(f, buf, pos + 1, streamed, limit)  # (streamed: the objects as Events, step 1 of 21/11)
        return
    first_line_end = buf.find("\n", pos)
    while first_line_end < 0:
        chunk = f.read(_CHUNK)
        if not chunk:
            first_line_end = len(buf)
            break
        buf += chunk
        if len(buf) > limit:
            raise _too_big()
        first_line_end = buf.find("\n", pos)
    head = buf[pos:first_line_end]
    try:
        first = json.loads(head)
    except json.JSONDecodeError:
        rest = f.read(limit + 1)
        if len(buf) - pos + len(rest) > limit:
            raise _too_big() from None
        whole = json.loads(buf[pos:] + rest)
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
    while True:
        line = f.readline(limit + 1)
        if not line:
            break
        if len(pending) + len(line) > limit:
            raise _too_big()
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
    others: list[Source] = field(default_factory=list)  # JSON files CEV does not use (memories…)


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
    found.others = [s for s in others if s not in found.conversations]
    return found


# --- What an import leaves out (AE-f2) --------------------------------------

# Block types the pages show for what they are; any other one is shown raw ("Contenu de type …").
_SHOWN_BLOCKS = {"text", "thinking", "tool_use", "tool_result", "token_budget",
                 "document", "image", "injected_prompt_block"}
_ID_LIKE = re.compile(r"^[0-9a-f-]{16,}$")


@dataclass
class LeftOut:
    duplicates: int = 0  # conversations met twice: the second one is skipped
    unknown_blocks: Counter[str] = field(default_factory=Counter)  # type -> number of blocks
    broken_blocks: int = 0  # blocks that are not objects with a type: dropped


_left_out = LeftOut()


def pop_left_out() -> LeftOut:
    global _left_out
    out, _left_out = _left_out, LeftOut()
    return out


def _note_blocks(raw: dict[str, Any]) -> None:
    for m in raw.get("chat_messages") or []:
        if not isinstance(m, dict):
            continue
        for b in m.get("content") or []:
            btype = b.get("type") if isinstance(b, dict) else None
            if not isinstance(btype, str) or not btype:
                _left_out.broken_blocks += 1
            elif btype not in _SHOWN_BLOCKS:
                _left_out.unknown_blocks[btype] += 1


def file_categories(sources: list[Source]) -> Counter[str]:
    """Name of each unused file without its number (memories-000.json → memories), else its folder."""
    out: Counter[str] = Counter()
    for s in sources:
        stem = re.sub(r"[-_ ]?\d+$", "", s.name.rsplit(".", 1)[0]) or s.name
        if _ID_LIKE.match(stem) and s.folder:
            stem = s.folder
        out[stem] += 1
    return out


_conversation_read_errors = 0  # files of conversations read with an error since pop_read_errors (audit A1)


def pop_read_errors() -> int:
    """How many files of conversations could not be read to their end since the last call (and reset)."""
    global _conversation_read_errors
    n, _conversation_read_errors = _conversation_read_errors, 0
    return n


STREAMED = ("chat_messages",)  # the lists read element by element (step 1 of the reading in pieces, 21/11)


def _iter_events(sources: list[Source], conversations: bool = False) -> Iterator[Any]:
    """The items of the files, each object of an array as Events (its messages one by one); a read error is told
    (and counted for the files of conversations)."""
    global _conversation_read_errors
    for s in sources:
        try:
            with s.open() as f:
                yield from iter_json_items(f, STREAMED)
        except (json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, OSError) as exc:
            warn(t("warn.read_interrupted", source=s.label, error=type(exc).__name__))
            if conversations:
                _conversation_read_errors += 1


def _iter_raw(sources: list[Source], conversations: bool = False) -> Iterator[Any]:
    """The items whole (each object made back from its events)."""
    for item in _iter_events(sources, conversations):
        yield item.assemble() if isinstance(item, Events) else item


def _load_list(sources: list[Source], model: Any) -> list[Any]:
    out = []
    for raw in _iter_raw(sources):
        try:
            out.append(model.model_validate(raw))
        except ValidationError:
            warn(t("warn.bad_item", kind=model.__name__))
    return out


def _valid_text(raw: dict[str, Any]) -> dict[str, Any]:
    """The conversation, with each lone half of a character (an emoji cut in two, "\\ud83d" in the JSON) replaced
    by "?": such a text cannot be written as UTF-8 and would stop the import (11/11)."""
    text = json.dumps(raw, ensure_ascii=False)
    try:
        text.encode("utf-8")
        return raw
    except UnicodeEncodeError:
        return json.loads(text.encode("utf-8", "replace").decode("utf-8"))


def iter_conversation_records(sources: list[Source]) -> Iterator[tuple[dict[str, Any], Conversation]]:
    """Yield (raw dict, validated conversation) one at a time; unreadable ones and duplicates are skipped.

    The raw dict is what the archive keeps, so that nothing of the export is lost.
    """
    seen: set[str] = set()
    for n, raw in enumerate(_iter_raw(sources, conversations=True)):
        if not isinstance(raw, dict):
            warn(t("warn.not_a_conversation"))
            continue
        if not raw.get("uuid"):
            raw = {**raw, "uuid": f"conversation-{n}"}
        raw = _valid_text(raw)
        try:
            convo = Conversation.model_validate(raw)
        except ValidationError:
            warn(t("warn.bad_conversation"))
            continue
        if convo.uuid in seen:
            _left_out.duplicates += 1
            continue
        seen.add(convo.uuid)
        _note_blocks(raw)
        yield raw, convo


def _valid_value(value: Any) -> Any:
    """_valid_text for one value (a field, a message): each lone half of a character becomes "?"."""
    text = json.dumps(value, ensure_ascii=False)
    try:
        text.encode("utf-8")
        return value
    except UnicodeEncodeError:
        return json.loads(text.encode("utf-8", "replace").decode("utf-8"))


def iter_conversation_spools(sources: list[Source], folder: Path) -> Iterator[tuple[Any, Conversation, bool]]:
    """Step 3b of the reading in pieces (21/11): as iter_conversation_records, the same conversations kept and left
    out with the same warnings, but never whole in memory. Yields (spool, conversation, has_text): ``spool`` an
    archive.RawSpool holding the conversation (its messages in a temporary file of ``folder``, removed when the next
    one is asked); ``conversation`` validated from its fields only (``chat_messages`` empty: a message that cannot be
    read never rejected a conversation, see models._lenient_list); ``has_text`` as not is_empty_conversation."""
    from .archive import RawSpool

    seen: set[str] = set()
    for n, item in enumerate(_iter_events(sources, conversations=True)):
        if isinstance(item, dict):  # (a JSONL line, a single object: already whole)
            events: Any = [("field", k, v) for k, v in item.items() if not (k in STREAMED and isinstance(v, list))]
            for k in STREAMED:
                if isinstance(item.get(k), list):
                    events += [("start", k)] + [("item", k, m) for m in item[k]]
        elif isinstance(item, Events):
            events = item
        else:
            warn(t("warn.not_a_conversation"))
            continue
        with RawSpool(folder) as spool:
            has_text, broken, unknown = False, 0, Counter()
            for ev in events:
                if len(ev) == 3 and isinstance(ev[2], TooBig):
                    continue  # a message (or field) too big for the memory: set aside, told after the import
                if ev[0] == "field":
                    spool.field(ev[1], _valid_value(ev[2]))
                elif ev[0] == "start":
                    spool.start(ev[1])
                else:
                    m = _valid_value(ev[2])
                    spool.item(ev[1], m)
                    if ev[1] != "chat_messages" or not isinstance(m, dict):
                        continue
                    for blk in m.get("content") or []:  # what _note_blocks counts, kept until the conversation is
                        btype = blk.get("type") if isinstance(blk, dict) else None
                        if not isinstance(btype, str) or not btype:
                            broken += 1
                        elif btype not in _SHOWN_BLOCKS:
                            unknown[btype] += 1
                    msg = parse_message(m) if not has_text else None
                    has_text = has_text or bool(msg and any(isinstance(b, TextContent) and b.text.strip() for b in msg.content))
            if not spool.meta.get("uuid"):
                spool.meta["uuid"] = f"conversation-{n}"
            try:
                convo = Conversation.model_validate({k: ([] if k in spool.lists else v) for k, v in spool.meta.items()})
            except ValidationError:
                warn(t("warn.bad_conversation"))
                continue
            if convo.uuid in seen:
                _left_out.duplicates += 1
                continue
            seen.add(convo.uuid)
            _left_out.broken_blocks += broken
            _left_out.unknown_blocks.update(unknown)
            yield spool, convo, has_text


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
    for c in _iter_events(found.conversations):
        # the fields only: the messages are read one by one and let go (a conversation bigger than the memory too)
        fields = [(ev[1], ev[2]) for ev in c if ev[0] == "field"] if isinstance(c, Events) else \
            list(c.items()) if isinstance(c, dict) else []
        for key, value in fields:
            d = _parse_dt(value) if key in ("updated_at", "created_at") else None
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


BIG_MARK = "\x1fCEV-BIG "  # "<mark> size need free" (Mo): a message set aside, the page asks whether to read it
DATE_MARK = "\x1fCEV-DATE "  # "<mark> export clock newest|-" (ISO): read by the server, which asks in the page
FUTURE_MARGIN = _ONE_DAY  # an export date beyond the clock by more: asked (time zones and a computer clock a few hours off)


@dataclass
class DateQuestion:
    """An export date later than the computer's clock (review of 21/11): one of them is wrong. ``newest`` (the
    newest conversation of the export, None if none dated) helps the user tell which; nothing is imported until
    the user chooses."""
    export: datetime
    clock: datetime
    newest: datetime | None


def date_question(found: ExportSources, date: ExportDate, now: datetime | None = None) -> DateQuestion | None:
    """None when the export date is not beyond the clock by more than FUTURE_MARGIN. An export date in the future
    would make that export the latest for ever: every later export taken as older (its changes never shown) and the
    conversations it lacks marked deleted. Reads the conversations (for ``newest``) only in that rare case."""
    now = now or datetime.now(timezone.utc)
    if date.value <= now + FUTURE_MARGIN:
        return None
    return DateQuestion(date.value, now, data_date(found))


def export_date(found: ExportSources, manual: datetime | None = None) -> ExportDate:
    """The date of an export and where it comes from (manual > manifest > manifest nearby > ZIP > data > today)."""
    if manual:
        return ExportDate(manual, t("cli.date_source.manual"))
    d = manifest_date(found)
    if d:
        return ExportDate(d, t("cli.date_source.manifest"))
    latest = data_date(found)
    nearby = nearby_manifest_date(found, latest)
    if nearby:
        return ExportDate(nearby[0], t("cli.date_source.nearby", name=nearby[1]))
    d = zip_date(found)
    if d and (latest is None or d >= latest):
        return ExportDate(d, t("cli.date_source.zip"))
    if latest:
        return ExportDate(latest, t("cli.date_source.data"))
    return ExportDate(datetime.now(timezone.utc), t("cli.date_source.today"))
