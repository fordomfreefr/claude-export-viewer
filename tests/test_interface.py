"""Index and page information: French dates, versions badge, last activity, last export, claude.ai link."""

import json
import re
import zipfile
from pathlib import Path

from claude_export_viewer import tree
from claude_export_viewer.cli import main

ROOT = "00000000-0000-4000-8000-000000000000"
UUID_A = "11111111-2222-4333-8444-555555555555"
UUID_B = "66666666-7777-4888-9999-aaaaaaaaaaaa"


def msg(uuid, parent, sender, when, text):
    return {"uuid": uuid, "parent_message_uuid": parent, "sender": sender, "created_at": when,
            "content": [{"type": "text", "text": text}]}


def conv_a(extra_retry: bool = True) -> dict:
    msgs = [msg("q", ROOT, "human", "2026-10-01T08:00:00Z", "Question"),
            msg("r1", "q", "assistant", "2026-10-01T08:01:00Z", "Première réponse")]
    if extra_retry:
        msgs.append(msg("r2", "q", "assistant", "2026-10-05T09:00:00Z", "Réponse relancée"))
    return {"uuid": UUID_A, "name": "Conversation A", "created_at": "2026-10-01T08:00:00Z",
            "updated_at": "2026-10-05T09:00:00Z", "chat_messages": msgs}


def conv_b() -> dict:
    return {"uuid": UUID_B, "name": "Conversation B", "created_at": "2026-09-01T08:00:00Z",
            "chat_messages": [msg("x", ROOT, "human", "2026-09-01T08:00:00Z", "Bonjour")]}


def export(tmp: Path, name: str, convs: list[dict]) -> Path:
    z = tmp / f"{name}.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(convs))
    return z


def site(tmp: Path) -> Path:
    out = tmp / "site"
    main([str(export(tmp, "e1", [conv_a(), conv_b()])), "-o", str(out), "--date-export", "2026-10-10"])
    main([str(export(tmp, "e2", [conv_a()])), "-o", str(out), "--date-export", "2026-10-20"])  # B deleted
    return out


def item(index: str, name: str) -> str:
    return re.search(r'<li class="conversation-item"(?:(?!</li>).)*' + name + r"(?:(?!</li>).)*</li>", index, re.S).group(0)


def test_summary_counts_versions_and_last_message() -> None:
    s = tree.summarize(tree.items_from_raw(conv_a()))
    assert (s.other_versions, s.removed_parts, s.last_message) == (1, 0, "2026-10-05T09:00:00Z")
    assert tree.summarize(tree.items_from_raw(conv_b())).other_versions == 0


def test_index_information(tmp_path: Path) -> None:
    index = (site(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert '<html lang="fr">' in index and ">Conversations Claude</span></h1>" in index
    assert "Dernier export importé : 20/10/2026" in index
    a, b = item(index, "Conversation A"), item(index, "Conversation B")
    assert "01/10/2026 &middot; dernier échange le 05/10/2026" in re.sub(r"<[^>]+>|\n\s*", "", a)
    assert '1 autre version</span>' in a and "versions-badge" not in b
    assert "dernier échange" not in b  # same day as the creation: not repeated
    assert 'data-activity="2026-10-05T09:00:00' in a
    assert 'id="result-count"' in index and 'value="activity-desc"' in index
    for go in ("top", "middle", "bottom"):
        assert f'data-go="{go}"' in index
    assert 'src="nav.js"' in index and (tmp_path / "site" / "nav.js").is_file()
    for english in ("Filter conversations", "All users", "newest", "Untitled", "Claude Conversations"):
        assert english not in index


def test_page_information(tmp_path: Path) -> None:
    out = site(tmp_path)
    page_a = next((out / "conversations").glob("1111*.html")).read_text(encoding="utf-8")
    page_b = next((out / "conversations").glob("6666*.html")).read_text(encoding="utf-8")
    assert "Toutes les conversations" in page_a
    assert re.search(r"01/10/2026 à \d\d:00", page_a)  # local time, French format
    assert f'href="https://claude.ai/chat/{UUID_A}"' in page_a
    assert "claude.ai/chat/" not in page_b  # deleted on claude.ai: no dead link
    for go in ("top", "middle", "bottom"):
        assert f'data-go="{go}"' in page_a
    assert 'src="../nav.js"' in page_a
    assert 'id="export-pdf"' in page_a and ">.pdf</button>" in page_a


def test_bad_identifier_gives_no_link(tmp_path: Path) -> None:
    out = tmp_path / "site"
    bad = {**conv_b(), "uuid": "x\" onmouseover=\"alert(1)"}
    main([str(export(tmp_path, "e", [bad])), "-o", str(out), "--date-export", "2026-10-10"])
    page = next((out / "conversations").glob("*.html")).read_text(encoding="utf-8")
    assert "claude.ai/chat/" not in page and 'onmouseover="' not in page
