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
overlays U+0334-U+0338: "≠" stays "≠"), then lower case. The data of each conversation
is kept in ``archive/search.json``, updated when its page is generated again.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DATA_JS = "search-data.js"
CACHE = "search.json"
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


def load_cache(site_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads((Path(site_dir) / "archive" / CACHE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(site_dir: Path, cache: dict[str, Any], keys: dict[str, str]) -> None:
    """Keep the cache of the conversations still there; write search-data.js (``keys``: uuid -> page key)."""
    cache = {u: e for u, e in cache.items() if u in keys and isinstance(e.get("data"), dict)}
    path = Path(site_dir) / "archive" / CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(CACHE + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    data = {keys[u]: e["data"] for u, e in cache.items()}
    js = Path(site_dir) / DATA_JS
    tmp = js.with_name(DATA_JS + ".tmp")
    tmp.write_text("window.CEV_SEARCH = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    os.replace(tmp, js)
