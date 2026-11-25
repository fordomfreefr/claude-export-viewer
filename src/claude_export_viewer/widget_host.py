"""The style sheet claude.ai puts around its visuals (show_widget), learnt from the user's own files.

A visual saved from the chat ("<title>.html") is claude.ai's page: its <head> holds the whole style sheet
of claude.ai (design tokens, light and dark, the classes of the visuals), then the code of the visual in
<div id="vis-container">. That style sheet belongs to Anthropic: it is never shipped with the program, only
read from a file the user saved and associated with a visual (userfiles, kind "widget"), kept in the
archive (archive/claude-widget.css) and handed to the pages (claude-widget.js, window.CEV_WIDGET_CSS), so
that every visual is drawn as on claude.ai (run.js), even those the user did not save."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CSS_FILE = "claude-widget.css"   # in archive/
JS_FILE = "claude-widget.js"     # in the site folder
MAX_READ = 4_000_000             # bytes read of a saved visual
_HOST = re.compile(r"<(?:script|link|img|iframe)\b[^>]*?\s(?:src|href)\s*=\s*[\"']?(https?://[^\"'\s>/]+)", re.I)


def is_saved_visual(text: str) -> bool:
    return text.lstrip()[:300].lower().startswith("<!doctype html>") and "data-saved" in text[:300] \
        and 'id="vis-container"' in text


def extract_css(text: str) -> str | None:
    """The style sheet of claude.ai in a saved visual (its first <style> of the <head>), else None."""
    if not is_saved_visual(text):
        return None
    head = text[: text.find("</head>")] if "</head>" in text else ""
    start = head.find("<style>")
    end = head.find("</style>", start)
    if start < 0 or end < 0:
        return None
    css = head[start + len("<style>"): end]
    return css if "--text-primary" in css and "data-mode" in css else None


def hosts(text: str) -> list[str]:
    """The Internet hosts a page loads scripts, styles or images from (asked before running it)."""
    out: list[str] = []
    for m in _HOST.finditer(text):
        h = m.group(1).split("//", 1)[1].lower()
        if h not in out:
            out.append(h)
    return out


def read(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            return f.read(MAX_READ).decode("utf-8", "replace")
    except OSError:
        return ""


def learn(site_dir: Path, files: dict[str, Any]) -> None:
    """Take the style sheet from the most recent saved visual associated with a link, keep it in the
    archive, and write claude-widget.js (empty when none was ever found)."""
    site_dir = Path(site_dir)
    found: list[tuple[float, Path]] = []
    for links in (files.get("assoc") or {}).values():
        for link_id, e in links.items():
            if "/widget/" in link_id and e.get("copy"):
                p = site_dir / e["copy"]
                if p.is_file():
                    found.append((float(e.get("mtime") or 0), p))
    kept = site_dir / "archive" / CSS_FILE
    for _, p in sorted(found, reverse=True):
        css = extract_css(read(p))
        if css:
            if not kept.is_file() or kept.read_text(encoding="utf-8") != css:
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_text(css, encoding="utf-8")
            break
    css = kept.read_text(encoding="utf-8") if kept.is_file() else ""
    (site_dir / JS_FILE).write_text(f"window.CEV_WIDGET_CSS = {json.dumps(css, ensure_ascii=False)};\n",
                                    encoding="utf-8")
