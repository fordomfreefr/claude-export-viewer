"""Reading the JSON files of the user's work in archive/ (annotations, topics, settings, files) without ever losing
them (11/11): a file that cannot be read (cut short by a full disk or a bad copy, edited by hand) is renamed
"<name>.illisible-<date>" instead of being treated as empty, which the next change would have written over. The
index tells about it (`damaged`), until the user removes that file."""

from __future__ import annotations

import functools
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

MARK = ".illisible-"


def one_at_a_time() -> Callable[[F], F]:
    """A decorator: the functions it wraps run one at a time (a lock of their own, re-entrant). The server answers
    requests in threads: two changes of the notes at once (two tabs) would otherwise read the same file, each write
    its own version, and one change would be lost (review of 21/11)."""
    lock = threading.RLock()

    def wrap(fn: F) -> F:
        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> Any:
            with lock:
                return fn(*args, **kwargs)
        return run  # type: ignore[return-value]
    return wrap


def read(path: Path) -> Any:
    """The JSON of the file; None when it is missing or unreadable (then moved aside)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        return json.loads(text)
    except ValueError:
        aside = path.with_name(path.name + MARK + datetime.now().strftime("%Y-%m-%d-%H%M%S"))
        try:
            path.rename(aside)
        except OSError:
            pass
        return None


def damaged(site_dir: Path) -> list[str]:
    """The files moved aside, for the index."""
    folder = Path(site_dir) / "archive"
    return sorted(p.name for p in folder.glob("*" + MARK + "*")) if folder.is_dir() else []
