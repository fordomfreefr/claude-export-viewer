"""The user's own copies of the files of the conversations, associated link by link.

A **link** is one file named by one message: an image or file sent by the user (``files``), a
document joined to a message (``attachments``), or a file handed over by Claude whose exact
content the export lacks (created.py rebuilds the others; one changed afterwards by a program is
a link too, ``partial``). Each link is associated with a file of the computer on its own, so that
five versions of the same name can point to five different files.

**Automatic association**, at each run of the program, for every link the user has not set:

- candidates: files of the folders chosen by the user (sub-folders included, hidden ones skipped)
  named exactly as the link, or a copy renamed by the browser (``name (1).ext``);
- a joined text document (.md, .py, .txt…) whose whole text is in the export: the candidate with
  the same text wins, even under a renamed copy (status ``same``); else the most recent of the exact
  name (status ``modified``: probably the right file, changed since);
- any other link: the most recent of the exact name (status ``auto``); none: status ``none``;
- a file found once stays associated when it disappears from the computer (the site is an archive).

**Manual association** (menu 🔗 of the pages, through the local server): a candidate, a file sent by
the browser, or no file at all; the program never changes it ("back to the automatic choice"
removes it). The file is copied into the site, once per content:
``files/<page>/<sha256 12>/<link name>``; a copy no link uses any more is an **orphan**, listed and
removed by the "clean" button of the index (copies written for created.py are kept).

State in ``archive/files.json`` (format 2; earlier states are dropped, their copies become orphans)::

    {"format": 2,
     "links": {uuid: {"hash": h, "v": n, "list": [{"id", "kind", "name", "msg", "text"?, "partial"?}]}},
     "assoc": {uuid: {link id: {"how": "auto" | "user", "status", "copy", "source", "size", "mtime"}}},
     "candidates": {name: [[path, size, mtime], ...]},   # most recent first
     "claude": {uuid: [copies written for the files created by Claude]}}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import jsonfile
from . import system
from .attachments import TEXT_EXTENSIONS

_one_at_a_time = jsonfile.one_at_a_time()  # reading, changing, writing: one change at a time

FILE = "files.json"
FOLDER = "files"
FORMAT = 2
LINKS_VERSION = 2  # changes when the way links are read from a conversation changes (2: visuals)
IMAGES = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"}
MAX_CANDIDATES = 40
_SKIP = {"__pycache__", "node_modules"}
_RENUM = re.compile(r"^(.*?) ?\((\d+)\)(\.[^.]*)?$")
ACTIONS = ("path", "none", "auto")


@dataclass(frozen=True)
class Candidate:
    path: Path
    size: int
    mtime: float
    exact: bool  # named exactly as the link (else a copy renamed by the browser)


NAME_CHARS, NAME_BYTES = 100, 180  # a file name written by CEV, at most (review of 21/11)


def short_name(name: str) -> str:
    """``name`` shortened when too long for a disk: at most NAME_CHARS characters and NAME_BYTES bytes in UTF-8
    (Linux refuses more than 255 bytes, about 85 Japanese characters; Windows a path over 260 characters), the
    extension kept and 8 characters of a hash added so that two long names stay apart."""
    if len(name) <= NAME_CHARS and len(name.encode("utf-8")) <= NAME_BYTES:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or len(ext) > 10:
        stem, dot, ext = name, "", ""
    tail = "~" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8] + dot + ext
    stem = stem[:NAME_CHARS - len(tail)]
    while len((stem + tail).encode("utf-8")) > NAME_BYTES:
        stem = stem[:-1]
    return stem.rstrip(" .") + tail


def safe_name(name: str) -> str:
    return short_name(re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .") or "file")


def _key(name: str) -> str:
    return name.casefold() if system.WINDOWS else name


def base_name(name: str) -> str:
    """"x (1).ods" -> "x.ods" (a copy renamed by the browser); other names unchanged."""
    m = _RENUM.match(name)
    return (m.group(1) + (m.group(3) or "")) if m else name


def text_hash(text: str) -> str:
    """Of a text, line ends and final blanks aside (a file saved on Windows is the same text)."""
    return hashlib.sha256(text.replace("\r\n", "\n").rstrip().encode("utf-8")).hexdigest()


def _is_text(name: str) -> bool:
    return "." in name and name.rpartition(".")[2].lower() in TEXT_EXTENSIONS


# --- links of a conversation ---------------------------------------------------------


def view_key(msg: str, kind: str, name: str, nth: int = 1) -> str:
    """Id of a link: message, kind ("file", "attachment", "created"), name, rank of that name."""
    return f"{msg}/{kind}/{name}" + (f"#{nth}" if nth > 1 else "")


def widget_file(title: Any) -> str:
    """The name claude.ai gives a visual saved from the chat: its title (snake_case id) + .html."""
    return (title.strip() if isinstance(title, str) and title.strip() else "visualisation") + ".html"


def links_in(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Every link of a conversation, in the order of the messages (all branches)."""
    from . import created, tree
    files_of = created.reconstruct(raw)
    out: list[dict[str, Any]] = []
    for item in tree.items_from_raw(raw):
        msg = item.payload if isinstance(item.payload, dict) else {}
        seen: dict[tuple[str, str], int] = {}

        def add(kind: str, name: Any, **extra: Any) -> None:
            if not isinstance(name, str) or not name.strip():
                return
            n = seen.get((kind, name), 0) + 1
            seen[(kind, name)] = n
            out.append({"id": view_key(item.key, kind, name, n), "kind": kind, "name": name, "msg": item.key, **extra})

        for f in msg.get("files") or []:
            if isinstance(f, dict):
                add("file", f.get("file_name"))
        for a in msg.get("attachments") or []:
            if isinstance(a, dict):
                name, text = a.get("file_name"), a.get("extracted_content")
                if isinstance(name, str) and _is_text(name) and isinstance(text, str) and text.strip():
                    add("attachment", name, text=text_hash(text))
                else:
                    add("attachment", name)
        for b in msg.get("content") or []:  # a visual of claude.ai, saved from the chat as <title>.html
            if isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("name") or "").endswith("show_widget"):
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                if isinstance(inp.get("widget_code"), str) and inp["widget_code"].strip():
                    add("widget", widget_file(inp.get("title")))
        for p in files_of.get(item.key, []):
            if p.text is None:
                add("created", p.name)
            elif not p.complete:
                add("created", p.name, partial=True)
    return out


def links_of(archive: Any, uuid: str) -> list[dict[str, Any]]:
    """links_in of a conversation of the archive; a very long one (in parts, html_builder.plan_of) part by part,
    never whole in memory (21/11)."""
    from . import html_builder
    parts = html_builder.plan_of(archive, uuid)
    if parts is None:
        return links_in(archive.load_raw(uuid))
    return [link for _, raw, _ in html_builder.iter_part_raws(archive, uuid, parts) for link in links_in(raw)]


# --- state ---------------------------------------------------------------------------


def _path(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FILE


def load(site_dir: Path) -> dict[str, Any]:
    data = jsonfile.read(_path(site_dir))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        data = {"format": FORMAT}  # earlier state (one answer per name): dropped
    for k in ("links", "assoc", "candidates", "claude"):
        if not isinstance(data.get(k), dict):
            data[k] = {}
    return data


@_one_at_a_time
def save(site_dir: Path, data: dict[str, Any]) -> None:
    path = _path(site_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _links(data: dict[str, Any], archive: Any, uuid: str) -> list[dict[str, Any]]:
    """The links of a conversation (cached by the hash of the conversation)."""
    meta = archive.conversations.get(uuid) or {}
    cached = data["links"].get(uuid)
    if not cached or cached.get("hash") != meta.get("hash") or cached.get("v") != LINKS_VERSION:
        try:
            cached = {"hash": meta.get("hash"), "v": LINKS_VERSION, "list": links_of(archive, uuid)}
        except Exception:  # noqa: BLE001 - an unreadable conversation is reported by the rendering
            cached = {"hash": None, "v": LINKS_VERSION, "list": []}
        data["links"][uuid] = cached
    return cached["list"]


def signature(data: dict[str, Any], uuid: str) -> str:
    """Changes when what a page shows about the files of its conversation changes."""
    links = (data["links"].get(uuid) or {}).get("list", [])
    names = sorted({link["name"] for link in links})
    return json.dumps([data["assoc"].get(uuid, {}), {n: data["candidates"].get(n, []) for n in names}],
                      ensure_ascii=False, sort_keys=True)


# --- search --------------------------------------------------------------------------


def scan(folders: Iterable[Path], wanted: set[str], skip: Iterable[Path] = ()) -> dict[str, list[Candidate]]:
    """Files named as one of ``wanted``, or renamed copies of them, in the folders and their
    sub-folders; by wanted name (``_key``), most recent first."""
    keys = {_key(n) for n in wanted}
    skipped = set()
    for p in skip:
        try:
            skipped.add(Path(p).resolve())
        except OSError:
            pass
    out: dict[str, list[Candidate]] = {}
    seen: set[Path] = set()
    for folder in folders:
        try:
            folder = Path(folder).expanduser().resolve()
        except OSError:
            continue
        if not folder.is_dir():
            continue
        for root, dirs, files in os.walk(folder, onerror=lambda e: None):
            base = Path(root)
            if base in seen:
                dirs[:] = []
                continue
            seen.add(base)
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP and (base / d) not in skipped]
            for name in files:
                exact, renamed = _key(name), _key(base_name(name))
                for k, is_exact in ((exact, True), (renamed, False)):
                    if k in keys and (is_exact or renamed != exact):
                        try:
                            st = (base / name).stat()
                        except OSError:
                            continue
                        out.setdefault(k, []).append(Candidate(base / name, st.st_size, st.st_mtime, is_exact))
    for k in out:
        out[k].sort(key=lambda c: (-c.mtime, str(c.path)))
    return out


def _candidates(data: dict[str, Any], name: str) -> list[Candidate]:
    return [Candidate(Path(p), s, m, _key(Path(p).name) == _key(name)) for p, s, m in data["candidates"].get(name, [])]


def _same_text(path: Path, size: int, wanted: str) -> bool:
    if size > 50_000_000:
        return False
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return text_hash(text) == wanted


def _choose(link: dict[str, Any], cands: list[Candidate]) -> tuple[Candidate | None, str]:
    if link.get("text"):
        for c in cands:  # the same text as in the export: certainly the file, whatever its name
            if _same_text(c.path, c.size, link["text"]):
                return c, "same"
    exact = [c for c in cands if c.exact]
    if not exact:
        return None, "none"
    return exact[0], "modified" if link.get("text") else "auto"


def _store(site_dir: Path, page: str, name: str, src: Path) -> str:
    """Copy a file into the site, once per content; its path from the site folder."""
    h = hashlib.sha256()
    with src.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    rel = f"{FOLDER}/{page}/{h.hexdigest()[:12]}/{safe_name(name)}"
    dst = Path(site_dir) / rel
    if not dst.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    return rel


def _page(archive: Any, uuid: str) -> str:
    return archive.conversations[uuid]["filename"].removesuffix(".html")


NONE = {"how": "auto", "status": "none", "copy": None}


def _auto(site_dir: Path, archive: Any, uuid: str, link: dict[str, Any], old: dict[str, Any] | None,
          cands: list[Candidate]) -> tuple[dict[str, Any], bool]:
    """The automatic association of a link; True when it now points to another file."""
    best, status = _choose(link, cands)
    if best is None:
        if old and old.get("copy") and (Path(site_dir) / old["copy"]).is_file():
            return old, False  # found once, gone from the computer since: kept
        return dict(NONE), False
    unchanged = (old and old.get("source") == str(best.path) and old.get("size") == best.size
                 and old.get("mtime") == best.mtime and old.get("copy") and (Path(site_dir) / old["copy"]).is_file())
    if unchanged:
        return {**old, "status": status}, False
    try:
        copy = _store(site_dir, _page(archive, uuid), link["name"], best.path)
    except OSError:
        return old or dict(NONE), False
    return {"how": "auto", "status": status, "copy": copy, "source": str(best.path), "size": best.size,
            "mtime": best.mtime}, True


@_one_at_a_time
def update(archive: Any, site_dir: Path, folders: list[Path], skip: Iterable[Path] = (),
           say: Callable[[int, int, list[Path]], None] | None = None) -> int:
    """Look for the files of every link and associate those the user has not set; returns how
    many links now point to a file they did not point to before."""
    site_dir = Path(site_dir)
    data = load(site_dir)
    for key in ("links", "assoc", "claude"):
        for uuid in list(data[key]):
            if uuid not in archive.conversations:
                del data[key][uuid]
    all_links = {uuid: _links(data, archive, uuid) for uuid in archive.conversations}
    names = {link["name"] for links in all_links.values() for link in links}
    folders = [f for f in folders if Path(f).is_dir()]
    if say and names:
        say(len(names), sum(len(v) for v in all_links.values()), folders)
    found = scan(folders, names, [site_dir, *skip]) if names else {}
    data["candidates"] = {n: [[str(c.path), c.size, c.mtime] for c in found.get(_key(n), [])[:MAX_CANDIDATES]]
                          for n in sorted(names) if found.get(_key(n))}
    count = 0
    replaced: set[str] = set()  # copies an automatic association no longer points to
    for uuid, links in all_links.items():
        old_assoc = data["assoc"].get(uuid, {})
        assoc: dict[str, Any] = {}
        for link in links:
            old = old_assoc.get(link["id"])
            if old and old.get("how") == "user":
                if old.get("copy") and not (site_dir / old["copy"]).is_file() and old.get("source") \
                        and Path(old["source"]).is_file():
                    try:  # the copy was removed from the site: copied again from its source
                        old["copy"] = _store(site_dir, _page(archive, uuid), link["name"], Path(old["source"]))
                    except OSError:
                        pass
                assoc[link["id"]] = old
                continue
            entry, changed = _auto(site_dir, archive, uuid, link, old, _candidates(data, link["name"]))
            if old and old.get("copy") and old["copy"] != entry.get("copy"):
                replaced.add(old["copy"])
            assoc[link["id"]] = entry
            count += changed
        if assoc:
            data["assoc"][uuid] = assoc
        else:
            data["assoc"].pop(uuid, None)
    save(site_dir, data)
    _drop_replaced(site_dir, data, replaced)
    return count


def _drop_replaced(site_dir: Path, data: dict[str, Any], replaced: set[str]) -> None:
    """G2: the copy an automatic association replaced (a newer file of the same name, often another program
    of the same name) goes at once, unless a link still uses it; the user's own choices are never replaced
    here. Before, it stayed until "Nettoyer les fichiers inutilisés" (21 copies of one zip seen)."""
    used = {e["copy"] for a in data["assoc"].values() for e in a.values() if e.get("copy")}
    used |= {rel for rels in data["claude"].values() for rel in rels}
    for rel in replaced - used:
        path = Path(site_dir) / rel
        try:
            path.unlink()
            for folder in (path.parent, path.parent.parent):  # files/<page>/<sha>/ then files/<page>/
                folder.rmdir()
        except OSError:
            pass


@_one_at_a_time
def associate(archive: Any, site_dir: Path, uuid: str, link_id: str, action: str, path: str | None = None,
              upload: Path | None = None, upload_name: str = "") -> bool:
    """A choice of the user for one link: ``action`` "path" (a candidate shown in the menu, or the
    file ``upload`` sent by the browser), "none" (no file), "auto" (back to the automatic choice).
    False when the link or the file is unknown."""
    site_dir = Path(site_dir)
    data = load(site_dir)
    if uuid not in archive.conversations or action not in ACTIONS:
        return False
    link = next((x for x in _links(data, archive, uuid) if x["id"] == link_id), None)
    if link is None:
        return False
    assoc = data["assoc"].setdefault(uuid, {})
    if action == "none":
        assoc[link_id] = {"how": "user", "status": "user", "copy": None}
    elif action == "auto":
        old = assoc.pop(link_id, None)
        assoc[link_id], _ = _auto(site_dir, archive, uuid, link, None if old and old.get("how") == "user" else old,
                                  _candidates(data, link["name"]))
    elif upload is not None:
        st = upload.stat()
        copy = _store(site_dir, _page(archive, uuid), link["name"], upload)
        assoc[link_id] = {"how": "user", "status": "user", "copy": copy, "source": "", "upload": upload_name,
                          "size": st.st_size, "mtime": st.st_mtime}
    else:
        offered = {p for p, _, _ in data["candidates"].get(link["name"], [])}
        current = (assoc.get(link_id) or {}).get("source")
        if not path or (path not in offered and path != current) or not Path(path).is_file():
            return False  # only a file the menu showed
        src = Path(path)
        st = src.stat()
        copy = _store(site_dir, _page(archive, uuid), link["name"], src)
        assoc[link_id] = {"how": "user", "status": "user", "copy": copy, "source": str(src),
                          "size": st.st_size, "mtime": st.st_mtime}
    save(site_dir, data)
    return True


# --- what a page shows -----------------------------------------------------------------


def shared(raw: dict[str, Any], links: list[dict[str, Any]], assoc: dict[str, Any]) -> dict[str, int]:
    """Links associated automatically with the same file as a link of the same name in an earlier or
    later message of the same branch (successive versions: surely a wrong association), with the size
    of their group. A file sent again in another version of a message (edited on claude.ai) is really
    the same file: those links are on sibling branches and do not count."""
    from . import tree
    parent = {it.key: it.parent for it in tree.items_from_raw(raw)}

    def ancestors(key: str) -> set[str]:
        out: set[str] = set()
        while key in parent and key not in out:
            out.add(key)
            key = parent[key] or ""
        return out

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for link in links:
        e = assoc.get(link["id"]) or {}
        if e.get("how") == "auto" and e.get("copy") and e.get("status") != "same":
            groups.setdefault((link["name"], e.get("source", "")), []).append(link)
    out: dict[str, int] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        anc = {m["id"]: ancestors(m["msg"]) for m in members}
        root = {m["id"]: m["id"] for m in members}

        def find(x: str) -> str:
            while root[x] != x:
                x = root[x]
            return x

        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if a["msg"] != b["msg"] and (a["msg"] in anc[b["id"]] or b["msg"] in anc[a["id"]]):
                    root[find(a["id"])] = find(b["id"])
        sizes: dict[str, int] = {}
        for m in members:
            sizes[find(m["id"])] = sizes.get(find(m["id"]), 0) + 1
        for m in members:
            if sizes[find(m["id"])] > 1:
                out[m["id"]] = sizes[find(m["id"])]
    return out


def views(data: dict[str, Any], uuid: str, raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """For the renderer, by link id: the link, its association, the size of its group of surely
    wrong associations, and the candidates of its menu (with how many other links use each)."""
    cached = data["links"].get(uuid)
    links = cached["list"] if cached else links_in(raw)
    assoc = data["assoc"].get(uuid, {})
    wrong = shared(raw, links, assoc)
    used: dict[str, int] = {}
    for e in assoc.values():
        if e.get("source") and e.get("copy"):
            used[e["source"]] = used.get(e["source"], 0) + 1
    out = {}
    for link in links:
        e = assoc.get(link["id"]) or dict(NONE)
        cands = []
        for p, size, mtime in data["candidates"].get(link["name"], []):
            mine = bool(e.get("copy")) and p == e.get("source")
            cands.append({"path": p, "size": size, "mtime": mtime, "current": mine,
                          "others": used.get(p, 0) - (1 if mine else 0)})
        if e.get("copy") and e.get("source") and not any(c["current"] for c in cands):
            cands.insert(0, {"path": e["source"], "size": e.get("size", 0), "mtime": e.get("mtime", 0),
                             "current": True, "others": used.get(e["source"], 1) - 1})
        out[link["id"]] = {"link": link, "entry": e, "shared": wrong.get(link["id"], 0), "candidates": cands}
    return out


# --- orphans -------------------------------------------------------------------------


def orphans(archive: Any, site_dir: Path) -> list[tuple[str, int]]:
    """Copies of the site no link uses any more (path from the site folder, size)."""
    from .attachments import CREATED
    site_dir = Path(site_dir)
    data = load(site_dir)
    used = {e["copy"] for a in data["assoc"].values() for e in a.values() if e.get("copy")}
    used |= {rel for rels in data["claude"].values() for rel in rels}
    recorded = {_page(archive, u) for u in data["claude"] if u in archive.conversations}
    root = site_dir / FOLDER
    out = []
    for path in sorted(root.rglob("*")) if root.is_dir() else []:
        if not path.is_file():
            continue
        rel = path.relative_to(site_dir).as_posix()
        parts = rel.split("/")
        if rel in used or (len(parts) > 3 and parts[2] == CREATED and parts[1] not in recorded):
            continue  # a page not rendered since this version: its copies are kept
        out.append((rel, path.stat().st_size))
    return out


@_one_at_a_time
def remove_orphans(archive: Any, site_dir: Path) -> tuple[int, int]:
    """Remove the orphans (and the folders left empty); returns how many files and bytes."""
    site_dir = Path(site_dir)
    n = size = 0
    for rel, s in orphans(archive, site_dir):
        try:
            (site_dir / rel).unlink()
        except OSError:
            continue
        n += 1
        size += s
    root = site_dir / FOLDER
    folders = sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)) if root.is_dir() else []
    for folder in folders:
        try:
            folder.rmdir()
        except OSError:
            pass
    return n, size
