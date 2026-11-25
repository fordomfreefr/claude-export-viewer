"""Libraries of the Internet downloaded once with the user's agreement, kept in the archive and used by
every page loading the same address, without asking and without the Internet (cdn_cache.py, run.js)."""

import json
import threading
from pathlib import Path

from claude_export_viewer import cdn_cache

from .test_run_browser import site, widget
from .test_topics_browser import page  # noqa: F401 - fixture

JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"
CSS = "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.42.0/dist/tabler-icons.min.css"
FILES = {
    JS: b"window.Chart = function () {}; window.LIBOK = 'bibliotheque gardee </script> ok';",
    CSS: b"@font-face{src:url('./fonts/t.woff2?v3') format('woff2'),url(./fonts/t.woff) format('woff')}.ti{color:red}",
    "https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.42.0/dist/fonts/t.woff2?v3": b"WOFF2",
}
CALLS: list[str] = []


def fake(url: str) -> bytes:
    CALLS.append(url)
    if url not in FILES:
        raise OSError("introuvable")
    return FILES[url]


def test_download_keeps_once(tmp_path: Path) -> None:
    CALLS.clear()
    assert cdn_cache.download(tmp_path, [JS, CSS], fake) == {}
    assert cdn_cache.download(tmp_path, [JS, CSS], fake) == {}            # already kept: not fetched again
    assert CALLS.count(JS) == 1
    data = json.loads((tmp_path / "cdn-cache.js").read_text(encoding="utf-8").removeprefix("window.CEV_CDN = ").rstrip(";\n"))
    assert "LIBOK" in data[JS] and "</script>" not in (tmp_path / "cdn-cache.js").read_text(encoding="utf-8")
    assert "url(data:font/woff2;base64,V09GRjI=)" in data[CSS] and "url(data:,)" in data[CSS]  # woff2 kept, woff dropped
    errors = cdn_cache.download(tmp_path, ["http://example.com/a.js", "https://x.example/absent.js"], fake)
    assert set(errors) == {"http://example.com/a.js", "https://x.example/absent.js"}


CODE = (f'<script src="{JS}"></script><link rel="stylesheet" href="{CSS}">'
        '<p id="lib">rien</p><script>document.getElementById("lib").textContent = window.LIBOK || "absente";</script>')


def test_kept_once_then_used_without_asking(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    from claude_export_viewer.server import make_server
    monkeypatch.setattr(cdn_cache, "_fetch", fake)
    out = site(tmp_path, *widget(CODE))
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html"
        page.goto(url)
        page.click(".widget .run-btn")
        ask = page.locator(".cev-confirm-text")
        assert "cdnjs.cloudflare.com" in ask.text_content() and "garder dans l'archive" in ask.text_content()
        page.click(".cev-confirm-yes")
        lib = page.frame_locator(".cev-run-frame").locator("#lib")
        lib.filter(has_text="gardee").wait_for(timeout=30000)
        rule = page.locator(".cev-run-frame").get_attribute("srcdoc").split('Content-Security-Policy" content="')[1].split('"')[0]
        assert "https:" not in rule                                        # from the archive: no Internet at all
        assert (out / "archive" / "cdn" / "index.json").is_file()
        page.goto(url)                                                     # another time: nothing asked
        page.click(".widget .run-btn")
        page.frame_locator(".cev-run-frame").locator("#lib").filter(has_text="gardee").wait_for(timeout=30000)
        assert page.locator(".cev-confirm").count() == 0
    finally:
        server.shutdown()
        server.server_close()
    other = site(tmp_path / "autre", *widget(CODE, "autre_visuel"))       # another page, opened as a file
    cdn_cache.download(other, [JS, CSS], fake)
    page.goto((other / "conversations" / "c1.html").as_uri())
    page.click(".widget .run-btn")
    page.frame_locator(".cev-run-frame").locator("#lib").filter(has_text="gardee").wait_for(timeout=30000)
    assert page.locator(".cev-confirm").count() == 0


def test_failure_is_said_once(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    """A download that fails says why in the strip, with no second question; the next click asks for this
    run only. A server of an older program (404) is named as such."""
    from claude_export_viewer.server import make_server

    def broken(url: str) -> bytes:
        raise OSError("réseau injoignable")
    monkeypatch.setattr(cdn_cache, "_fetch", broken)
    out = site(tmp_path, *widget(CODE))
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html"
        page.goto(url)
        page.click(".widget .run-btn")
        page.click(".cev-confirm-yes")
        err = page.locator(".cev-run-err")
        err.wait_for(timeout=30000)
        assert "réseau injoignable" in err.text_content() and page.locator(".cev-confirm").count() == 0
        page.click(".widget .run-btn")                                     # now: for this run only
        assert "accès à Internet, pour ce lancement seulement" in page.locator(".cev-confirm-text").text_content()
        page.click(".cev-confirm-no")
        page.route("**/__cev__/cdn", lambda r: r.fulfill(status=404, body="inconnu"))
        page.goto(url)
        page.click(".widget .run-btn")
        page.click(".cev-confirm-yes")
        err.wait_for(timeout=30000)
        assert "version plus ancienne" in err.text_content()
    finally:
        server.shutdown()
        server.server_close()
