"""Point 22: archives of thousands of conversations. The search data is kept once, in parts of about
PART_SIZE conversations (searchdata.Store): a launch with nothing changed reads and writes none, a change
reads and writes only its part, a full rebuild holds one part in memory, the browser reads the parts one
after the other. Here with parts of 5 conversations, so that a few dozen conversations make several."""

import json
import os
from pathlib import Path

import pytest

from claude_export_viewer import searchdata
from claude_export_viewer.archive import Archive
from claude_export_viewer.html_builder import build_site_from_archive

from .helpers import ExportData, build_site
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def conv(i: int, word: str = "") -> dict:
    msgs = [{"uuid": f"c{i}-m{j}", "parent_message_uuid": ROOT if j == 0 else f"c{i}-m{j - 1}",
             "sender": "human" if j % 2 == 0 else "assistant", "created_at": f"2026-01-01T10:0{j}:00Z",
             "text": f"message {j} de la conversation {i} {word}",
             "content": [{"type": "text", "text": f"message {j} de la conversation {i} {word}"}]} for j in range(2)]
    return {"uuid": f"u{i:03d}", "name": f"Conv {i}", "chat_messages": msgs}


@pytest.fixture(autouse=True)
def small_parts(monkeypatch):
    monkeypatch.setattr(searchdata, "PART_SIZE", 5)


@pytest.fixture
def stores(monkeypatch) -> list:
    """Every Store the builder makes (to see what it read)."""
    made: list = []
    real = searchdata.Store.__init__

    def spy(self, *a, **k):
        real(self, *a, **k)
        made.append(self)
    monkeypatch.setattr(searchdata.Store, "__init__", spy)
    return made


def mtimes(site: Path) -> dict:
    """The times of the files of the search, after setting them in the past: a file written afterwards always shows
    (21/11: the clock of the files moves by steps of a few milliseconds; a write within the same step as the build
    before would not change the time, which made the test fail now and then)."""
    for p in (site / "search").iterdir():
        os.utime(p, ns=(1_000_000_000 * 10**9, 1_000_000_000 * 10**9))
    return {p.name: p.stat().st_mtime_ns for p in (site / "search").iterdir()}


def times_now(site: Path) -> dict:
    return {p.name: p.stat().st_mtime_ns for p in (site / "search").iterdir()}


def test_nothing_changed_nothing_read_nor_written(tmp_path: Path, stores) -> None:
    site = tmp_path / "site"
    build_site(ExportData(conversations=[conv(i) for i in range(40)]), site)
    assert len(json.loads((site / "search" / "index.json").read_text(encoding="utf-8"))["parts"]) == 8
    before = mtimes(site)
    stats = build_site_from_archive(Archive(site), site)
    assert stats.rendered == 0 and stores[-1].reads == 0 and times_now(site) == before


def test_one_change_one_part(tmp_path: Path, stores) -> None:
    site = tmp_path / "site"
    convs = [conv(i) for i in range(40)]
    build_site(ExportData(conversations=convs), site)
    before = mtimes(site)
    archive = Archive(site)
    raw = archive.load_raw("u007")
    raw["chat_messages"][0]["content"][0]["text"] += " zanzibar"
    archive.conversations["u007"]["hash"] = "changé"
    archive._store_raw(archive.conversations["u007"], raw)
    build_site_from_archive(archive, site)
    part = stores[-1].part_of("u007") + ".js"
    changed = {n for n, t in times_now(site).items() if before.get(n) != t}
    assert stores[-1].reads == 1 and changed == {part}                   # index files unchanged too
    assert "zanzibar" in searchdata.read_all(site)["u007"]["t"]


def test_full_rebuild_holds_one_part(tmp_path: Path, monkeypatch) -> None:
    most = [0]
    real = searchdata.Store.put

    def put(self, uuid, data):
        real(self, uuid, data)
        most[0] = max(most[0], len(self.loaded))
    monkeypatch.setattr(searchdata.Store, "put", put)
    build_site(ExportData(conversations=[conv(i) for i in range(40)]), tmp_path / "site")
    assert most[0] == 1


def test_parts_spread_again_as_the_archive_grows(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build_site(ExportData(conversations=[conv(i) for i in range(8)]), site)
    assert json.loads((site / "search" / "index.json").read_text(encoding="utf-8"))["n"] == 2
    archive = Archive(site)
    build_site(ExportData(conversations=[conv(i) for i in range(30)]), site)
    index = json.loads((site / "search" / "index.json").read_text(encoding="utf-8"))
    assert index["n"] == 8 and set(searchdata.read_all(site)) == {f"u{i:03d}" for i in range(30)}
    files = {p.name for p in (site / "search").glob("p*.js")}
    assert files == {f"{n}.js" for n in index["parts"]}                  # no part left behind
    del archive


def test_earlier_storage_moved_without_rendering_again(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build_site(ExportData(conversations=[conv(i) for i in range(12)]), site)
    data = searchdata.read_all(site)
    archive = Archive(site)
    old = {u: {"hash": m.pop("search"), "data": data[m["filename"].removesuffix(".html")]}
           for u, m in archive.conversations.items()}
    archive.save()
    (site / "archive" / "search.json").write_text(json.dumps(old), encoding="utf-8")
    (site / "search-data.js").write_text("window.CEV_SEARCH = {};\n", encoding="utf-8")
    for f in (site / "search").iterdir():
        f.unlink()
    stats = build_site_from_archive(Archive(site), site)
    assert stats.rendered == 0 and searchdata.read_all(site) == data
    assert not (site / "archive" / "search.json").exists() and not (site / "search-data.js").exists()


def test_search_reads_the_parts_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    site = tmp_path / "site"
    build_site(ExportData(conversations=[conv(i, "zanzibar" if i % 3 == 0 else "") for i in range(40)]), site)
    for keep in ("undefined", "1"):                                      # parts kept, then read again each time
        page.add_init_script(f"window.CEV_SEARCH_KEEP = {keep};")
        page.goto((site / "index.html").as_uri())
        page.click("#tab-filters")  # 14/11: the filters in their tab
        for _ in range(2):
            page.fill("#content-search", "")
            page.fill("#content-search", "zanzibar")
            page.wait_for_function("() => document.querySelectorAll('.content-hits:not([hidden])').length === 14"
                                   " && document.getElementById('content-status').hidden")
