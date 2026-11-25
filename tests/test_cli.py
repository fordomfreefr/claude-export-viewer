import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

LAUNCHER = str(Path(__file__).resolve().parent.parent / "claude-export-viewer.py")


@pytest.fixture()
def sample_zip(tmp_path: Path) -> Path:
    conversations = [
        {
            "uuid": "c1",
            "name": "CLI Test",
            "summary": "",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "account": {"uuid": "u1"},
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Hello",
                    "content": [{"type": "text", "text": "Hello"}],
                    "sender": "human",
                    "attachments": [],
                    "files": [],
                },
            ],
        }
    ]

    zip_path = tmp_path / "test-export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("users.json", json.dumps([]))
        zf.writestr("projects.json", json.dumps([]))
        zf.writestr("memories.json", json.dumps([]))
        zf.writestr("conversations.json", json.dumps(conversations))

    return zip_path


def test_cli_generates_site(sample_zip: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, LAUNCHER, str(sample_zip), "-o", str(output_dir)],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0
    assert "1 conversation " in result.stdout
    assert (output_dir / "index.html").exists()
    assert (output_dir / "conversations" / "c1.html").exists()


def test_cli_missing_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, LAUNCHER, str(tmp_path / "nonexistent.zip")],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 1
    assert "introuvable" in result.stderr


def test_cli_reports_left_out(sample_zip: Path, tmp_path: Path) -> None:
    """AE-f2: one line at the end of the import says what CEV did not take, and why."""
    convo = json.loads(zipfile.ZipFile(sample_zip).read("conversations.json"))[0]
    convo["chat_messages"][0]["content"] += [{"type": "web_search_x", "text": "?"}, "pas un bloc"]
    zip_path = tmp_path / "export2.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.json", json.dumps([convo, convo]))
        zf.writestr("memories.json", json.dumps([]))
        zf.writestr("design_chats/0123456789abcdef0123.json", json.dumps({}))
        zf.writestr("design_chats/fedcba9876543210fedc.json", json.dumps({}))
    run = lambda z: subprocess.run(  # noqa: E731
        [sys.executable, LAUNCHER, str(z), "-o", str(tmp_path / "site")],
        capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = run(zip_path).stdout
    line = next(x for x in out.splitlines() if "Laissé de côté" in x)
    assert line.strip() == (
        "Laissé de côté : fichiers non utilisés par CEV (design_chats ×2, memories) ; "
        "1 conversation en double, la seconde ignorée ; "
        "blocs d'un type inconnu de CEV, montrés tels quels (web_search_x) ; 1 bloc illisible ignoré.")
    assert "Laissé de côté : rien." in run(_plain(tmp_path)).stdout


def _plain(tmp_path: Path) -> Path:
    z = tmp_path / "plain.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("conversations.json", json.dumps([{
            "uuid": "c9", "name": "x", "chat_messages": [
                {"uuid": "m9", "sender": "human", "content": [{"type": "text", "text": "Bonjour"}]}]}]))
    return z


def test_left_out_lists_manifest_categories(capsys: pytest.CaptureFixture[str]) -> None:
    from claude_export_viewer import cli
    from claude_export_viewer.loader import ExportSources

    cli._print_left_out(ExportSources(), ["design_chats", "feedback", "memories"])
    assert capsys.readouterr().out.strip() == (
        "Laissé de côté : parties de l'export gardées dans l'archive, pas encore affichées (design_chats, feedback, memories).")
