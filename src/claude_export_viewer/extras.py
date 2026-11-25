"""The other data of the export (11/11): the memory of claude.ai, the reflections, the Claude Design chats and the
artifacts ("frames"), read from the export ZIPs kept in archive/exports/<date>/ (all the categories are downloaded
since 08/11), shown read-only in pages of their own (extras/) linked from a folded section of the index.

Shapes seen (export of 23/10/2026):
- memories-000.zip  memories/<account>.json      {account_uuid, memory_files: [{path, content, updated_at}]}
- feedback-000.zip  reflections/<account>.json   {account_uuid, feedback: [], reflections: [{content, created_at,
                                                  period, updated_at}]}
- design_chats-000.zip design_chats/<uuid>.json  {uuid, title, created_at, updated_at, project {name, uuid},
                                                  messages: [{uuid, role, content (an object), created_at}]}
- frames-000.zip    artifacts/<id>/artifact.json {id, kind, active_version, owner_account, updated_at, visibility,
                                                  versions: [{id, title, created_at, description?}]}
                    artifacts/<id>/versions/<v>.files.json {files: [{original_path, exported_as, mime_type, sha256,
                                                  size_bytes}]}, the files under artifacts/<id>/versions/<v>/
                    (index.html, project/canvas.json {title, boards {file: {title…}}, order}, project/*.dc.html,
                    artifact-type/… — the whole Claude Design application, 4 MB a version).

Every export keeps its own copy: the memory is shown version by version (one per export where it changed); the
other data are merged, the most recent export winning. A version of an artifact is extracted only when it is
opened (artifact_server: a second local server on another port, so another origin: no access to the site, its
storage or its commands; nothing from the Internet)."""

from __future__ import annotations

import difflib
import html
import json
import re
import shutil
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

FOLDER = "extras"                    # in the site folder: the pages, and artifacts/<id>/<version>/ once opened
ARTIFACTS = "artifacts"
SAFE_ID = re.compile(r"^[\w.-]{1,100}$")
MAX_VERSION = 300 * 1024 * 1024      # bytes of one version extracted
MAX_META = 20 * 1024 * 1024         # bytes of one JSON describing an artifact (artifact.json, .files.json, canvas.json)
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


# --- reading the exports ------------------------------------------------------------------------------------------

def _export_dirs(site_dir: Path) -> list[Path]:
    """The export folders, oldest first (by the date of their ZIPs)."""
    root = Path(site_dir) / "archive" / "exports"
    if not root.is_dir():
        return []
    dirs = [d for d in root.iterdir() if d.is_dir() and any(d.glob("*.zip"))]
    return sorted(dirs, key=lambda d: (max(z.stat().st_mtime for z in d.glob("*.zip")), d.name))


def _label(folder: Path) -> str:
    """The date of an export: its folder name (2026-10-23_175235), else the date of its ZIPs."""
    m = _DATE.match(folder.name)
    if m:
        return m.group(1)
    return datetime.fromtimestamp(max(z.stat().st_mtime for z in folder.glob("*.zip"))).strftime("%Y-%m-%d")


def _members(folder: Path, category: str, prefix: str, suffix: str = ".json") -> Iterator[tuple[Path, str, Any]]:
    """(ZIP, member name, JSON) of the members of a category starting with ``prefix``; broken ones skipped."""
    for z in sorted(folder.glob(f"{category}*.zip")):
        try:
            with zipfile.ZipFile(z) as f:
                for name in f.namelist():
                    if name.startswith(prefix) and name.endswith(suffix):
                        try:
                            yield z, name, json.loads(f.read(name).decode("utf-8"))
                        except (ValueError, UnicodeDecodeError, OSError):
                            continue
        except (OSError, zipfile.BadZipFile):
            continue


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""


def memory_versions(site_dir: Path) -> list[dict[str, Any]]:
    """The memory of claude.ai in each export where it changed, oldest first: [{date, files: [{path, content,
    updated_at}]}]."""
    out: list[dict[str, Any]] = []
    for folder in _export_dirs(site_dir):
        files = []
        for _z, _n, data in _members(folder, "memories", "memories/"):
            for m in (data.get("memory_files") or []) if isinstance(data, dict) else []:
                if isinstance(m, dict) and _s(m.get("path")):
                    files.append({"path": m["path"], "content": _s(m.get("content")), "updated_at": _s(m.get("updated_at"))})
        if not files:
            continue
        files.sort(key=lambda m: m["path"])
        if out and [(m["path"], m["content"]) for m in out[-1]["files"]] == [(m["path"], m["content"]) for m in files]:
            continue  # unchanged
        out.append({"date": _label(folder), "files": files})
    return out


def reflections(site_dir: Path) -> list[dict[str, str]]:
    """The reflections of claude.ai, newest first, merged over the exports."""
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for folder in _export_dirs(site_dir):
        for _z, _n, data in _members(folder, "feedback", "reflections/"):
            for r in (data.get("reflections") or []) if isinstance(data, dict) else []:
                if isinstance(r, dict) and _s(r.get("content")):
                    seen[(_s(r.get("period")), _s(r.get("created_at")))] = {
                        "period": _s(r.get("period")), "created_at": _s(r.get("created_at")),
                        "updated_at": _s(r.get("updated_at")), "content": r["content"]}
    return sorted(seen.values(), key=lambda r: (r["created_at"], r["period"]), reverse=True)


def _text_of(content: Any) -> str:
    """The text of a message of Claude Design, whatever its shape: a string, a list of blocks, an object holding
    "text" / "content" / "parts"…; "" when none (then shown raw)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n\n".join(t for t in (_text_of(x) for x in content) if t)
    if isinstance(content, dict):
        if content.get("type") not in (None, "text") and "text" not in content:
            return ""
        for key in ("text", "content", "parts", "markdown", "value", "message"):
            if key in content:
                t = _text_of(content[key])
                if t:
                    return t
    return ""


def design_chats(site_dir: Path) -> list[dict[str, Any]]:
    """The Claude Design chats, newest first, merged over the exports (the latest export wins)."""
    chats: dict[str, dict[str, Any]] = {}
    for folder in _export_dirs(site_dir):
        for _z, name, data in _members(folder, "design_chats", "design_chats/"):
            if not isinstance(data, dict):
                continue
            uid = _s(data.get("uuid")) or Path(name).stem
            if not SAFE_ID.match(uid):
                continue
            messages = []
            for m in data.get("messages") or []:
                if not isinstance(m, dict):
                    continue
                body = m.get("content")
                text = _text_of(body)
                body = body if isinstance(body, dict) else {}
                # your files joined (name, text) and the tools Claude Design used (name, its answer cut)
                files = [{"name": _s(a.get("name")) or "?", "content": _s(a.get("content"))}
                         for a in body.get("attachments") or [] if isinstance(a, dict)]
                tools = []
                for b in body.get("contentBlocks") or []:
                    call = b.get("toolCall") if isinstance(b, dict) else None
                    if isinstance(call, dict):
                        tools.append({"name": _s(call.get("name")) or "?",
                                      "input": json.dumps(call.get("input"), ensure_ascii=False)[:2000],
                                      "output": _s(call.get("output"))[:2000]})
                messages.append({"role": "human" if m.get("role") in ("user", "human") else "assistant",
                                 "text": text, "raw": "" if text else json.dumps(m.get("content"), ensure_ascii=False, indent=1),
                                 "created_at": _s(m.get("created_at")) or _s(body.get("timestamp")),
                                 "files": files, "tools": tools})
            project = data.get("project") if isinstance(data.get("project"), dict) else {}
            chats[uid] = {"uuid": uid, "title": _s(data.get("title")), "created_at": _s(data.get("created_at")),
                          "updated_at": _s(data.get("updated_at")), "project": _s(project.get("name")), "messages": messages}
    return sorted(chats.values(), key=lambda c: c["updated_at"] or c["created_at"], reverse=True)


@dataclass
class Version:
    id: str
    title: str
    created_at: str
    description: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)   # {path, member, size}
    boards: list[tuple[str, str]] = field(default_factory=list)  # (file under project/, title)

    @property
    def size(self) -> int:
        return sum(f["size"] for f in self.files)

    @property
    def openable(self) -> bool:
        return any(f["path"] == "index.html" for f in self.files)


@dataclass
class Artifact:
    id: str
    kind: str
    updated_at: str
    zip: Path
    active: str = ""
    versions: list[Version] = field(default_factory=list)

    @property
    def title(self) -> str:
        return next((v.title for v in self.versions if v.id == self.active and v.title),
                    next((v.title for v in self.versions if v.title), self.id))


def _safe_path(p: str) -> bool:
    parts = p.replace("\\", "/").split("/")
    return bool(p) and not p.startswith("/") and ".." not in parts and "" not in parts and ":" not in parts[0]


def artifacts(site_dir: Path) -> list[Artifact]:
    """The artifacts of the export, newest first, the latest export of each winning."""
    found: dict[str, Artifact] = {}
    for folder in _export_dirs(site_dir):
        for z in sorted(folder.glob("frames*.zip")):
            try:
                f = zipfile.ZipFile(z)
            except (OSError, zipfile.BadZipFile):
                continue
            with f:
                names = set(f.namelist())

                def load(name: str) -> Any:
                    try:
                        if f.getinfo(name).file_size > MAX_META:  # (25/11, Gemini audit) never read a huge JSON
                            return None
                        return json.loads(f.read(name).decode("utf-8"))
                    except (KeyError, ValueError, UnicodeDecodeError, OSError):
                        return None

                for name in sorted(n for n in names if n.startswith(ARTIFACTS + "/") and n.endswith("/artifact.json")):
                    aid = name.split("/")[1]
                    data = load(name)
                    if not SAFE_ID.match(aid) or not isinstance(data, dict):
                        continue
                    art = Artifact(id=aid, kind=_s(data.get("kind")), updated_at=_s(data.get("updated_at")), zip=z,
                                   active=_s(data.get("active_version")))
                    for v in data.get("versions") or []:
                        if not isinstance(v, dict) or not SAFE_ID.match(_s(v.get("id"))):
                            continue
                        ver = Version(id=v["id"], title=_s(v.get("title")), created_at=_s(v.get("created_at")),
                                      description=_s(v.get("description")))
                        base = f"{ARTIFACTS}/{aid}/versions/{ver.id}"
                        listing = load(base + ".files.json")
                        for x in (listing or {}).get("files") or [] if isinstance(listing, dict) else []:
                            if not isinstance(x, dict):
                                continue
                            path, member = _s(x.get("original_path")), f"{base}/{_s(x.get('exported_as'))}"
                            if _safe_path(path) and member in names:
                                # the size of the ZIP itself, never the "size_bytes" of the listing: zipfile never gives
                                # more bytes than it (review of 21/11, A3), so MAX_VERSION really bounds an extraction
                                size = f.getinfo(member).file_size
                                ver.files.append({"path": path, "member": member, "size": size})
                        canvas = load(base + "/project/canvas.json")
                        if isinstance(canvas, dict) and isinstance(canvas.get("boards"), dict):
                            order = [b for b in canvas.get("order") or [] if b in canvas["boards"]]
                            order += [b for b in canvas["boards"] if b not in order]
                            for b in order:
                                info = canvas["boards"][b] if isinstance(canvas["boards"][b], dict) else {}
                                if _safe_path(b):
                                    ver.boards.append((b, _s(info.get("title")) or b))
                            if not ver.title:
                                ver.title = _s(canvas.get("title"))
                        art.versions.append(ver)
                    art.versions.sort(key=lambda v: v.created_at, reverse=True)
                    found[aid] = art
    return sorted(found.values(), key=lambda a: a.updated_at, reverse=True)


# --- opening a version ----------------------------------------------------------------------------------------------

def extract(site_dir: Path, art_id: str, version: str) -> Path:
    """The folder of a version, extracted from its ZIP once (KeyError when unknown, ValueError when too big)."""
    if not (SAFE_ID.match(str(art_id)) and SAFE_ID.match(str(version))):
        raise KeyError(art_id)
    art = next((a for a in artifacts(site_dir) if a.id == art_id), None)
    ver = next((v for v in art.versions if v.id == version), None) if art else None
    if art is None or ver is None or not ver.files:
        raise KeyError(version)
    if ver.size > MAX_VERSION:
        raise ValueError("version trop grosse")
    target = Path(site_dir) / FOLDER / ARTIFACTS / art_id / version
    if (target / ".complete").is_file():
        return target
    tmp = target.with_name(version + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(art.zip) as f:
            root = tmp.resolve()
            for x in ver.files:
                out = tmp / x["path"]
                # (25/11, Gemini audit) defence in depth after _safe_path: the final path stays in the folder
                if not out.resolve().is_relative_to(root) or out.resolve() == root:
                    raise ValueError(f"chemin refusé : {x['path']!r}")
                out.parent.mkdir(parents=True, exist_ok=True)
                with f.open(x["member"]) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)  # nothing half-written left in the site
        raise
    (tmp / ".complete").write_text("", encoding="utf-8")
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return target


def extracted_size(site_dir: Path) -> int:
    root = Path(site_dir) / FOLDER / ARTIFACTS
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.is_dir() else 0


def clear_extracted(site_dir: Path) -> int:
    """Remove the versions extracted (extracted again when opened); returns the bytes freed."""
    size = extracted_size(site_dir)
    shutil.rmtree(Path(site_dir) / FOLDER / ARTIFACTS, ignore_errors=True)
    return size


def extracted_state(site_dir: Path) -> dict[str, int]:
    """For the cleaning frame of the index (AF-f1, 14/11): the versions extracted and their bytes."""
    root = Path(site_dir) / FOLDER / ARTIFACTS
    count = sum(1 for p in root.glob("*/*/.complete")) if root.is_dir() else 0
    return {"count": count, "size": extracted_size(site_dir)}


# The artifacts run on their own local server: another port is another origin, so a page of an artifact reaches
# neither the site (its storage, the token of its commands) nor the Internet (CSP).
CSP = ("default-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data:; connect-src 'self' blob: data:; "
       "frame-ancestors 'self'; form-action 'none'")


class _ArtifactHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        port = self.server.server_address[1]
        if self.headers.get("Host", "") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            self.send_error(403)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()


_servers: dict[str, ThreadingHTTPServer] = {}
_lock = threading.Lock()


def artifact_server(folder: Path) -> int:
    """The port of the server of one version extracted (started the first time): its folder at the root, as the
    application of Claude Design asks some files by "/…" paths."""
    root = Path(folder).resolve()
    with _lock:
        server = _servers.get(str(root))
        if server is None:
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_ArtifactHandler, directory=str(root)))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            _servers[str(root)] = server
        return server.server_address[1]


def stop_servers() -> None:
    with _lock:
        for s in _servers.values():
            s.shutdown()
            s.server_close()
        _servers.clear()


# --- the summary of the index and the pages ------------------------------------------------------------------------

# --- categories CEV does not know yet (11/11) ---------------------------------------------------------------------

KNOWN = {"conversations", "projects", "light_metadata", "users", "memories", "feedback", "design_chats", "frames"}
_CATEGORY = re.compile(r"^([a-z][a-z_]*)-\d{3}\.zip$")   # the split ZIPs of the manifest: <category>-000.zip
MAX_SHOWN = 200 * 1024                                     # characters of one file shown on its page


def other_categories(site_dir: Path) -> dict[str, Path]:
    """{category: latest export folder holding it} for the export categories CEV has no page for (scheduled
    tasks, Claude Code… whatever claude.ai adds): shown as they are, read-only."""
    found: dict[str, Path] = {}
    for d in _export_dirs(site_dir):
        for z in d.glob("*.zip"):
            m = _CATEGORY.match(z.name)
            if m and m.group(1) not in KNOWN:
                found[m.group(1)] = d
    return dict(sorted(found.items()))


def other_files(folder: Path, category: str) -> list[dict[str, Any]]:
    """The files of a category in one export: {name, size, text} (JSON indented; text cut at MAX_SHOWN, None when
    not text)."""
    out: list[dict[str, Any]] = []
    for z in sorted(folder.glob(f"{category}-*.zip")):
        try:
            with zipfile.ZipFile(z) as f:
                for info in f.infolist():
                    if info.is_dir():
                        continue
                    text: str | None = None
                    if info.file_size <= 20 * MAX_SHOWN:
                        try:
                            text = f.read(info).decode("utf-8")
                            if info.filename.endswith(".json"):
                                text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
                        except (ValueError, UnicodeDecodeError, OSError):
                            text = None
                    if text is not None and len(text) > MAX_SHOWN:
                        text = text[:MAX_SHOWN] + "\n…"
                    out.append({"name": info.filename, "size": info.file_size, "text": text})
        except (OSError, zipfile.BadZipFile):
            continue
    return out


def category_label(category: str) -> str:
    """design_chats → Design chats."""
    words = category.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def summary(site_dir: Path, read: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the index shows of the other data. ``read``: what write_extras has already read ("memory",
    "reflections", "design", "artifacts", "others": {category: files}), so that no ZIP is read twice (review of
    21/11, P2); whatever it lacks is read here."""
    read = read or {}
    mem = read["memory"] if "memory" in read else memory_versions(site_dir)
    arts = read["artifacts"] if "artifacts" in read else artifacts(site_dir)
    files = read["others"] if "others" in read else {c: other_files(d, c) for c, d in other_categories(site_dir).items()}
    others = [{"category": c, "label": category_label(c), "files": len(f)} for c, f in files.items()]
    refl = read["reflections"] if "reflections" in read else reflections(site_dir)
    design = read["design"] if "design" in read else design_chats(site_dir)
    return {"memory": len(mem[-1]["files"]) if mem else 0, "memory_date": mem[-1]["date"] if mem else "",
            "memory_versions": len(mem), "reflections": len(refl),
            "design": len(design), "artifacts": len(arts),
            "artifact_versions": sum(len(a.versions) for a in arts), "others": others}


def diff_html(old: str, new: str) -> str:
    """The lines added (ins) and removed (del) from one version of a memory file to the next."""
    out = []
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        tag, text = line[:2], html.escape(line[2:])
        if tag == "+ ":
            out.append(f'<ins class="ex-add">{text}</ins>')
        elif tag == "- ":
            out.append(f'<del class="ex-del">{text}</del>')
        elif tag == "  ":
            out.append(f'<span class="ex-same">{text}</span>')
    return "".join(out)  # block lines: no newline between them (it made an empty line)
