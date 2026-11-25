"""Files handed over by Claude on the pages: content from the export, at the end of the message."""

import json
import re
from pathlib import Path

from claude_export_viewer import userfiles
from claude_export_viewer.archive import Archive
from claude_export_viewer.office_export import archived_markdown

from .helpers import ExportData, build_site

ROOT = "00000000-0000-4000-8000-000000000000"
OUT = "/mnt/user-data/outputs/"
CODE = "def f(x):\n    return x < 2  # <script>\n"


def use(i, name, **inp):
    return {"type": "tool_use", "id": i, "name": name, "input": inp}


def conv(*replies, uuid="c1"):
    msgs, parent = [], ROOT
    for n, blocks in enumerate(replies):
        msgs.append({"uuid": f"h{n}", "sender": "human", "parent_message_uuid": parent,
                     "created_at": f"2026-07-12T10:{n:02d}:00Z", "content": [{"type": "text", "text": "Question"}]})
        msgs.append({"uuid": f"a{n}", "sender": "assistant", "parent_message_uuid": f"h{n}",
                     "created_at": f"2026-07-12T10:{n:02d}:30Z",
                     "content": [{"type": "text", "text": f"Réponse {n}"}, *blocks]})
        parent = f"a{n}"
    return {"uuid": uuid, "name": "Fichiers", "created_at": "2026-07-12T10:00:00Z", "chat_messages": msgs}


def site_with(tmp_path: Path, raw) -> tuple[Path, str]:
    site = tmp_path / "site"
    build_site(ExportData(conversations=[raw]), site)
    page = next((site / "conversations").glob("*.html")).read_text(encoding="utf-8")
    return site, page


def messages(page: str) -> list[str]:
    """The messages of the page (the embedded Markdown left out)."""
    return re.split(r'<div class="message message-', page.split('<script type="application/json"')[0])[1:]


def test_file_shown_at_the_end_of_its_message_with_its_content(tmp_path: Path) -> None:
    raw = conv([use("t1", "create_file", path="/home/claude/f.py", file_text=CODE),
                use("t2", "bash_tool", command="cp /home/claude/f.py /mnt/user-data/outputs/"),
                use("t3", "present_files", filepaths=[OUT + "f.py"])])
    site, page = site_with(tmp_path, raw)
    reply = messages(page)[1]
    card = reply[reply.index('class="userfile created-file"'):]
    assert reply.index("Réponse 0") < reply.index("created-file")  # after the text, as on claude.ai
    assert 'title="/mnt/user-data/outputs/f.py">f.py</span>' in card
    assert "cf-ver" not in card  # one version only: no number
    assert "&lt;script&gt;" in card and "<script>" not in card.split("</details>")[0]
    assert "userfile-check" not in card  # no question: the content is certain
    copies = list((site / "files").rglob("f.py"))
    assert len(copies) == 1 and copies[0].read_text(encoding="utf-8") == CODE
    rel = copies[0].relative_to(site).as_posix()
    assert f'data-open="{rel}"' in card and f'href="../{rel}" download="f.py"' in card
    assert 'class="copy-file"' in card and 'class="attachment-content"' in card and "<details " in card
    assert " open" not in card.split("<details")[1].split(">")[0]  # folded
    assert 'class="language-python"' in card


def test_each_message_shows_its_version(tmp_path: Path) -> None:
    raw = conv([use("t1", "create_file", path=OUT + "L.bas", file_text="Sub v1()\n"),
                use("t2", "present_files", filepaths=[OUT + "L.bas"])],
               [use("u1", "bash_tool", command="cat > /mnt/user-data/outputs/L.bas << 'EOF'\nSub v2()\nEOF"),
                use("u2", "present_files", filepaths=[OUT + "L.bas"])])
    site, page = site_with(tmp_path, raw)
    first, second = messages(page)[1], messages(page)[3]
    assert "Sub v1()" in first and "Sub v2()" not in first and "version 1/2" in first
    assert "Sub v2()" in second and "Sub v1()" not in second and "version 2/2" in second
    assert sorted(p.read_text(encoding="utf-8") for p in (site / "files").rglob("L.bas")) == ["Sub v1()\n", "Sub v2()\n"]


def test_incomplete_and_absent_files(tmp_path: Path) -> None:
    raw = conv([use("t1", "create_file", path=OUT + "s.py", file_text="a = 1\n"),
                use("t2", "bash_tool", command="sed -i 's/1/2/' /mnt/user-data/outputs/s.py"),
                use("t3", "bash_tool", command="python3 gen.py > /mnt/user-data/outputs/data.csv"),
                use("t4", "present_files", filepaths=[OUT + "s.py", OUT + "data.csv"])])
    site, page = site_with(tmp_path, raw)
    reply = messages(page)[1]
    s_card = reply[reply.index('data-link="a0/created/s.py"'):reply.index('data-link="a0/created/data.csv"')]
    # changed afterwards: a link to the user's file (none found), with the last content of the export
    assert 'data-link="a0/created/s.py"' in s_card and "Aucun fichier associé" in s_card
    assert 'class="cf-warn"' in s_card and "peut-être incomplète" in s_card and '<span class="mi">1</span>' in s_card
    d_card = reply[reply.index('data-link="a0/created/data.csv"'):]
    assert 'data-link="a0/created/data.csv"' in d_card and "cf-dim" in d_card and "Aucun fichier associé" in d_card
    assert 'class="cf-link"' in d_card and "attachment-open" not in d_card.split("</div>")[0]
    assert not list((site / "files").rglob("data.csv"))
    # only the file the export lacks is looked for on the computer
    assert [(x["kind"], x["name"], x.get("partial", False)) for x in userfiles.links_in(raw)] == [
        ("created", "s.py", True), ("created", "data.csv", False)]


def test_markdown_exports_hold_the_files(tmp_path: Path) -> None:
    raw = conv([use("t1", "create_file", path=OUT + "f.py", file_text=CODE),
                use("t2", "bash_tool", command="python3 gen.py > /mnt/user-data/outputs/data.csv"),
                use("t3", "present_files", filepaths=[OUT + "f.py", OUT + "data.csv"])])
    site, page = site_with(tmp_path, raw)
    payload = re.search(r'id="cev-markdown">(.*?)</script>', page, re.S).group(1)
    md = json.loads(payload)["markdown"]
    assert "```python\n" + CODE.rstrip() + "\n```" in md
    assert "⟦cev:md.created:" in md and "⟦cev:md.created_absent:" in md
    copy = re.search(r'class="copy-msg"[^>]*data-md="([^"]*)"', messages(page)[1]).group(1)
    assert "def f(x):" in copy  # the copy of the message too
    text, _ = archived_markdown(Archive(site), "c1", lang="fr")
    assert "**Fichier : f.py**\n\n```python\n" in text
    assert "*Fichier créé par Claude : data.csv (contenu absent de l'export)*" in text


def test_page_without_files_is_unchanged(tmp_path: Path) -> None:
    _, page = site_with(tmp_path, conv([]))
    assert "created-file" not in page and "created-files" not in page


def test_copy_icon_copies_the_whole_file_in_a_browser(tmp_path: Path) -> None:
    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    raw = conv([use("t1", "create_file", path=OUT + "f.py", file_text=CODE),
                use("t2", "present_files", filepaths=[OUT + "f.py"])])
    site, _ = site_with(tmp_path, raw)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser not installed
            pytest.skip(f"Chromium unavailable: {exc}")
        pg = browser.new_context(locale="fr-FR").new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(next((site / "conversations").glob("*.html")).as_uri())
        pg.evaluate("() => { window.__copied = null; navigator.clipboard.writeText = t => {"
                    " window.__copied = t; return Promise.resolve(); }; }")
        button = pg.locator(".created-file .copy-file")
        assert button.is_visible() and not pg.locator(".created-file pre").is_visible()  # folded
        button.click()  # copies without unfolding
        pg.wait_for_function("() => window.__copied !== null")
        assert pg.evaluate("() => window.__copied") == CODE.rstrip("\n")
        assert "copied" in button.get_attribute("class") and button.get_attribute("title") == "Copié ✓"
        pg.wait_for_function("() => !document.querySelector('.copy-file').classList.contains('copied')", timeout=4000)
        assert button.get_attribute("title") == "Copier le contenu du fichier"
        pg.locator(".created-file summary").click()
        assert pg.locator(".created-file pre").is_visible()
        assert errors == []
        browser.close()
