"""The site: one HTML page per archived conversation, and the index.

Pages are regenerated only when needed (see ``build_site_from_archive``), so
that importing a new export only rewrites what changed.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from . import jsonfile
from . import __version__, annotations, cdn_cache, esm_cache, extras, widget_host, attachments, backup, created, dates, icons, tokens, i18n, searchdata, system, topics, tree, userfiles
from .i18n import html_date, html_text, t
from .markdown_export import conversation_markdown, embed, export_filename, marker, message_body
from .math_plugin import contains_math
from .models import ChatMessage, Conversation, TextContent, ThinkingContent, TokenBudgetContent, parse_message
from .renderer import render_markdown, render_message

if TYPE_CHECKING:
    from .archive import Archive

_PACKAGE_DIR = Path(__file__).parent
_STATIC_FILES = ("style.css", "code.js", "export.js", "admin.js", "nav.js", "i18n.js", "topics.js", "files.js", "fold.js", "msg.js", "search.js", "query.js", "favorites.js", "dashboard.js", "confirm.js", "annot.js", "links.js", "notes.js", "marks.js", "plan.js", "plan.css", "structure.js", "speak.js", "extras.js",
                 "run.js", "run-libs.js", "run-libs-LICENSES.txt", "icon.svg", "parts.js")
_UUID = re.compile(r"[0-9a-fA-F-]{8,64}")


@dataclass
class IndexEntry:
    """What the index page needs about a conversation (its messages are not kept)."""

    name: str
    created_at: datetime | None
    updated_at: datetime | None
    account_uuid: str
    project_uuid: str
    n_messages: int
    filename: str
    deleted_since: str = ""  # ISO day of the first export missing it, when deleted on claude.ai
    last_message: datetime | None = None  # most recent message, other versions included
    other_versions: int = 0
    removed_parts: int = 0
    uuid: str = ""
    tokens: dict | None = None  # rough evaluation of the tokens used (tokens.py)

    @property
    def last_activity(self) -> datetime | None:
        return self.last_message or self.updated_at or self.created_at

    @property
    def active_later(self) -> bool:
        """Last message on another day than the creation (worth showing)."""
        a, c = self.last_activity, self.created_at
        return bool(a and c and dates.local(a).date() != dates.local(c).date())


@dataclass
class RenderStats:
    rendered: int = 0
    total: int = 0
    deleted: int = 0
    failed: int = 0


# --- Templates -----------------------------------------------------------------


def _claude_url(uuid: str | None) -> str:
    """Address of the conversation on claude.ai ("" if the identifier looks wrong)."""
    return f"https://claude.ai/chat/{uuid}" if uuid and _UUID.fullmatch(uuid) else ""


def _environment() -> Environment:
    env = Environment(
        loader=PackageLoader("claude_export_viewer", "templates"),
        autoescape=select_autoescape(["html.j2"]),
    )
    env.filters["claude_url"] = _claude_url
    env.globals.update(
        t=t,
        T=lambda key, tag="span", attrs="", **args: Markup(html_text(key, tag, attrs, **args)),
        Rich=lambda key, **args: Markup(i18n.html_rich(key, **args)),
        date=lambda d, with_time=False, to_local=True: Markup(html_date(d, with_time, to_local)),
        attr=lambda name, key, **args: Markup(
            f'{name}="{html.escape(t(key, **args))}" data-i18n-attr="{name}:{key}"'),
        # (22/11) two translated attributes on one element: one data-i18n-attr (two of them, the browser keeps the
        # first only, and the second attribute was no longer translated when the language changes)
        attr2=lambda n1, k1, n2, k2: Markup(
            f'{n1}="{html.escape(t(k1))}" {n2}="{html.escape(t(k2))}" data-i18n-attr="{n1}:{k1};{n2}:{k2}"'),
        args=lambda **kw: Markup(i18n.html_args(**kw)),
        Day=i18n.Day,
        icon=lambda name, size=16, cls="": Markup(icons.svg(name, size, cls)),
        LocalDate=i18n.LocalDate,
        Tokens=i18n.Tokens,
        lang=i18n.language,
        isodate=lambda s, with_time=False: Markup(html_date(dates.parse(s), with_time)),
        md=lambda text: Markup(render_markdown(text or "")),
    )
    return env


def _prepare_output(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    convo_dir = output_dir / "conversations"
    convo_dir.mkdir(exist_ok=True)
    for name in _STATIC_FILES:
        shutil.copy(_PACKAGE_DIR / "static" / name, output_dir / name)
    # KaTeX goes *under* conversations/ so that every browser (Firefox included)
    # accepts loading its fonts from file:// URLs.
    shutil.copytree(_PACKAGE_DIR / "static" / "katex", convo_dir / "katex", dirs_exist_ok=True)
    # texts of every language for the pages (see static/i18n.js)
    (output_dir / "i18n-data.js").write_text(i18n.web_data_script(), encoding="utf-8")
    (output_dir / "icons.js").write_text(icons.script(), encoding="utf-8")  # the icons for the scripts (AF-f3)
    (output_dir / "i18n").mkdir(exist_ok=True)
    for lang, text in i18n.web_text_scripts().items():
        (output_dir / "i18n" / f"{lang}.js").write_text(text, encoding="utf-8")
    topics.write_data_js(output_dir)
    annotations.write_data_js(output_dir)
    return convo_dir


def search_signature() -> str:
    """What the text of the search depends on (15/11): the extraction and the rendering of the messages, not the
    look of the pages. An update of the program that leaves them alone makes the pages again, not this text
    (measured: half of a rebuild)."""
    h = hashlib.sha256()
    for f in (_PACKAGE_DIR / "searchdata.py", _PACKAGE_DIR / "renderer.py",
              _PACKAGE_DIR / "templates" / "conversation.html.j2"):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def generator_signature() -> str:
    """Changes whenever the code or templates producing the pages change."""
    h = hashlib.sha256()
    files = sorted(
        [*_PACKAGE_DIR.glob("*.py"), *(_PACKAGE_DIR / "templates").glob("*"), *(_PACKAGE_DIR / "static").glob("*.*"),
         *(_PACKAGE_DIR / "i18n").glob("*.json")]
    ) + [_PACKAGE_DIR / "static" / "katex" / "render.js"]
    for f in files:
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _launcher() -> str:
    """Path of the program, for the commands shown on the pages."""
    candidate = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if candidate and candidate.name == "claude-export-viewer.py" and candidate.exists():
        return str(candidate.resolve())
    return "claude-export-viewer.py"


# --- A conversation ------------------------------------------------------------


def _branch_frame(branch: tree.Branch) -> str:
    n = branch.size
    if branch.removed:
        seen = dates.parse(branch.first.last_seen)
        title = (html_text("web.frame.removed_seen", n=n, date=i18n.Day(branch.first.last_seen[:10])) if seen
                 else html_text("web.frame.removed", n=n))
        css = "removed-part"
    else:
        started = dates.parse(branch.first.created)
        title = (html_text("web.frame.alt_started", n=n, date=started) if started
                 else html_text("web.frame.alt", n=n))
        css = "removed-part alt-version"
    return (
        f'<details class="{css}">'
        f"<summary>{title}</summary>"
        f'<div class="removed-messages">{"".join(branch.content)}</div>'
        "</details>"
    )


def _render_tree(
    items: list[tree.Item], to_message: Callable[[Any], ChatMessage | None],
    files: dict[str, list[created.Presented]] | None = None,
) -> tuple[list[str], list[ChatMessage]]:
    files = files or {}

    def render_item(item: tree.Item) -> str:
        msg = to_message(item.payload)
        if msg is None:
            return ""
        handed = files.get(item.key)
        cut = _cut_reply(msg)
        return render_message(msg, message_body(msg, files=handed, as_typed=False), handed,
                              note=html_text("web.cut", "div", ' class="cut-note"') if cut else "",
                              css=" cev-cut" if cut else "")

    pieces, path = tree.render(items, render_item, _branch_frame)
    main = [m for m in (to_message(it.payload) for it in path) if m is not None]
    return [p for p in pieces if p], main


# A reply of Claude without text, holding only thinking or empty text (or nothing): the user interrupted
# it, or claude.ai compacted the conversation there; the export tells nothing more. Its bubble keeps the
# thinking and ends with "Message interrompu ou compaction"; the whole message is hidden with claude.ai's
# resources (style.css .cev-cut), so that no empty bubble is ever shown.
def _cut_reply(msg: ChatMessage) -> bool:
    if msg.sender != "assistant" or msg.text.strip() or msg.attachments or msg.files:
        return False
    return all(isinstance(b, (ThinkingContent, TokenBudgetContent))
               or (isinstance(b, TextContent) and not b.text.strip()) for b in msg.content)


def render_archived_conversation(raw: dict[str, Any], files: dict[str, list[created.Presented]] | None = None,
                                 to_message: Callable[[Any], ChatMessage | None] = parse_message,
                                 items: list[tree.Item] | None = None,
                                 ) -> tuple[Conversation, list[str]]:
    """Validate an archived conversation and render it as a tree: main branch, other branches in frames
    (``files``: created.reconstruct(raw), computed when not given)."""
    convo = Conversation.model_validate({**raw, "chat_messages": []})
    rendered, main = _render_tree(tree.items_from_raw(raw) if items is None else items, to_message,
                                  created.reconstruct(raw) if files is None else files)
    convo.chat_messages = main  # the header counts the messages of the main branch
    return convo, rendered


# --- Very long conversations: several pages (step 4 of the reading in pieces, 21/11) --------------------------------
# A conversation whose messages hold more than SPLIT_ABOVE characters is shown in parts of about PART_CHARS: each part
# is an ordinary page (search in the page, Structure, favorites, notes, export: on that part), the next part begins
# with one of your messages, the branches that leave a message stay in its part. Parts 2… are "<name>.p2.html"…;
# "<name>.parties.js" (window.CEV_PART_OF: message -> part) is read by parts.js when a link #msg=… names a message
# of another part. An ordinary conversation is one page, made as before.

SPLIT_ABOVE = 8 << 20   # characters of messages beyond which a conversation is cut into parts
PART_CHARS = 4 << 20    # characters of messages in one part (a page a browser shows at ease)
SMALL_FILE = 512 << 10  # a stored file smaller than this (compressed) is shown whole without being measured first
SEARCH_CAP = 16 << 20   # characters of a cut conversation given to the search of the index (its first parts)


def part_limits() -> tuple[int, int]:
    """(SPLIT_ABOVE, PART_CHARS), lower on a computer with little free memory (making a page takes about ten times
    its text: measured 4.5 times for the import alone)."""
    free = system.available_memory()
    if not free:
        return SPLIT_ABOVE, PART_CHARS
    split = max(1 << 20, min(SPLIT_ABOVE, free // 40))
    return split, max(512 << 10, min(PART_CHARS, split // 2))


def part_pages(key: str, n: int) -> list[str]:
    return [f"{key}.html"] + [f"{key}.p{k}.html" for k in range(2, n + 1)]


@dataclass
class _Parts:
    plan: tree.PartPlan
    summary: tree.Summary


def _plan_parts(archive: Archive, meta: dict[str, Any]) -> _Parts | None:
    """The parts of a very long conversation, None for an ordinary one (shown in one page). Reads the conversation
    line by line: in memory only the skeletons, sizes and senders of its messages."""
    from .archive import StoredConversation, _extras_of as archive_extras

    path = archive.raw_file(meta)
    if path.stat().st_size < SMALL_FILE:
        return None
    split, budget = part_limits()
    stored = StoredConversation(path)
    weight: dict[str, int] = {}
    human: set[str] = set()
    current, extras = [], []
    for m in stored.items("chat_messages"):
        if isinstance(m, dict):
            k = tree.message_key(m)
            weight[k] = weight.get(k, 0) + len(json.dumps(m, ensure_ascii=False))
            if m.get("sender") == "human":
                human.add(k)
            current.append(tree.skeleton(m))
    for m in archive_extras(stored):
        k = tree.message_key(m)
        weight[k] = weight.get(k, 0) + len(json.dumps(m, ensure_ascii=False))
        extras.append(tree.skeleton(m, extra=True))
    if sum(weight.values()) <= split:
        return None
    plan = tree.plan_parts(tree.skeleton_items(current, extras), weight, human, budget)
    if len(plan.ranges) <= 1:
        return None
    return _Parts(plan, tree.summarize(tree.skeleton_items(current, extras)))


def plan_of(archive: Archive, uuid: str) -> _Parts | None:
    """The parts of a conversation of the archive (None: an ordinary one, whole in one page)."""
    return _plan_parts(archive, archive.conversations[uuid])


def iter_part_raws(archive: Archive, uuid: str, parts: _Parts) -> Iterator[tuple[int, dict[str, Any], str]]:
    """(part, conversation of that part, last message of its main branch) for each part, in order: the messages are
    first spread over one temporary file per part (one reading of the conversation); one part at a time in memory.
    A part holds its messages and the branches leaving them, as an archived conversation (tree.EXTRA_KEY for the
    messages kept from earlier exports)."""
    from .archive import _extras_of as archive_extras, _raw_lists

    plan = parts.plan
    stored = archive.stored(uuid)
    fields = {k: v for k, v in stored.meta.items() if k not in _raw_lists()}
    tmp = archive.temp_dir / f"parties-{archive.conversations[uuid]['filename'].removesuffix('.html')}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        for tag, messages in (("c", stored.items("chat_messages")), ("x", archive_extras(stored))):
            out, current = None, None
            for m in messages:
                part = plan.part_of.get(tree.message_key(m)) if isinstance(m, dict) else None
                if part is None:
                    continue
                if part != current:
                    if out:
                        out.close()
                    out, current = (tmp / f"{part}-{tag}.jsonl").open("a", encoding="utf-8"), part
                out.write(json.dumps(m, ensure_ascii=False) + "\n")
            if out:
                out.close()

        def read(part: int, tag: str) -> list[Any]:
            path = tmp / f"{part}-{tag}.jsonl"
            if not path.exists():
                return []
            with path.open(encoding="utf-8") as f:
                return [json.loads(line) for line in f]

        for part, (_, b) in enumerate(plan.ranges):
            raw = dict(fields)
            raw["chat_messages"] = read(part, "c")
            extras = read(part, "x")
            if extras:
                raw[tree.EXTRA_KEY] = extras
            yield part, raw, plan.path[b - 1]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _render_parts(template: Any, archive: Archive, uuid: str, meta: dict[str, Any], info: dict[str, Any],
                  parts: _Parts, convo_dir: Path, key: str, files: dict[str, Any]) -> dict[str, Any]:
    """Write the pages of the parts; returns the search data (its first parts, at most SEARCH_CAP characters)."""
    plan = parts.plan
    pages = part_pages(key, len(plan.ranges))
    texts, formulas, size, partial_search = [], [], 0, False
    for part, raw, leaf in iter_part_raws(archive, uuid, parts):
        pinfo = {**info, "part": part, "part_pages": pages, "parts_map": f"{key}.parties.js", "n_total": len(plan.path)}
        attachments.set_links(userfiles.views(files, uuid, raw))
        html = _render_page(template, raw, pinfo, meta, leaf_key=leaf)
        (convo_dir / pages[part]).write_text(html, encoding="utf-8")
        if not partial_search:
            data = searchdata.from_page(html)
            if size + len(data["t"]) > SEARCH_CAP and texts:
                partial_search = True
            else:
                texts.append(data["t"])
                formulas += data["m"]
                size += len(data["t"])
        del raw, html
    (convo_dir / f"{key}.parties.js").write_text(
        "window.CEV_PART_OF = " + json.dumps(plan.part_of, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")
    for old in convo_dir.glob(f"{key}.p*.html"):
        if old.name not in pages:
            old.unlink()
    s = parts.summary  # of the whole conversation, not of the last part made
    meta["other_versions"], meta["removed_parts"], meta["last_message"] = s.other_versions, s.removed_parts, s.last_message
    meta["parts"] = len(pages)
    meta["search_partial"] = partial_search
    return {"t": searchdata.SEPARATOR.join(texts), "m": formulas}


def _one_page(convo_dir: Path, key: str, meta: dict[str, Any]) -> None:
    """A conversation shown in one page: the parts of an earlier rendering removed."""
    for old in convo_dir.glob(f"{key}.p*.html"):
        old.unlink()
    (convo_dir / f"{key}.parties.js").unlink(missing_ok=True)
    meta.pop("parts", None)
    meta.pop("search_partial", None)


# --- The site ------------------------------------------------------------------


def _last_import(archive: Archive) -> float | None:
    """When the latest export was imported (timestamp): a backup older than that misses it (AF-f4)."""
    stamps = [e.get("imported_at") for e in archive.state.get("exports", []) if e.get("imported_at")]
    if not stamps:
        return None
    try:
        return datetime.fromisoformat(max(stamps).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _write_index(
    env: Environment,
    output_dir: Path,
    entries: list[IndexEntry],
    user_map: dict[str, str],
    all_projects: dict[str, str],
    latest_export: str = "",
    import_cut: str = "",
    last_import: float | None = None,
) -> None:
    extra = write_extras(env, Path(output_dir))  # the other data of the export, linked from the index
    # Only list projects actually referenced by conversations
    referenced = {e.project_uuid for e in entries if e.project_uuid}
    project_map = {k: v for k, v in all_projects.items() if k in referenced}

    def sort_key(e: IndexEntry) -> str:
        d = e.created_at or e.updated_at
        return d.isoformat() if d else ""

    entries.sort(key=sort_key, reverse=True)
    index_html = env.get_template("index.html.j2").render(
        conversations=entries,
        user_map=user_map,
        project_map=project_map,
        n_deleted=sum(1 for e in entries if e.deleted_since),
        version=__version__,
        latest_export=latest_export,
        import_cut=import_cut,
        damaged=jsonfile.damaged(output_dir),
        site_name=Path(output_dir).resolve().name,
        site_size=backup.site_size(output_dir),
        last_backup=backup.last_backup(output_dir) or "",
        last_import=last_import or "",
        extras=extra,
    )
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")


def write_extras(env: Environment, output_dir: Path) -> dict[str, Any]:
    """The pages of the other data of the export (extras.py): extras/memory.html, reflections.html, design.html and
    one page per Claude Design chat, artifacts.html; pages left from data no longer there are removed. Returns the
    summary shown by the index."""
    folder = Path(output_dir) / extras.FOLDER
    folder.mkdir(exist_ok=True)
    template = env.get_template("extras.html.j2")
    written: set[str] = set()

    def page(name: str, **ctx: Any) -> None:
        (folder / name).write_text(template.render(**ctx), encoding="utf-8")
        written.add(name)

    versions = extras.memory_versions(output_dir)
    diffs: dict[str, str] = {}
    removed: list[list[str]] = []
    for i, v in enumerate(versions):
        before = {f["path"]: f["content"] for f in versions[i - 1]["files"]} if i else {}
        for f in v["files"]:
            diffs[f"{i}:{f['path']}"] = Markup(extras.diff_html(before.get(f["path"], ""), f["content"]))
        removed.append(sorted(set(before) - {f["path"] for f in v["files"]}))
    page("memory.html", kind="memory", title_key="web.extras.memory", versions=versions, diffs=diffs, removed=removed)
    refl = extras.reflections(output_dir)
    page("reflections.html", kind="reflections", title_key="web.extras.reflections", items=refl)
    chats = extras.design_chats(output_dir)
    page("design.html", kind="design", title_key="web.extras.design", chats=chats)
    for c in chats:
        page(f"design-{c['uuid']}.html", kind="chat", title_key="web.extras.design", chat=c)
    arts = extras.artifacts(output_dir)
    page("artifacts.html", kind="artifacts", title_key="web.extras.artifacts", items=arts)
    others: dict[str, list[dict[str, Any]]] = {}
    for cat, where in extras.other_categories(output_dir).items():
        others[cat] = extras.other_files(where, cat)
        page(f"other-{cat}.html", kind="other", title_key="web.extras.other", label=extras.category_label(cat),
             category=cat, date=extras._label(where), files=others[cat])
    for old in folder.glob("*.html"):
        if old.name not in written:
            old.unlink()
    return extras.summary(output_dir, {"memory": versions, "reflections": refl, "design": chats, "artifacts": arts,
                                       "others": others})  # what was read above: no ZIP read twice (P2)


def _render_page(template: Any, raw: dict[str, Any], info: dict[str, Any], meta: dict[str, Any],
                 leaf_key: str | None = None) -> str:
    """HTML of one conversation page; also records in ``meta`` what the index shows about it. ``leaf_key``: the
    last message of the main branch of this page (a part of a very long conversation, where the next part begins)."""
    files = created.reconstruct_kept(raw, meta["hash"] + "|" + meta.get("removed_hash", ""))
    parsed: dict[int, tuple[Any, ChatMessage | None]] = {}

    def to_message(payload: Any) -> ChatMessage | None:  # each message validated once (PT-m6)
        if id(payload) not in parsed:  # the payload is kept: its id cannot go to another object
            parsed[id(payload)] = (payload, parse_message(payload))
        return parsed[id(payload)][1]

    items = tree.items_from_raw(raw)  # once: it copies the messages it changes
    if leaf_key is not None:
        last = next((it for it in items if it.key == leaf_key), None)
        if last is not None:
            last.forced = True
    convo, rendered = render_archived_conversation(raw, files, to_message, items)
    kept: dict[str, str] = {}
    summary = tree.summarize(items)
    meta["other_versions"] = summary.other_versions
    meta["removed_parts"] = summary.removed_parts
    meta["last_message"] = summary.last_message
    md, md_main = (
        conversation_markdown(convo.name, convo.created_at, items, to_message, info["deleted_since"],
                              versions=v, tr=marker, files=files, kept=kept)
        for v in (True, False)
    )
    return template.render(
        conversation=convo,
        rendered_messages=rendered,
        has_math=any(contains_math(m) for m in rendered),
        has_code=any('class="code-block"' in m for m in rendered),
        markdown_json=embed(md, export_filename(convo.name, convo.created_at), md_main),
        **info,
    )


def build_site_from_archive(
    archive: Archive,
    output_dir: Path,
    force: bool = False,
    progress: Callable[[int], None] | None = None,
) -> RenderStats:
    """(Re)generate the pages that changed since the last run, then the index.

    A page is regenerated when its conversation changed, when its "deleted on
    claude.ai" status changed, when the program itself changed, or if missing.
    A conversation that cannot be rendered is reported and skipped: it never
    stops the rest of the site.
    """
    env = _environment()
    convo_dir = _prepare_output(output_dir)
    template = env.get_template("conversation.html.j2")
    signature = generator_signature()
    launcher = _launcher()
    site = str(Path(output_dir).resolve())
    stats = RenderStats()
    entries: list[IndexEntry] = []
    files = userfiles.load(Path(output_dir))
    widget_host.learn(Path(output_dir), files)  # claude.ai's style sheet, from a visual the user saved
    cdn_cache.write_data_js(Path(output_dir))   # the libraries of the Internet kept in the archive
    esm_cache.write_data_js(Path(output_dir))   # the packages of esm.sh kept in the archive
    files_changed = False
    keys = {u: m["filename"].removesuffix(".html") for u, m in archive.conversations.items()}
    search = searchdata.Store(Path(output_dir), keys)  # read part by part, only where something changed
    search_sig = search_signature()
    for uuid, h in search.legacy_hashes.items():       # moved from the earlier storage: not to render again
        archive.conversations[uuid].setdefault("search", h)

    # part by part, so that one part of the search data at most is in memory
    for uuid, meta in sorted(archive.conversations.items(), key=lambda kv: search.part_of(kv[0])):
        search.focus(search.part_of(uuid))
        info: dict[str, Any] = archive.display_info(meta)
        page = convo_dir / meta["filename"]
        key = meta["filename"].removesuffix(".html")
        # Commands shown on pages opened without the local server; the page adds
        # " --fil-principal" when "sans les autres versions" is checked.
        info["office_key"] = key
        info["office_commands"] = {
            fmt: system.command_line([system.python_command(), launcher, "-o", site, f"--{fmt}", key])
            for fmt in ("odt", "docx", "txt")
        }
        wanted = "|".join((meta["hash"], meta.get("removed_hash", ""), info["deleted_since"], signature, launcher,
                           site, i18n.language(), userfiles.signature(files, uuid)))
        # the text for the search comes from the page itself, read again only when the conversation or the way of
        # reading it changed (15/11), not at every update of the program
        swanted = "|".join((meta["hash"], meta.get("removed_hash", ""), search_sig, i18n.language()))
        render = force or meta.get("rendered") != wanted or not page.exists()
        resample = meta.get("search") != swanted or not search.has(uuid)  # (not forced: its own key, 15/11)
        if not render and resample:
            try:
                search.put(uuid, searchdata.from_page(page.read_text(encoding="utf-8")))
                meta["search"] = swanted
            except (OSError, ValueError):
                render = True
        if render:
            try:
                attachments.begin(output_dir, key)  # texts of joined documents saved as files
                try:
                    parts = _plan_parts(archive, meta)
                    if parts is None:
                        raw = archive.load_raw(uuid)
                        attachments.set_links(userfiles.views(files, uuid, raw))
                        meta["tokens"] = info["tokens"] = tokens.evaluate(raw)  # also shown on the page
                        page_html = _render_page(template, raw, info, meta)
                        del raw
                        page.write_text(page_html, encoding="utf-8")
                        _one_page(convo_dir, key, meta)
                        data = searchdata.from_page(page_html) if resample else None
                    else:  # a very long conversation: in parts, never whole in memory (step 4, 21/11)
                        meta["tokens"] = info["tokens"] = tokens.evaluate_messages(archive.iter_messages(uuid))
                        data = _render_parts(template, archive, uuid, meta, info, parts, convo_dir, key, files)
                    copies = attachments.created_copies()
                finally:
                    attachments.end()
                if files["claude"].get(uuid) != copies:  # what the cleaning of the files must keep
                    files["claude"][uuid] = copies
                    files_changed = True
                if resample and data is not None:
                    search.put(uuid, data)
                    meta["search"] = swanted
            except Exception as exc:  # noqa: BLE001 - one unreadable conversation must not stop the site
                stats.failed += 1
                print("  " + t("build.failed", name=meta["filename"], error=f"{type(exc).__name__}: {exc}"))
                continue
            meta["rendered"] = wanted
            stats.rendered += 1
            if progress:
                progress(stats.rendered)
        if (meta.get("tokens") or {}).get("v") != tokens.VERSION:  # evaluated by an older program
            try:
                meta["tokens"] = tokens.evaluate_messages(archive.iter_messages(uuid))
            except Exception:  # noqa: BLE001 - only a rough figure: never stops the site
                meta["tokens"] = {}
        entries.append(
            IndexEntry(
                name=meta.get("name", ""),
                created_at=dates.parse(meta.get("created_at")),
                updated_at=dates.parse(meta.get("updated_at")),
                account_uuid=meta.get("account_uuid", ""),
                project_uuid=meta.get("project_uuid", ""),
                n_messages=meta.get("n_messages", 0),
                filename=meta["filename"],
                deleted_since=info["deleted_since"],
                last_message=dates.parse(meta.get("last_message")),
                other_versions=meta.get("other_versions", 0),
                removed_parts=meta.get("removed_parts", 0),
                uuid=uuid,
                tokens=meta.get("tokens") or None,
            )
        )

    search.finish()
    if files_changed:
        userfiles.save(Path(output_dir), files)
    stats.total = len(entries)
    stats.deleted = sum(1 for e in entries if e.deleted_since)
    _write_index(
        env,
        output_dir,
        entries,
        archive.state.get("users", {}),
        archive.state.get("projects", {}),
        i18n.Day(archive.latest_export[:10]) if archive.latest_export else "",
        i18n.Day(archive.interrupted_import["date"][:10]) if archive.interrupted_import else "",
        _last_import(archive),
    )
    archive.save()
    return stats
