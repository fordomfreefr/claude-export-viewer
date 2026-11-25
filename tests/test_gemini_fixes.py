"""Security fixes after the audit by Gemini and CodeQL (25/11, AF-f3)."""

from __future__ import annotations

import email.message
import gzip
import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from claude_export_viewer import archive, cdn_cache, extras, system
from claude_export_viewer.server import make_server

from .test_admin import token
from .test_attachments import _data, post
from .helpers import build_site
from .test_extras import ART, _export

SRC = Path(__file__).resolve().parents[1] / "src"


# --- Python 3.11, the version announced: every module must at least compile there ------------------------------------


@pytest.mark.skipif(not shutil.which("python3.11"), reason="Python 3.11 absent")
def test_sources_compile_under_python_311(tmp_path: Path) -> None:
    files = [str(p) for p in sorted((SRC / "claude_export_viewer").rglob("*.py"))]
    code = "import sys\nfor f in sys.argv[1:]:\n    compile(open(f, encoding='utf-8').read(), f, 'exec')\n"
    r = subprocess.run(["python3.11", "-I", "-c", code, *files], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr


# --- a damaged line of a conversation is always a ValueError ----------------------------------------------------------


def _lines(path: Path, lines: list[str], cut: int | None = None) -> Path:
    data = gzip.compress("".join(line + "\n" for line in lines).encode("utf-8"))
    path.write_bytes(data[:cut] if cut else data)
    return path


@pytest.mark.parametrize("bad", ["12", '["chat_messages", 1, 2]', "{", '["inconnue", {}]', '[["x"], {}]',
                                 '["name", {}]', "null"])
def test_damaged_line_is_value_error(tmp_path: Path, bad: str) -> None:
    head = json.dumps({"cev": archive.RAW_FORMAT, "meta": {"uuid": "c", "name": "N", "chat_messages": []}})
    path = _lines(tmp_path / ("c" + archive.RAW_SUFFIX), [head, '["chat_messages", {"uuid": "m"}]', bad])
    with pytest.raises(ValueError):
        archive.read_raw_file(path)


def test_cut_gzip_is_value_error(tmp_path: Path) -> None:
    head = json.dumps({"cev": archive.RAW_FORMAT, "meta": {"uuid": "c", "chat_messages": []}})
    good = [head] + [json.dumps(["chat_messages", {"uuid": f"m{i}", "text": "x" * 50}]) for i in range(200)]
    whole = _lines(tmp_path / ("a" + archive.RAW_SUFFIX), good)
    assert len(archive.read_raw_file(whole)["chat_messages"]) == 200
    cut = _lines(tmp_path / ("b" + archive.RAW_SUFFIX), good, cut=len(whole.read_bytes()) - 30)
    with pytest.raises(ValueError):
        archive.read_raw_file(cut)


# --- artifacts: JSON size bounded, final path checked -----------------------------------------------------------------


def test_huge_artifact_json_not_read(tmp_path: Path, monkeypatch) -> None:
    _export(tmp_path, "2026-10-22", "profil")
    assert [a.id for a in extras.artifacts(tmp_path)] == [ART]
    monkeypatch.setattr(extras, "MAX_META", 100)
    assert extras.artifacts(tmp_path) == []


def test_extract_checks_final_path(tmp_path: Path, monkeypatch) -> None:
    _export(tmp_path, "2026-10-22", "profil")
    monkeypatch.setattr(extras, "_safe_path", lambda p: True)  # the first defence fails: the second one holds
    with pytest.raises(ValueError):
        extras.extract(tmp_path, ART, "v2")
    assert not (tmp_path / extras.FOLDER / extras.ARTIFACTS / ART / "evil").exists()
    assert not list((tmp_path / extras.FOLDER / extras.ARTIFACTS / ART).glob("*"))


# --- libraries of the Internet: never a local or private address (CodeQL, SSRF) ---------------------------------------


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.1.2.3", "192.168.1.1", "172.16.0.1", "[::1]",
                                  "169.254.169.254", "100.64.0.1", "0.0.0.0", "2130706433", "[fd00::1]", "", None])
def test_local_addresses_refused(host) -> None:
    assert not cdn_cache.public_host(host)
    if host:
        with pytest.raises(OSError):
            cdn_cache.open_https(f"https://{host}/lib.js", 1)


def test_public_literal_address_accepted() -> None:
    assert cdn_cache.public_host("8.8.8.8") and cdn_cache.public_host("[2606:4700::1111]")


def test_redirection_to_local_address_refused() -> None:
    req, headers = urllib.request.Request("https://cdn.example/lib.js"), email.message.Message()
    for newurl in ("https://127.0.0.1/x", "https://192.168.0.10/x", "https://localhost/x"):
        with pytest.raises(urllib.error.HTTPError):
            cdn_cache._Redirects(None).redirect_request(req, None, 302, "Found", headers, newurl)
    # esm.sh keeps its own rule (that site only)
    assert cdn_cache._Redirects("esm.sh").redirect_request(req, None, 302, "Found", headers,
                                                           "https://esm.sh/x").full_url == "https://esm.sh/x"


def test_get_pip_through_open_https(monkeypatch, tmp_path: Path) -> None:
    from claude_export_viewer import speech
    seen: list[tuple] = []

    def fake(url, timeout, host=None):
        seen.append((url, host))
        raise OSError("hors ligne")

    monkeypatch.setattr(cdn_cache, "open_https", fake)
    monkeypatch.setattr(speech, "_run", lambda cmd: None)
    with pytest.raises(speech.SpeechError):
        speech._venv(tmp_path / "env")
    assert seen == [(speech.GET_PIP, "bootstrap.pypa.io")]


# --- a document that could run: its folder is opened, never the file --------------------------------------------------


def test_runnable_attachment_opens_its_folder(tmp_path: Path, monkeypatch) -> None:
    assert system.runnable(Path("a/Lancer.SH")) and system.runnable(Path("x.desktop"))
    assert not system.runnable(Path("notes.txt")) and not system.runnable(Path("README"))
    out = tmp_path / "site"
    build_site(_data({"file_name": "lancer.sh", "extracted_content": "rm -rf ~"},
                     {"file_name": "a.txt", "extracted_content": "x"}), out)
    opened: list[Path] = []
    monkeypatch.setattr(system, "open_file", opened.append)
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        tok = token(server)
        status, answer = post(server, json.dumps({"path": "attachments/c1/lancer.sh"}), tok)
        assert status == 200 and json.loads(answer)["folder"] is True
        assert opened == [(out / "attachments/c1").resolve()]
        status, answer = post(server, json.dumps({"path": "attachments/c1/a.txt"}), tok)
        assert status == 200 and json.loads(answer)["folder"] is False
        assert opened[-1] == (out / "attachments/c1/a.txt").resolve()
    finally:
        server.shutdown()
        server.server_close()
