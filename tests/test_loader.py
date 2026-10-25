import json
import zipfile
from pathlib import Path

import pytest

from claude_export_viewer.loader import classify, iter_conversation_records, load_project_names, load_users


@pytest.fixture()
def sample_zip(tmp_path: Path) -> Path:
    """Create a minimal valid export ZIP for testing."""
    users = [{"uuid": "u1", "full_name": "Test User", "email_address": "test@test.com"}]
    projects = [
        {
            "uuid": "p1",
            "name": "Test Project",
            "description": "",
            "is_private": False,
            "is_starter_project": False,
            "prompt_template": "",
            "docs": [],
        }
    ]
    memories = [{"project_memories": {}, "account_uuid": "u1"}]
    conversations = [
        {
            "uuid": "c1",
            "name": "Test Conversation",
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
                {
                    "uuid": "m2",
                    "text": "Hi there!",
                    "content": [
                        {"type": "thinking", "thinking": "Let me respond", "summaries": []},
                        {"type": "text", "text": "Hi there!"},
                    ],
                    "sender": "assistant",
                    "attachments": [],
                    "files": [],
                },
            ],
        }
    ]

    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("users.json", json.dumps(users))
        zf.writestr("projects.json", json.dumps(projects))
        zf.writestr("memories.json", json.dumps(memories))
        zf.writestr("conversations.json", json.dumps(conversations))

    return zip_path


def conversations(found):
    return [convo for _, convo in iter_conversation_records(found.conversations)]


def test_load_export(sample_zip: Path) -> None:
    found = classify([sample_zip])
    users = load_users(found)
    assert len(users) == 1 and users[0].full_name == "Test User"
    assert list(load_project_names(found).values()) == ["Test Project"]
    convs = conversations(found)
    assert len(convs) == 1
    assert convs[0].name == "Test Conversation"
    assert len(convs[0].chat_messages) == 2


def test_load_export_nested_paths(tmp_path: Path) -> None:
    """Test loading when JSON files are in a subdirectory inside the ZIP."""
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data/users.json", json.dumps([]))
        zf.writestr("data/projects.json", json.dumps([]))
        zf.writestr("data/memories.json", json.dumps([]))
        zf.writestr("data/conversations.json", json.dumps([]))

    assert conversations(classify([zip_path])) == []


def test_load_export_missing_files(tmp_path: Path) -> None:
    """Test loading when some JSON files are missing."""
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.json", json.dumps([]))

    found = classify([zip_path])
    assert load_users(found) == [] and conversations(found) == []


def test_streaming_split_export_and_formats(tmp_path: Path) -> None:
    """New split export: several ZIPs, JSONL conversations, folder input."""
    
    convs = [{"uuid": f"c{i}", "name": f"Conv {i}", "chat_messages": [{"sender": "human", "text": "hi"}]} for i in range(5)]
    with zipfile.ZipFile(tmp_path / "conversations-000.zip", "w") as zf:
        zf.writestr("conversations-000.jsonl", "\n".join(json.dumps(c) for c in convs))
    with zipfile.ZipFile(tmp_path / "projects-000.zip", "w") as zf:
        zf.writestr("projects.json", json.dumps([{"uuid": "p1", "name": "Mon projet", "docs": [{"content": "x" * 1000}]}]))
    with zipfile.ZipFile(tmp_path / "light_metadata-000.zip", "w") as zf:
        zf.writestr("users.json", json.dumps([{"uuid": "u1", "full_name": "Camille", "email_address": None}]))

    found = classify([tmp_path])
    assert [c.uuid for c in conversations(found)] == [f"c{i}" for i in range(5)]
    assert load_project_names(found) == {"p1": "Mon projet"}
    assert load_users(found)[0].full_name == "Camille"


def test_unconventional_file_name_detected(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text(json.dumps([{"uuid": "x", "chat_messages": []}]), encoding="utf-8")
    found = classify([tmp_path])
    assert [c.uuid for c in conversations(found)] == ["x"]


def test_broken_conversation_is_skipped(tmp_path: Path) -> None:
    from claude_export_viewer.loader import pop_warnings

    pop_warnings()
    (tmp_path / "conversations.json").write_text(
        json.dumps([{"uuid": "a", "chat_messages": []}, "garbage", {"uuid": "b", "chat_messages": []}])
    , encoding="utf-8")
    found = classify([tmp_path])
    assert [c.uuid for c in conversations(found)] == ["a", "b"]
    assert pop_warnings()


def test_project_written_over_several_lines(tmp_path: Path) -> None:
    """A pretty-printed project file is one project, not its list of documents."""
    proj = {"uuid": "p1", "name": "Mon projet", "docs": [{"uuid": "d1", "filename": "a.txt", "content": "x"}]}
    with zipfile.ZipFile(tmp_path / "projects-000.zip", "w") as zf:
        zf.writestr("projects/p1.json", json.dumps(proj, indent=2))
        zf.writestr("projects/p2.json", json.dumps({"uuid": "p2", "name": "Sur une ligne", "docs": [{"uuid": "d2"}]}))
    assert load_project_names(classify([tmp_path])) == {"p1": "Mon projet", "p2": "Sur une ligne"}


def test_list_wrapped_in_an_object_over_several_lines(tmp_path: Path) -> None:
    (tmp_path / "conversations.json").write_text(json.dumps({"conversations": [{"uuid": "w1"}, {"uuid": "w2"}]}, indent=2), encoding="utf-8")
    assert [c.uuid for c in conversations(classify([tmp_path]))] == ["w1", "w2"]


def test_unreadable_unknown_file_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text(json.dumps([{"uuid": "x", "chat_messages": []}]), encoding="utf-8")
    (tmp_path / "zzz.json").write_text("{ pas du JSON", encoding="utf-8")
    assert [c.uuid for c in conversations(classify([tmp_path]))] == ["x"]
