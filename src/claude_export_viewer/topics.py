"""Topics chosen by the user for the conversations ("math", "medicine"…): archive/topics.json.

One topic at most per conversation. The list is kept in the order of creation.
The index page reads them from ``topics-data.js`` (written in the site folder at
every build and every change), so that filtering also works on a page opened as
a file; changing them goes through the local server.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

FILE = "topics.json"
DATA_JS = "topics-data.js"
MAX_LENGTH = 40


class TopicError(ValueError):
    """A refused change; ``key`` is the i18n key of the message (with ``params``)."""

    def __init__(self, key: str, **args: Any) -> None:
        super().__init__(key)
        self.key, self.params = key, args


def _path(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FILE


def load(site_dir: Path) -> dict[str, Any]:
    """{"topics": [names], "assign": {conversation uuid: name}} (cleaned: no unknown name)."""
    try:
        data = json.loads(_path(site_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    names = [n for n in data.get("topics", []) if isinstance(n, str) and n.strip()] \
        if isinstance(data.get("topics"), list) else []
    assign = data.get("assign") if isinstance(data.get("assign"), dict) else {}
    return {"topics": names, "assign": {u: n for u, n in assign.items() if isinstance(u, str) and n in names}}


def save(site_dir: Path, data: dict[str, Any]) -> None:
    path = _path(site_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    write_data_js(site_dir, data)


def write_data_js(site_dir: Path, data: dict[str, Any] | None = None) -> None:
    """The topics for the index page (a script, so that a page opened as a file can read it)."""
    data = load(site_dir) if data is None else data
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    (Path(site_dir) / DATA_JS).write_text(f"window.CEV_TOPICS = {text};\n", encoding="utf-8")


def _clean(name: Any) -> str:
    if not isinstance(name, str):
        raise TopicError("web.topics.bad_name")
    name = " ".join(name.split())
    if not name:
        raise TopicError("web.topics.bad_name")
    if len(name) > MAX_LENGTH:
        raise TopicError("web.topics.too_long", n=MAX_LENGTH)
    return name


def _find(names: list[str], name: str) -> str | None:
    """The existing topic with this name, whatever the case."""
    folded = name.casefold()
    return next((n for n in names if n.casefold() == folded), None)


def change(site_dir: Path, request: dict[str, Any], known: set[str]) -> dict[str, Any]:
    """Apply one change and return the new state. ``known`` are the uuids of the archive.

    {"action": "assign", "uuid": …, "topic": name or ""}   ("" removes the topic;
                                                            a new name is created)
    {"action": "rename", "topic": old, "name": new}       (into an existing name: merged)
    {"action": "delete", "topic": name}                   (its conversations lose it)
    """
    data = load(site_dir)
    names, assign = data["topics"], data["assign"]
    action = request.get("action")
    if action == "assign":
        uuid = request.get("uuid")
        if not isinstance(uuid, str) or uuid not in known:
            raise TopicError("web.topics.unknown_conversation")
        topic = request.get("topic")
        if topic in ("", None):
            assign.pop(uuid, None)
        else:
            name = _clean(topic)
            existing = _find(names, name)
            if existing is None:
                names.append(name)
                existing = name
            assign[uuid] = existing
    elif action == "rename":
        old = _find(names, _clean(request.get("topic")))
        if old is None:
            raise TopicError("web.topics.unknown_topic")
        new = _clean(request.get("name"))
        target = _find([n for n in names if n != old], new)
        if target is None:  # a plain rename (possibly only of the case)
            names[names.index(old)] = new
            target = new
        else:  # into another existing topic: merged
            names.remove(old)
        for uuid, n in assign.items():
            if n == old:
                assign[uuid] = target
    elif action == "delete":
        old = _find(names, _clean(request.get("topic")))
        if old is None:
            raise TopicError("web.topics.unknown_topic")
        names.remove(old)
        data["assign"] = {u: n for u, n in assign.items() if n != old}
    else:
        raise TopicError("server.bad_request")
    save(site_dir, data)
    return data
