"""Rough evaluation ("évaluation grossière") of the tokens a conversation made claude.ai use.

Only an order of magnitude, to compare conversations with one another:
- a token is counted as ``CHARS_PER_TOKEN`` characters of text (French prose; code and formulas
  differ), with no tokenizer;
- every reply of Claude reads again the whole conversation before it (the path of its
  ancestors, so that other versions count too), and once more after each tool it used, with
  the results already received: what it reads is counted as input, what it writes (text,
  thinking, calls of tools) as output;
- left out because the export does not hold them: the instructions of claude.ai (system,
  tools, memory), images and documents (only their names are exported), the files of a
  project, and the effect of caching. The figure is thus rather a minimum.

``evaluate(raw)`` -> {"v": VERSION, "content": tokens of the content, "tools": of which tools
(calls and results), "total": content read again and written over all the replies}.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable

import json
import math
from typing import Any

from .tree import extra_messages

VERSION = 1
CHARS_PER_TOKEN = 3.5


def _chars(block: Any) -> tuple[int, bool]:
    """(characters, is a tool block) of a content block of the raw export."""
    if not isinstance(block, dict):
        return 0, False
    kind = block.get("type")
    if kind == "text":
        return len(str(block.get("text") or "")), False
    if kind == "thinking":
        return len(str(block.get("thinking") or "")), False
    if kind == "tool_use":
        try:
            return len(json.dumps(block.get("input") or {}, ensure_ascii=False)) + len(str(block.get("name") or "")), True
        except (TypeError, ValueError):
            return 0, True
    if kind == "tool_result":
        content = block.get("content")
        if isinstance(content, list):
            text = "".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
        else:
            text = "" if content is None else str(content)
        return len(text), True
    if kind == "injected_prompt_block":
        return len(str(block.get("prompt") or "")), False
    return len(str(block.get("text") or "")), False


def _message_chars(msg: dict[str, Any]) -> tuple[int, int, list[tuple[int, bool, bool]]]:
    """(characters, of which tools, blocks as (characters, is a tool use, is a tool result))."""
    blocks = msg.get("content") if isinstance(msg.get("content"), list) else []
    out: list[tuple[int, bool, bool]] = []
    total = tools = 0
    for b in blocks:
        n, tool = _chars(b)
        kind = b.get("type") if isinstance(b, dict) else None
        out.append((n, kind == "tool_use", kind == "tool_result"))
        total += n
        tools += n if tool else 0
    if not blocks:  # older exports: the flat text only
        total = len(str(msg.get("text") or ""))
    for att in msg.get("attachments") or []:
        if isinstance(att, dict):
            total += len(str(att.get("extracted_content") or ""))
    return total, tools, out


def evaluate(raw: dict[str, Any]) -> dict[str, int]:
    msgs = raw.get("chat_messages") if isinstance(raw.get("chat_messages"), list) else []
    return evaluate_messages(itertools.chain(msgs, extra_messages(raw)))


def evaluate_messages(messages: Iterable[Any]) -> dict[str, int]:
    """evaluate() from the messages one by one (the current ones, then the extra ones): only their sizes, parents
    and senders are kept (step 4 of the reading in pieces, 21/11: a conversation bigger than the memory)."""
    by_id: dict[str, dict[str, Any]] = {}
    sizes: dict[str, Any] = {}
    for m in messages:
        if isinstance(m, dict) and m.get("uuid") and m["uuid"] not in by_id:
            by_id[m["uuid"]] = {"parent_message_uuid": m.get("parent_message_uuid"), "sender": m.get("sender")}
            sizes[m["uuid"]] = _message_chars(m)
    content = sum(s[0] for s in sizes.values())
    tools = sum(s[1] for s in sizes.values())

    context: dict[str, int] = {}  # characters read before a message: all its ancestors

    def before(uid: str) -> int:
        """Characters of all the ancestors of ``uid`` (what is read before writing it)."""
        chain, seen, cur = [], set(), uid
        while cur in by_id and cur not in context and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            parent = by_id[cur].get("parent_message_uuid")
            cur = parent if isinstance(parent, str) else None
        base = context[cur] + sizes[cur][0] if cur in context else 0
        for cid in reversed(chain):
            context[cid] = base
            base += sizes[cid][0]
        return context[uid]

    total = 0
    for uid, m in by_id.items():
        if m.get("sender") != "assistant":
            continue
        ctx = before(uid)
        _, _, blocks = sizes[uid]
        written = sum(n for n, _, is_result in blocks if not is_result)  # text, thinking, calls of tools
        read, prefix = ctx, 0  # the first call reads the context
        for n, is_use, is_result in blocks:
            prefix += n
            if is_result:  # after a tool: one more call, which reads everything again
                read += ctx + prefix
        total += read + written
    return {"v": VERSION, "content": round(content / CHARS_PER_TOKEN), "tools": round(tools / CHARS_PER_TOKEN),
            "total": round(total / CHARS_PER_TOKEN)}


def short(n: int) -> tuple[float, str]:
    """(value, unit) shown: 850 -> (850, ""), 4 230 -> (4.2, "k"), 482 000 -> (482, "k"), 1.4e6 -> (1.4, "M").
    Rounded half up, as Math.round in the pages (static/i18n.js)."""
    if n < 1000:
        return float(n), ""
    v, unit = (n / 1000, "k") if n < 999_500 else (n / 1_000_000, "M")  # never "1000 k"
    return (math.floor(v * 10 + 0.5) / 10 if v < 10 else float(math.floor(v + 0.5))), unit
