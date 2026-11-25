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
    forced: bool = False  # the end of the main branch, whatever comes after (one part of a very long conversation)

    @property
    def gone(self) -> bool:
        return self.last_seen is not None


_ARTIFACT_FIELDS = ("type", "title", "language")


def _inherit_artifact_fields(items: list[Item]) -> None:
    """A ``rewrite`` / ``update`` of an artifact holds only its id and content: it takes the type, title
    and language of the earlier blocks with the same id (in time order), so that code stays code. The
    raw messages are copied where a field is added, never changed in place."""
    known: dict[str, dict[str, Any]] = {}
    for item in sorted(items, key=lambda it: (it.created, it.order)):
        msg = item.payload
        blocks = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(blocks, list):
            continue
        new_blocks, changed = [], False
        for b in blocks:
            inp = b.get("input") if isinstance(b, dict) and b.get("type") == "tool_use" \
                and b.get("name") == "artifacts" else None
            if isinstance(inp, dict) and isinstance(inp.get("id"), str) and inp["id"]:
                seen = known.setdefault(inp["id"], {})
                missing = {k: seen[k] for k in _ARTIFACT_FIELDS if not inp.get(k) and seen.get(k)}
                seen.update({k: inp[k] for k in _ARTIFACT_FIELDS if inp.get(k)})
                if missing:
                    b, changed = {**b, "input": {**inp, **missing}}, True
            new_blocks.append(b)
        if changed:
            item.payload = {**msg, "content": new_blocks}


def _move_injected(items: list[Item]) -> None:
    """claude.ai files the instructions it adds (``injected_prompt_block``) in the user's message: they
    go to each reply of Claude to that message, after its opening thinking (they stay where they are
    without a reply).
    The raw messages are copied, never changed in place."""
    replies: dict[str, list[Item]] = {}
    for it in items:
        if isinstance(it.payload, dict) and it.payload.get("sender") == "assistant" and it.parent:
            replies.setdefault(it.parent, []).append(it)
    for it in items:
        msg = it.payload
        if not isinstance(msg, dict) or msg.get("sender") != "human" or not replies.get(it.key):
            continue
        blocks = msg.get("content")
        if not isinstance(blocks, list):
            continue
        injected = [b for b in blocks if isinstance(b, dict) and b.get("type") == "injected_prompt_block"]
        if not injected:
            continue
        it.payload = {**msg, "content": [b for b in blocks if b not in injected]}
        for r in replies[it.key]:
            content = r.payload.get("content")
            content = content if isinstance(content, list) else []
            # after the thinking that opens the reply, which stays outside the frame "Ressources"
            n = next((i for i, b in enumerate(content) if not (isinstance(b, dict) and b.get("type") == "thinking")),
                     len(content))
            r.payload = {**r.payload, "content": content[:n] + injected + content[n:]}


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
    _inherit_artifact_fields(items)
    _move_injected(items)
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
    stack = list(roots)
    while stack:  # a part of a very long conversation ends its main branch where the next part begins
        n = stack.pop()
        if n.forced:
            return n
        stack.extend(n.children)
    leaves = [leaf for r in roots for leaf in _leaves(r)]
    if not leaves:
        return None
    # The most recent message, preferring messages still present on claude.ai.
    return max(leaves, key=lambda n: (not n.gone, n.created, n.order))


def _root_of(roots: list[Item], leaf: Item) -> Item:
    for r in roots:
        stack = [r]
        while stack:
            n = stack.pop()
            if n is leaf:
                return r
            stack.extend(n.children)
    raise ValueError("leaf not in the tree")


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


def skeleton(msg: dict[str, Any], extra: bool = False) -> tuple[str, ...]:
    """What main_path needs of a message (step 3c of the reading in pieces, 21/11): its key, parent, date and, for a
    message kept from an earlier export, the date of the last export holding it; never its content."""
    if extra:
        return (message_key(msg), msg.get("parent_message_uuid") or msg.get(LINEAR_PARENT) or None,
                str(msg.get("created_at") or ""), str(msg.get(LAST_SEEN) or "?"))
    return (message_key(msg), msg.get("parent_message_uuid") or None, str(msg.get("created_at") or ""))


def count_main(current: list[tuple[str, ...]], extras: list[tuple[str, ...]]) -> int:
    """len(main_path(items_from_raw(raw))) from the skeletons of the messages (the dict ones, in their order) and of
    the extra messages: the same items, without their contents (main_path does not look at them)."""
    return len(main_path(skeleton_items(current, extras)))


def skeleton_items(current: list[tuple[str, ...]], extras: list[tuple[str, ...]]) -> list[Item]:
    """The items of items_from_raw, without contents (payload None), from the skeletons."""
    with_parents = any(p for _, p, _ in current)
    items: list[Item] = []
    previous: str | None = None
    for k, p, created in current:
        items.append(Item(k, p if with_parents else previous, created, len(items), None, None))
        previous = k
    for k, p, created, last_seen in extras:
        items.append(Item(k, p, created, len(items), last_seen, None))
    return items


@dataclass
class PartPlan:
    """A very long conversation cut into parts (step 4 of the reading in pieces, 21/11): ``ranges`` the slices of the
    main branch, ``part_of`` the part of every message (key), ``path`` the keys of the main branch."""
    ranges: list[tuple[int, int]]
    part_of: dict[str, int]
    path: list[str]


def plan_parts(items: list[Item], weight: dict[str, int], human: set[str], budget: int) -> PartPlan:
    """Cut the conversation along its main branch into parts of about ``budget`` (the sizes in ``weight``): each
    message of the main branch takes the branches that leave from it (they stay in its part, as frames after it),
    the trees apart from the main one go to the first part. A part ends before a message of yours (``human``) once
    it holds ``budget`` (at most twice ``budget`` waiting for one), so that a question and its answer stay
    together."""
    roots = _link(items)
    leaf = _best_leaf(roots)
    if leaf is None:
        return PartPlan([], {}, [])
    main_root = _root_of(roots, leaf)
    path = _path(main_root, leaf)
    on_path = {id(n) for n in path}

    def subtree(node: Item) -> list[str]:
        out, stack = [], [node]
        while stack:
            n = stack.pop()
            out.append(n.key)
            stack.extend(n.children)
        return out

    first = [k for r in roots if r is not main_root for k in subtree(r)]
    blocks: list[list[str]] = []
    for node in path:
        keys = [node.key]
        for c in node.children:
            if id(c) not in on_path:
                keys += subtree(c)
        blocks.append(keys)
    ranges: list[tuple[int, int]] = []
    start, acc = 0, sum(weight.get(k, 0) for k in first)
    for i, keys in enumerate(blocks):
        if i > start and acc >= budget and (path[i].key in human or acc >= 2 * budget):
            ranges.append((start, i))
            start, acc = i, 0
        acc += sum(weight.get(k, 0) for k in keys)
    ranges.append((start, len(path)))
    part_of = {k: 0 for k in first}
    for p, (a, b) in enumerate(ranges):
        for i in range(a, b):
            for k in blocks[i]:
                part_of[k] = p
    return PartPlan(ranges, part_of, [n.key for n in path])


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
