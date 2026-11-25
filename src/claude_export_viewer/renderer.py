"""HTML of one message: Markdown (mistune), formulas, code (Pygments), artifacts, attachments, other blocks."""

from __future__ import annotations

import base64
import functools
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import mistune
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from . import attachments, codecache, created, i18n, icons, userfiles, widget_host
from .i18n import html_date, html_text, t
from .math_plugin import latex_math
from .models import (
    Attachment,
    ChatMessage,
    FileRef,
    TextContent,
    ThinkingContent,
    TokenBudgetContent,
    ToolResultContent,
    ToolUseContent,
    UnknownContent,
)

# --- Markdown renderer with Pygments code highlighting ---

_pygments_formatter = HtmlFormatter(nowrap=True)


def _plugins_once() -> None:
    """The plugins of Pygments looked for once per run (15/11): older Pygments (those of the distributions) go
    through every Python package installed at each lookup of a language, by its name or by a file name (measured:
    23 ms each, about 20 % of a rebuild). The list cannot change during a run."""
    try:
        import pygments.lexers as lexers
        import pygments.plugin as plugin
        # pygments.lexers swaps its module for a lazy one: its functions read their names from the namespace of the
        # first module, reached through __globals__ (setting the attribute alone changed nothing, 15/11)
        names = lexers.find_lexer_class_for_filename.__globals__
        found = list(names["find_plugin_lexers"]())
        names["find_plugin_lexers"] = plugin.find_plugin_lexers = lambda: iter(found)
    except Exception:  # noqa: BLE001 - only a speed-up
        pass


_plugins_once()


@functools.lru_cache(maxsize=256)
def _lexer_for(lang: str) -> Any:
    """One lexer per language, reused; None for a language Pygments does not know. The failures are kept too
    (15/11): for an unknown name, Pygments looks through every Python package installed for a plugin, each time
    (measured: 23 ms a block, 14 % of a rebuild)."""
    try:
        return get_lexer_by_name(lang, stripall=True)
    except Exception:  # noqa: BLE001 - ClassNotFound, or a broken plugin: plain text
        return None


def _language_label(lang: str | None) -> str:
    """Human-readable language name ("python" -> "Python"), or "" if unknown."""
    if not lang:
        return ""
    lexer = _lexer_for(lang.lower())
    return lexer.name if lexer is not None else lang


# A code frame longer than this shows only its first lines, folded by default: a triangle before the
# label and the arrow of the frames "Favoris" on the right open and close it (code.js)
PREVIEW_LINES = 10
_TRIANGLE = '<span class="cev-tri" aria-hidden="true">&#9654;&#xFE0E;</span> '
_FOLD_ICON = icons.svg("fold", 16, "fold-icon")
_COPY_SVG = icons.svg("copy", 12)
_COPY_LABEL = ' class="copy-label"'  # (25/11) outside the f-string: quotes reused in one are an error under Python 3.11


def _long(code: str) -> bool:
    return len(code.rstrip("\n").split("\n")) > PREVIEW_LINES


def code_block(code: str, lang: str | None, foldable: bool = True) -> str:
    """A code frame with a header: language on the left, "Copy" button on the right (code.js); folded to
    its first lines when long (``foldable`` False: never, e.g. inside a frame already folded)."""
    highlighted = _highlight_code(code, lang)
    lang_class = f' class="language-{html.escape(lang)}"' if lang else ""
    label = html.escape(_language_label(lang))
    long = foldable and _long(code)
    return (
        f'<div class="code-block{" cev-long" if long else ""}">'
        '<div class="code-header">'
        f'<span class="code-lang">{_TRIANGLE if long else ""}{label}</span>'
        # (22/11) the icon "copy" of the messages too, before the word
        + f'<button type="button" class="copy-btn" title="{html.escape(t("web.copy_title"))}"'
          f' data-i18n-attr="title:web.copy_title">{_COPY_SVG}{html_text("web.copy", "span", _COPY_LABEL)}</button>'
        + (_FOLD_ICON if long else "")
        + "</div>"
        f"<pre class='highlight' translate='no'><code{lang_class}>{highlighted}</code></pre>"
        "</div>"
    )


def _highlight_code(code: str, lang: str | None) -> str:
    # Without a language, the code is shown as plain text: guessing the language
    # is slow on long blocks and often wrong.
    if not lang:
        return html.escape(code)
    lexer = _lexer_for(lang.lower())
    if lexer is None:
        return html.escape(code)
    kept = codecache.get(lang.lower(), code)  # the same code gives the same colours (15/11)
    if kept is not None:
        return kept
    done = highlight(code, lexer, _pygments_formatter)
    codecache.put(lang.lower(), code, done)
    return done


class _HighlightRenderer(mistune.HTMLRenderer):
    """Extends the default HTML renderer to use Pygments for code blocks."""

    def block_code(self, code: str, info: str | None = None, **attrs: Any) -> str:
        lang = info.split()[0] if info else None
        return code_block(code, lang) + "\n"

    def link(self, text: str, url: str, title: str | None = None) -> str:
        # safe_url() neutralises javascript:, vbscript:, data: (non image) and file: links
        safe = self.safe_url(url)
        title_attr = f' title="{html.escape(title)}"' if title else ""
        return f'<a href="{safe}"{title_attr} target="_blank" rel="noopener noreferrer">{text}</a>'

    def image(self, text: str, url: str, title: str | None = None) -> str:
        # An archive read offline must not load pictures from the Internet (nor
        # files of this computer): a Markdown image is shown as a link.
        label = text or html.escape(url)
        return self.link(f"[{html_text('web.image_link', label='')}{label}]", url, title)


_md = mistune.create_markdown(
    renderer=_HighlightRenderer(),
    plugins=["strikethrough", "table", latex_math],
)


@functools.lru_cache(maxsize=16)
def _markdown_signature(lang: str) -> str:
    """What the HTML of a Markdown text depends on (15/11): this module, the formulas, the icons, the texts of the
    language, the versions of mistune and Pygments. The rest of the program can change: the HTML kept stays good."""
    import hashlib

    import pygments

    h = hashlib.sha256(f"{mistune.__version__}\0{pygments.__version__}\0{lang}".encode())
    here = Path(__file__).resolve().parent
    for name in ("renderer.py", "math_plugin.py", "icons.py", f"i18n/{lang}.json"):
        try:
            h.update((here / name).read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:16]


def render_markdown(text: str) -> str:
    """Render markdown text to HTML; the HTML is kept from one rebuild to the next (15/11: measured at the
    user's, the reading of the Markdown by mistune was then most of a rebuild)."""
    sig = "md:" + _markdown_signature(i18n.language())
    kept = codecache.get(sig, text)
    if kept is not None:
        return kept
    done = _md(text)
    codecache.put(sig, text, done)
    return done


# --- Content block renderers ---


def _render_text(block: TextContent, plain: bool = False) -> str:
    """``plain``: the user's text, shown as typed (no Markdown), as on claude.ai."""
    if not block.text:
        return ""
    if plain:
        return f'<div class="content-text plain-text">{_plain_lists(block.text.strip(chr(10)))}</div>'
    return f'<div class="content-text">{render_markdown(block.text)}</div>'


# A line of the user's text starting a list item ("1. ", "2) ", "- ", "* ", "• "), as claude.ai shows it: the
# text stays as typed, the lines of the item that wrap start under its text, not under its marker.
_LIST_LINE = re.compile(r"^([ \t]*(?:\d{1,3}[.)]|[-*•])[ \t]+)\S")


def _plain_lists(text: str) -> str:
    """The user's text escaped; each list line in a block with a hanging indent (`.li-line`, its marker in
    a box `.li-mark` as wide as the indent), its newline kept in the text but not drawn (`.li-nl`), so that the copy, the search and
    the highlighter read the very same characters."""
    out = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        nl = "\n" if i < len(lines) - 1 else ""
        m = _LIST_LINE.match(line)
        if m:
            mark = m.group(1)
            width = len(mark.expandtabs(4))  # its box (ch): the text starts at the same place on every line
            out.append(f'<span class="li-line" style="--m:{width}ch"><span class="li-mark">{html.escape(mark, quote=False)}</span>'
                       f'{html.escape(line[len(mark):], quote=False)}</span>'
                       + (f'<span class="li-nl">{nl}</span>' if nl else ""))
        else:
            out.append(html.escape(line, quote=False) + nl)
    return "".join(out)


def _render_thinking(block: ThinkingContent) -> str:
    sums = [x.summary for x in block.summaries if x.summary.strip()]
    if not block.thinking:
        # recent exports: only the summaries of the thinking, listed as on claude.ai
        if not sums:
            return ""
        items = "".join(f"<li>{html.escape(x)}</li>" for x in sums)
        return (f'<details class="thinking"><summary>{html.escape(sums[-1])}</summary>'
                f'<ul class="thinking-content thinking-summaries">{items}</ul></details>')
    if block.summaries:
        summary = f"<summary>{html.escape(block.summaries[-1].summary)}</summary>"
    else:
        summary = html_text("web.thinking", "summary")
    return (
        f'<details class="thinking">'
        f"{summary}"
        f'<div class="thinking-content">{render_markdown(block.thinking)}</div>'
        f"</details>"
    )


# Artifact type → label (a translation key, or a name that needs none)
_ARTIFACT_TYPE_LABELS: dict[str, str] = {
    "text/markdown": "web.artifact.document",
    "text/html": "HTML",
    "application/vnd.ant.code": "Code",
    "application/vnd.ant.react": "web.artifact.react",
    "application/vnd.ant.mermaid": "web.artifact.mermaid",
    "image/svg+xml": "SVG",
}


def _render_artifact(block: ToolUseContent) -> str:
    ai = block.artifact_input
    if ai is None:
        return ""

    # Only render create/rewrite commands (they have full content)
    if ai.command not in ("create", "rewrite"):
        return ""

    title = html.escape(ai.title) if ai.title else html_text("web.untitled")
    artifact_type = ai.type or ""
    type_label = _ARTIFACT_TYPE_LABELS.get(artifact_type, artifact_type)
    type_html = html_text(type_label) if type_label.startswith("web.") else html.escape(type_label)
    content = ai.content or ""
    kind = {"application/vnd.ant.react": "jsx", "text/html": "html"}.get(artifact_type)
    if kind:  # a program: run or read, one strip under the bar
        return _runnable(kind, title, type_html, code_block(content, "jsx" if kind == "jsx" else "html", foldable=False),
                         code=content)
    long = _long(content)  # folded by its own header, not by the code frame inside

    # Render content based on type
    if artifact_type in ("text/markdown",):
        rendered = render_markdown(content)
    elif artifact_type in ("application/vnd.ant.code", "application/vnd.ant.mermaid"):
        lang = ai.language or ""
        rendered = code_block(content, lang or None, foldable=False)
    elif artifact_type in ("text/html", "application/vnd.ant.react", "image/svg+xml"):
        # Show as highlighted code — rendering raw HTML/React would be unsafe
        lang = "html" if artifact_type != "application/vnd.ant.react" else "jsx"
        rendered = code_block(content, lang, foldable=False)
    else:
        rendered = render_markdown(content)

    return (
        f'<div class="artifact{" cev-long" if long else ""}">'
        f'<div class="artifact-header">'
        f'<span class="artifact-title">{_TRIANGLE if long else ""}{title}</span>'
        f'<span class="artifact-type">{type_html}</span>'
        f'{_FOLD_ICON if long else ""}'
        f"</div>"
        f'<div class="artifact-content">{rendered}</div>'
        f"</div>"
    )


def _render_widget(title: str, code: str, view: dict | None = None) -> str:
    """A visual claude.ai showed in the chat (show_widget): a runnable frame (run.js, kind "widget"). Its
    link "html" is the file the user saved from the chat (<title>.html, userfiles kind "widget"), found
    like the other files and changed with 🔗; when there is one, Lancer runs that very file."""
    name = html.escape(title.replace("_", " ").strip().capitalize()) if title else html_text("web.untitled")
    svg = code.lstrip().startswith("<svg")
    attrs, extra = "", ""
    if view:
        e, link = view["entry"], view["link"]
        copy = e.get("copy")
        cands = [{"path": c["path"], "shown": _home(c["path"]), "size": c["size"], "mtime": c["mtime"],
                  "current": c["current"], "others": c["others"]} for c in view["candidates"]]
        attrs = (f' data-link="{html.escape(link["id"])}" data-how="{html.escape(str(e.get("how", "auto")))}"'
                 f' data-cands="{html.escape(json.dumps(cands, ensure_ascii=False))}"')
        saved_text = ""
        if copy:
            path = attachments.site_file(copy)
            saved_text = widget_host.read(path) if path else ""
            source = _home(e.get("source") or e.get("upload") or "")
            extra = (f'<a class="cev-html" href="../{html.escape(quote(copy))}" target="_blank" rel="noopener"'
                     f' title="{html.escape(source)}">html</a>')
        else:
            extra = html_text("web.widget.no_html", "span", ' class="cev-html cf-dim"')
        extra += (f'<button type="button" class="cf-link" title="{html.escape(t("web.widget.choose"))}"'
                  f' data-i18n-attr="title:web.widget.choose">{_LINK_SVG}</button>')
    # the saved file itself, held in the page: run.js runs it with the same rules (CSP, height fitted)
    saved = ""
    if view and saved_text:
        saved = ('<script type="application/octet-stream" class="cev-saved">'  # base64: never ends the script
                 + base64.b64encode(saved_text.encode("utf-8")).decode("ascii") + "</script>")
    return _runnable("widget", name, "", code_block(code, "xml" if svg else "html", foldable=False) + saved,
                     css=" widget" + (" userfile" if view else ""), data_file=userfiles.widget_file(title), extra=extra,
                     attrs=attrs) or _runnable("widget", name, "", code_block(code, "xml" if svg else "html", foldable=False),
                     css=" widget" + (" userfile" if view else ""), data_file=userfiles.widget_file(title), extra=extra,
                     attrs=attrs)


def _runnable(kind: str, title_html: str, type_html: str, code_html: str, css: str = "", data_file: str = "",
              bar: str = "", extra: str = "", attrs: str = "", code: str = "") -> str:
    """A program of Claude (artifact, visual, file) with one strip under its bar (run.js, data-state): its
    result after "Lancer", or its code ("Code": 10 lines, ↓: all); folded at first. ``bar``: replaces the
    title and the type (the bar of a file of Claude)."""
    head = bar or f'<span class="artifact-title">{_TRIANGLE}{title_html}</span><span class="artifact-type">{type_html}</span>'
    return (
        f'<div class="artifact cev-runnable{css}{" cev-longcode" if _long(code) else ""}" data-run="{kind}" data-state="closed"'
        f'{f" data-file={chr(34)}{html.escape(data_file)}{chr(34)}" if data_file else ""}{attrs}>'
        f'<div class="artifact-header cev-bar{" userfile-bar" if "userfile" in css else ""}">{head}'
        f'{_run_buttons(extra, code=kind != "widget")}</div>'
        f'<div class="artifact-content cev-pane">{code_html}</div>'
        f"</div>"
    )


def _run_buttons(extra: str = "", code: bool = True) -> str:
    """Lancer, Code, ↓ (run.js); greyed out by style.css after the state of the frame."""
    def btn(cls: str, key: str, title: str, inner: str) -> str:
        return (f'<button type="button" class="{cls}" title="{html.escape(t(title))}" data-i18n-attr="title:{title}">'
                f"{inner}</button>")
    run = btn("run-btn", "web.run.launch", "web.run.title",
              '<span class="run-tri" aria-hidden="true">&#9654;&#xFE0E;</span> ' + html_text("web.run.launch"))
    if not code:  # a visual: its code only draws it, never meant for the reader (kept hidden for run.js)
        return run + extra
    return (run + btn("code-btn", "web.run.code", "web.run.code_title",
                      '<span aria-hidden="true">&lt;/&gt;</span> ' + html_text("web.run.code"))
            + extra + btn("full-btn", "", "web.run.full_less", _FOLD_ICON))


def _render_tool_use(block: ToolUseContent) -> str:
    if block.is_artifact:
        return _render_artifact(block)
    if block.widget:
        return _render_widget(*block.widget)

    summary = (f"<summary>{html.escape(block.message)}</summary>" if block.message
               else html_text("web.tool_used", "summary", name=block.name))
    tool = html_text("web.tool", "div", ' class="tool-name"', name=block.name)
    return f'<details class="tool-use">{summary}{tool}</details>'


def _render_tool_result(block: ToolResultContent) -> str:
    # Skip artifact results (usually just "OK")
    if block.name == "artifacts":
        return ""

    content_text = ""
    if isinstance(block.content, str):
        content_text = block.content
    elif isinstance(block.content, list):
        parts = []
        for item in block.content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        content_text = "\n".join(parts)

    if not content_text or len(content_text.strip()) == 0:
        return ""

    # Truncate very long tool results
    truncated = len(content_text) > 2000
    display = html.escape(content_text[:2000]) + ("\n" + html_text("web.truncated") if truncated else "")

    error_class = " tool-error" if block.is_error else ""
    summary = (html_text("web.tool_result", "summary", name=block.name) if block.name
               else html_text("web.tool_result_unnamed", "summary"))
    return (
        f'<details class="tool-result{error_class}">'
        f"{summary}"
        f"<pre>{display}</pre>"
        f"</details>"
    )


def _render_attachment(att: Attachment, link_id: str) -> str:
    # no name: a text pasted into claude.ai
    name = html.escape(att.file_name) if att.file_name else html_text("web.pasted_text")
    file_type = html.escape(att.file_type) if att.file_type else html_text("web.file")
    size_kb = att.file_size / 1024 if att.file_size else 0.0
    size = (html_text("web.size_kb", size=float(size_kb)) if size_kb < 1024
            else html_text("web.size_mb", size=float(size_kb / 1024)))

    parts = ['<div class="attachment">']
    details = f"{file_type}, {size}" if att.file_size else file_type
    pill = f'<span class="attachment-pill">{name} ({details})</span>'
    text = att.extracted_content
    saved = attachments.save(att.file_name or "document", text) if text else None
    view = attachments.link(link_id)
    # the original document associated on the computer, else the text of the export as a file
    fallback = _open_link(saved.href.removeprefix("../"), "web.attachment.open_text") if saved else ""
    parts.append(_linked(att.file_name, view, pill, fallback) if view else pill + fallback)

    if text:
        n = len(text)
        long_doc = n > attachments.LONG
        summary_key = "web.attachment.view_long" if long_doc else "web.attachment.view"
        details = [f'<details class="attachment-content">{html_text(summary_key, "summary", n=n)}']
        if long_doc or (saved and saved.text_only):
            notes = []
            if long_doc:
                notes.append(html_text("web.attachment.long", n=n))
            if saved and saved.text_only:
                notes.append(html_text("web.attachment.text_only"))
            if saved:
                notes.append(html_text("web.attachment.path") + f' <code translate="no">{html.escape(str(saved.path))}</code>')
            details.append('<p class="attachment-note">' + " ".join(notes) + "</p>")
        details.append(f'<pre translate="no">{html.escape(text)}</pre></details>')
        parts.append("".join(details))

    parts.append("</div>")
    return "".join(parts)


def _open_link(rel: str, key: str = "web.attachment.open") -> str:
    """Icon opening a file of the site (``rel``: URL path from the site folder) with the program of the computer."""
    rel = html.escape(rel)
    return (
        f'<a class="attachment-open" href="../{rel}" data-open="{rel}" target="_blank"'
        f' title="{html.escape(t(key))}" data-i18n-attr="title:{key}">'
        '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M14 3h7v7M21 3l-9 9'
        'M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg></a>'
    )


_LINK_SVG = ('<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/>'
             '<path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>')


def _home(path: str) -> str:
    """A path of the computer as shown: the personal folder written ~."""
    try:
        home = str(Path.home())
    except RuntimeError:
        return path
    return "~" + path[len(home):] if home and (path == home or path.startswith(home.rstrip("/\\") + ("\\" if "\\" in home else "/"))) else path


def _status(view: dict) -> str:
    """The line under a link: how its file was associated (nothing when the user chose it)."""
    e = view["entry"]
    if e.get("how") == "user":
        return "" if e.get("copy") else html_text("web.link.none", "div", ' class="cf-info"')
    status = e.get("status")
    if not e.get("copy") or status == "none":
        return html_text("web.link.none", "div", ' class="cf-info"')
    if view.get("shared"):
        return html_text("web.link.shared", "div", f' class="cf-warn" title="{html.escape(t("web.link.shared_title"))}"'
                         ' data-i18n-attr="title:web.link.shared_title"', n=view["shared"])
    if status == "same":
        return html_text("web.link.same", "div", ' class="cf-ok"')
    if status == "modified":
        return html_text("web.link.modified", "div", ' class="cf-warn"')
    return html_text("web.link.auto", "div", ' class="cf-info"')


def _linked(name: str, view: dict, pill: str = "", fallback_open: str = "") -> str:
    """A file named by a message, associated (or not) with a file of the computer copied into the
    site; the button 🔗 (local server only) opens the menu to change it (files.js)."""
    e, link = view["entry"], view["link"]
    copy = e.get("copy")
    source = e.get("source") or e.get("upload") or ""
    ext = name.rpartition(".")[2].lower() if "." in name else ""
    cands = [{"path": c["path"], "shown": _home(c["path"]), "size": c["size"], "mtime": c["mtime"],
              "current": c["current"], "others": c["others"]} for c in view["candidates"]]
    out = [f'<div class="userfile" data-link="{html.escape(link["id"])}" data-file="{html.escape(name)}"'
           f' data-how="{html.escape(str(e.get("how", "auto")))}" data-cands="{html.escape(json.dumps(cands, ensure_ascii=False))}">']
    if copy and ext in userfiles.IMAGES:
        rel = html.escape(quote(copy))
        out.append(f'<a class="userfile-image" href="../{rel}" target="_blank">'
                   f'<img src="../{rel}" alt="{html.escape(name)}" loading="lazy"></a>')
    title = f' title="{html.escape(_home(source))}"' if copy and source else ""
    if not pill:
        pill = f'<span class="file-pill{"" if copy else " cf-dim"}"{title}>{html.escape(name)}</span>'
    elif title:
        pill = pill.replace("<span ", f"<span{title} ", 1)
    key = "web.link.change" if copy else "web.link.add"
    button = (f'<button type="button" class="cf-link" title="{html.escape(t(key))}" data-i18n-attr="title:{key}">'
              f"{_LINK_SVG}</button>")
    out.append(f'<div class="userfile-bar">{pill}{_open_link(quote(copy)) if copy else fallback_open}{button}</div>')
    # (22/11) the icon opens then the text of the export: said, no longer "no file associated" beside "open"
    out.append(html_text("web.link.none_text", "div", ' class="cf-info"') if fallback_open and not copy else _status(view))
    out.append("</div>")
    return "".join(out)


_SAVE_SVG = icons.svg("export", 16)  # (22/11) the drawing of the exports, no longer the fold arrow
_COPY_FILE_SVG = icons.svg("copy", 16)
SHOWN_MAX = 300_000  # characters: a longer file is only offered to open or save


# Files of Claude that the browser can run (run.js): kind given to the button "Lancer"
_RUNNABLE = {".jsx": "jsx", ".tsx": "tsx", ".js": None, ".html": "html", ".htm": "html"}


def _created_file(p: created.Presented) -> str:
    """A file created by Claude, with the content it had in this message (from the export); a .jsx / .html
    shown whole is a runnable frame (_runnable) whose bar is that of the file."""
    text = p.text or ""
    rel = attachments.save_created(p.name, text)
    kind = _RUNNABLE.get(Path(p.name).suffix.lower())
    if kind and len(text) <= SHOWN_MAX and p.complete:
        return f'<div class="userfile created-file" data-file="{html.escape(p.name)}">' + _runnable(
            kind, "", "", code_block(text, created.language(p.name) or None, foldable=False), data_file=p.name,
            bar=_created_bar(p, rel, text, triangle=True), code=text) + "</div>"
    out = [f'<div class="userfile created-file" data-file="{html.escape(p.name)}">'
           f'<div class="userfile-bar">{_created_bar(p, rel, text)}']
    shown = len(text) <= SHOWN_MAX
    out.append("</div>")
    out.append(_created_content(p, shown))
    out.append("</div>")
    return "".join(out)


def _created_bar(p: created.Presented, rel: str | None, text: str, triangle: bool = False) -> str:
    """Name, version, open, save and copy of a file of Claude."""
    out = [f'<span class="file-pill" title="{html.escape(p.path)}">{_TRIANGLE if triangle else ""}{html.escape(p.name)}</span>']
    if p.versions > 1:
        out.append(html_text("web.created.version", "span", ' class="cf-ver"', n=p.version, total=p.versions))
    if rel:
        href = html.escape("../" + quote(rel))
        out.append(_open_link(quote(rel)))
        out.append(f'<a class="cf-save" href="{href}" download="{html.escape(p.name)}" title="{html.escape(t("web.created.save"))}"'
                   f' data-i18n-attr="title:web.created.save">{_SAVE_SVG}</a>')
    if len(text) <= SHOWN_MAX:
        out.append(f'<button type="button" class="copy-file" title="{html.escape(t("web.created.copy"))}"'
                   f' data-i18n-attr="title:web.created.copy">{_COPY_FILE_SVG}</button>')
    return "".join(out)


def _created_content(p: created.Presented, shown: bool = True) -> str:
    text = p.text or ""
    out = "" if p.complete else html_text("web.created.incomplete", "div", ' class="cf-warn"')
    if shown:
        return out + (f'<details class="attachment-content">{html_text("web.attachment.view", "summary", n=len(text))}'
                      f"{code_block(text, created.language(p.name) or None, foldable=False)}</details>")
    return out + html_text("web.created.too_long", "div", ' class="cf-info"')


def _render_handed(p: created.Presented, link_id: str) -> str:
    """A file handed over by Claude: its content when the export has it all; else a link to the
    user's copy (a version changed afterwards keeps the last content the export shows)."""
    if p.text is not None and p.complete:
        return _created_file(p)
    view = attachments.link(link_id)
    if view is None:
        pill = (f'<div class="userfile"><div class="userfile-bar"><span class="file-pill cf-dim" title="{html.escape(p.path)}">'
                f'{html.escape(p.name)}</span></div>')
        return pill + (_created_content(p, len(p.text) <= SHOWN_MAX) if p.text is not None else "") + "</div>"
    box = _linked(p.name, view)
    if p.text is not None:
        box = box[:-len("</div>")] + _created_content(p, len(p.text) <= SHOWN_MAX) + "</div>"
    return box


def _render_file(f: FileRef, link_id: str) -> str:
    view = attachments.link(link_id)
    if view is not None:
        return _linked(f.file_name, view)
    name = html.escape(f.file_name) if f.file_name else html_text("web.unknown_file")
    return f'<span class="file-pill">{name}</span>'


_PILL = ' class="file-pill"'


def _render_unknown(block: UnknownContent) -> str:
    kind = block.original_type or "?"
    if kind == "document":
        pill = html_text("web.document_attached", "span", _PILL)
        return f'<div class="unknown-block">{pill}</div>'
    if kind == "injected_prompt_block":
        if not block.text.strip() or not attachments.first_injected(block.source, block.text.strip()):
            return ""  # the same instructions repeated by claude.ai: shown once per page
        summary = (html_text("web.injected_from", "summary", source=block.source) if block.source
                   else html_text("web.injected", "summary"))
        text = block.text if len(block.text) <= 8000 else block.text[:8000] + "\n..."
        return (
            f'<details class="tool-result unknown-block injected">'
            f"{summary}"
            f"<pre>{html.escape(text)}</pre>"
            f"</details>"
        )
    key, args = ("web.image_not_included", {}) if kind == "image" else ("web.content_of_type", {"type": kind})
    if not block.text:
        pill = html_text(key, "span", _PILL, **args)
        return f'<div class="unknown-block">{pill}</div>'
    return (
        f'<details class="tool-result unknown-block">'
        f"{html_text(key, 'summary', **args)}"
        f"<pre>{html.escape(block.text)}</pre>"
        f"</details>"
    )


_SAFE_CLASS = re.compile(r"[^a-z0-9_-]")


_STAR_SVG = icons.svg("star", 13)
_EXPORT_SVG = icons.svg("export", 12)  # (22/11: its own drawing, no longer the fold arrow)
_COPY_SVG = icons.svg("copy", 12)


def _group_resources(blocks: list[tuple[str, str]]) -> list[str]:
    """Each run of blocks added by claude.ai (its instructions, the tools used and their results,
    other blocks it adds) in one closed frame "Ressources de claude.ai (n)" listing them. Claude's
    thinking between two of them stays in the frame; before the first or after the last, outside.
    ``blocks``: (kind, html), kind "resource", "thinking" or "text" (anything else: ends a run)."""
    out: list[str] = []
    run: list[tuple[str, str]] = []

    def flush() -> None:
        first = next((i for i, (k, _) in enumerate(run) if k == "resource"), None)
        if first is None:
            out.extend(h for _, h in run)
        else:
            last = max(i for i, (k, _) in enumerate(run) if k == "resource")
            out.extend(h for _, h in run[:first])
            n = sum(1 for k, _ in run if k == "resource")
            inner = "".join(h for _, h in run[first:last + 1])
            out.append(f'<details class="cev-resources">{html_text("web.resources", "summary", n=n)}'
                       f'<div class="cev-resources-list">{inner}</div></details>')
            out.extend(h for _, h in run[last + 1:])
        run.clear()

    for kind, part in blocks:
        if not part:
            continue  # nothing shown (an artifact result, repeated instructions…): does not end a run
        if kind == "text":
            flush()
            out.append(part)
        else:
            run.append((kind, part))
    flush()
    return out


def render_message(msg: ChatMessage, markdown: str = "", files: list[created.Presented] | None = None,
                   note: str = "", css: str = "") -> str:
    """Render a full chat message to HTML (``markdown``: its text, copied by the icon after the date;
    ``files``: the files it hands over, from created.reconstruct; ``note``: HTML ending the bubble; ``css``: classes added to the message)."""
    parts: list[str] = []

    # Links to files (userfiles): one id per message, kind, name and rank of that name
    ranks: dict[tuple[str, str], int] = {}

    def link_id(kind: str, name: str) -> str:
        ranks[(kind, name)] = ranks.get((kind, name), 0) + 1
        return userfiles.view_key(msg.uuid, kind, name, ranks[(kind, name)])

    # Render attachments first (they appear above the message), then file references
    for att in msg.attachments:
        parts.append(_render_attachment(att, link_id("attachment", att.file_name)))
    refs = list(msg.files)
    if any(not a.file_name for a in msg.attachments):
        # a pasted text also comes as a nameless file reference: nothing more to show
        refs = [f for f in refs if not isinstance(f, FileRef) or f.file_name]
    if refs:
        file_html = " ".join(_render_file(f, link_id("file", f.file_name)) for f in refs)
        parts.append(f'<div class="files">{file_html}</div>')

    # Render content blocks; what claude.ai added is grouped (see _group_resources)
    blocks: list[tuple[str, str]] = []
    for block in msg.content:
        if isinstance(block, TextContent):
            blocks.append(("text", _render_text(block, plain=msg.sender == "human")))
        elif isinstance(block, ThinkingContent):
            blocks.append(("thinking", _render_thinking(block)))
        elif isinstance(block, ToolUseContent) and block.widget:
            title, code = block.widget
            view = attachments.link(link_id("widget", userfiles.widget_file(title)))
            blocks.append(("text", _render_widget(title, code, view)))
        elif isinstance(block, ToolUseContent):
            blocks.append(("text" if block.is_artifact else "resource", _render_tool_use(block)))
        elif isinstance(block, ToolResultContent):
            blocks.append(("resource", _render_tool_result(block)))
        elif isinstance(block, TokenBudgetContent):
            pass  # Skip
        elif isinstance(block, UnknownContent):
            own = (block.original_type or "") in ("document", "image")  # the user's files: not claude.ai's
            blocks.append(("text" if own else "resource", _render_unknown(block)))
    parts.extend(_group_resources(blocks))

    # Files handed over by Claude, at the end as on claude.ai: their content when the export has it,
    # else the user's copy found on the computer, else only their name
    shown = [_render_handed(p, link_id("created", p.name)) if not (p.text is not None and p.complete) else _created_file(p)
             for p in files or []]
    if shown:
        parts.append('<div class="files created-files">' + "".join(shown) + "</div>")
    parts.append(note)

    rendered = "\n".join(p for p in parts if p)

    sender = _SAFE_CLASS.sub("", msg.sender.lower()) or "unknown"
    copy = ""
    if markdown.strip():
        copy = (f'<button type="button" class="copy-msg" title="{html.escape(t("web.copy_msg"))}"'
                f' data-i18n-attr="title:web.copy_msg" data-md="{html.escape(markdown)}">{_COPY_SVG}</button>'
                # export this message only (PT-m1, export.js): .md .odt .docx .txt .pdf
                f'<button type="button" class="export-msg" title="{html.escape(t("web.export_msg"))}"'
                f' data-i18n-attr="title:web.export_msg">{_EXPORT_SVG}</button>')
    date = html_date(msg.created_at, with_time=True) if msg.created_at else ""
    who = ""
    if sender in ("human", "assistant"):  # "Moi" / "Claude" before the date
        key = f"web.who.{sender}"
        who = f'<b class="message-who" data-i18n="{key}">{html.escape(t(key))}</b> '
    star = ""
    if msg.uuid:  # favorite: shown and changed by favorites.js
        star = (f'<button type="button" class="fav-star" aria-pressed="false" title="{html.escape(t("web.fav.add"))}"'
                f' data-i18n-attr="title:web.fav.add">{_STAR_SVG}</button>')
    time_html = f'<div class="message-time">{who}{date}{star}{copy}</div>\n' if who or date or copy else ""
    return (
        f'<div class="message message-{sender}{css}" data-uuid="{html.escape(msg.uuid)}">\n{time_html}'
        f'<div class="message-bubble">\n{rendered}\n</div>\n</div>'
    )
