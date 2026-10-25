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
