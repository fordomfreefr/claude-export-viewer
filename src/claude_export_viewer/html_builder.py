"""The site: one HTML page per archived conversation, and the index.

Pages are regenerated only when needed (see ``build_site_from_archive``), so
that importing a new export only rewrites what changed.
"""

from __future__ import annotations

import hashlib
import html
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from . import __version__, dates, i18n, system, topics, tree
from .i18n import html_date, html_text, t
from .markdown_export import conversation_markdown, embed, export_filename, marker
from .math_plugin import contains_math
from .models import ChatMessage, Conversation, parse_message
from .renderer import render_message

if TYPE_CHECKING:
    from .archive import Archive

_PACKAGE_DIR = Path(__file__).parent
_STATIC_FILES = ("style.css", "code.js", "export.js", "admin.js", "nav.js", "i18n.js", "topics.js")
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
        date=lambda d, with_time=False, to_local=True: Markup(html_date(d, with_time, to_local)),
        attr=lambda name, key, **args: Markup(
            f'{name}="{html.escape(t(key, **args))}" data-i18n-attr="{name}:{key}"'),
        args=lambda **kw: Markup(i18n.html_args(**kw)),
        Day=i18n.Day,
        LocalDate=i18n.LocalDate,
        lang=i18n.language,
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
    topics.write_data_js(output_dir)
    return convo_dir


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
    items: list[tree.Item], to_message: Callable[[Any], ChatMessage | None]
) -> tuple[list[str], list[ChatMessage]]:
    def render_item(item: tree.Item) -> str:
        msg = to_message(item.payload)
        return render_message(msg) if msg is not None else ""

    pieces, path = tree.render(items, render_item, _branch_frame)
    main = [m for m in (to_message(it.payload) for it in path) if m is not None]
    return [p for p in pieces if p], main


def render_archived_conversation(raw: dict[str, Any]) -> tuple[Conversation, list[str]]:
    """Validate an archived conversation and render it as a tree: main branch, other branches in frames."""
    convo = Conversation.model_validate({**raw, "chat_messages": []})
    rendered, main = _render_tree(tree.items_from_raw(raw), parse_message)
    convo.chat_messages = main  # the header counts the messages of the main branch
    return convo, rendered


# --- The site ------------------------------------------------------------------


def _write_index(
    env: Environment,
    output_dir: Path,
    entries: list[IndexEntry],
    user_map: dict[str, str],
    all_projects: dict[str, str],
    latest_export: str = "",
) -> None:
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
    )
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")


def _render_page(template: Any, raw: dict[str, Any], info: dict[str, Any], meta: dict[str, Any]) -> str:
    """HTML of one conversation page; also records in ``meta`` what the index shows about it."""
    convo, rendered = render_archived_conversation(raw)
    items = tree.items_from_raw(raw)
    summary = tree.summarize(items)
    meta["other_versions"] = summary.other_versions
    meta["removed_parts"] = summary.removed_parts
    meta["last_message"] = summary.last_message
    md, md_main = (
        conversation_markdown(convo.name, convo.created_at, items, parse_message, info["deleted_since"],
                              versions=v, tr=marker)
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

    for uuid, meta in archive.conversations.items():
        info: dict[str, Any] = archive.display_info(meta)
        page = convo_dir / meta["filename"]
        key = meta["filename"].removesuffix(".html")
        # Commands shown on pages opened without the local server; the page adds
        # " --fil-principal" when "Inclure les autres versions" is unchecked.
        info["office_key"] = key
        info["office_commands"] = {
            fmt: system.command_line([system.python_command(), launcher, "-o", site, f"--{fmt}", key])
            for fmt in ("odt", "docx")
        }
        wanted = "|".join((meta["hash"], meta.get("removed_hash", ""), info["deleted_since"], signature, launcher,
                           site, i18n.language()))
        if force or meta.get("rendered") != wanted or not page.exists():
            try:
                page.write_text(_render_page(template, archive.load_raw(uuid), info, meta), encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 - one unreadable conversation must not stop the site
                stats.failed += 1
                print("  " + t("build.failed", name=meta["filename"], error=f"{type(exc).__name__}: {exc}"))
                continue
            meta["rendered"] = wanted
            stats.rendered += 1
            if progress:
                progress(stats.rendered)
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
            )
        )

    stats.total = len(entries)
    stats.deleted = sum(1 for e in entries if e.deleted_since)
    _write_index(
        env,
        output_dir,
        entries,
        archive.state.get("users", {}),
        archive.state.get("projects", {}),
        i18n.Day(archive.latest_export[:10]) if archive.latest_export else "",
    )
    archive.save()
    return stats
