"""The downloads folder set by the user (archive/settings.json): module, command line, server, import."""

import json
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_export_viewer import fetch, settings
from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server, import_job, Job, ServerContext

from .test_admin import PROGRAM, conv, request, run_job, token


@pytest.fixture
def system_dl(tmp_path: Path, monkeypatch) -> Path:
    """A fake downloads folder of the system (the real one must not be searched)."""
    folder = tmp_path / "Downloads"
    folder.mkdir()
    monkeypatch.setattr(fetch, "user_download_dirs", lambda: [folder])
    return folder


def write_manifest(folder: Path, age_hours: float, zip_name: str = "conversations-000.zip") -> Path:
    created = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    path = folder / f"manifest-{age_hours}.json"
    path.write_text(json.dumps({"created_at": created.isoformat(), "data_files": [
        {"category": "conversations", "filename": zip_name, "export_url": "https://claude.ai/x"}]}), encoding="utf-8")
    return path


# --- module --------------------------------------------------------------------


def test_set_reset_and_search_order(tmp_path: Path, system_dl: Path) -> None:
    site = tmp_path / "site"
    usb = tmp_path / "clé USB"
    usb.mkdir()
    assert settings.downloads_folder(site) is None
    assert settings.search_folders(site) == [system_dl]

    assert settings.set_downloads_folder(site, f"  {usb}  ") == usb.resolve()
    assert json.loads((site / "archive" / "settings.json").read_text(encoding="utf-8")) == {"downloads": str(usb.resolve())}
    assert settings.search_folders(site) == [usb.resolve(), system_dl]  # the chosen folder first

    # the same folder as the system's is not searched twice
    settings.set_downloads_folder(site, str(system_dl))
    assert settings.search_folders(site) == [system_dl.resolve()]

    assert settings.set_downloads_folder(site, "") is None
    assert settings.load(site) == {}
    assert settings.search_folders(site) == [system_dl]


def test_bad_folder_is_refused_and_nothing_changes(tmp_path: Path, system_dl: Path) -> None:
    site = tmp_path / "site"
    usb = tmp_path / "usb"
    usb.mkdir()
    settings.set_downloads_folder(site, str(usb))
    a_file = tmp_path / "file.txt"
    a_file.write_text("x", encoding="utf-8")
    for bad in (str(tmp_path / "missing"), str(a_file)):
        with pytest.raises(ValueError):
            settings.set_downloads_folder(site, bad)
        assert settings.downloads_folder(site) == usb.resolve()


def test_removed_folder_or_broken_file_falls_back_to_the_system(tmp_path: Path, system_dl: Path) -> None:
    site = tmp_path / "site"
    usb = tmp_path / "usb"
    usb.mkdir()
    settings.set_downloads_folder(site, str(usb))
    usb.rmdir()  # USB key unplugged
    assert settings.downloads_folder(site) is None
    assert settings.search_folders(site) == [system_dl]
    (site / "archive" / "settings.json").write_text("{not json", encoding="utf-8")
    assert settings.load(site) == {}
    (site / "archive" / "settings.json").write_text('["a list"]', encoding="utf-8")
    assert settings.load(site) == {}


def test_tilde_is_expanded(tmp_path: Path, system_dl: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Mes fichiers").mkdir()
    assert settings.set_downloads_folder(tmp_path / "site", "~/Mes fichiers") == (tmp_path / "Mes fichiers").resolve()


# --- command line --------------------------------------------------------------


def test_command_line_option(tmp_path: Path, system_dl: Path, capsys) -> None:
    site = tmp_path / "site"
    usb = tmp_path / "usb"
    usb.mkdir()
    main(["--telechargements", str(usb), "-o", str(site)])
    assert f"Dossier des téléchargements retenu : {usb.resolve()}" in capsys.readouterr().out
    assert settings.downloads_folder(site) == usb.resolve()

    with pytest.raises(SystemExit) as exc:
        main(["--downloads", str(tmp_path / "missing"), "-o", str(site)])
    assert exc.value.code == 1
    assert "Ce dossier n'existe pas" in capsys.readouterr().err
    assert settings.downloads_folder(site) == usb.resolve()

    main(["--telechargements", "", "-o", str(site)])
    assert f"retour au dossier du système ({system_dl})" in capsys.readouterr().out
    assert settings.downloads_folder(site) is None


# --- server ----------------------------------------------------------------------


def start(tmp_path: Path):
    z = tmp_path / "first.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv("c1", "premier")]))
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-10-20"])
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")  # real search folders
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return site, server


def post(server, body: bytes, tok: str | None):
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
    if tok:
        headers["X-CEV-Token"] = tok
    port = server.server_address[1]
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request("POST", "/__cev__/settings", body=body, headers={"Host": f"127.0.0.1:{port}", **headers})
    r = c.getresponse()
    out = r.status, r.read().decode("utf-8")
    c.close()
    return out


def test_settings_endpoints(tmp_path: Path, system_dl: Path) -> None:
    site, server = start(tmp_path)
    usb = tmp_path / "usb"
    usb.mkdir()
    try:
        assert request(server, "GET", "/__cev__/settings")[0] == 403
        assert post(server, json.dumps({"downloads": str(usb)}).encode(), None)[0] == 403
        assert settings.downloads_folder(site) is None  # refused: nothing written

        tok = token(server)
        status, body = request(server, "GET", "/__cev__/settings", {"X-CEV-Token": tok})
        assert status == 200 and json.loads(body) == {"downloads": "", "system": str(system_dl),
                                            "file_folders": [str(system_dl)], "file_folders_set": False}

        status, body = post(server, json.dumps({"downloads": str(usb)}).encode(), tok)
        assert status == 200 and json.loads(body) == {"downloads": str(usb.resolve())}
        assert json.loads(request(server, "GET", "/__cev__/settings", {"X-CEV-Token": tok})[1])["downloads"] == str(usb.resolve())

        status, body = post(server, json.dumps({"downloads": str(tmp_path / "missing")}).encode(), tok)
        assert status == 400 and body == f"Ce dossier n'existe pas : {tmp_path / 'missing'}"
        for bad in (b"{not json", b'{"downloads": 3}', b"[1]", b"\xff\xfe"):
            assert post(server, bad, tok) == (400, "Requête invalide."), bad
        assert settings.downloads_folder(site) == usb.resolve()  # unchanged by the refused requests

        assert post(server, b'{"downloads": ""}', tok)[0] == 200
        assert settings.downloads_folder(site) is None
    finally:
        server.shutdown()


def test_import_button_searches_the_chosen_folder(tmp_path: Path, system_dl: Path) -> None:
    site, server = start(tmp_path)
    usb = tmp_path / "usb"
    usb.mkdir()
    try:
        # counter-check: with the manifest on the USB key only, the system folder alone finds nothing
        write_manifest(usb, age_hours=1)
        with zipfile.ZipFile(usb / "conversations-000.zip", "w") as f:
            f.writestr("conversations.json", json.dumps([conv("c1", "premier"), conv("c2", "de la clé")]))
        state = run_job(server, "/__cev__/import")
        assert state["ok"] is False and state["lines"][0] == f"Aucun manifeste trouvé dans {system_dl}."

        assert post(server, json.dumps({"downloads": str(usb)}).encode(), token(server))[0] == 200
        state = run_job(server, "/__cev__/import")
        out = "\n".join(state["lines"])
        assert state["ok"] is True, out
        assert (site / "conversations" / "c2.html").is_file()
    finally:
        server.shutdown()


def test_most_recent_manifest_wins_whatever_its_folder(tmp_path: Path, system_dl: Path, monkeypatch) -> None:
    usb = tmp_path / "usb"
    usb.mkdir()
    seen = []
    monkeypatch.setattr("claude_export_viewer.server.run_streaming", lambda cmd, job: seen.append(cmd[3]) or 0)
    ctx = ServerContext(tmp_path / "site", PROGRAM / "claude-export-viewer.py", None)
    ctx.downloads = lambda: [usb, system_dl]
    for newer, older in ((system_dl, usb), (usb, system_dl)):
        for f in (usb, system_dl):
            for m in f.glob("manifest-*.json"):
                m.unlink()
        write_manifest(newer, age_hours=1)
        write_manifest(older, age_hours=5)
        import_job(Job("import", "fr"), ctx)
        assert seen[-1] == str(newer)
