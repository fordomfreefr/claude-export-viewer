"""Corrections of the review of 21/11 (2026.11.21.3): each test reproduces the fault it guards against."""

import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_export_viewer import loader
from claude_export_viewer.archive import Archive
from claude_export_viewer.loader import ExportDate, classify, iter_conversation_records, pop_read_errors

from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def conv(uuid: str, text: str = "q") -> dict:
    return {"uuid": uuid, "name": uuid, "updated_at": "2026-01-01T00:00:00Z",
            "chat_messages": [{"uuid": f"{uuid}-0", "parent_message_uuid": ROOT, "sender": "human",
                               "created_at": "2026-01-01T00:00:00Z", "content": [{"type": "text", "text": text}]}]}


def day(n: int) -> ExportDate:
    return ExportDate(datetime(2026, 1, n, tzinfo=timezone.utc), "test")


# --- A1: a cut or malformed JSON array is never taken for a complete one ---------------------------------------------

@pytest.mark.parametrize("text", ['[{"a":1},{"b":2}', '[{"a":1},', '[{"a":1}] garbage', '[{"a":1},,{"b":2}]',
                                  '[{"a":1}{"b":2}]', '[{"a":1},]', "[,]", "[", '[{"a":1},{"b'])
def test_bad_array_raises(text: str) -> None:
    with pytest.raises(json.JSONDecodeError):
        list(loader.iter_json_items(io.StringIO(text)))


@pytest.mark.parametrize("chunk", [1, 3, 1 << 20])
def test_good_arrays_across_chunks(monkeypatch, chunk: int) -> None:
    monkeypatch.setattr(loader, "_CHUNK", chunk)
    for value in ([], [1], [{"a": "x" * 50}, {"b": [1, 2]}]):
        for text in (json.dumps(value), json.dumps(value, indent=1) + "\n  \n"):
            assert list(loader.iter_json_items(io.StringIO(text))) == value


def _import(site: Path, folder: Path, n: int):
    archive = Archive(site)
    found = classify([folder])
    pop_read_errors()
    stats = archive.import_export(iter_conversation_records(found.conversations), day(n),
                                  read_ok=lambda: not pop_read_errors())
    archive.save()
    return Archive(site), stats


def test_cut_export_marks_nothing_deleted(tmp_path: Path) -> None:
    site, folder = tmp_path / "site", tmp_path / "in"
    folder.mkdir()
    full = [conv("a"), conv("b"), conv("c"), conv("d")]
    (folder / "conversations.json").write_text(json.dumps(full), encoding="utf-8")
    _import(site, folder, 1)
    # day 2: "a" changed, the file cut after "b" (exactly between two objects: read silently before)
    text = json.dumps([conv("a", "nouveau"), conv("b"), conv("c"), conv("d")])
    cut = text[:text.index('{"uuid": "c"')]
    (folder / "conversations.json").write_text(cut, encoding="utf-8")
    archive, stats = _import(site, folder, 2)
    assert stats.incomplete and not stats.newly_deleted and not stats.suspicious
    assert not any(archive.deleted_since(m) for m in archive.conversations.values())
    assert archive.latest_export.startswith("2026-01-01")  # the cut export is not the reference
    assert archive.conversations["a"]["version_export"].startswith("2026-01-02")  # what was read is kept
    assert [e.get("incomplete", False) for e in archive.state["exports"]] == [False, True]
    # the complete export of day 2, imported again: the reference now; "d" gone from claude.ai is marked
    (folder / "conversations.json").write_text(json.dumps([conv("a", "nouveau"), conv("b"), conv("c")]),
                                               encoding="utf-8")
    archive, stats = _import(site, folder, 2)
    assert not stats.incomplete and stats.newly_deleted == ["d"]
    assert [e.get("incomplete", False) for e in archive.state["exports"]] == [False, False]


# --- Changes of the notes at once (the server answers in threads): none is lost -------------------------------------

def test_concurrent_annotation_changes_all_kept(tmp_path: Path, monkeypatch) -> None:
    import threading
    import time

    from claude_export_viewer import annotations

    msgs = [{"uuid": f"c-{i}", "sender": "human", "created_at": "2026-01-01T00:00:00Z",
             "content": [{"type": "text", "text": str(i)}]} for i in range(8)]
    raw = {"uuid": "c", "chat_messages": msgs}
    real_load = annotations.load

    def slow_load(site_dir):  # widens the window between reading and writing
        data = real_load(site_dir)
        time.sleep(0.05)
        return data

    monkeypatch.setattr(annotations, "load", slow_load)
    threads = [threading.Thread(target=annotations.change, args=(
        tmp_path, {"action": "favorite", "conversation": "c", "message": f"c-{i}", "on": True}, lambda u: raw))
        for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(real_load(tmp_path)["favorites"]["c"]) == [f"c-{i}" for i in range(8)]


# --- A2: a restore cut short, or from an incomplete backup, can be made again -------------------------------------

def _backup(tmp_path: Path) -> Path:
    from claude_export_viewer import backup

    from .test_favorites import _site

    site = _site(tmp_path)
    dest = tmp_path / "dl"
    dest.mkdir()
    return backup.make_backup(site, dest)


def test_restore_cut_short_can_be_made_again(tmp_path: Path, monkeypatch) -> None:
    import shutil

    from claude_export_viewer import uninstall

    import zipfile

    zip_path, again = _backup(tmp_path), tmp_path / "again"
    with zipfile.ZipFile(zip_path) as z:
        total = sum(1 for i in z.infolist() if not i.is_dir())
    real, count = shutil.copyfileobj, {"n": 0}

    def cut(src, dst, *a):
        count["n"] += 1
        if count["n"] >= total:  # cut at the very last file
            raise KeyboardInterrupt  # the window closed in the middle
        return real(src, dst, *a)

    monkeypatch.setattr(uninstall.shutil, "copyfileobj", cut)
    with pytest.raises(KeyboardInterrupt):
        uninstall.restore(zip_path, again)
    assert not Archive(again).conversations  # the state comes last: still an empty Library
    monkeypatch.setattr(uninstall.shutil, "copyfileobj", real)
    assert uninstall.restore(zip_path, again) > 0
    archive = Archive(again)
    assert archive.conversations and all(archive.raw_path(m).is_file() for m in archive.conversations.values())


def test_restore_from_backup_missing_a_conversation(tmp_path: Path) -> None:
    import zipfile

    from claude_export_viewer import uninstall

    zip_path = _backup(tmp_path)
    broken = tmp_path / "site-2026-01-01.zip"
    with zipfile.ZipFile(zip_path) as z, zipfile.ZipFile(broken, "w") as out:
        raws = [n for n in z.namelist() if "/archive/conversations/" in n and n.endswith(".jsonl.gz")]
        for name in z.namelist():
            if name != raws[0]:
                out.writestr(name, z.read(name))
    again = tmp_path / "again"
    with pytest.raises(uninstall.UninstallError):
        uninstall.restore(broken, again)
    assert not Archive(again).conversations and (again / "archive" / "etat.json.incomplet").is_file()
    assert uninstall.restore(zip_path, again) > 0  # the good backup afterwards


# --- A3: the limit of an artifact version is checked on the real sizes, not on what its listing says --------------

def test_artifact_limit_uses_real_sizes(tmp_path: Path, monkeypatch) -> None:
    from claude_export_viewer import extras

    from .test_extras import ART, _site

    site = _site(tmp_path)
    monkeypatch.setattr(extras, "MAX_VERSION", 100)  # the listing says 60 + 40 bytes: the real files are bigger
    with pytest.raises(ValueError):
        extras.extract(site, ART, "v2")
    assert not list((site / extras.FOLDER).rglob("v2*"))  # nothing extracted


# --- B1: the libraries downloaded follow redirections to https only (to esm.sh only for its packages) ---------------

def test_download_redirections_kept_to_https(monkeypatch) -> None:
    import email.message
    import urllib.error
    import urllib.request

    from claude_export_viewer import cdn_cache, esm_cache
    monkeypatch.setattr(cdn_cache, "public_host", lambda h: h == "autre.example")  # no DNS in the tests (25/11)

    req, headers = urllib.request.Request("https://cdn.example/lib.js"), email.message.Message()

    def follow(host, newurl):
        return cdn_cache._Redirects(host).redirect_request(req, None, 302, "Found", headers, newurl)

    assert follow(None, "https://autre.example/lib.js").full_url == "https://autre.example/lib.js"
    assert follow("esm.sh", "https://esm.sh/react@18").full_url == "https://esm.sh/react@18"
    for host, newurl in ((None, "http://192.168.1.1/"), (None, "file:///etc/passwd"), ("esm.sh", "https://evil.example/"),
                         (None, "https://user:pw@x.example/")):
        with pytest.raises(urllib.error.HTTPError):
            follow(host, newurl)
    with pytest.raises(OSError):
        cdn_cache.open_https("http://cdn.example/lib.js", 1)
    with pytest.raises(OSError):
        esm_cache._fetch("https://evil.example/x.js")


# --- B5: a drop is refused before it fills the disk -------------------------------------------------------------------

def test_drop_refused_when_the_disk_is_nearly_full(tmp_path: Path, monkeypatch) -> None:
    from collections import namedtuple

    from claude_export_viewer import drop

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(drop.shutil, "disk_usage", lambda p: usage(10**12, 10**12 - drop.RESERVE - 10, drop.RESERVE + 10))
    with pytest.raises(drop.DropError) as exc:
        drop.receive(tmp_path, "abcdefgh12", "conversations.zip", 0, io.BytesIO(b"x" * 100), 100, True, None)
    assert exc.value.key == "drop.no_space"
    monkeypatch.undo()
    assert drop.receive(tmp_path, "abcdefgh12", "conversations.zip", 0, io.BytesIO(b"x" * 100), 100, True, None) == 100


# --- B6: replacing the program never touches a folder of the user, and puts the old program back on failure -------

def test_install_keeps_user_folders_and_rolls_back(tmp_path: Path, monkeypatch) -> None:
    from claude_export_viewer import install

    source, dest, site = tmp_path / "src", tmp_path / "claude-export-viewer", tmp_path / "site"
    for folder, text in ((source, "nouveau"), (dest, "ancien")):
        folder.mkdir()
        (folder / install.LAUNCHER).write_text(text, encoding="utf-8")
    mine = tmp_path / "claude-export-viewer.nouveau"  # a folder of the user with that name
    mine.mkdir()
    (mine / "notes.txt").write_text("à moi", encoding="utf-8")
    real_rename = Path.rename

    def failing(self, target):  # the new program cannot take the place (a file held open…)
        if Path(target) == dest and ".nouveau-" in self.name:
            raise OSError("occupé")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", failing)
    with pytest.raises(OSError):
        install.place_program(source, dest, site)
    assert (dest / install.LAUNCHER).read_text(encoding="utf-8") == "ancien"  # the old program back
    monkeypatch.undo()
    assert install.place_program(source, dest, site)
    assert (dest / install.LAUNCHER).read_text(encoding="utf-8") == "nouveau"
    assert (mine / "notes.txt").is_file()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["claude-export-viewer", "claude-export-viewer.nouveau", "src"]


# --- P2: making the pages of the other data reads each kind of ZIP once -----------------------------------------------

def test_extras_pages_read_each_kind_once(tmp_path: Path, monkeypatch) -> None:
    from collections import Counter

    from claude_export_viewer import extras, html_builder

    from .test_extras import _site

    site = _site(tmp_path)
    calls: Counter[str] = Counter()
    for name in ("memory_versions", "reflections", "design_chats", "artifacts", "other_files"):
        real = getattr(extras, name)

        def counted(*a, _real=real, _name=name):
            calls[_name] += 1
            return _real(*a)
        monkeypatch.setattr(extras, name, counted)
    summary = html_builder.write_extras(html_builder._environment(), site)
    assert summary["artifacts"] == 1 and summary["memory_versions"] == 2
    assert max(calls.values()) == 1, calls


# --- Dates (attack review of 21/11): an export dated after the clock is asked, never imported silently ----------------

def _records(convs):
    from claude_export_viewer.models import Conversation

    for c in convs:
        yield json.loads(json.dumps(c)), Conversation.model_validate(c)


def _imp(site: Path, convs, when: datetime):
    archive = Archive(site)
    stats = archive.import_export(_records(convs), ExportDate(when, "test"))
    archive.save()
    return stats


def test_date_question_only_beyond_the_clock(tmp_path: Path) -> None:
    from claude_export_viewer.loader import date_question

    (tmp_path / "conversations.json").write_text(json.dumps([conv("a")]), encoding="utf-8")
    found = classify([tmp_path])
    now = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
    assert date_question(found, ExportDate(datetime(2026, 11, 22, 11, tzinfo=timezone.utc), "m"), now) is None  # < 1 day
    q = date_question(found, ExportDate(datetime(2099, 1, 1, tzinfo=timezone.utc), "m"), now)
    assert q is not None and q.clock == now and q.newest == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_cli_asks_for_a_future_date_then_imports_when_confirmed(tmp_path: Path, capsys) -> None:
    from claude_export_viewer.cli import main

    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "conversations.json").write_text(json.dumps([conv("a")]), encoding="utf-8")
    site = tmp_path / "site"
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2099-01-01", "--sans-navigateur"])
    assert exc.value.code == 3 and not Archive(site).conversations  # nothing imported
    out = capsys.readouterr().out
    assert "--date-confirmee" in out and "2026-01-01T00:00:00+00:00" in out  # the date of its newest conversation
    main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2026-01-01T00:00:00+00:00", "--date-confirmee",
          "--sans-navigateur"])
    assert list(Archive(site).conversations) == ["a"]


def test_server_keeps_the_question_and_runs_the_answer(monkeypatch) -> None:
    import sys

    from claude_export_viewer import server
    from claude_export_viewer.loader import DATE_MARK

    job = server.Job("import")
    line = f"{DATE_MARK}2099-01-01T00:00:00+00:00 2026-11-21T12:00:00+00:00 2026-01-01T00:00:00+00:00"
    server.run_streaming([sys.executable, "-c", f"print({line!r})"], job)
    assert job.extra["date_question"]["newest"] == "2026-01-01T00:00:00+00:00"
    seen = []

    class Ctx:
        pending_import = {"args": ["/exports/x"], "newest": "2026-01-01T00:00:00+00:00"}

    monkeypatch.setattr(server, "_run_import", lambda j, c, args: seen.append(args) or 0)
    server.date_job(server.Job("import"), Ctx, "newest")
    assert seen == [["/exports/x", "--date-confirmee", "--date-export", "2026-01-01T00:00:00+00:00"]]
    assert Ctx.pending_import is None


def test_a_date_before_the_newest_conversation_is_told(tmp_path: Path) -> None:
    stats = _imp(tmp_path, [conv("a")], datetime(2025, 6, 1, tzinfo=timezone.utc))
    assert stats.date_before_newest and stats.newest == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert not _imp(tmp_path / "b", [conv("a")], datetime(2026, 1, 2, tzinfo=timezone.utc)).date_before_newest


def test_verify_redates_an_export_from_the_future(tmp_path: Path) -> None:
    from claude_export_viewer import verify

    site = tmp_path
    _imp(site, [conv("a", "v1"), conv("b", "v1")], datetime(2026, 1, 1, tzinfo=timezone.utc))
    _imp(site, [{**conv("a", "FAUX"), "updated_at": "2026-01-05T00:00:00Z"}], datetime(2099, 1, 1, tzinfo=timezone.utc))
    said = []
    rep = verify.run(site, lambda k, a: said.append(k), repair_now=True)
    assert "verify.future_export" in said and "verify.redated" in said and rep.redate
    archive = Archive(site)
    assert archive.latest_export.startswith("2026-01-05")  # the date of its newest conversation, not of the clock
    # an ordinary export now: "b", missing from it, is marked as for any export; the next one tells (below)
    assert archive.deleted_since(archive.conversations["b"]) and not archive.deleted_since(archive.conversations["a"])
    a2 = {**conv("a", "v2"), "chat_messages": [{**conv("a")["chat_messages"][0], "uuid": "a-1",
                                                 "content": [{"type": "text", "text": "v2"}]}]}
    stats = _imp(site, [a2, conv("b", "v1")], datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert stats.is_latest and Archive(site).conversations["a"]["version_export"].startswith("2026-02-01")
    assert stats.restored == ["b"] and not any(Archive(site).deleted_since(m) for m in Archive(site).conversations.values())


def test_verify_does_not_repair_when_the_clock_seems_wrong(tmp_path: Path) -> None:
    from claude_export_viewer import verify

    _imp(tmp_path, [{**conv("a"), "updated_at": "2099-01-01T00:00:00Z"}], datetime(2099, 1, 2, tzinfo=timezone.utc))
    said = []
    rep = verify.check(tmp_path, lambda k, a: said.append(k))
    assert "verify.future_export_clock" in said and not rep.redate


# --- Long file names: shortened, the page made all the same ----------------------------------------------------------

def test_long_attachment_names(tmp_path: Path) -> None:
    from claude_export_viewer.cli import main
    from claude_export_viewer.userfiles import NAME_BYTES, short_name

    assert short_name("rapport.pdf") == "rapport.pdf"
    long = "長い名前の論文" * 20 + ".pdf"  # 140 characters, 420 bytes: refused by Linux before
    short = short_name(long)
    assert short.endswith(".pdf") and len(short.encode("utf-8")) <= NAME_BYTES and short != short_name(long[1:])
    c = conv("a")
    c["chat_messages"][0]["attachments"] = [{"file_name": long, "extracted_content": "texte joint"}]
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "conversations.json").write_text(json.dumps([c]), encoding="utf-8")
    site = tmp_path / "site"
    main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2026-01-02", "--sans-navigateur"])
    assert (site / "conversations" / "a.html").is_file()
    assert [p.name for p in (site / "attachments").rglob("*.pdf.txt")] or list((site / "attachments").rglob("*~*"))


# --- A made-up export cannot fill the memory nor the disk -------------------------------------------------------------

@pytest.mark.parametrize("text", ['{"a":1}\n{"a":"' + "x" * 300 + '"}\n', '{\n"a":"' + "x" * 300 + '"\n}'])
def test_one_json_element_too_big(monkeypatch, text: str) -> None:
    """A line (JSONL) or a single object too big: refused (they are read whole)."""
    monkeypatch.setattr(loader, "MAX_ELEMENT", 200)
    monkeypatch.setattr(loader, "_CHUNK", 16)
    with pytest.raises(json.JSONDecodeError):
        list(loader.iter_json_items(io.StringIO(text)))


def test_a_value_too_big_is_set_aside_and_the_reading_goes_on(monkeypatch) -> None:
    import random

    rnd = random.Random(17)
    monkeypatch.setattr(loader, "MAX_ELEMENT", 300)
    for chunk in (7, 64, 1 << 20):
        monkeypatch.setattr(loader, "_CHUNK", chunk)
        for _ in range(100):
            big = rnd.choice([{"t": 'a"b\\c[{]}' * 120}, ['}' * 50, '"\\' * 200], "é\"\\]" * 400])
            items = [_random_value(rnd), big, {"suite": 1}, _random_value(rnd)]
            loader.pop_too_big()
            got = list(loader.iter_json_items(io.StringIO(json.dumps(items, ensure_ascii=rnd.random() < 0.5))))
            assert isinstance(got[1], loader.TooBig) and got[2] == {"suite": 1} and json.dumps(got[3]) == json.dumps(items[3])
            assert loader.pop_too_big()[0] == got[1].size


def test_a_message_too_big_leaves_its_conversation_and_the_rest(tmp_path: Path, monkeypatch, capsys) -> None:
    from claude_export_viewer.cli import main

    c = conv("a")
    c["chat_messages"].append({"uuid": "geant", "parent_message_uuid": "a-0", "sender": "assistant",
                               "content": [{"type": "text", "text": "x" * 5000}]})
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "conversations.json").write_text(json.dumps([c, conv("b")]), encoding="utf-8")
    monkeypatch.setattr(loader, "MAX_ELEMENT", 1000)
    site = tmp_path / "site"
    main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2026-01-02", "--sans-navigateur"])
    out = capsys.readouterr().out
    archive = Archive(site)
    assert sorted(archive.conversations) == ["a", "b"] and "--limite-message 1" in out
    assert [m["uuid"] for m in archive.load_raw("a")["chat_messages"]] == ["a-0"]  # the rest of it kept
    main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2026-01-02", "--sans-navigateur", "--limite-message", "1"])
    assert [m["uuid"] for m in Archive(site).load_raw("a")["chat_messages"]] == ["a-0", "geant"]
    loader.MESSAGE_LIMIT = None


def test_server_asks_for_a_message_set_aside(monkeypatch) -> None:
    import sys

    from claude_export_viewer import server
    from claude_export_viewer.loader import BIG_MARK

    job = server.Job("import")
    server.run_streaming([sys.executable, "-c", f"print({BIG_MARK + '650 3250 2000'!r})"], job)
    assert job.extra["big_message"] == {"size": 650, "need": 3250, "free": 2000}
    seen = []

    class Ctx:
        pending_import = {"args": ["/exports/x"], "newest": "", "big": 650}

    monkeypatch.setattr(server, "_run_import", lambda j, c, args: seen.append(args) or 0)
    server.date_job(server.Job("import"), Ctx, "big")
    assert seen == [["/exports/x", "--limite-message", "651"]]


def test_import_stops_before_a_full_disk(tmp_path: Path, monkeypatch) -> None:
    from collections import namedtuple

    from claude_export_viewer import archive as archive_mod

    _imp(tmp_path, [conv("a")], datetime(2026, 1, 1, tzinfo=timezone.utc))
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(archive_mod.shutil, "disk_usage", lambda p: usage(10**12, 10**12, archive_mod.DISK_RESERVE - 1))
    with pytest.raises(archive_mod.DiskFull):
        _imp(tmp_path, [conv("b")], datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert list(Archive(tmp_path).conversations) == ["a"] and Archive(tmp_path).interrupted_import
    monkeypatch.undo()
    _imp(tmp_path, [conv("b")], datetime(2026, 2, 1, tzinfo=timezone.utc))  # imported again: completed
    assert sorted(Archive(tmp_path).conversations) == ["a", "b"] and not Archive(tmp_path).interrupted_import


# --- Step 1 of the reading in pieces (21/11): a conversation read message by message, exactly as json.loads ----------

def _random_value(rnd, depth=0):
    kinds = ["int", "float", "str", "bool", "null"] + (["list", "dict"] if depth < 3 else [])
    k = rnd.choice(kinds)
    if k == "int":
        return rnd.randint(-10**12, 10**12)
    if k == "float":
        return rnd.choice([0.5, -1e-7, 3.25e10, 12345.678])
    if k == "str":
        return "".join(rnd.choice('aé"\\\\/\n\t€😀 ,]}{[:') for _ in range(rnd.randint(0, 12)))
    if k == "bool":
        return rnd.random() < 0.5
    if k == "null":
        return None
    if k == "list":
        return [_random_value(rnd, depth + 1) for _ in range(rnd.randint(0, 4))]
    return {f"k{i}": _random_value(rnd, depth + 1) for i in range(rnd.randint(0, 4))}


def test_streamed_reading_equals_json_loads(monkeypatch) -> None:
    import random

    rnd = random.Random(21)
    for chunk in (1, 2, 3, 7, 1 << 20):
        monkeypatch.setattr(loader, "_CHUNK", chunk)
        for _ in range(150):
            items = []
            for _ in range(rnd.randint(0, 4)):
                if rnd.random() < 0.2:
                    items.append(_random_value(rnd))  # not an object: given whole
                    continue
                keys = [f"f{i}" for i in range(rnd.randint(0, 4))]
                keys.insert(rnd.randint(0, len(keys)), "chat_messages")
                items.append({k: ([_random_value(rnd) for _ in range(rnd.randint(0, 5))]
                                  if k == "chat_messages" and rnd.random() < 0.9 else _random_value(rnd)) for k in keys})
            text = json.dumps(items, ensure_ascii=rnd.random() < 0.5, indent=rnd.choice([None, 1]))
            got = [e.assemble() if isinstance(e, loader.Events) else e
                   for e in loader.iter_json_items(io.StringIO(text), loader.STREAMED)]
            assert json.dumps(got) == json.dumps(json.loads(text)), text  # same values, same order of the keys


def test_repeated_key_and_cut_conversation() -> None:
    text = '[{"chat_messages": [1], "uuid": "a", "chat_messages": [2, 3]}]'
    got = [e.assemble() for e in loader.iter_json_items(io.StringIO(text), loader.STREAMED)]  # read as it comes
    assert json.dumps(got) == json.dumps(json.loads(text))
    cut = '[{"uuid": "a", "chat_messages": [{"uuid": "m1"}, {"uuid": "m2"'
    with pytest.raises(json.JSONDecodeError):
        [e.assemble() for e in loader.iter_json_items(io.StringIO(cut), loader.STREAMED)]


def test_data_date_reads_a_big_conversation_in_little_memory(tmp_path: Path) -> None:
    """The memory does not grow with the size of a conversation: 4 times bigger, the same peak (within 50 %)."""
    import tracemalloc

    peaks = []
    for n in (400, 1600):
        msgs = [{"uuid": f"m{i}", "parent_message_uuid": ROOT if not i else f"m{i - 1}", "sender": "human",
                 "created_at": "2026-01-01T00:00:00Z", "content": [{"type": "text", "text": "é" * 20000}]}
                for i in range(n)]
        big = {"uuid": "big", "name": "big", "updated_at": "2026-03-04T00:00:00Z", "chat_messages": msgs}
        folder = tmp_path / str(n)
        folder.mkdir()
        (folder / "conversations.json").write_text(json.dumps([conv("a"), big], ensure_ascii=False), encoding="utf-8")
        del msgs, big
        found = classify([folder])
        tracemalloc.start()
        when = loader.data_date(found)
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        assert when == datetime(2026, 3, 4, tzinfo=timezone.utc)
    assert peaks[1] < 1.5 * peaks[0], peaks  # read whole, the peak would be about 4 times bigger


# --- Step 2 (21/11): a conversation stored line by line; the former whole form still read, moved when written --------

def test_raw_file_round_trip(tmp_path: Path) -> None:
    import random

    from claude_export_viewer.archive import read_raw_file, write_raw
    from claude_export_viewer.tree import EXTRA_KEY

    rnd = random.Random(7)
    for i in range(200):
        keys = [f"f{j}" for j in range(rnd.randint(0, 4))]
        for k in ("chat_messages", EXTRA_KEY):
            if rnd.random() < 0.8:
                keys.insert(rnd.randint(0, len(keys)), k)
        raw = {k: ([_random_value(rnd) for _ in range(rnd.randint(0, 4))]
                   if k in ("chat_messages", EXTRA_KEY) and rnd.random() < 0.9 else _random_value(rnd)) for k in keys}
        path = tmp_path / f"c{i}.jsonl.gz"
        write_raw(path, raw)
        assert json.dumps(read_raw_file(path)) == json.dumps(raw)  # same values, same order of the keys


def test_former_form_read_then_moved(tmp_path: Path) -> None:
    import gzip

    from claude_export_viewer import verify

    _imp(tmp_path, [conv("a", "v1"), conv("b", "v1")], datetime(2026, 1, 1, tzinfo=timezone.utc))
    archive = Archive(tmp_path)
    for uuid in ("a", "b"):  # the archive as written before 2026.11.21.7
        meta, raw = archive.conversations[uuid], archive.load_raw(uuid)
        new = archive.raw_path(meta)
        new.with_name(new.name.replace(".jsonl.gz", ".json.gz")).write_bytes(
            gzip.compress(json.dumps(raw, ensure_ascii=False).encode("utf-8")))
        new.unlink()
    assert Archive(tmp_path).load_raw("a")["chat_messages"][0]["content"][0]["text"] == "v1"
    assert not verify.check(tmp_path, lambda k, a: None).problems
    a2 = conv("a", "v2")
    a2["chat_messages"].append({**a2["chat_messages"][0], "uuid": "a-1", "parent_message_uuid": "a-0"})
    stats = _imp(tmp_path, [a2, conv("b", "v1")], datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert stats.updated == 1 and stats.unchanged == 1  # same hashes for the unchanged one: nothing seen as changed
    archive = Archive(tmp_path)
    assert archive.raw_file(archive.conversations["a"]).name.endswith(".jsonl.gz")  # written again: the new form
    assert archive.raw_file(archive.conversations["b"]).name.endswith(".json.gz")  # untouched: still the former one
    assert not list(archive.raw_dir.glob("a.json.gz"))


def test_stored_conversation_read_in_little_memory(tmp_path: Path) -> None:
    import tracemalloc

    from claude_export_viewer.archive import iter_raw_file, write_raw

    peaks = []
    for n in (300, 1200):
        raw = {"uuid": "big", "chat_messages": [{"uuid": f"m{i}", "text": "é" * 20000} for i in range(n)]}
        path = tmp_path / f"big{n}.jsonl.gz"
        write_raw(path, raw)
        del raw
        tracemalloc.start()
        count = sum(1 for ev in iter_raw_file(path) if ev[0] == "item")
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        assert count == n
    assert peaks[1] < 1.5 * peaks[0], peaks


def test_bad_header_is_an_unreadable_conversation(tmp_path: Path) -> None:
    import gzip

    from claude_export_viewer import verify

    _imp(tmp_path, [conv("a")], datetime(2026, 1, 1, tzinfo=timezone.utc))
    archive = Archive(tmp_path)
    archive.raw_path(archive.conversations["a"]).write_bytes(gzip.compress(b'{"cev": 99}\n'))
    said = []
    verify.check(tmp_path, lambda k, a: said.append(k))
    assert "verify.conv_unreadable" in said


# --- Step 3a (21/11): a conversation received message by message: same hash as whole, same file -----------------------

def test_spool_same_hash_and_same_conversation(tmp_path: Path, monkeypatch) -> None:
    import random

    from claude_export_viewer.archive import RawSpool, _hash, read_raw_file

    rnd = random.Random(3)
    for i in range(200):
        keys = [f"f{j}" for j in range(rnd.randint(0, 4))]
        keys.insert(rnd.randint(0, len(keys)), "chat_messages")
        raw = {k: ([_random_value(rnd) for _ in range(rnd.randint(0, 5))]
                   if k == "chat_messages" and rnd.random() < 0.9 else _random_value(rnd)) for k in keys}
        text = json.dumps([raw], ensure_ascii=False)
        monkeypatch.setattr(RawSpool, "MEMORY", rnd.choice([40, 8 << 20]))  # on the disk, in memory
        with RawSpool(tmp_path / "spool") as spool:
            for e in loader.iter_json_items(io.StringIO(text), loader.STREAMED):
                for ev in e:
                    {"field": lambda: spool.field(ev[1], ev[2]), "start": lambda: spool.start(ev[1]),
                     "item": lambda: spool.item(ev[1], ev[2])}[ev[0]]()
            assert spool.hash() == _hash(raw), raw
            spool.write(tmp_path / f"c{i}.jsonl.gz")
        assert _canon_eq(read_raw_file(tmp_path / f"c{i}.jsonl.gz"), raw)
    assert not list((tmp_path / "spool").iterdir())  # the temporary files removed


def _canon_eq(a, b) -> bool:
    return list(a) == list(b) and json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)  # same fields, same values


# --- Step 3b (21/11): the conversations read message by message, kept and left out exactly as before -----------------

def test_spools_same_as_records(tmp_path: Path, monkeypatch) -> None:
    import random

    from claude_export_viewer.archive import _hash
    from claude_export_viewer.loader import iter_conversation_spools, pop_left_out, pop_warnings
    from claude_export_viewer.models import is_empty_conversation

    def message(rnd, i):
        kind = rnd.choice(["text", "empty", "tool", "odd", "broken", "notdict"])
        if kind == "notdict":
            return rnd.choice([3, "x", None])
        blocks = {"text": [{"type": "text", "text": "bonjour \ud83d"}], "empty": [{"type": "text", "text": "  "}],
                  "tool": [{"type": "tool_use", "name": "t", "input": {}}], "odd": [{"type": "nouveau", "x": 1}],
                  "broken": [{"x": 1}, "texte"]}[kind]
        return {"uuid": f"m{i}", "sender": rnd.choice(["human", "assistant"]), "content": blocks,
                "created_at": rnd.choice(["2026-01-01T00:00:00Z", "pas une date", None])}

    rnd = random.Random(5)
    for case in range(40):
        convs = []
        for j in range(rnd.randint(0, 6)):
            c = {"uuid": rnd.choice([f"c{j}", f"c{j}", "c0", "", None, 7]), "name": rnd.choice(["n", None, 3]),
                 "updated_at": "2026-01-02T00:00:00Z", "chat_messages": [message(rnd, i) for i in range(rnd.randint(0, 5))]}
            convs.append(c if rnd.random() < 0.9 else rnd.choice(["pas un objet", [1, 2]]))
        folder = tmp_path / str(case)
        folder.mkdir()
        from claude_export_viewer.archive import RawSpool
        monkeypatch.setattr(RawSpool, "MEMORY", rnd.choice([40, 8 << 20]))
        jsonl = rnd.random() < 0.3 and all(isinstance(c, dict) for c in convs)
        (folder / "conversations.json").write_text(
            "\n".join(json.dumps(c) for c in convs) + "\n" if jsonl else json.dumps(convs), encoding="utf-8")
        found = classify([folder])
        pop_warnings(), pop_left_out()
        before = [(raw, convo) for raw, convo in iter_conversation_records(found.conversations)]
        w1, l1 = pop_warnings(), pop_left_out()
        after = [(spool.hash(), convo, has_text) for spool, convo, has_text in
                 iter_conversation_spools(found.conversations, tmp_path / "spools")]
        w2, l2 = pop_warnings(), pop_left_out()
        assert [c.uuid for _, c in before] == [c.uuid for _, c, _ in after]
        for (raw, c1), (h, c2, has) in zip(before, after):
            assert h == _hash(raw) and has == (not is_empty_conversation(c1))
            assert c1.model_dump(exclude={"chat_messages"}) == c2.model_dump(exclude={"chat_messages"})
        assert w1 == w2 and vars(l1) == vars(l2), (w1, w2, vars(l1), vars(l2))
    assert not list((tmp_path / "spools").iterdir())


# --- Step 3c (21/11): the main thread counted from skeletons, as from the whole conversation --------------------------

def _random_conversation(rnd, n_extra=True):
    from claude_export_viewer.tree import EXTRA_KEY, LAST_SEEN, LEGACY_REMOVED_KEY, LINEAR_PARENT

    keys = [f"m{i}" for i in range(rnd.randint(0, 8))]
    with_parents = rnd.random() < 0.7
    msgs = []
    for i, k in enumerate(keys):
        m = {"sender": rnd.choice(["human", "assistant"]), "created_at": rnd.choice(["2026-01-01", "2026-01-02", None]),
             "content": [{"type": "text", "text": rnd.choice(["", "texte", "  "])}]}
        if rnd.random() < 0.9:
            m["uuid"] = rnd.choice(keys)  # repeated keys too
        if with_parents and rnd.random() < 0.8:
            m["parent_message_uuid"] = rnd.choice(keys + [None, "inconnu"])
        msgs.append(m if rnd.random() < 0.95 else "pas un message")
    raw = {"uuid": "c", "chat_messages": msgs}
    if n_extra and rnd.random() < 0.5:
        raw[EXTRA_KEY] = [{"uuid": f"x{i}", "parent_message_uuid": rnd.choice(keys + [None]), LAST_SEEN: "2026-01-01",
                           LINEAR_PARENT: rnd.choice(keys + [None]), "content": []} for i in range(rnd.randint(0, 3))]
    if n_extra and rnd.random() < 0.2:
        raw[LEGACY_REMOVED_KEY] = [{"after": rnd.choice(keys + [None]), "export": "2025-12-01",
                                    "messages": [{"uuid": f"l{i}", "content": []} for i in range(rnd.randint(0, 2))]}]
    return raw


def test_count_main_from_skeletons() -> None:
    import random

    from claude_export_viewer.archive import visible_count
    from claude_export_viewer.tree import count_main, extra_messages, skeleton

    rnd = random.Random(11)
    for _ in range(1500):
        raw = _random_conversation(rnd)
        current = [skeleton(m) for m in raw["chat_messages"] if isinstance(m, dict)]
        extras = [skeleton(m, extra=True) for m in extra_messages(raw)]
        assert count_main(current, extras) == visible_count(raw), raw


# --- Step 3d (21/11): the merge of two versions read element by element, the same as merge_versions --------------------

def test_merge_stream_same_as_merge_versions(tmp_path: Path, monkeypatch) -> None:
    import random

    from claude_export_viewer.archive import (RawSpool, StoredConversation, _hash, merge_stream, merge_versions,
                                              read_raw_file, visible_count, write_raw)
    from claude_export_viewer.tree import EXTRA_KEY

    rnd = random.Random(13)
    for i in range(400):
        new, old = _random_conversation(rnd, n_extra=False), _random_conversation(rnd)
        if rnd.random() < 0.5:  # shared messages, so that some are known to both
            old["chat_messages"] = new["chat_messages"][: rnd.randint(0, 4)] + old["chat_messages"]
        write_raw(tmp_path / "old.jsonl.gz", old)
        stored = StoredConversation(tmp_path / "old.jsonl.gz")
        monkeypatch.setattr(RawSpool, "MEMORY", rnd.choice([40, 8 << 20]))
        with RawSpool.from_raw(tmp_path / "t", new) as spool:
            for current, other, cur_raw, other_raw in ((spool, stored, new, old), (stored, spool, old, new)):
                expected, added = merge_versions(cur_raw, other_raw, "2026-05-05")
                got = merge_stream(current, other, "2026-05-05", tmp_path / "t")
                merged = read_raw_file(got.path)
                got.path.unlink()
                assert list(merged) == list(expected) and json.dumps(merged, sort_keys=True) == json.dumps(expected, sort_keys=True)
                extras = expected.get(EXTRA_KEY) or []
                assert (got.added, got.removed_messages) == (added, len(extras))
                assert got.removed_hash == (_hash({"r": extras}) if extras else "")
                assert got.n_messages == visible_count(expected)
    assert not list((tmp_path / "t").iterdir())


# --- Step 4 (21/11): a very long conversation in several pages, the same messages as in one page ----------------------

def _long_conversation() -> dict:
    msgs, parent = [], ROOT
    for i in range(40):
        m = {"uuid": f"m{i:02d}", "parent_message_uuid": parent, "sender": "human" if i % 2 == 0 else "assistant",
             "created_at": f"2026-01-01T00:{i:02d}:00Z", "content": [{"type": "text", "text": f"message {i} " + "mot " * 60}]}
        msgs.append(m)
        parent = m["uuid"]
    # another version of the answer m11 (a branch leaving m10), older than the main one
    msgs.append({"uuid": "alt", "parent_message_uuid": "m10", "sender": "assistant", "created_at": "2026-01-01T00:10:30Z",
                 "content": [{"type": "text", "text": "autre version"}]})
    return {"uuid": "long", "name": "Très longue", "updated_at": "2026-01-02T00:00:00Z", "chat_messages": msgs}




def _page_uuids(html_text: str) -> tuple[list[str], list[str]]:
    """(the messages of the main branch, those in frames), in their order."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth, self.main, self.framed = 0, [], []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "details" and "removed-part" in (a.get("class") or ""):
                self.depth += 1
            if tag == "div" and "message " in (a.get("class") or "") + " " and a.get("data-uuid"):
                (self.framed if self.depth else self.main).append(a["data-uuid"])

        def handle_endtag(self, tag):
            if tag == "details" and self.depth:
                self.depth -= 1

    p = P()
    p.feed(html_text)
    return p.main, p.framed


def test_long_conversation_in_parts(tmp_path: Path, monkeypatch) -> None:
    from claude_export_viewer import html_builder
    from claude_export_viewer.cli import main

    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "conversations.json").write_text(json.dumps([_long_conversation()]), encoding="utf-8")
    one, cut = tmp_path / "one", tmp_path / "cut"
    main([str(tmp_path / "in"), "-o", str(one), "--date-export", "2026-01-03", "--sans-navigateur"])
    monkeypatch.setattr(html_builder, "SMALL_FILE", 0)
    monkeypatch.setattr(html_builder, "part_limits", lambda: (2000, 2500))
    main([str(tmp_path / "in"), "-o", str(cut), "--date-export", "2026-01-03", "--sans-navigateur"])
    page = Archive(cut).conversations["long"]["filename"].removesuffix(".html")
    pages = sorted((cut / "conversations").glob(page + "*.html"), key=lambda p: (len(p.name), p.name))
    assert len(pages) > 3 and (cut / "conversations" / f"{page}.parties.js").is_file()
    whole_main, whole_framed = _page_uuids((one / "conversations" / f"{page}.html").read_text(encoding="utf-8"))
    main_seq, framed = [], []
    for i, p in enumerate(pages):
        text = p.read_text(encoding="utf-8")
        m, f = _page_uuids(text)
        main_seq += m
        framed += f
        assert m[0].startswith("m") and int(m[0][1:]) % 2 == 0  # each part begins with one of your messages
        assert f"Partie {i + 1} sur {len(pages)}" in text
    assert main_seq == whole_main and framed == whole_framed == ["alt"]  # the same messages, in the same order
    part_of = json.loads((cut / "conversations" / f"{page}.parties.js").read_text(encoding="utf-8")
                         .removeprefix("window.CEV_PART_OF = ").rstrip(";\n"))
    assert part_of["alt"] == part_of["m10"]  # a branch stays with the message it leaves
    a, b = Archive(one).conversations["long"], Archive(cut).conversations["long"]
    for k in ("n_messages", "other_versions", "removed_parts", "last_message"):
        assert a.get(k) == b.get(k), k
    assert "40 messages" in pages[-1].read_text(encoding="utf-8")  # the header counts the whole conversation
    monkeypatch.undo()  # the same conversation, shown in one page again: the parts removed
    main(["-o", str(cut), "--reconstruire", "--sans-navigateur"])
    assert [p.name for p in (cut / "conversations").glob(page + "*")] == [f"{page}.html"]


def test_link_to_a_message_of_another_part(tmp_path: Path, monkeypatch, page) -> None:  # noqa: F811
    from claude_export_viewer import html_builder
    from claude_export_viewer.cli import main

    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "conversations.json").write_text(json.dumps([_long_conversation()]), encoding="utf-8")
    monkeypatch.setattr(html_builder, "SMALL_FILE", 0)
    monkeypatch.setattr(html_builder, "part_limits", lambda: (2000, 2500))
    site = tmp_path / "site"
    main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2026-01-03", "--sans-navigateur"])
    first = site / "conversations" / "long.html"
    page.goto(first.as_uri() + "#msg=m37")  # (opened as a file: the map is loaded as a script)
    page.wait_for_function("document.querySelector('.message[data-uuid=\"m37\"]') !== null", timeout=5000)
    assert page.url.endswith("#msg=m37") and ".p" in page.url.rsplit("/", 1)[1]
    assert not page.errors


def _cut_site(tmp_path: Path, monkeypatch) -> Path:
    from claude_export_viewer import html_builder
    from claude_export_viewer.cli import main

    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "conversations.json").write_text(json.dumps([_long_conversation()]), encoding="utf-8")
    monkeypatch.setattr(html_builder, "SMALL_FILE", 0)
    monkeypatch.setattr(html_builder, "part_limits", lambda: (2000, 2500))
    site = tmp_path / "site"
    main([str(tmp_path / "in"), "-o", str(site), "--date-export", "2026-01-03", "--sans-navigateur"])
    return site


def test_annotations_and_links_of_a_long_conversation(tmp_path: Path, monkeypatch) -> None:
    from claude_export_viewer import annotations, userfiles
    from claude_export_viewer.archive import MessageSource

    site = _cut_site(tmp_path, monkeypatch)
    archive = Archive(site)
    whole = annotations.change(site, {"action": "favorite", "conversation": "long", "message": "m33", "on": True},
                               archive.load_raw)
    fav_whole = annotations.load(site)["favorites"]["long"]["m33"]
    annotations.change(site, {"action": "favorite", "conversation": "long", "message": "m33", "on": False}, archive.load_raw)
    monkeypatch.setattr(MessageSource, "BIG_FILE", 0)  # the small index, as for a very long conversation
    annotations.change(site, {"action": "favorite", "conversation": "long", "message": "m33", "on": True},
                       archive.message_source)
    fav_index = annotations.load(site)["favorites"]["long"]["m33"]
    assert {k: v for k, v in fav_index.items() if k != "added"} == {k: v for k, v in fav_whole.items() if k != "added"}
    assert whole
    with pytest.raises(annotations.AnnotationError):
        annotations.change(site, {"action": "favorite", "conversation": "long", "message": "absent", "on": True},
                           archive.message_source)
    assert userfiles.links_of(archive, "long") == userfiles.links_in(archive.load_raw("long"))


def test_exports_of_a_long_conversation(tmp_path: Path, monkeypatch) -> None:
    import zipfile

    from claude_export_viewer import allexport, html_builder, office_export

    site = _cut_site(tmp_path, monkeypatch)
    archive = Archive(site)
    n = len(html_builder.plan_of(archive, "long").plan.ranges)
    md, name = office_export.archived_markdown(archive, "long", part=n - 1)
    assert name.endswith(f"(partie {n} sur {n})") and "message 39" in md and "message 0 " not in md
    md, name = office_export.archived_markdown(archive, "long", message="m20")
    assert "message 20" in md
    out = allexport.build_all(archive, site, dest=tmp_path)
    with zipfile.ZipFile(out) as z:
        parts = [x for x in z.namelist() if "partie" in x and x.endswith(".md")]
    assert len(parts) == n
    assert not list((site / "archive" / "temporaire").glob("parties-*"))  # the temporary files removed
