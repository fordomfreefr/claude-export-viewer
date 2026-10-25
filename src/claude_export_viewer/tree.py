"""Conversation trees.

On claude.ai, editing a message or retrying an answer creates a new branch.
The export keeps every branch: each message points to its parent through
``parent_message_uuid``. The page shows the main branch, i.e. the path that
leads to the most recent message, and every other branch in a collapsible
frame placed where it forks off.

Messages that are no longer in the latest export but were kept by the archive
(see archive.py) are part of the same tree; a branch made only of such
messages is labelled "removed on claude.ai".

Exports without ``parent_message_uuid`` are read as a single linear chain.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

EXTRA_KEY = "_cev_extra_messages"  # messages kept by the archive, absent from the latest export
LAST_SEEN = "_cev_last_seen"  # date of the last export holding an extra message
LINEAR_PARENT = "_cev_parent"  # parent of an extra message coming from an export without parent ids
LEGACY_REMOVED_KEY = "_cev_removed_parts"  # earlier archive format (frames of removed messages)


def message_key(msg: Any) -> str:
    if not isinstance(msg, dict):
        return ""
    if msg.get("uuid"):
        return str(msg["uuid"])
    blob = json.dumps([msg.get("sender"), msg.get("created_at"), msg.get("text"), msg.get("content")], sort_keys=True)
    return "h:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def has_text(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    if isinstance(msg.get("text"), str) and msg["text"].strip():
        return True
    blocks = msg.get("content") if isinstance(msg.get("content"), list) else []
    return any(isinstance(b, dict) and b.get("type") == "text" and str(b.get("text") or "").strip() for b in blocks)


def extra_messages(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extra messages of an archived conversation, including the earlier archive format."""
    out = [m for m in raw.get(EXTRA_KEY) or [] if isinstance(m, dict)]
    for group in raw.get(LEGACY_REMOVED_KEY) or []:
        if not isinstance(group, dict):
            continue
        previous = group.get("after")
        for m in group.get("messages") or []:
            if isinstance(m, dict):
                out.append({**m, LINEAR_PARENT: m.get(LINEAR_PARENT, previous), LAST_SEEN: group.get("export")})
                previous = message_key(m)
    return out


@dataclass(eq=False)  # two items are the same only if they are the same object
class Item:
    key: str
    parent: str | None
    created: str
    order: int
    last_seen: str | None  # set for messages absent from the latest export
    payload: Any
    children: list[Item] = field(default_factory=list)

    @property
    def gone(self) -> bool:
        return self.last_seen is not None


def items_from_raw(raw: dict[str, Any]) -> list[Item]:
    current = [m for m in raw.get("chat_messages") or [] if isinstance(m, dict)]
    with_parents = any(m.get("parent_message_uuid") for m in current)
    items: list[Item] = []
    previous: str | None = None
    for m in current:
        k = message_key(m)
        parent = (m.get("parent_message_uuid") or None) if with_parents else previous
        items.append(Item(k, parent, str(m.get("created_at") or ""), len(items), None, m))
        previous = k
    for m in extra_messages(raw):
        parent = m.get("parent_message_uuid") or m.get(LINEAR_PARENT) or None
        items.append(Item(message_key(m), parent, str(m.get("created_at") or ""), len(items),
                          str(m.get(LAST_SEEN) or "?"), m))
    return items


def _link(items: list[Item]) -> list[Item]:
    by_key: dict[str, Item] = {}
    for it in items:
        it.children.clear()  # the same items may be rendered more than once
        by_key.setdefault(it.key, it)  # duplicate keys: first one wins
    roots = []
    for it in by_key.values():
        parent = by_key.get(it.parent) if it.parent else None
        if parent is None or parent is it:
            roots.append(it)
        else:
            parent.children.append(it)
    # Guard against cycles: anything unreachable from a root becomes a root.
    reachable = set()
    stack = list(roots)
    while stack:
        n = stack.pop()
        if id(n) in reachable:
            continue
        reachable.add(id(n))
        stack.extend(n.children)
    for it in by_key.values():
        if id(it) not in reachable:
            if it.parent in by_key:
                by_key[it.parent].children.remove(it)
            roots.append(it)
            stack = [it]
            while stack:
                n = stack.pop()
                if id(n) not in reachable:
                    reachable.add(id(n))
                    stack.extend(n.children)
    order = lambda n: (n.created, n.order)  # noqa: E731
    for it in by_key.values():
        it.children.sort(key=order)
    roots.sort(key=order)
    return roots


def _leaves(root: Item) -> list[Item]:
    out, stack = [], [root]
    while stack:
        n = stack.pop()
        if n.children:
            stack.extend(n.children)
        else:
            out.append(n)
    return out


def _best_leaf(roots: list[Item]) -> Item | None:
    leaves = [leaf for r in roots for leaf in _leaves(r)]
    if not leaves:
        return None
    # The most recent message, preferring messages still present on claude.ai.
    return max(leaves, key=lambda n: (not n.gone, n.created, n.order))


def _root_of(roots: list[Item], leaf: Item) -> Item:
    return next(r for r in roots if any(x is leaf for x in _leaves(r)))


def _path(root: Item, leaf: Item) -> list[Item]:
    parents: dict[int, Item | None] = {id(root): None}
    stack = [root]
    while stack:
        n = stack.pop()
        if n is leaf:
            break
        for c in n.children:
            parents[id(c)] = n
            stack.append(c)
    path, cur = [], leaf
    while cur is not None:
        path.append(cur)
        cur = parents.get(id(cur))
    return path[::-1]


def _size(root: Item) -> tuple[int, bool]:
    """Number of messages in the subtree, and whether all of them are gone."""
    n, all_gone, stack = 0, True, [root]
    while stack:
        it = stack.pop()
        n += 1
        all_gone = all_gone and it.gone
        stack.extend(it.children)
    return n, all_gone


@dataclass
class Branch:
    """Information given to the frame renderer."""

    first: Item
    size: int
    removed: bool  # every message of the branch is gone from claude.ai
    content: list[str]


def main_path(items: list[Item]) -> list[Item]:
    roots = _link(items)
    leaf = _best_leaf(roots)
    if leaf is None:
        return []
    return _path(_root_of(roots, leaf), leaf)


def render(
    items: list[Item],
    render_item: Callable[[Item], str],
    render_branch: Callable[[Branch], str],
) -> tuple[list[str], list[Item]]:
    """HTML pieces of the conversation (main branch with frames), and the main branch."""
    roots = _link(items)
    leaf = _best_leaf(roots)
    if leaf is None:
        return [], []

    def line(root: Item, end: Item | None) -> tuple[list[str], list[Item]]:
        target = end if end is not None else _best_leaf([root])
        path = _path(root, target) if target is not None else [root]
        out: list[str] = []
        for i, node in enumerate(path):
            out.append(render_item(node))
            following = path[i + 1] if i + 1 < len(path) else None
            for child in node.children:
                if child is not following:
                    out.append(frame(child))
        return out, path

    def frame(child: Item) -> str:
        content, _ = line(child, None)
        size, removed = _size(child)
        return render_branch(Branch(child, size, removed, content))

    main_root = _root_of(roots, leaf)
    pieces = [frame(r) for r in roots if r is not main_root]
    main_pieces, path = line(main_root, leaf)
    return pieces + main_pieces, path


@dataclass
class Summary:
    """What the index shows about a conversation's tree."""

    other_versions: int = 0  # "Autre version" frames
    removed_parts: int = 0  # "Partie supprimée sur claude.ai" frames
    last_message: str = ""  # ISO date of the most recent message, all branches included


def summarize(items: list[Item]) -> Summary:
    s = Summary()

    def count(branch: Branch) -> str:
        if branch.removed:
            s.removed_parts += 1
        else:
            s.other_versions += 1
        return ""

    render(items, lambda item: "", count)
    s.last_message = max((it.created for it in items if it.created), default="")
    return s
