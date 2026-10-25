"""Export to .odt / .docx (Pandoc), command line and local server, with a fake pandoc."""

import json
import os
import stat
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from claude_export_viewer import office_export
from claude_export_viewer.cli import main
from claude_export_viewer.office_export import find_conversations, prepare_for_pandoc

ROOT = "00000000-0000-4000-8000-000000000000"

FAKE_PANDOC = r'''#!PYTHON
import sys
args = sys.argv[1:]
src = sys.stdin.buffer.read()
out = args[args.index("-o") + 1]
fmt = args[args.index("-t") + 1]
frm = args[args.index("-f") + 1]
open(out, "wb").write(b"FAKE-" + fmt.encode() + b"|" + frm.encode() + b"|" + src)
if b"\\unsupported" in src:
    sys.stderr.write("[WARNING] Could not convert TeX math \\unsupported, rendering as TeX\n")
'''


def install_fake_pandoc(tmp: Path) -> str:
    bindir = tmp / "bin"
    bindir.mkdir()
    exe = bindir / "pandoc"
    exe.write_text(FAKE_PANDOC.replace("PYTHON", sys.executable), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bindir}{os.pathsep}{old}"
    return old


def build(tmp: Path, convs: list[dict]) -> Path:
    z = tmp / "c.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(convs))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-23"])
    return site


def conv(uuid: str, name: str, text: str = "Bonjour $\\alpha$") -> dict:
    return {"uuid": uuid, "name": name, "created_at": "2026-10-23T08:00:00Z",
            "chat_messages": [{"uuid": uuid + "m", "parent_message_uuid": ROOT, "sender": "human",
                               "created_at": "2026-10-23T08:00:00Z", "content": [{"type": "text", "text": text}]}]}


# --- formula preparation -------------------------------------------------


def test_nested_text_commands_are_split_for_pandoc() -> None:
    # the four formulas Pandoc 3.7 could not convert in a real export
    src = r"$$\varphi \text{ a un \textbf{maximum local} en } x = 0$$"
    assert prepare_for_pandoc(src) == r"$$\varphi \text{ a un }\textbf{maximum local}\text{ en } x = 0$$"
    boxed = r"\boxed{\hat\alpha(z) \text{ a un \textbf{maximum} en } z = 0, \text{ de valeur } \alpha}"
    assert prepare_for_pandoc(boxed) == (
        r"\boxed{\hat\alpha(z) \text{ a un }\textbf{maximum}\text{ en } z = 0, \text{ de valeur } \alpha}")
    assert prepare_for_pandoc(r"\text{ \textbf{maximum} en }") == r"\text{ }\textbf{maximum}\text{ en }"
    assert prepare_for_pandoc(r"$\text{simple}$") == r"$\text{simple}$"


def test_code_blocks_are_left_untouched() -> None:
    code = "```python\ns = r'\\text{ a \\textbf{b} }'\n```"
    assert prepare_for_pandoc(code) == code
    quoted = "> ```\n> \\text{ a \\textbf{b} }\n> ```"
    assert prepare_for_pandoc(quoted) == quoted


# --- finding a conversation ------------------------------------------------


def test_find_by_identifier_page_name_or_title(tmp_path: Path) -> None:
    from claude_export_viewer.archive import Archive

    site = build(tmp_path, [conv("a1", "Loi normale et ratio"), conv("b2", "Loi normale : estimation"),
                            conv("c3", "Théorème de Pythagore")])
    archive = Archive(site)
    assert [u for u, _ in find_conversations(archive, "c3")] == ["c3"]
    assert [u for u, _ in find_conversations(archive, "pythagore")] == ["c3"]
    assert sorted(u for u, _ in find_conversations(archive, "LOI NORMALE")) == ["a1", "b2"]
    assert find_conversations(archive, "introuvable") == []


# --- command line (A) ------------------------------------------------------


def test_command_exports_odt_and_docx_through_pandoc(tmp_path: Path, capsys) -> None:
    site = build(tmp_path, [conv("c3", "Théorème de Pythagore", "Formule $\\text{a \\textbf{b} c}$ et $\\unsupported$")])
    old = install_fake_pandoc(tmp_path)
    try:
        out = tmp_path / "exports"
        main(["-o", str(site), "--odt", "pythagore", "--dossier-export", str(out)])
        main(["-o", str(site), "--docx", "c3", "--dossier-export", str(out)])
    finally:
        os.environ["PATH"] = old
    odt = out / "2026-10-23 Théorème de Pythagore.odt"
    docx = out / "2026-10-23 Théorème de Pythagore.docx"
    assert odt.is_file() and docx.is_file()
    content = odt.read_bytes()
    assert content.startswith(b"FAKE-odt|markdown+tex_math_dollars+tex_math_single_backslash|# Th")
    assert "\\text{a }\\textbf{b}\\text{ c}".encode() in content  # prepared for pandoc
    assert docx.read_bytes().startswith(b"FAKE-docx|")
    printed = capsys.readouterr().out
    assert "exportée :" in printed and "1 formule n'a pas pu être convertie" in printed


def test_command_lists_ambiguous_matches(tmp_path: Path, capsys) -> None:
    site = build(tmp_path, [conv("a1", "Loi normale A"), conv("b2", "Loi normale B")])
    try:
        main(["-o", str(site), "--odt", "normale"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("should have stopped")
    err = capsys.readouterr().err
    assert "Plusieurs conversations" in err and "a1" in err and "b2" in err


def test_command_without_pandoc_explains(tmp_path: Path, capsys) -> None:
    site = build(tmp_path, [conv("c3", "Pythagore")])
    saved = office_export.pandoc_path
    office_export.pandoc_path = lambda: None
    try:
        main(["-o", str(site), "--odt", "c3"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("should have stopped")
    finally:
        office_export.pandoc_path = saved
    assert "sudo apt install pandoc" in capsys.readouterr().err


def test_pages_show_the_command_to_copy(tmp_path: Path) -> None:
    site = build(tmp_path, [conv("c3", "Pythagore")])
    page = (site / "conversations" / "c3.html").read_text(encoding="utf-8")
    assert 'data-key="c3"' in page
    assert "--odt c3" in page and "--docx c3" in page
    assert f"-o {site.resolve()}" in page


# --- local server (B) ------------------------------------------------------


def start_server(site: Path):
    from claude_export_viewer.server import make_server

    server = make_server(site, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_server_pages_exports_and_refusals(tmp_path: Path) -> None:
    site = build(tmp_path, [conv("c3", "Théorème de Pythagore")])
    server, base = start_server(site)
    old = install_fake_pandoc(tmp_path)
    try:
        status, _, body = get(base + "/index.html")
        assert status == 200 and b"Pythagore" in body
        assert get(base + "/archive/etat.json")[0] == 403  # the raw archive is not served
        status, headers, body = get(base + "/export/c3.odt")
        assert status == 200
        assert headers["Content-Type"] == "application/vnd.oasis.opendocument.text"
        assert "filename*=UTF-8''2026-10-23%20Th%C3%A9or%C3%A8me%20de%20Pythagore.odt" in headers["Content-Disposition"]
        assert body.startswith(b"FAKE-odt|")
        status, headers, body = get(base + "/export/c3.md")
        assert status == 200 and body.startswith("# Théorème de Pythagore".encode())
        assert get(base + "/export/inconnue.odt")[0] == 404
        assert get(base + "/export/..%2F..%2Fetc%2Fpasswd.odt")[0] == 404
    finally:
        os.environ["PATH"] = old
        server.shutdown()


def test_server_without_pandoc(tmp_path: Path) -> None:
    site = build(tmp_path, [conv("c3", "Pythagore")])
    server, base = start_server(site)
    saved = office_export.pandoc_path
    office_export.pandoc_path = lambda: None
    try:
        status, _, body = get(base + "/export/c3.docx")
        assert status == 503 and "sudo apt install pandoc" in body.decode()
    finally:
        office_export.pandoc_path = saved
        server.shutdown()


def test_server_only_listens_locally(tmp_path: Path) -> None:
    site = build(tmp_path, [conv("c3", "Pythagore")])
    server, _ = start_server(site)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.shutdown()


def test_frames_are_indented_twice_as_much_for_office(tmp_path: Path) -> None:
    from claude_export_viewer.archive import Archive

    msgs = [
        {"uuid": "q", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-10-23T08:00:00Z",
         "content": [{"type": "text", "text": "Question"}]},
        {"uuid": "r1", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-23T08:01:00Z",
         "content": [{"type": "text", "text": "Ancienne réponse"}]},
        {"uuid": "r2", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-23T08:02:00Z",
         "content": [{"type": "text", "text": "> une citation\n\nNouvelle réponse"}]},
    ]
    site = build(tmp_path, [{"uuid": "c", "name": "T", "chat_messages": msgs}])
    archive = Archive(site)
    md = office_export.convert_archived(archive, "c", "md").data.decode()
    assert "\n> *Autre version" in md and "\n> Ancienne réponse" in md
    office_md, _ = office_export.archived_markdown(archive, "c", office_export.OFFICE_FRAME_LEVELS)
    assert "\n> > *Autre version" in office_md and "\n> > Ancienne réponse" in office_md
    assert "\n> une citation" in office_md  # quotes written in messages are not doubled


def test_main_thread_only_by_command_and_by_server(tmp_path: Path, capsys) -> None:
    msgs = [
        {"uuid": "q", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-10-23T08:00:00Z",
         "content": [{"type": "text", "text": "Question"}]},
        {"uuid": "r1", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-23T08:01:00Z",
         "content": [{"type": "text", "text": "Ancienne réponse"}]},
        {"uuid": "r2", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-23T08:02:00Z",
         "content": [{"type": "text", "text": "Nouvelle réponse"}]},
    ]
    site = build(tmp_path, [{"uuid": "c", "name": "Titre", "created_at": "2026-10-23T08:00:00Z",
                             "chat_messages": msgs}])
    old = install_fake_pandoc(tmp_path)
    server, base = start_server(site)
    try:
        out = tmp_path / "exports"
        main(["-o", str(site), "--odt", "c", "--dossier-export", str(out)])
        main(["-o", str(site), "--odt", "c", "--fil-principal", "--dossier-export", str(out)])
        full = (out / "2026-10-23 Titre.odt").read_bytes()
        main_only = (out / "2026-10-23 Titre (fil principal).odt").read_bytes()
        assert "Ancienne réponse".encode() in full and "Nouvelle réponse".encode() in full
        assert "Ancienne réponse".encode() not in main_only and "Nouvelle réponse".encode() in main_only

        status, headers, body = get(base + "/export/c.docx?versions=0")
        assert status == 200
        assert urllib.parse.unquote(headers["Content-Disposition"]).endswith("2026-10-23 Titre (fil principal).docx")
        assert "Ancienne réponse".encode() not in body and "Nouvelle réponse".encode() in body
        status, headers, body = get(base + "/export/c.docx")
        assert "Ancienne réponse".encode() in body
        assert urllib.parse.unquote(headers["Content-Disposition"]).endswith("2026-10-23 Titre.docx")
        status, _, body = get(base + "/export/c.md?versions=0")
        assert "Ancienne réponse".encode() not in body
    finally:
        os.environ["PATH"] = old
        server.shutdown()
