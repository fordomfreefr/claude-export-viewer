"""Packages of esm.sh a React program of Claude imports, downloaded once with the user's agreement with every
module they reach, kept in the archive and used without asking and without the Internet (esm_cache.py, run.js;
PT-m3, 08/11). esm.sh is not reachable here: a stand-in gives a package of three modules."""

import json
import threading
from pathlib import Path

from claude_export_viewer import esm_cache

from .test_run_browser import art, site
from .test_topics_browser import page  # noqa: F401 - fixture

ENTRY = "https://esm.sh/fake-pkg?external=react,react-dom&target=es2022"
MAIN = "https://esm.sh/fake-pkg@1.0.0/es2022/fake-pkg.mjs"
UTIL = "https://esm.sh/fake-pkg@1.0.0/es2022/util.mjs"
FILES = {
    ENTRY: b'export * from "/fake-pkg@1.0.0/es2022/fake-pkg.mjs";export{default}from"/fake-pkg@1.0.0/es2022/fake-pkg.mjs";',
    MAIN: b'import{h as x}from"./util.mjs";import "react";export const hello=()=>"bonjour "+x();export default 7;',
    UTIL: b'export const h=()=>"paquet garde";',
}
CALLS: list[str] = []


def fake(url: str) -> bytes:
    CALLS.append(url)
    if url not in FILES:
        raise OSError("introuvable")
    return FILES[url]


def test_download_follows_the_modules(tmp_path: Path) -> None:
    CALLS.clear()
    assert esm_cache.download(tmp_path, ["fake-pkg"], fake) == {}
    assert esm_cache.download(tmp_path, ["fake-pkg"], fake) == {}       # kept: not fetched again
    assert sorted(CALLS) == sorted([ENTRY, MAIN, UTIL])
    data = json.loads((tmp_path / "esm-cache.js").read_text(encoding="utf-8").removeprefix("window.CEV_ESM = ").rstrip(";\n"))
    mods = data["fake-pkg"]["modules"]
    assert data["fake-pkg"]["entry"] == ENTRY and set(mods) == {ENTRY, MAIN, UTIL}
    assert f'from "{MAIN}"' in mods[ENTRY] and f'from"{UTIL}"' in mods[MAIN]  # every path written out
    assert 'import "react"' in mods[MAIN]                                # a bare name stays (given by CEV)
    errors = esm_cache.download(tmp_path, ["../etc", "absent-pkg"], fake)
    assert set(errors) == {"../etc", "absent-pkg"}
    assert esm_cache.valid_spec("@react-three/fiber") and esm_cache.valid_spec("three/examples/jsm/controls/OrbitControls")
    assert not esm_cache.valid_spec("https://evil.example/x") and not esm_cache.valid_spec("a b")


APP = '''import React from "react";
import seven, { hello } from "fake-pkg";
export default function App() { return <p id="out">{hello()} {seven}</p>; }'''


def test_kept_once_then_run_without_the_internet(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    from claude_export_viewer.server import make_server
    monkeypatch.setattr(esm_cache, "_fetch", fake)
    out = site(tmp_path, art("p", "application/vnd.ant.react", "Paquet", APP))
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html"
        page.goto(url)
        page.click(".run-btn")
        ask = page.locator(".cev-confirm-text")
        assert "fake-pkg" in ask.text_content() and "garder dans l'archive" in ask.text_content()
        page.click(".cev-confirm-yes")
        out_p = page.frame_locator(".cev-run-frame").locator("#out")
        out_p.filter(has_text="bonjour paquet garde 7").wait_for(timeout=30000)
        rule = page.locator(".cev-run-frame").get_attribute("srcdoc").split('Content-Security-Policy" content="')[1].split('"')[0]
        assert "https:" not in rule                                        # from the archive: no Internet at all
        page.goto(url)                                                     # another time: nothing asked
        page.click(".run-btn")
        page.frame_locator(".cev-run-frame").locator("#out").filter(has_text="bonjour paquet garde").wait_for(timeout=30000)
        assert page.locator(".cev-confirm").count() == 0
    finally:
        server.shutdown()
        server.server_close()
    page.goto((out / "conversations" / "c1.html").as_uri())               # opened as a file: kept too
    page.click(".run-btn")
    page.frame_locator(".cev-run-frame").locator("#out").filter(has_text="bonjour paquet garde").wait_for(timeout=30000)
    assert page.locator(".cev-confirm").count() == 0
