"""Guided download from the manifest, with a fake browser."""

import json
import os
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import claude_export_viewer.fetch as fetch
from claude_export_viewer.cli import main

CATEGORIES = ["light_metadata", "projects", "memories", "feedback", "design_chats", "frames", "conversations"]


def make_manifest(folder: Path, age_hours: float = 1, name: str = "manifest-x.json", bad_link: bool = False) -> Path:
    created = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    files = [
        {
            "category": c,
            "filename": f"{c}-000.zip",
            "export_url": ("https://evil.example/x" if bad_link and c == "conversations"
                           else f"https://claude.ai/export/abc/download/{c}"),
        }
        for c in CATEGORIES
    ]
    path = folder / name
    path.write_text(json.dumps({"created_at": created.isoformat(), "data_files": files}), encoding="utf-8")
    return path


def make_zip(path: Path, category: str = "conversations") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        if category == "conversations":
            z.writestr("conversations.json", json.dumps([
                {"uuid": "c1", "name": "Test", "updated_at": "2020-01-01T00:00:00Z",
                 "chat_messages": [{"uuid": "m1", "sender": "human", "content": [{"type": "text", "text": "Bonjour"}]}]}
            ]))
        elif category == "projects":
            z.writestr("projects/p1.json", json.dumps({"uuid": "p1", "name": "Mon projet"}))
        else:
            z.writestr(f"{category}.json", "{}")
    return path


class FakeBrowser:
    """Simulates a browser download: partial file first, then the final (renamed) file."""

    def __init__(self, folder: Path, suffix: str = " (1)", delay: float = 0.2, style: str = "chromium"):
        self.folder, self.suffix, self.delay, self.style = folder, suffix, delay, style
        self.opened: list[str] = []

    def __call__(self, url: str) -> None:
        self.opened.append(url)
        if not url.startswith("https://claude.ai/"):
            return  # e.g. the index page opened at the end
        category = url.rsplit("/", 1)[-1]
        final = self.folder / f"{category}-000{self.suffix}.zip"
        tmp = self.folder / f"tmp-{category}.zip"
        make_zip(tmp, category)
        if self.style == "chromium":
            partial = final.with_name(final.name + ".crdownload")
            partial.write_bytes(b"incomplete")

            def finish() -> None:
                time.sleep(self.delay)
                os.replace(tmp, final)
                partial.unlink()
        else:  # firefox: empty placeholder + .part file
            final.write_bytes(b"")
            partial = final.with_name(final.name + ".part")
            partial.write_bytes(b"incomplete")

            def finish() -> None:
                time.sleep(self.delay)
                partial.unlink()
                os.replace(tmp, final)

        threading.Thread(target=finish).start()


def silent(_msg: str) -> None:
    pass


def test_already_downloaded_files_are_found_and_stored(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    stale = make_zip(dl / "conversations-000.zip")  # left over from an earlier export
    old = (manifest.created_at - timedelta(days=1)).timestamp()
    os.utime(stale, (old, old))
    make_zip(dl / "conversations-000 (1).zip")
    make_zip(dl / "projects-000.zip", "projects")
    make_zip(dl / "light_metadata-000.zip", "light_metadata")

    browser = FakeBrowser(dl)
    res = fetch.fetch_export(manifest, tmp_path / "site", opener=browser, folders=[dl], timeout=2, poll=0.05, say=silent)
    assert browser.opened == []
    assert res.missing == []
    stored = sorted(p.name for p in res.export_dir.iterdir())
    assert stored == ["conversations-000.zip", "light_metadata-000.zip", "manifest.json", "projects-000.zip"]
    assert stale.exists()  # the old export's file is left alone
    assert not (dl / "conversations-000 (1).zip").exists()  # moved into the archive
    assert not manifest.path.exists()


def test_missing_files_are_opened_one_by_one_and_awaited(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    browser = FakeBrowser(dl, delay=0.3)
    res = fetch.fetch_export(manifest, tmp_path / "site", opener=browser, folders=[dl], timeout=5, poll=0.05, say=silent)
    assert [u.rsplit("/", 1)[-1] for u in browser.opened] == ["conversations", "light_metadata", "projects"]
    assert res.missing == []
    assert (res.export_dir / "conversations-000.zip").is_file()
    with zipfile.ZipFile(res.export_dir / "conversations-000.zip") as z:
        assert z.namelist() == ["conversations.json"]  # the complete file, not the partial one


def test_firefox_style_placeholder_is_not_taken_too_early(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    browser = FakeBrowser(dl, suffix="", delay=0.4, style="firefox")
    res = fetch.fetch_export(manifest, tmp_path / "site", categories=["conversations"], opener=browser,
                             folders=[dl], timeout=5, poll=0.05, say=silent)
    assert res.missing == []
    with zipfile.ZipFile(res.files["conversations"][0]) as z:
        assert "conversations.json" in z.namelist()


def test_all_categories_on_request(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    browser = FakeBrowser(dl, delay=0.05)
    res = fetch.fetch_export(manifest, tmp_path / "site", categories=CATEGORIES, opener=browser,
                             folders=[dl], timeout=5, poll=0.05, say=silent)
    assert len(browser.opened) == 7 and res.missing == []
    assert browser.opened[0].endswith("/conversations")


def test_expired_links_are_not_opened(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl, age_hours=25))
    assert manifest.expired
    browser = FakeBrowser(dl)
    res = fetch.fetch_export(manifest, tmp_path / "site", opener=browser, folders=[dl], timeout=1, poll=0.05, say=silent)
    assert browser.opened == []
    assert "conversations-000.zip" in res.missing


def test_timeout_when_nothing_is_downloaded(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    opened = []
    res = fetch.fetch_export(manifest, tmp_path / "site", categories=["conversations"], opener=opened.append,
                             folders=[dl], timeout=0.4, poll=0.05, say=silent)
    assert len(opened) == 1
    assert res.missing == ["conversations-000.zip"]


def test_only_claude_links_are_opened(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl, bad_link=True))
    opened = []
    res = fetch.fetch_export(manifest, tmp_path / "site", categories=["conversations"], opener=opened.append,
                             folders=[dl], timeout=0.3, poll=0.05, say=silent)
    assert opened == []
    assert res.missing == ["conversations-000.zip"]


def test_latest_manifest_is_chosen(tmp_path: Path) -> None:
    make_manifest(tmp_path, age_hours=30, name="manifest-old.json")
    make_manifest(tmp_path, age_hours=1, name="manifest-new.json")
    assert fetch.latest_manifest(tmp_path).path.name == "manifest-new.json"


# --- whole command ---------------------------------------------------------


def run_cli(args: list[str], browser) -> None:
    saved = (fetch.browser_opener, fetch.download_folders)
    fetch.browser_opener = lambda command: browser
    fetch.download_folders = lambda manifest, extra=(): [manifest.path.parent, *extra]
    try:
        main(args)
    finally:
        fetch.browser_opener, fetch.download_folders = saved


def test_one_command_downloads_imports_and_opens(tmp_path: Path, capsys) -> None:
    dl = tmp_path / "Téléchargements"
    dl.mkdir()
    make_manifest(dl)
    browser = FakeBrowser(dl, delay=0.1)
    site = tmp_path / "site"
    run_cli([str(dl), "-o", str(site), "--delai", "5"], browser)
    out = capsys.readouterr().out
    assert "source : manifeste fourni" in out
    assert "1 conversation lue : 1 nouvelle" in out
    assert (site / "conversations" / "c1.html").is_file()
    assert browser.opened[-1].startswith("file://") and browser.opened[-1].endswith("index.html")
    exports = list((site / "archive" / "exports").iterdir())
    assert len(exports) == 1 and (exports[0] / "conversations-000.zip").is_file()


def test_command_explains_expired_links(tmp_path: Path, capsys) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    make_manifest(dl, age_hours=26)
    try:
        run_cli([str(dl), "-o", str(tmp_path / "site")], FakeBrowser(dl))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("should have stopped")
    err = capsys.readouterr().err
    assert "expiré" in err and "Exporter les données" in err


def test_file_from_an_earlier_export_is_not_mistaken_for_the_new_one(tmp_path: Path) -> None:
    """Only the previous export's conversations-000.zip is in the folder: the new one must be downloaded."""
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    stale = make_zip(dl / "conversations-000.zip")
    old = (manifest.created_at - timedelta(days=1)).timestamp()
    os.utime(stale, (old, old))
    browser = FakeBrowser(dl, delay=0.1)
    res = fetch.fetch_export(manifest, tmp_path / "site", categories=["conversations"], opener=browser,
                             folders=[dl], timeout=5, poll=0.05, say=silent)
    assert [u.rsplit("/", 1)[-1] for u in browser.opened] == ["conversations"]
    assert res.missing == []
    assert stale.exists()  # untouched
    assert res.files["conversations"][0].stat().st_mtime > old


def test_manual_mode_prints_links_and_never_opens_the_browser(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    lines: list[str] = []
    user = FakeBrowser(dl, delay=0.1)  # the user clicking the printed link

    def say(msg: str) -> None:
        lines.append(msg)
        if msg.strip().startswith("https://claude.ai/"):
            user(msg.strip())

    opened = []
    res = fetch.fetch_export(manifest, tmp_path / "site", opener=opened.append, folders=[dl],
                             timeout=5, poll=0.05, say=say, manual=True)
    assert opened == []  # nothing opened by the program
    assert res.missing == []
    out = "\n".join(lines)
    assert "[1/3] conversations-000.zip" in out and "[3/3] projects-000.zip" in out
    assert "Ctrl + clic" in out
    assert out.count("https://claude.ai/export/abc/download/") == 3
    assert out.count("✓ reçu") == 3


def test_automatic_mode_also_prints_the_link(tmp_path: Path) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    manifest = fetch.read_manifest(make_manifest(dl))
    lines: list[str] = []
    fetch.fetch_export(manifest, tmp_path / "site", categories=["conversations"], opener=FakeBrowser(dl, delay=0.05),
                       folders=[dl], timeout=5, poll=0.05, say=lines.append)
    assert "  https://claude.ai/export/abc/download/conversations" in lines


def test_ctrl_c_stops_cleanly_and_keeps_files(tmp_path: Path, capsys) -> None:
    dl = tmp_path / "dl"
    dl.mkdir()
    make_manifest(dl)
    received = make_zip(dl / "light_metadata-000.zip", "light_metadata")
    saved = fetch.wait_for_download

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    fetch.wait_for_download = interrupted
    try:
        run_cli([str(dl), "-o", str(tmp_path / "site"), "--manuel"], FakeBrowser(dl))
    except SystemExit as exc:
        assert exc.code == 130
    else:
        raise AssertionError("should have stopped")
    finally:
        fetch.wait_for_download = saved
    assert "relancez la même commande" in capsys.readouterr().err
    assert received.exists()  # nothing moved: the next run resumes
