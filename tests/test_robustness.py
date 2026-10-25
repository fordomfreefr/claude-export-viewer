"""Robustness: what used to break, or to do more than asked, on unusual data."""

import gzip
import re
import json
import subprocess
import zipfile
from pathlib import Path

from claude_export_viewer import office_export, tree
from claude_export_viewer.cli import main
from claude_export_viewer.office_export import prepare_for_pandoc
from claude_export_viewer.renderer import render_markdown

ROOT = "00000000-0000-4000-8000-000000000000"


def site_with(tmp: Path, convs: list[dict]) -> Path:
    z = tmp / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(convs))
    out = tmp / "site"
    main([str(z), "-o", str(out), "--date-export", "2026-10-20"])
    return out


def conv(uuid: str, text: str = "Bonjour") -> dict:
    return {"uuid": uuid, "name": f"Conv {uuid}", "chat_messages": [
        {"uuid": uuid + "m", "parent_message_uuid": ROOT, "sender": "human", "content": [{"type": "text", "text": text}]}]}


def test_tree_items_are_distinct_even_when_identical() -> None:
    a = tree.Item("k", None, "", 0, None, {"x": 1})
    b = tree.Item("k", None, "", 0, None, {"x": 1})
    assert a != b and b not in [a]


def test_images_never_make_pandoc_read_a_file_or_the_network() -> None:
    md = "Voir ![schéma](/home/moi/secret.png) et ![web](https://exemple.fr/a.png)\n\n`![code](x)`\n\n```\n![bloc](y)\n```\n"
    out = prepare_for_pandoc(md)
    assert "![" not in out.replace("`![code](x)`", "").replace("![bloc](y)", "")
    assert "[Image : schéma](/home/moi/secret.png)" in out
    assert "`![code](x)`" in out and "![bloc](y)" in out  # code is left as written


def test_pandoc_timeout_is_a_clear_error() -> None:
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 300)

    saved = office_export.pandoc_path, subprocess.run
    office_export.pandoc_path, subprocess.run = (lambda: "/usr/bin/pandoc"), slow
    try:
        office_export.run_pandoc("# x", "odt")
    except RuntimeError as exc:
        assert "5 minutes" in str(exc)
    else:
        raise AssertionError("should have failed")
    finally:
        office_export.pandoc_path, subprocess.run = saved


def test_one_unreadable_conversation_does_not_stop_the_site(tmp_path: Path, capsys) -> None:
    out = site_with(tmp_path, [conv("a"), conv("b")])
    # archived copy of "a" replaced by valid JSON of the wrong shape
    (out / "archive" / "conversations" / "a.json.gz").write_bytes(gzip.compress(b"[1, 2]"))
    capsys.readouterr()
    main(["-o", str(out), "--reconstruire"])
    printed = capsys.readouterr().out
    assert "conversation a.html non générée" in printed and "1 conversation non générée" in printed
    assert "1 page générée" in printed  # b was regenerated
    assert "Conv b" in (out / "index.html").read_text(encoding="utf-8")


def test_damaged_archive_state_gives_a_clear_message(tmp_path: Path, capsys) -> None:
    out = site_with(tmp_path, [conv("a")])
    (out / "archive" / "etat.json").write_text("{ abîmé", encoding="utf-8")
    try:
        main(["-o", str(out)])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("should have stopped")
    assert "illisible" in capsys.readouterr().err


def test_code_without_language_is_plain_text() -> None:
    out = render_markdown("```\n#!/usr/bin/env python3\nimport os\nprint(os.name)\n```")
    assert "import os" in out and "<span" not in out.split("<pre")[1]


def test_job_poll_with_a_bad_parameter(tmp_path: Path) -> None:
    import http.client
    import threading

    from claude_export_viewer.server import make_server

    out = site_with(tmp_path, [conv("a")])
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        host = {"Host": f"127.0.0.1:{port}"}
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/__cev__/token", headers=host)
        tok = json.loads(c.getresponse().read())["token"]
        c.request("GET", "/__cev__/job?since=abc", headers={**host, "X-CEV-Token": tok})
        r = c.getresponse()
        r.read()
        assert r.status == 200
    finally:
        server.shutdown()


def test_markdown_images_are_links_not_loaded() -> None:
    out = render_markdown("Voir ![schéma](https://exemple.fr/a.png) et ![](/etc/hostname)")
    assert "<img" not in out
    text = re.sub(r"<[^>]+>", "", out)
    assert '<a href="https://exemple.fr/a.png"' in out and "[Image : schéma]" in text
    assert "[Image : /etc/hostname]" in text
