"""Text of the conversations for the search in the content (index page).

``search-data.js`` (site folder) holds, for each conversation page, what the page shows
of the messages (every version) — only what you wrote and Claude's answers: not the tool
calls and results, the thinking, the documents made by Claude or the instructions added by
claude.ai. It is taken from the HTML of the page itself, with the rules of the highlighting
on the page (static/msg.js), so that the index counts exactly the passages the page shows:

- ``t``: the text of the messages, one text node after another, separated by U+0001 (a
  word never spans two nodes, as on the page);
- ``m``: the TeX of each formula (a formula holding a word is one passage).

Both are lower case and without accents, character by character as in the browser: NFD,
combining accents U+0300-U+036F removed (except the
overlays U+0334-U+0338: "≠" stays "≠"), then lower case. The data is kept in parts (Store, below),
updated when a page is generated again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DATA_JS = "search-data.js"  # the earlier storage (one file), removed when found
SEPARATOR = "\u0001"
_ACCENTS = re.compile("[̀-̳̹-ͯ]")  # overlays kept: "≠" is not "="
_SKIP = {"tool-use", "tool-result", "thinking", "unknown-block"}  # as msg.js
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def _norm_char(c: str) -> str:
    return _ACCENTS.sub("", unicodedata.normalize("NFD", c)).lower()


def normalize(text: str) -> str:
    """As norm() in the browser, applied to each character (as the highlighting does)."""
    return "".join(_norm_char(c) for c in text)


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool, bool]] = []  # tag, in text, skipped, in formula
        self.texts: list[str] = []
        self.formulas: list[str] = []
        self.tex: list[str] | None = None

    def _state(self) -> tuple[bool, bool, bool]:
        return self.stack[-1][1:] if self.stack else (False, False, False)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID:
            return
        classes = set((dict(attrs).get("class") or "").split())
        text, skipped, formula = self._state()
        text = text or "content-text" in classes
        skipped = skipped or bool(classes & _SKIP) or tag in ("button", "script", "style", "textarea")
        if "math" in classes and not formula and text and not skipped:
            self.tex = []
            formula = True
        self.stack.append((tag, text, skipped, formula))

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID or not any(t == tag for t, *_ in self.stack):
            return
        while self.stack:
            t, _, _, formula = self.stack.pop()
            if t == tag:
                break
        if self.tex is not None and not self._state()[2]:
            self.formulas.append("".join(self.tex))
            self.tex = None

    def handle_data(self, data: str) -> None:
        text, skipped, formula = self._state()
        if formula and self.tex is not None:
            self.tex.append(data)
        elif text and not skipped and not formula:
            self.texts.append(data)


def from_page(page_html: str) -> dict[str, Any]:
    """What the search uses of a conversation page."""
    p = _Extractor()
    p.feed(page_html)
    p.close()
    return {"t": SEPARATOR.join(normalize(t) for t in p.texts if t.strip()),
            "m": [normalize(f) for f in p.formulas]}


# --- Storage: parts of about PART_SIZE conversations ---------------------------------------------
#
# The text of thousands of conversations is too much to read, write or load at once (35 MB for 1000
# conversations of 30 messages). It is kept ONCE, in the site folder, in parts: search/pNNN.js
# (``CEV_SEARCH_PART({page key: {t, m}})``), a conversation going to the part its uuid falls into
# (hash modulo a power of two, so that the parts stay of about PART_SIZE conversations and only change
# when the archive doubles). search/index.json (for the program: the keys of each part) and
# search/index.js (for the browser: the list of the parts). The page signature of each conversation's
# data is in the archive meta ("search"), so that nothing is read to know what changed: a part is
# loaded only to update one of its conversations, written only when changed, and the builder handles the
# conversations part by part (one part in memory). The browser reads the parts one after the other
# (static/search.js).

FOLDER = "search"
PART_SIZE = 100
VERSION = 2


def parts_for(n: int) -> int:
    """Number of parts for n conversations: a power of two, about PART_SIZE conversations each."""
    k = 1
    while k * PART_SIZE < n:
        k *= 2
    return k


def _bucket(uuid: str, n: int) -> str:
    return f"p{int(hashlib.sha1(uuid.encode('utf-8')).hexdigest()[:8], 16) % n:03d}"


_PREFIX, _SUFFIX = "CEV_SEARCH_PART(", ");\n"


class Store:
    """The search data of the site, read and written part by part (see above)."""

    def __init__(self, site_dir: Path, keys: dict[str, str]) -> None:
        self.dir = Path(site_dir) / FOLDER
        self.keys = keys                                  # uuid -> page key, every conversation of the site
        self.uuid_of = {k: u for u, k in keys.items()}
        self.n = parts_for(len(keys))
        self.index = self._read_index()                  # part name -> keys
        self.loaded: dict[str, dict[str, Any]] = {}
        self.dirty: set[str] = set()
        self.reads = 0                                    # parts read (tests)
        self.legacy_hashes: dict[str, str] = {}           # uuid -> page signature, from the earlier storage
        if self.index.get("n") != self.n:                # more parts now (or none yet): spread again
            self._spread()

    def part_of(self, uuid: str) -> str:
        return _bucket(uuid, self.n)

    def _read_index(self) -> dict[str, Any]:
        try:
            data = json.loads((self.dir / "index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) and data.get("v") == VERSION else {}

    def _load(self, name: str) -> dict[str, Any]:
        if name not in self.loaded:
            data: dict[str, Any] = {}
            try:
                text = (self.dir / f"{name}.js").read_text(encoding="utf-8")
                if text.startswith(_PREFIX) and text.endswith(_SUFFIX):
                    data = json.loads(text[len(_PREFIX):-len(_SUFFIX)])
                self.reads += 1
            except (OSError, ValueError):
                data = {}
            self.loaded[name] = data
        return self.loaded[name]

    def _spread(self) -> None:
        """Into self.n parts: what the parts hold (another number of parts), else the search data of the
        earlier program (archive/search.json, one file), read once; the old files are removed after."""
        old_parts = self.index.get("parts") or {}
        gathered: dict[str, Any] = {}
        for name in old_parts:
            gathered.update(self._load(name))
        self.loaded.clear()
        self.legacy_hashes: dict[str, str] = {}
        legacy = self.dir.parent / "archive" / "search.json"
        if not old_parts and legacy.is_file():
            try:
                old = json.loads(legacy.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                old = {}
            for uuid, e in old.items() if isinstance(old, dict) else []:
                if uuid in self.keys and isinstance(e, dict) and isinstance(e.get("data"), dict):
                    gathered[self.keys[uuid]] = e["data"]
                    self.legacy_hashes[uuid] = str(e.get("hash") or "")
        self.index = {"v": VERSION, "n": self.n, "parts": {}}
        for key, data in gathered.items():
            uuid = self.uuid_of.get(key)
            if uuid:
                self._put_key(self.part_of(uuid), key, data)
        self.flush()
        self._write_index(force=True)
        for name in old_parts:
            if name not in self.index["parts"]:
                (self.dir / f"{name}.js").unlink(missing_ok=True)
        for f in (legacy, self.dir.parent / DATA_JS):     # the earlier storage, in one file, twice
            f.unlink(missing_ok=True)

    def has(self, uuid: str) -> bool:
        name = self.part_of(uuid)
        return self.keys[uuid] in (self.index["parts"].get(name) or []) and (self.dir / f"{name}.js").is_file()

    def _put_key(self, name: str, key: str, data: dict[str, Any]) -> None:
        self._load(name)[key] = data
        self.dirty.add(name)

    def put(self, uuid: str, data: dict[str, Any]) -> None:
        self._put_key(self.part_of(uuid), self.keys[uuid], data)

    def focus(self, name: str) -> None:
        """Write and forget the parts other than ``name`` (the builder goes part by part)."""
        for other in [n for n in self.loaded if n != name]:
            self._write_part(other)
            del self.loaded[other]

    def _write_part(self, name: str) -> None:
        if name not in self.dirty:
            return
        data = self.loaded[name]
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{name}.js.tmp"
        tmp.write_text(_PREFIX + json.dumps(data, ensure_ascii=False) + _SUFFIX, encoding="utf-8")
        os.replace(tmp, self.dir / f"{name}.js")
        self.index["parts"][name] = sorted(data)
        self.dirty.discard(name)

    def flush(self) -> None:
        for name in list(self.loaded):
            self._write_part(name)
        self.loaded.clear()

    def finish(self) -> None:
        """Remove the conversations gone from the site (only the parts holding one are read), write what
        changed, and the index files when they changed."""
        known = set(self.uuid_of)
        for name, keys in list(self.index["parts"].items()):
            gone = [k for k in keys if k not in known or self.part_of(self.uuid_of[k]) != name]
            if gone:
                data = self._load(name)
                for k in gone:
                    data.pop(k, None)
                self.dirty.add(name)
        self.flush()
        for name, keys in list(self.index["parts"].items()):
            if not keys:
                del self.index["parts"][name]
                (self.dir / f"{name}.js").unlink(missing_ok=True)
        self._write_index()

    def _write_index(self, force: bool = False) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.index, ensure_ascii=False, sort_keys=True)
        path = self.dir / "index.json"
        if not force and path.is_file() and path.read_text(encoding="utf-8") == text:
            return
        path.write_text(text, encoding="utf-8")
        parts = sorted(f"{name}.js" for name in self.index["parts"])
        (self.dir / "index.js").write_text(f"window.CEV_SEARCH_INDEX = {json.dumps({'v': VERSION, 'parts': parts})};\n",
                                           encoding="utf-8")


def read_all(site_dir: Path) -> dict[str, Any]:
    """Every conversation's data, by page key (tests, diagnosis): never used by the builder."""
    store_dir = Path(site_dir) / FOLDER
    try:
        index = json.loads((store_dir / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, Any] = {}
    for name in index.get("parts", {}):
        text = (store_dir / f"{name}.js").read_text(encoding="utf-8")
        out.update(json.loads(text[len(_PREFIX):-len(_SUFFIX)]))
    return out
