"""Hostile content (attack review of 21/11): an export whose every text field carries classic injections. No script of
it may run in the pages of the site; only the sandboxed frames run code, and only when asked. The static part reads
every page made; the browser part (skipped without Chromium) opens them through CEV's own server and fails on any
dialog (alert) opened by a main page."""

from __future__ import annotations

import json
import re
import threading
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest

from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"
PAYLOADS = [
    '<img src=x onerror=alert(1)>', '"><svg onload=alert(2)>', "'><script>alert(3)</script>",
    '</script><script>alert(4)</script>', '<!--', ']]>', '{{7*7}}', '${alert(5)}',
    '[lien](javascript:alert(6))', '![i](javascript:alert(7))', '<a href="javascript:alert(8)">x</a>',
    '[l](JaVaScRiPt:alert(9))', '[l](&#106;avascript:alert(10))', '<iframe src="javascript:alert(11)">',
    '```html\n</code></pre><script>alert(12)</script>\n```', '‮<b onmouseover=alert(13)>',
    '<meta http-equiv="refresh" content="0;url=javascript:alert(14)">', '<form action=javascript:alert(15)><button>',
    '$$\\href{javascript:alert(16)}{x}$$', '<details open ontoggle=alert(17)>', 'data:text/html,<script>alert(18)</script>',
]
H = " ".join(PAYLOADS)


def _artifact(ident: str, kind: str, content: str) -> dict:
    return {"type": "tool_use", "name": "artifacts",
            "input": {"command": "create", "id": ident, "type": kind, "title": H, "content": content}}


def _site(tmp: Path) -> Path:
    blocks = [{"type": "text", "text": H}, {"type": "thinking", "thinking": H},
              {"type": "tool_use", "name": H, "input": {"query": H, "url": "javascript:alert(19)"}},
              {"type": "tool_result", "name": H, "content": [{"type": "text", "text": H}]},
              _artifact('x"><b>', "text/html", H), _artifact("y", "application/vnd.ant.react", H),
              _artifact("z", "image/svg+xml", '<svg onload="alert(20)"><script>alert(21)</script></svg>'),
              _artifact("m", "text/markdown", H)]
    msgs = [{"uuid": "q", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-01-01T00:00:00Z",
             "text": H, "content": [{"type": "text", "text": H}],
             "attachments": [{"file_name": PAYLOADS[0] + PAYLOADS[1] + ".txt", "file_type": H, "extracted_content": H}],
             "files": [{"file_name": PAYLOADS[2] + ".png", "file_uuid": 'f"><b>'}]},
            {"uuid": "r", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-01-01T00:01:00Z",
             "content": blocks}]
    conv = {"uuid": "c1", "name": H, "summary": H, "updated_at": "2026-01-01T00:00:00Z", "project_uuid": "p1",
            "chat_messages": msgs}
    z = tmp / "conversations-000.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv]))
        f.writestr("projects.json", json.dumps([{"uuid": "p1", "name": H, "docs": []}]))
        f.writestr("users.json", json.dumps([{"uuid": "u", "full_name": H}]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-01-02", "--sans-navigateur"])
    return site


class _Scan(HTMLParser):
    """What could run in a page: a handler or a javascript:/data: address carrying a payload, or a script with one."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[str] = []
        self.script: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for k, v in attrs:
            v = v or ""
            if k.startswith("on") and "alert(" in v:
                self.hits.append(f"<{tag} {k}={v[:60]}>")
            if k in ("href", "src", "action", "formaction", "content") and re.match(r"\s*(javascript|data:text/html)", v, re.I):
                self.hits.append(f"<{tag} {k}={v[:60]}>")
        self.script = dict(attrs) if tag == "script" else None

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.script = None

    def handle_data(self, data: str) -> None:
        if self.script is not None and "alert(" in data and self.script.get("type") not in ("application/json", "text/plain"):
            self.hits.append(f"<script {self.script}> {data[:80]!r}")


def test_scanner_sees_live_injections() -> None:
    s = _Scan()
    s.feed('<p><img src=x onerror=alert(1)><a href="javascript:alert(2)">x</a><script>alert(3)</script></p>')
    assert len(s.hits) == 3


def test_no_injection_in_the_pages(tmp_path: Path) -> None:
    site = _site(tmp_path)
    pages = [p for p in site.rglob("*.html") if "archive" not in p.relative_to(site).parts]
    conv = (site / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert conv.count("alert(") > 100  # the payloads are there, as text
    hits = []
    for p in pages:
        s = _Scan()
        s.feed(p.read_text(encoding="utf-8"))
        hits += [f"{p.relative_to(site)}: {h}" for h in s.hits]
    assert not hits, hits


def test_no_alert_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    alerts: list[str] = []
    page.on("dialog", lambda d: (alerts.append(f"{page.url}: {d.message}"), d.dismiss()))
    search = ("for (const id of ['search', 'content-search']) { const e = document.getElementById(id); if (!e) continue;"
              " e.value = 'alert'; e.dispatchEvent(new Event('input', {bubbles: true}));"
              " e.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); }")
    try:
        page.goto(base + "index.html")
        page.evaluate(search)
        page.wait_for_timeout(500)
        page.goto(base + "conversations/c1.html")
        page.click('#page-nav [data-go="find"]')
        page.fill(".hit-words", "alert")
        page.press(".hit-words", "Enter")
        page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        page.click("#fav-list > summary")
        page.click("#note-list > summary")
        page.wait_for_timeout(300)
        for extra in sorted((site / "extras").glob("*.html")):
            page.goto(base + "extras/" + extra.name)
        page.wait_for_timeout(300)
    finally:
        server.shutdown()
        server.server_close()
    assert not alerts, alerts
