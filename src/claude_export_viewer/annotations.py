"""What the user adds to the conversations: archive/annotations.json.

{"favorites": {conversation uuid: {message uuid: {"added": ISO date, "sender": "human" |
"assistant", "date": ISO date of the message or "", "excerpt": its first words}}},
 "links": {conversation uuid: [linked conversation uuids]}  (always both ways, never transitive),
 "series": [[conversation uuids]] (AE-m3, 16/11: suites, each a link with a direction — 18/11: read in the order
 set by the user, "series_ordered": true once the suites of the 16-17/11, kept sorted, are put in the order of
 their dates; a conversation is in one suite at most; 2 or more in each),
 "notes": {conversation uuid: {message uuid: {"text": the note, "updated": ISO date}}},
 "titles": {conversation uuid: {message uuid: {"text": the title, "updated": ISO date}}} (a note of one line
 shown at the top of the bubble),
 "moves": {conversation uuid: {question uuid: {"to": uuid | null, "how": "under" | "after" | "cut", "bend": number}}}
 (structure view, logical order: the question and all that follows it on its thread goes under the question
 "to" (another version of it), after the answer "to" (its continuation, which becomes another version of the
 question moved), or alone (cut: no line to what came before); "bend": the curve of its line, by the user),
 "relations": {conversation uuid: [{"a": uuid, "b": uuid, "dir": "to" | "back" | "both", "bend": number}]}
 (structure view: a logical link between two messages, its arrow towards b, towards a, or both),
 "structure_history": {conversation uuid: [{"moves": …, "relations": …}]} (the states before the last
 STRUCTURE_UNDO changes of the moves and links, for "Annuler"; only their number goes to the pages),
 "marks": {conversation uuid: {message uuid: [{"s": start, "q": the text highlighted}]}}}
(``s``: offset in the text of the message as the page reads it, see static/marks.js).

The pages read them from ``annotations-data.js`` (written in the site folder at every build
and every change), so that a page opened as a file shows them; changing them goes through the
local server (POST /__cev__/annotations), which checks that the message is in the archive.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import jsonfile
from . import dates
from .tree import extra_messages

_one_at_a_time = jsonfile.one_at_a_time()  # reading, changing, writing: one change at a time

FILE = "annotations.json"
DATA_JS = "annotations-data.js"
EXCERPT = 160  # characters


class AnnotationError(ValueError):
    """A refused change; ``key`` is the i18n key of the message."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _path(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FILE


def load(site_dir: Path) -> dict[str, Any]:
    """The annotations, cleaned (a broken or missing file gives none)."""
    data = _clean(jsonfile.read(_path(site_dir)))
    if data["series"] and not data.get("series_ordered"):  # 18/11: the suites before the order set by the user
        convs = _titles(site_dir, {u for g in data["series"] for u in g})
        data["series"] = [sorted(g, key=lambda u: (convs.get(u, ["", "", ""])[2], u)) for g in data["series"]]
    data["series_ordered"] = True
    _link_suites(data)  # 18/11: also the suites made before this rule
    return data


def _link_suites(data: dict[str, Any]) -> None:
    """18/11: a suite is a link — its conversations are linked together (the links missing are made); taken out of
    the suite, a conversation keeps them."""
    links = data["links"]
    for g in data["series"]:
        for u in g:
            links[u] = sorted(set(links.get(u, [])) | (set(g) - {u}))


def _clean(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    favs = data.get("favorites") if isinstance(data.get("favorites"), dict) else {}
    clean = {c: {m: e for m, e in msgs.items() if isinstance(m, str) and isinstance(e, dict)}
             for c, msgs in favs.items() if isinstance(c, str) and isinstance(msgs, dict)}
    data["favorites"] = {c: msgs for c, msgs in clean.items() if msgs}
    links = data.get("links") if isinstance(data.get("links"), dict) else {}
    data["links"] = {c: sorted({o for o in v if isinstance(o, str) and o != c})
                     for c, v in links.items() if isinstance(c, str) and isinstance(v, list)}
    data["links"] = {c: v for c, v in data["links"].items() if v}
    data["series"] = _clean_series(data.get("series"))
    for key in ("notes", "titles"):
        notes = data.get(key) if isinstance(data.get(key), dict) else {}
        data[key] = {c: {m: e for m, e in v.items() if isinstance(e, dict) and isinstance(e.get("text"), str)}
                     for c, v in notes.items() if isinstance(c, str) and isinstance(v, dict)}
        data[key] = {c: v for c, v in data[key].items() if v}
    marks = data.get("marks") if isinstance(data.get("marks"), dict) else {}
    data["marks"] = {c: {m: [x for x in v if isinstance(x, dict) and isinstance(x.get("q"), str)
                             and isinstance(x.get("s"), int)] for m, v in msgs.items() if isinstance(v, list)}
                     for c, msgs in marks.items() if isinstance(c, str) and isinstance(msgs, dict)}
    data["marks"] = {c: {m: v for m, v in msgs.items() if v} for c, msgs in data["marks"].items()}
    data["marks"] = {c: msgs for c, msgs in data["marks"].items() if msgs}
    moves = data.get("moves") if isinstance(data.get("moves"), dict) else {}
    data["moves"] = {c: _clean_moves(v) for c, v in moves.items() if isinstance(c, str) and isinstance(v, dict)}
    data["moves"] = {c: v for c, v in data["moves"].items() if v}
    rels = data.get("relations") if isinstance(data.get("relations"), dict) else {}
    data["relations"] = {c: _clean_relations(v) for c, v in rels.items() if isinstance(c, str) and isinstance(v, list)}
    data["relations"] = {c: v for c, v in data["relations"].items() if v}
    hist = data.get("structure_history") if isinstance(data.get("structure_history"), dict) else {}
    data["structure_history"] = {
        c: [{"moves": _clean_moves(h.get("moves") if isinstance(h.get("moves"), dict) else {}),
             "relations": _clean_relations(h.get("relations") if isinstance(h.get("relations"), list) else [])}
            for h in v if isinstance(h, dict)][-STRUCTURE_UNDO:]
        for c, v in hist.items() if isinstance(c, str) and isinstance(v, list)}
    data["structure_history"] = {c: v for c, v in data["structure_history"].items() if v}
    data.pop("convs", None)  # written in the script only
    return data


# --- Copies kept for "Récupération des annotations…" (AF-f5, 15/11) ---------------------------------------------
# Before the file is replaced, its former state is kept in archive/annotations-copies/ (KEEP copies at most), without a
# word to the user: at most one copy every SPACING seconds (a note written in several steps is one state), always one
# when more than one annotation goes at once (a frame emptied, "Retirer toutes les annotations", a recovery).
COPIES = "annotations-copies"
KEEP = 5
SPACING = 300.0


def _clean_series(value: Any) -> list[list[str]]:
    """Lists of 2 conversations or more (in their order), each conversation in one of them at most (the first one)."""
    seen: set[str] = set()
    out: list[list[str]] = []
    for group in value if isinstance(value, list) else []:
        if not isinstance(group, list):
            continue
        members = [u for u in dict.fromkeys(group) if isinstance(u, str) and u not in seen]
        if len(members) >= 2:
            seen.update(members)
            out.append(members)
    return out


def _with_series(data: dict[str, Any]) -> set[str]:
    """Every conversation named by a link or a suite (their titles go to the pages)."""
    return ({o for v in data.get("links", {}).values() for o in v} | set(data.get("links", {}))
            | {u for g in data.get("series", []) for u in g})


def counts(data: dict[str, Any]) -> dict[str, int]:
    """What a state holds: notes, favorites, titles, highlighted passages, links, moves of the structure."""
    return {"notes": sum(len(v) for v in data.get("notes", {}).values()),
            "favorites": sum(len(v) for v in data.get("favorites", {}).values()),
            "titles": sum(len(v) for v in data.get("titles", {}).values()),
            "marks": sum(len(x) for m in data.get("marks", {}).values() for x in m.values()),
            "links": sum(len(v) for v in data.get("links", {}).values()) // 2,
            "moves": sum(len(v) for v in data.get("moves", {}).values())}


def _copies_dir(site_dir: Path) -> Path:
    return _path(site_dir).parent / COPIES


def _keep_copy(site_dir: Path, new: dict[str, Any], force: bool) -> None:
    path = _path(site_dir)
    if not path.is_file():
        return
    old_text = path.read_text(encoding="utf-8", errors="replace")
    try:
        old = _clean(json.loads(old_text))
    except ValueError:
        return  # an unreadable file is set aside by jsonfile (S1), never copied here
    if old == _clean(json.loads(json.dumps(new))):
        return
    folder = _copies_dir(site_dir)
    kept = sorted(folder.glob("annotations-*.json")) if folder.is_dir() else []
    lost = sum(counts(old).values()) - sum(counts(_clean(json.loads(json.dumps(new)))).values())
    if not force and lost <= 1 and kept and datetime.now().timestamp() - kept[-1].stat().st_mtime < SPACING:
        return
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"annotations-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json").write_text(old_text, encoding="utf-8")
    for extra in sorted(folder.glob("annotations-*.json"))[:-KEEP]:
        extra.unlink(missing_ok=True)


def copies(site_dir: Path) -> list[dict[str, Any]]:
    """The states kept, the most recent first: {"name", "date" (ms), "counts"}."""
    folder = _copies_dir(site_dir)
    out = []
    for f in sorted(folder.glob("annotations-*.json"), reverse=True) if folder.is_dir() else []:
        try:
            data = _clean(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        out.append({"name": f.name, "date": int(f.stat().st_mtime * 1000), "counts": counts(data)})
    return out


@_one_at_a_time
def recover(site_dir: Path, name: str) -> dict[str, int]:
    """Put a state kept back (the current one kept first: a recovery can be undone the same way)."""
    folder = _copies_dir(site_dir)
    if name not in {c["name"] for c in copies(site_dir)}:
        raise AnnotationError("annot.copy_unknown")
    data = _clean(json.loads((folder / name).read_text(encoding="utf-8")))
    save(site_dir, data, force=True)
    return counts(data)


@_one_at_a_time
def save(site_dir: Path, data: dict[str, Any], force: bool = False) -> None:
    path = _path(site_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _keep_copy(site_dir, data, force)  # (AF-f5: never in the way of the saving itself)
    except OSError:
        pass
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    write_data_js(site_dir, data)


def _titles(site_dir: Path, uuids: set[str]) -> dict[str, list[str]]:
    """Name, page and date of the linked conversations (the frame "Liens" of a page)."""
    if not uuids:
        return {}
    from .archive import Archive
    try:
        convs = Archive(site_dir).conversations
    except Exception:  # noqa: BLE001 - no archive yet: no titles
        return {}
    return {u: [m.get("name") or "", m.get("filename") or "", m.get("created_at") or ""]
            for u in uuids if (m := convs.get(u)) and m.get("filename")}


def write_data_js(site_dir: Path, data: dict[str, Any] | None = None) -> None:
    """The annotations for the pages (a script, so that a page opened as a file can read it), with
    the titles of the linked conversations ("convs")."""
    data = load(site_dir) if data is None else data
    data = {**{k: v for k, v in data.items() if k != "series_ordered"}, "convs": _titles(site_dir, _with_series(data)),
            "structure_history": {c: len(v) for c, v in data.get("structure_history", {}).items()}}
    text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    (Path(site_dir) / DATA_JS).write_text(f"window.CEV_ANNOTATIONS = {text};\n", encoding="utf-8")


def _excerpt(msg: dict[str, Any]) -> str:
    blocks = msg.get("content") if isinstance(msg.get("content"), list) else []
    text = " ".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    text = " ".join((text or str(msg.get("text") or "")).split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1].rstrip() + "…"


def find_message(raw: dict[str, Any], uuid: str) -> dict[str, Any] | None:
    """The message of an archived conversation (also one kept after its removal on claude.ai). ``raw``: the
    conversation, or an archive.MessageSource (the server: a very long conversation is never loaded whole)."""
    if hasattr(raw, "find"):
        return raw.find(uuid)
    msgs = raw.get("chat_messages") if isinstance(raw.get("chat_messages"), list) else []
    for m in [*msgs, *extra_messages(raw)]:
        if isinstance(m, dict) and m.get("uuid") == uuid:
            return m
    return None


@_one_at_a_time
def change(site_dir: Path, request: dict[str, Any], load_raw: Any) -> dict[str, Any]:
    """Apply one change and return the new state.

    {"action": "favorite", "conversation": uuid, "message": uuid, "on": true | false}
    {"action": "clear_favorites", "conversation": uuid}: every favorite of the conversation
    ``load_raw(uuid)``: the archived conversation (KeyError when unknown).
    """
    action = request.get("action")
    if action in ("link", "unlink", "clear_links", "series_set"):
        return _change_links(site_dir, request, load_raw)
    if action in ("move", "relation", "bend", "reset_structure", "undo_structure"):
        return _change_structure(site_dir, request, load_raw)
    if action in ("note", "clear_notes", "title"):
        return _change_note(site_dir, request, load_raw)
    if action in ("mark", "unmark", "clear_marks"):
        return _change_marks(site_dir, request, load_raw)
    if request.get("action") == "clear_favorites":
        conv = request.get("conversation")
        if not isinstance(conv, str):
            raise AnnotationError("web.fav.bad_request")
        data = load(site_dir)
        data["favorites"].pop(conv, None)
        save(site_dir, data)
        return load_state(site_dir)
    if request.get("action") != "favorite":
        raise AnnotationError("web.fav.bad_request")
    conv, mid, on = request.get("conversation"), request.get("message"), request.get("on")
    if not isinstance(conv, str) or not isinstance(mid, str) or not isinstance(on, bool):
        raise AnnotationError("web.fav.bad_request")
    data = load(site_dir)
    favs = data["favorites"]
    if on:
        try:
            raw = load_raw(conv)
        except KeyError:
            raise AnnotationError("web.fav.unknown_message") from None
        msg = find_message(raw, mid)
        if msg is None:
            raise AnnotationError("web.fav.unknown_message")
        when = dates.parse(msg.get("created_at"))
        favs.setdefault(conv, {})[mid] = {
            "added": dates.iso_utc(datetime.now(timezone.utc)),
            "sender": "human" if msg.get("sender") == "human" else "assistant",
            "date": dates.iso_utc(when) if when else "",
            "excerpt": _excerpt(msg),
        }
    else:
        favs.get(conv, {}).pop(mid, None)
        if conv in favs and not favs[conv]:
            del favs[conv]
    save(site_dir, data)
    return load_state(site_dir)


# --- Links between conversations (both ways, never transitive) -----------------------------


def _change_links(site_dir: Path, request: dict[str, Any], load_raw: Any) -> dict[str, Any]:
    """{"action": "link" | "unlink", "a": uuid, "b": uuid}; {"action": "clear_links", "conversation": uuid} (its
    suite too); AE-m3 (18/11): {"action": "series_set", "here": uuid, "order": [uuids]} — the suite of "here" (if
    any) becomes "order" (made, ordered, added to, left: one action); a conversation of "order" in another suite
    leaves it (the page asks first); fewer than 2: no more suite. The conversations of a suite are linked together
    (`_link_suites`); "unlink" of two of one suite takes b out of it."""
    data = load(site_dir)
    links: dict[str, list[str]] = data["links"]
    series: list[list[str]] = data["series"]
    if request["action"] == "clear_links":
        conv = request.get("conversation")
        if not isinstance(conv, str):
            raise AnnotationError("web.fav.bad_request")
        for other in links.pop(conv, []):
            links[other] = [x for x in links.get(other, []) if x != conv]
        data["series"] = [[u for u in g if u != conv] for g in series]
    elif request["action"] == "series_set":
        here, order = request.get("here"), request.get("order")
        if not isinstance(here, str) or not isinstance(order, list) or not all(isinstance(u, str) for u in order) \
                or len(set(order)) != len(order):
            raise AnnotationError("web.fav.bad_request")
        for conv in set(order) | {here}:
            try:
                load_raw(conv)
            except KeyError:
                raise AnnotationError("web.fav.unknown_message") from None
        kept = [[u for u in g if u not in order] for g in series if here not in g]  # a conversation moved leaves its suite
        data["series"] = kept + ([order] if len(order) >= 2 else [])
    else:
        a, b = request.get("a"), request.get("b")
        if not isinstance(a, str) or not isinstance(b, str) or a == b:
            raise AnnotationError("web.fav.bad_request")
        if request["action"] == "link":
            for conv in (a, b):
                try:
                    load_raw(conv)
                except KeyError:
                    raise AnnotationError("web.fav.unknown_message") from None
            links[a] = sorted(set(links.get(a, [])) | {b})
            links[b] = sorted(set(links.get(b, [])) | {a})
        else:
            links[a] = [x for x in links.get(a, []) if x != b]
            links[b] = [x for x in links.get(b, []) if x != a]
            # a suite links its conversations together: two of one suite unlinked, b leaves it
            data["series"] = [[u for u in g if u != b] if a in g else g for g in data["series"]]
    data["links"] = {c: v for c, v in links.items() if v}
    data["series"] = _clean_series(data["series"])
    _link_suites(data)
    save(site_dir, data)
    return load_state(site_dir)


def load_state(site_dir: Path) -> dict[str, Any]:
    """What a page reads after a change: the annotations and the titles of the linked conversations."""
    data = load(site_dir)
    return {**{k: v for k, v in data.items() if k != "series_ordered"}, "convs": _titles(site_dir, _with_series(data))}


# --- Notes (one per message, yours or Claude's) ---------------------------------------------

NOTE_MAX = 20000  # characters


def _change_note(site_dir: Path, request: dict[str, Any], load_raw: Any) -> dict[str, Any]:
    """{"action": "note" | "title", "conversation": uuid, "message": uuid, "text": the note or the title ("" removes
    it; a title is one line: its white space is folded)}."""
    if request.get("action") == "clear_notes":  # {"action": "clear_notes", "conversation": uuid}
        conv = request.get("conversation")
        if not isinstance(conv, str):
            raise AnnotationError("web.fav.bad_request")
        data = load(site_dir)
        data["notes"].pop(conv, None)
        save(site_dir, data)
        return load_state(site_dir)
    conv, mid, text = request.get("conversation"), request.get("message"), request.get("text")
    if not isinstance(conv, str) or not isinstance(mid, str) or not isinstance(text, str) or len(text) > NOTE_MAX:
        raise AnnotationError("web.fav.bad_request")
    data = load(site_dir)
    key = "titles" if request.get("action") == "title" else "notes"
    text = " ".join(text.split()) if key == "titles" else text.strip()
    if text:
        try:
            msg = find_message(load_raw(conv), mid)
        except KeyError:
            msg = None
        if msg is None:
            raise AnnotationError("web.fav.unknown_message")
        data[key].setdefault(conv, {})[mid] = {"text": text, "updated": dates.iso_utc(datetime.now(timezone.utc))}
    else:
        data[key].get(conv, {}).pop(mid, None)
    data[key] = {c: v for c, v in data[key].items() if v}
    save(site_dir, data)
    return load_state(site_dir)


# --- Highlighted passages ------------------------------------------------------------------

MARK_MAX = 5000  # characters of one passage


MARK_COLORS = ("y", "g", "r", "p", "c")  # yellow, green, red, pink, cyan (marks.js, style.css --hl-*)


def _change_marks(site_dir: Path, request: dict[str, Any], load_raw: Any) -> dict[str, Any]:
    """{"action": "mark", "conversation", "passages": [{"message", "s", "q", "c"?}], "replace"?: [same]}: highlight
    them (c: colour, MARK_COLORS, yellow when absent; 11/11), the passages of "replace" removed first;
    {"action": "unmark", "conversation", "passages": [same]}: remove those passages;
    {"action": "clear_marks", "conversation"}: every passage of the conversation."""
    conv = request.get("conversation")
    if not isinstance(conv, str):
        raise AnnotationError("web.fav.bad_request")
    data = load(site_dir)
    marks = data["marks"].setdefault(conv, {})
    if request["action"] == "clear_marks":
        marks.clear()
    else:
        passages = request.get("passages")
        if not isinstance(passages, list) or not passages:
            raise AnnotationError("web.fav.bad_request")
        raw = None
        replace = request.get("replace") if request["action"] == "mark" else None
        if replace is not None:
            if not isinstance(replace, list):
                raise AnnotationError("web.fav.bad_request")
            for p in replace:
                if not isinstance(p, dict) or not isinstance(p.get("message"), str):
                    raise AnnotationError("web.fav.bad_request")
                marks[p["message"]] = [x for x in marks.get(p["message"], [])
                                       if not (x["s"] == p.get("s") and x["q"] == p.get("q"))]
        for p in passages:
            mid, s, q = (p.get("message"), p.get("s"), p.get("q")) if isinstance(p, dict) else (None, None, None)
            if not isinstance(mid, str) or not isinstance(s, int) or s < 0 or not isinstance(q, str) \
                    or not q.strip() or len(q) > MARK_MAX:
                raise AnnotationError("web.fav.bad_request")
            if request["action"] == "mark":
                if raw is None:
                    try:
                        raw = load_raw(conv)
                    except KeyError:
                        raise AnnotationError("web.fav.unknown_message") from None
                if find_message(raw, mid) is None:
                    raise AnnotationError("web.fav.unknown_message")
                c = p.get("c", "y")
                if c not in MARK_COLORS:
                    raise AnnotationError("web.fav.bad_request")
                lst = [x for x in marks.get(mid, []) if not (x["s"] == s and x["q"] == q)]
                lst.append({"s": s, "q": q, **({"c": c} if c != "y" else {})})
                lst.sort(key=lambda x: x["s"])
                marks[mid] = lst
            else:
                marks[mid] = [x for x in marks.get(mid, []) if not (x["s"] == s and x["q"] == q)]
    data["marks"] = {c: {m: v for m, v in msgs.items() if v} for c, msgs in data["marks"].items()}
    data["marks"] = {c: msgs for c, msgs in data["marks"].items() if msgs}
    save(site_dir, data)
    return load_state(site_dir)


# --- Structure view: moves of the logical order, logical links --------------------------------------------

DIRECTIONS = ("to", "back", "both")
HOWS = ("under", "after", "cut")
STRUCTURE_UNDO = 10  # the changes "Annuler" can take back


def _bend(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 5000 else None


def _clean_moves(v: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for q, m in v.items():
        if isinstance(m, str):  # the first form: a question under a question
            m = {"to": m, "how": "under"}
        if not isinstance(q, str) or not isinstance(m, dict) or m.get("how") not in HOWS:
            continue
        to = m.get("to") if isinstance(m.get("to"), str) else None
        if (to is None) != (m["how"] == "cut") or to == q:
            continue
        move = {"to": to, "how": m["how"]}
        if _bend(m.get("bend")) is not None:
            move["bend"] = _bend(m.get("bend"))
        out[q] = move
    return out


def _clean_relations(v: list[Any]) -> list[dict[str, Any]]:
    out = []
    for x in v:
        if isinstance(x, dict) and isinstance(x.get("a"), str) and isinstance(x.get("b"), str) and x.get("dir") in DIRECTIONS:
            rel = {"a": x["a"], "b": x["b"], "dir": x["dir"]}
            if _bend(x.get("bend")) is not None:
                rel["bend"] = _bend(x.get("bend"))
            out.append(rel)
    return out


def _change_structure(site_dir: Path, request: dict[str, Any], load_raw: Any) -> dict[str, Any]:
    """{"action": "move", "conversation", "message": question, "how": "under" | "after" | "cut", "target": the
    question (under) or the answer (after); without how and target: back in place; after the answer it
    follows on claude.ai: back in place too}; {"action": "relation", "conversation", "a", "b", "dir": "to" |
    "back" | "both" (null: removed)}: one link per pair of messages, its curve kept; {"action": "bend",
    "conversation", "message" (a move) or "a" and "b" (a link), "bend": number (null: the automatic curve)};
    {"action": "reset_structure", "conversation"}: every move and link of it; {"action": "undo_structure",
    "conversation"}: back to the state before the last change (STRUCTURE_UNDO at most, kept between visits)."""
    conv = request.get("conversation")
    if not isinstance(conv, str):
        raise AnnotationError("web.fav.bad_request")
    data = load(site_dir)
    action = request["action"]
    history = data["structure_history"].setdefault(conv, [])
    if action == "undo_structure":
        if history:
            last = history.pop()
            data["moves"][conv], data["relations"][conv] = last["moves"], last["relations"]
    else:
        before = {"moves": json.loads(json.dumps(data["moves"].get(conv, {}))),
                  "relations": json.loads(json.dumps(data["relations"].get(conv, [])))}
        _apply_structure(data, conv, request, load_raw)
        if before != {"moves": data["moves"].get(conv, {}), "relations": data["relations"].get(conv, [])}:
            history.append(before)
            del history[:-STRUCTURE_UNDO]
    data["moves"] = {c: v for c, v in data["moves"].items() if v}
    data["relations"] = {c: v for c, v in data["relations"].items() if v}
    data["structure_history"] = {c: v for c, v in data["structure_history"].items() if v}
    save(site_dir, data)
    return load_state(site_dir)


def _apply_structure(data: dict[str, Any], conv: str, request: dict[str, Any], load_raw: Any) -> None:
    action = request["action"]
    if action == "reset_structure":
        data["moves"].pop(conv, None)
        data["relations"].pop(conv, None)
        return
    try:
        raw = load_raw(conv)
    except KeyError:
        raise AnnotationError("web.fav.unknown_message") from None

    def known(uuid: Any) -> bool:
        return isinstance(uuid, str) and find_message(raw, uuid) is not None

    moves = data["moves"].setdefault(conv, {})
    rels = data["relations"].setdefault(conv, [])
    if action == "move":
        mid, target, how = request.get("message"), request.get("target") or None, request.get("how")
        if not known(mid) or (how is not None and how not in HOWS) or (target is not None and (not known(target) or target == mid)) \
                or (how in ("under", "after")) != (target is not None) or (how is None and target is not None):
            raise AnnotationError("web.fav.unknown_message")
        old = moves.pop(mid, None)
        if how == "after" and (find_message(raw, mid) or {}).get("parent_message_uuid") == target:
            return  # after the answer it follows on claude.ai: back in place
        if how:
            moves[mid] = {"to": target, "how": how}
            if old and old.get("how") == how and "bend" in old:
                moves[mid]["bend"] = old["bend"]
    elif action == "relation":
        a, b, way = request.get("a"), request.get("b"), request.get("dir")
        if not known(a) or not known(b) or a == b or (way is not None and way not in DIRECTIONS):
            raise AnnotationError("web.fav.bad_request")
        old = next((x for x in rels if {x["a"], x["b"]} == {a, b}), None)
        rels[:] = [x for x in rels if x is not old]
        if way:
            rel = {"a": a, "b": b, "dir": way}
            if old and "bend" in old and old["a"] == a:
                rel["bend"] = old["bend"]
            rels.append(rel)
    else:  # bend
        bend = _bend(request.get("bend"))
        if request.get("message") is not None:
            target = moves.get(request.get("message"))
        else:
            target = next((x for x in rels if x["a"] == request.get("a") and x["b"] == request.get("b")), None)
        if target is None:
            raise AnnotationError("web.fav.bad_request")
        target.pop("bend", None)
        if bend is not None:
            target["bend"] = bend
