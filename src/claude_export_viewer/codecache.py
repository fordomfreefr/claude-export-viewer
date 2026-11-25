"""Highlighted code kept from one rebuild to the next (15/11).

After an update of the program every page is made again, and the colouring of the code by Pygments was the largest
part left (measured at the user's: about 40 % of a rebuild), though the same code gives the same colours. The HTML
of each block is kept in one SQLite file of the user's cache (cev-highlight.sqlite, next to the sounds read aloud),
keyed by the version of Pygments, the language and the code. A cache: any error leaves the colouring as it was,
a file grown over MAX_BYTES is started again; the uninstall removes it.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import threading
from pathlib import Path

MAX_BYTES = 100_000_000
_lock = threading.Lock()
_db: sqlite3.Connection | None = None
_broken = False


def path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cev-highlight.sqlite"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "cev-highlight.sqlite"


def _key(lang: str, code: str) -> str:
    import pygments
    return hashlib.sha256(f"{pygments.__version__}\0{lang}\0{code}".encode("utf-8", "surrogatepass")).hexdigest()


def _open() -> sqlite3.Connection | None:
    global _db, _broken
    if _db is not None or _broken:
        return _db
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > MAX_BYTES:
            p.unlink()
        db = sqlite3.connect(str(p), timeout=5, isolation_level=None, check_same_thread=False)
        db.execute("PRAGMA synchronous=OFF")
        db.execute("CREATE TABLE IF NOT EXISTS h (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        _db = db
    except (OSError, sqlite3.Error):
        _broken = True
    return _db


def get(lang: str, code: str) -> str | None:
    global _broken
    with _lock:
        db = _open()
        if db is None:
            return None
        try:
            row = db.execute("SELECT v FROM h WHERE k = ?", (_key(lang, code),)).fetchone()
        except sqlite3.Error:
            _broken = True
            return None
    return row[0] if row else None


def put(lang: str, code: str, html: str) -> None:
    global _broken
    with _lock:
        db = _open()
        if db is None:
            return
        try:
            db.execute("INSERT OR REPLACE INTO h (k, v) VALUES (?, ?)", (_key(lang, code), html))
        except sqlite3.Error:
            _broken = True
