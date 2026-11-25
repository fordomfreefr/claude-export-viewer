"""D2 of 2026-10-29: the export in a dated ZIP with the files it names (folder "fichiers/")."""

from __future__ import annotations

import io
import shutil
import threading
import zipfile
from datetime import date
from pathlib import Path

import pytest

from claude_export_viewer import i18n, system, userfiles, zipexport
from claude_export_viewer.archive import Archive
from claude_export_viewer.server import make_server

from .helpers import ExportData, build_site
from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def _site(tmp: Path) -> Path:
    msgs = [{"uuid": "q1", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-10-20T10:00:00Z",
             "content": [{"type": "text", "text": "Voici"}],
             "attachments": [{"file_name": "notes.txt", "extracted_content": "mes notes"},
                             {"file_name": "", "file_type": "txt", "extracted_content": "texte collé ici"}],
             "files": [{"file_name": "photo.png"}]},
            {"uuid": "a1", "parent_message_uuid": "q1", "sender": "assistant", "created_at": "2026-10-20T10:01:00Z",
             "content": [{"type": "tool_use", "name": "create_file",
                          "input": {"path": "/mnt/user-data/outputs/calc.py", "file_text": "print(1)\n"}},
                         {"type": "tool_result", "name": "create_file", "content": [{"type": "text", "text": "ok"}]},
                         {"type": "tool_use", "name": "present_files",
                          "input": {"filepaths": ["/mnt/user-data/outputs/calc.py"]}},
                         {"type": "text", "text": "Fait."}]}]
    site = tmp / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai: ZIP", "chat_messages": msgs}]), site)
    # photo.png associated with a file of the computer (its copy in the site)
    copy = site / "files" / "c1" / "abc" / "photo.png"
    copy.parent.mkdir(parents=True)
    copy.write_bytes(b"PNG")
    data = userfiles.load(site)
    data["assoc"]["c1"] = {userfiles.view_key("q1", "file", "photo.png"): {"how": "user", "copy": "files/c1/abc/photo.png"}}
    userfiles.save(site, data)
    return site


def test_zip_with_files_and_links(tmp_path: Path) -> None:
    i18n.set_language("fr")
    site = _site(tmp_path)
    blob, name, _ = zipexport.build(Archive(site), site, "c1", "md")
    assert name == f"Essai ZIP_{date.today().isoformat()}.zip"
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    md = next(n for n in names if n.endswith(".md"))
    assert set(names) - {md} == {"fichiers/notes.txt", "fichiers/Texte collé.txt", "fichiers/photo.png", "fichiers/calc.py"}
    assert z.read("fichiers/photo.png") == b"PNG" and z.read("fichiers/notes.txt") == "mes notes".encode()
    assert z.read("fichiers/calc.py") == b"print(1)\n"
    text = z.read(md).decode("utf-8")
    for f in ("notes.txt", "photo.png", "calc.py"):
        assert f"[{f}](<fichiers/{f}>)" in text, f
    assert "[Texte collé](<fichiers/Texte collé.txt>)" in text
    # written in the folder chosen, without replacing an earlier ZIP
    out = tmp_path / "envois"
    out.mkdir()
    first, second = zipexport.write(blob, out, name), zipexport.write(blob, out, name)
    assert first.name == name and second.name == name[:-4] + " (2).zip"


def test_links_in_a_word_file(tmp_path: Path) -> None:
    if not shutil.which("pandoc"):
        pytest.skip("pandoc absent")
    site = _site(tmp_path)
    blob, _, _ = zipexport.build(Archive(site), site, "c1", "docx")
    z = zipfile.ZipFile(io.BytesIO(blob))
    docx = zipfile.ZipFile(io.BytesIO(z.read(next(n for n in z.namelist() if n.endswith(".docx")))))
    rels = docx.read("word/_rels/document.xml.rels").decode("utf-8")
    assert 'Target="fichiers/photo.png"' in rels and 'TargetMode="External"' in rels  # a relative link


def test_zip_box_in_the_browser(tmp_path: Path, page, monkeypatch) -> None:  # noqa: F811
    site = _site(tmp_path)
    out = tmp_path / "envois"
    out.mkdir()
    asked = []
    monkeypatch.setattr(system, "choose_folder", lambda start, title: asked.append(start) or str(out))
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        page_name = next((site / "conversations").glob("*.html")).name
        pg.goto((site / "conversations" / page_name).as_uri())
        pg.evaluate("document.getElementById('export-tab').open = true")  # (22/11: in the tab Exporter)
        assert pg.locator("#export-md").is_visible() and not pg.locator("#export-zip").is_visible()  # as a file: no ZIP
        pg.goto(base + "conversations/" + page_name)
        pg.evaluate("document.getElementById('export-tab').open = true")
        assert not pg.locator("#export-zip").is_checked()
        pg.locator("#export-zip").check()
        pg.click("#export-md")
        pg.wait_for_selector("#export-help:not([hidden])")
        assert "ZIP enregistré" in pg.inner_text("#export-help")
        assert [p.suffix for p in out.iterdir()] == [".zip"]
        assert asked == [site]  # first time: the folder of the index; then the last one chosen
        pg.click("#export-md")
        pg.wait_for_function("document.querySelector('#export-help').textContent.includes('(2).zip')")
        assert asked[1] == out
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()
