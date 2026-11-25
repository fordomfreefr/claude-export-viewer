"""F1: an import cut short (Ctrl+C, closed window, power cut) leaves an archive that still loads and
builds, and importing the same export again gives exactly the archive of an import never cut."""

import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_export_viewer.archive import Archive, read_raw_file
from claude_export_viewer.html_builder import build_site_from_archive
from claude_export_viewer.loader import ExportDate
from claude_export_viewer.models import Conversation

ROOT = "00000000-0000-4000-8000-000000000000"


def conv(uuid: str, *texts: str) -> dict:
    msgs, parent = [], ROOT
    for i, t in enumerate(texts):
        msgs.append({"uuid": f"{uuid}-{i}", "parent_message_uuid": parent, "sender": "human" if i % 2 == 0 else "assistant",
                     "created_at": f"2026-01-01T00:0{i}:00Z", "content": [{"type": "text", "text": t}]})
        parent = f"{uuid}-{i}"
    return {"uuid": uuid, "name": uuid, "updated_at": "2026-01-01T00:00:00Z", "chat_messages": msgs}


OLD = [conv("a", "q", "r"), conv("b", "q", "r"), conv("c", "q"), conv("d", "q", "r")]
NEW = [conv("a", "q", "r"),                          # unchanged
       conv("b", "q", "r", "q2", "r2"),              # continued
       {**conv("c", "q bis"), "chat_messages": [{**conv("c", "q bis")["chat_messages"][0], "uuid": "c-x"}]},  # edited
       conv("e", "nouvelle"), conv("f", "autre")]    # new; "d" gone from claude.ai


def date(day: int) -> ExportDate:
    return ExportDate(datetime(2026, 1, day, tzinfo=timezone.utc), "test")


def records(convs: list[dict], stop: int | None = None):
    for i, raw in enumerate(convs):
        if stop is not None and i == stop:
            raise KeyboardInterrupt  # what Ctrl+C does in the middle of the import
        yield json.loads(json.dumps(raw)), Conversation.model_validate(raw)


def do_import(site: Path, convs: list[dict], day: int, stop: int | None = None) -> None:
    archive = Archive(site)
    archive.import_export(records(convs, stop), date(day), label=f"export {day}")
    archive.save()  # not reached when the import is cut


def snapshot(site: Path) -> dict:
    """Everything the archive holds, except the time of the imports."""
    st = json.loads((site / "archive" / "etat.json").read_text(encoding="utf-8"))
    for e in st["exports"]:
        e.pop("imported_at")
    raws = {}
    for p in sorted((site / "archive" / "conversations").glob("*.gz")):
        raws[p.name] = read_raw_file(p)
    return json.loads(json.dumps({"state": st, "raws": raws}).replace(str(site), "SITE"))  # the folder differs


@pytest.fixture(scope="module")
def reference(tmp_path_factory) -> dict:
    site = tmp_path_factory.mktemp("ref") / "site"
    do_import(site, OLD, 1)
    build_site_from_archive(Archive(site), site)
    do_import(site, NEW, 2)
    build_site_from_archive(Archive(site), site)
    return snapshot(site)


@pytest.mark.parametrize("stop", range(len(NEW) + 1))
def test_cut_import_then_again(tmp_path: Path, reference: dict, stop: int) -> None:
    site = tmp_path / "site"
    do_import(site, OLD, 1)
    build_site_from_archive(Archive(site), site)
    with pytest.raises(KeyboardInterrupt):
        if stop < len(NEW):
            do_import(site, NEW, 2, stop=stop)
        else:
            _cut_before_save(site)
    build_site_from_archive(Archive(site), site)  # the archive left behind still loads and builds
    do_import(site, NEW, 2)
    build_site_from_archive(Archive(site), site)
    assert snapshot(site) == reference
    assert "q2" in (site / "conversations" / "b.html").read_text(encoding="utf-8")


def _cut_before_save(site: Path) -> None:
    """Every conversation imported, cut just before the state is written."""
    archive = Archive(site)
    archive.import_export(records(NEW), date(2), label="export 2")
    raise KeyboardInterrupt


def test_cut_import_then_older_export_then_again(tmp_path: Path, reference: dict) -> None:
    """Cut, then an older export imported (nothing must be lost), then the cut one again."""
    site = tmp_path / "site"
    do_import(site, OLD, 1)
    with pytest.raises(KeyboardInterrupt):
        do_import(site, NEW, 2, stop=3)
    do_import(site, OLD, 1)
    do_import(site, NEW, 2)
    build_site_from_archive(Archive(site), site)
    assert snapshot(site) == reference


def test_cut_import_is_announced_until_done_again(tmp_path: Path, capsys) -> None:
    """A mark tells the user (console, index) that the import was cut, until that export is imported
    again; another export imported meanwhile does not remove it."""
    from claude_export_viewer.cli import main
    site = tmp_path / "site"
    do_import(site, OLD, 1)
    assert Archive(site).interrupted_import is None
    with pytest.raises(KeyboardInterrupt):
        do_import(site, NEW, 2, stop=2)
    assert Archive(site).interrupted_import["date"].startswith("2026-01-02")
    main(["-o", str(site)])
    assert "02/01/2026" in capsys.readouterr().err
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'class="import-cut"' in index and "02/01/2026" in index
    do_import(site, [conv("g", "autre export")], 3)          # another export: still announced
    assert Archive(site).interrupted_import["date"].startswith("2026-01-02")
    do_import(site, NEW, 2)                                   # the cut one again: done
    assert Archive(site).interrupted_import is None
    build_site_from_archive(Archive(site), site)
    assert "import-cut" not in (site / "index.html").read_text(encoding="utf-8")
