"""F1: two programs on the same archive (an import from the index and one in a terminal, a rebuild…):
one at a time, through a lock the system releases even when the program is killed."""

import json
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

from claude_export_viewer.archive import Archive, ArchiveBusy, ArchiveLock
from claude_export_viewer.cli import main

SRC = str(Path(__file__).resolve().parent.parent / "src")
HOLD = ("import sys, time; sys.path.insert(0, sys.argv[1]);"
        "from claude_export_viewer.archive import ArchiveLock;"
        "l = ArchiveLock(sys.argv[2]).acquire(); print('pris', flush=True); time.sleep(float(sys.argv[3]))")


def holder(site: Path, seconds: float) -> subprocess.Popen:
    """Another program holding the lock for ``seconds``."""
    p = subprocess.Popen([sys.executable, "-c", HOLD, SRC, str(site), str(seconds)], stdout=subprocess.PIPE,
                         encoding="utf-8")
    assert p.stdout.readline().strip() == "pris"
    return p


def export(tmp: Path, name: str, uuid: str) -> Path:
    path = tmp / f"{name}.zip"
    msgs = [{"uuid": f"{uuid}-m", "sender": "human", "content": [{"type": "text", "text": "texte " + uuid}]}]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json", json.dumps([{"uuid": uuid, "name": uuid, "chat_messages": msgs}]))
    return path


def test_second_program_waits(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    main([str(export(tmp_path, "a", "a")), "-o", str(site)])
    capsys.readouterr()
    p = holder(site, 2)
    t0 = time.monotonic()
    main([str(export(tmp_path, "b", "b")), "-o", str(site)])
    waited = time.monotonic() - t0
    p.wait()
    assert "attente de la fin" in capsys.readouterr().out and waited > 1
    assert set(Archive(site).conversations) == {"a", "b"}


def test_lock_released_when_killed(tmp_path: Path) -> None:
    site = tmp_path / "site"
    p = holder(site, 60)
    try:
        try:
            ArchiveLock(site).acquire(wait=False)
            raise AssertionError("the lock should be taken")
        except ArchiveBusy:
            pass
    finally:
        p.kill()
        p.wait()
    ArchiveLock(site).acquire(wait=False).release()  # free again, nothing left behind


def test_two_imports_at_once_lose_nothing(tmp_path: Path) -> None:
    site = tmp_path / "site"
    main([str(export(tmp_path, "a", "a")), "-o", str(site)])
    zips = [export(tmp_path, f"x{i}", f"c{i}") for i in range(3)]
    errors: list[BaseException] = []

    def run(z: Path) -> None:
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]);"
                            "from claude_export_viewer.cli import main; main(sys.argv[2:])", SRC, str(z),
                            "-o", str(site)], capture_output=True, encoding="utf-8")
        if r.returncode:
            errors.append(RuntimeError(r.stderr))

    threads = [threading.Thread(target=run, args=(z,)) for z in zips]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert not errors
    assert set(Archive(site).conversations) == {"a", "c0", "c1", "c2"}


def test_server_answers_busy(tmp_path: Path) -> None:
    from tests.test_userfiles import _post, token  # noqa: PLC0415
    from claude_export_viewer.server import make_server
    site = tmp_path / "site"
    main([str(export(tmp_path, "a", "a")), "-o", str(site)])
    server = make_server(site, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    p = holder(site, 30)
    try:
        tok = token(server)
        body = {"page": "a", "link": "a-m/file/x.png", "action": "auto"}
        assert _post(server, "/__cev__/link", body, tok)[0] == 409
        assert _post(server, "/__cev__/orphans", {}, tok)[0] == 409
    finally:
        p.kill()
        p.wait()
        server.shutdown()
        server.server_close()
