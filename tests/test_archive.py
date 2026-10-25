"""Cumulative archive: successive exports, deletions, duplicates, incremental pages."""

import json
import re
import zipfile
from pathlib import Path

from claude_export_viewer.cli import main


def conv(uuid: str, text: str = "", name: str = "", updated: str = "2026-01-01T00:00:00Z") -> dict:
    msgs = [{"uuid": f"{uuid}-m", "sender": "human", "content": [{"type": "text", "text": text}]}] if text else []
    return {"uuid": uuid, "name": name or uuid, "updated_at": updated, "chat_messages": msgs}


def export(tmp: Path, name: str, convs: list[dict]) -> Path:
    path = tmp / f"{name}.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json", json.dumps(convs))
    return path


def run(site: Path, *args: str) -> None:
    main([*args, "-o", str(site)])


def state(site: Path) -> dict:
    return json.loads((site / "archive" / "etat.json").read_text(encoding="utf-8"))


def page(site: Path, uuid: str) -> str:
    return (site / "conversations" / f"{uuid}.html").read_text(encoding="utf-8")


def test_successive_exports_deletion_and_update(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    a = export(tmp_path, "a", [conv("c1", "un"), conv("c2", "deux"), conv("c3")])
    run(site, str(a), "--date-export", "2026-09-01")
    s = state(site)
    assert set(s["conversations"]) == {"c1", "c2"}  # c3 has no text
    assert "Supprimée sur claude.ai" not in (site / "index.html").read_text(encoding="utf-8")

    # Later export: c1 modified, c2 deleted on claude.ai, c4 new
    b = export(tmp_path, "b", [conv("c1", "un modifié"), conv("c4", "quatre")])
    run(site, str(b), "--date-export", "2026-10-01")
    out = capsys.readouterr().out
    assert "1 nouvelle, 1 mise à jour, 0 inchangée" in out
    assert "1 supprimée sur claude.ai" in out

    assert "un modifié" in page(site, "c1")
    assert "deux" in page(site, "c2")  # still there
    assert "Supprimée sur claude.ai" in page(site, "c2")
    assert "absente de l'export du 01/10/2026" in page(site, "c2")
    index = (site / "index.html").read_text(encoding="utf-8")
    assert index.count('class="deleted-badge"') == 1
    assert 'id="filter-deleted"' in index
    assert "3 conversations (dont 1 supprimée sur claude.ai, conservée ici)" in re.sub(r"<[^>]+>", "", index)


def test_emptied_shell_keeps_archived_copy(tmp_path: Path) -> None:
    site = tmp_path / "site"
    run(site, str(export(tmp_path, "a", [conv("c1", "texte précieux")])), "--date-export", "2026-09-01")
    run(site, str(export(tmp_path, "b", [conv("c1")])), "--date-export", "2026-10-01")  # same uuid, emptied
    assert "texte précieux" in page(site, "c1")
    assert "Supprimée sur claude.ai" in page(site, "c1")


def test_older_export_never_overwrites_newer(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    new = export(tmp_path, "new", [conv("c1", "version récente"), conv("c2", "deux")])
    old = export(tmp_path, "old", [conv("c1", "version ancienne"), conv("c0", "seulement dans l'ancien")])
    run(site, str(new), "--date-export", "2026-10-01")
    run(site, str(old), "--date-export", "2026-08-01")
    out = capsys.readouterr().out
    assert "plus ancien" in out
    assert "version récente" in page(site, "c1")
    assert "Supprimée sur claude.ai" not in page(site, "c2")
    # c0 only existed in the old export: it was deleted before the new one
    assert "Supprimée sur claude.ai" in page(site, "c0")
    assert "absente de l'export du 01/10/2026" in page(site, "c0")


def test_conversation_reappearing_is_no_longer_deleted(tmp_path: Path) -> None:
    site = tmp_path / "site"
    run(site, str(export(tmp_path, "a", [conv("c1", "un"), conv("c2", "deux")])), "--date-export", "2026-08-01")
    run(site, str(export(tmp_path, "b", [conv("c1", "un")])), "--date-export", "2026-09-01")
    assert "Supprimée sur claude.ai" in page(site, "c2")
    run(site, str(export(tmp_path, "c", [conv("c1", "un"), conv("c2", "deux")])), "--date-export", "2026-10-01")
    assert "Supprimée sur claude.ai" not in page(site, "c2")


def test_reimporting_same_export_creates_no_duplicates(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    a = export(tmp_path, "a", [conv("c1", "un"), conv("c2", "deux")])
    run(site, str(a), "--date-export", "2026-09-01")
    run(site, str(a), "--date-export", "2026-09-01")
    out = capsys.readouterr().out
    assert "0 nouvelle, 0 mise à jour, 2 inchangées" in out
    s = state(site)
    assert len(s["exports"]) == 1 and len(s["conversations"]) == 2
    assert (site / "index.html").read_text(encoding="utf-8").count('class="conversation-item"') == 2


def test_only_changed_pages_are_regenerated(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    convs = [conv(f"c{i}", f"texte {i}") for i in range(5)]
    run(site, str(export(tmp_path, "a", convs)), "--date-export", "2026-09-01")
    capsys.readouterr()
    convs[0] = conv("c0", "texte modifié")
    run(site, str(export(tmp_path, "b", convs)), "--date-export", "2026-10-01")
    assert "1 page générée" in capsys.readouterr().out
    run(site)  # no export: just refresh the site from the archive
    assert "0 page générée" in capsys.readouterr().out
    run(site, "--reconstruire")
    assert "5 pages générées" in capsys.readouterr().out


def test_missing_page_is_regenerated(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    run(site, str(export(tmp_path, "a", [conv("c1", "un")])), "--date-export", "2026-09-01")
    (site / "conversations" / "c1.html").unlink()
    run(site)
    assert "un" in page(site, "c1")


def test_mass_disappearance_warns(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    convs = [conv(f"c{i}", f"t{i}") for i in range(20)]
    run(site, str(export(tmp_path, "a", convs)), "--date-export", "2026-09-01")
    run(site, str(export(tmp_path, "b", convs[:5])), "--date-export", "2026-10-01")  # part of the export missing
    assert "ATTENTION" in capsys.readouterr().out
    # nothing is lost: re-importing the complete export removes the marks
    run(site, str(export(tmp_path, "b2", convs)), "--date-export", "2026-10-01")
    assert "Supprimée sur claude.ai" not in (site / "index.html").read_text(encoding="utf-8")


def test_export_date_read_from_zip_and_manifest(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    path = tmp_path / "conversations-000.zip"
    with zipfile.ZipFile(path, "w") as z:
        info = zipfile.ZipInfo("conversations.json", date_time=(2026, 10, 22, 18, 20, 52))
        z.writestr(info, json.dumps([conv("c1", "un")]))
    run(site, str(path))
    assert "22/10/2026 18:20 UTC (source : archive zip)" in capsys.readouterr().out

    manifest = tmp_path / "manifest-x.json"
    manifest.write_text(json.dumps({"created_at": "2026-10-23T08:00:00+00:00", "data_files": []}), encoding="utf-8")
    run(site, str(path), str(manifest))
    assert "23/10/2026 08:00 UTC (source : manifeste fourni)" in capsys.readouterr().out


def test_archive_survives_and_rebuilds_site(tmp_path: Path) -> None:
    """The site can be rebuilt from the archive alone (e.g. after a program update)."""
    site = tmp_path / "site"
    run(site, str(export(tmp_path, "a", [conv("c1", "un $\\alpha$")])), "--date-export", "2026-09-01")
    for f in (site / "conversations").glob("*.html"):
        f.unlink()
    (site / "index.html").unlink()
    run(site)
    assert "math math-inline" in page(site, "c1")
    assert (site / "archive" / "LISEZMOI.txt").is_file()


# --- Parts removed inside a conversation (edited message, retried answer) ---


def msg(uuid: str, text: str, sender: str = "human") -> dict:
    return {"uuid": uuid, "sender": sender, "content": [{"type": "text", "text": text}]}


def conv_msgs(uuid: str, messages: list[dict]) -> dict:
    return {"uuid": uuid, "name": uuid, "chat_messages": messages}


def order(html_page: str, *needles: str) -> list[int]:
    return [html_page.index(n) for n in needles]


def test_edited_message_keeps_removed_part_at_branch_point(tmp_path: Path, capsys) -> None:
    site = tmp_path / "site"
    v1 = [msg("m1", "Question A"), msg("m2", "Réponse A", "assistant"),
          msg("m3", "Question B ancienne"), msg("m4", "Réponse B ancienne", "assistant")]
    v2 = v1[:2] + [msg("m3b", "Question B corrigée"), msg("m4b", "Réponse B nouvelle", "assistant")]
    run(site, str(export(tmp_path, "a", [conv_msgs("c", v1)])), "--date-export", "2026-09-01")
    run(site, str(export(tmp_path, "b", [conv_msgs("c", v2)])), "--date-export", "2026-10-01")
    assert "1 conversation raccourcie" in capsys.readouterr().out
    p = page(site, "c")
    assert p.count('class="removed-part"') == 1
    assert "Partie supprimée sur claude.ai — 2 messages (présente dans l'export du 01/09/2026)" in p
    # order: kept start, removed frame, then the new branch
    a, frame, old_b, new_b = order(p, "Réponse A", 'class="removed-part"', "Question B ancienne", "Question B corrigée")
    assert a < frame < old_b < new_b
    assert "Supprimée sur claude.ai</strong>" not in p  # the conversation itself is not deleted


def test_successive_edits_and_branch_switch_back(tmp_path: Path) -> None:
    site = tmp_path / "site"
    v1 = [msg("m1", "Q1"), msg("m2", "R1", "assistant"), msg("m3", "Q2"), msg("m4", "R2", "assistant")]
    v2 = v1[:2] + [msg("m3b", "Q2bis"), msg("m4b", "R2bis", "assistant")]
    v3 = v1[:1] + [msg("m2c", "R1ter", "assistant")]  # retry of the first answer
    for i, (name, v) in enumerate((("a", v1), ("b", v2), ("c", v3))):
        run(site, str(export(tmp_path, name, [conv_msgs("c", v)])), "--date-export", f"2026-0{7 + i}-01")
    p = page(site, "c")
    for text in ("Q1", "R1ter", "R1", "Q2", "R2", "Q2bis", "R2bis"):
        assert f">{text}<" in p, text  # nothing lost
    assert order(p, ">Q1<")[0] < order(p, 'class="removed-part"')[0] < order(p, ">R1ter<")[0]

    # back to the original branch: its messages leave the frames (no duplicates)
    run(site, str(export(tmp_path, "d", [conv_msgs("c", v1)])), "--date-export", "2026-10-01")
    p = page(site, "c")
    for text in ("Q2", "R2", "R1"):
        assert p.count(f">{text}<") == 1, text
    assert ">R1ter<" in p and ">Q2bis<" in p  # the other branches are now the removed parts


def test_older_export_adds_messages_never_seen(tmp_path: Path) -> None:
    site = tmp_path / "site"
    new = [msg("m1", "Q1"), msg("m2b", "R1 nouvelle", "assistant")]
    old = [msg("m1", "Q1"), msg("m2", "R1 ancienne", "assistant")]
    run(site, str(export(tmp_path, "new", [conv_msgs("c", new)])), "--date-export", "2026-10-01")
    run(site, str(export(tmp_path, "old", [conv_msgs("c", old)])), "--date-export", "2026-09-01")
    p = page(site, "c")
    assert "R1 nouvelle" in p and "R1 ancienne" in p
    assert order(p, "R1 ancienne")[0] < order(p, "R1 nouvelle")[0]  # frame right after Q1
    assert 'class="removed-part"' in p


def test_appended_messages_create_no_frame(tmp_path: Path) -> None:
    site = tmp_path / "site"
    v1 = [msg("m1", "Q1"), msg("m2", "R1", "assistant")]
    run(site, str(export(tmp_path, "a", [conv_msgs("c", v1)])), "--date-export", "2026-09-01")
    run(site, str(export(tmp_path, "b", [conv_msgs("c", v1 + [msg("m3", "Q2")])])), "--date-export", "2026-10-01")
    assert 'class="removed-part"' not in page(site, "c")


def test_nearby_manifest_matching_each_export(tmp_path: Path, capsys) -> None:
    """Two exports and their two manifests in the same Downloads folder (zip dates are 1980)."""
    dl = tmp_path / "Téléchargements"
    dl.mkdir()
    (dl / "manifest-x-2026-10-22-18-20-52.json").write_text(
        json.dumps({"created_at": "2026-10-22T18:20:52+00:00", "data_files": []}), encoding="utf-8")
    (dl / "manifest-x-2026-10-23-17-52-35.json").write_text(
        json.dumps({"created_at": "2026-10-23T17:52:35+00:00", "data_files": []}), encoding="utf-8")

    def zip_with(name: str, convs: list[dict]) -> Path:
        path = dl / name
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(zipfile.ZipInfo("conversations.json", date_time=(1980, 1, 1, 0, 0, 0)), json.dumps(convs))
        return path

    old = zip_with("conversations-000.zip", [conv("c1", "un", updated="2026-10-22T17:00:00Z")])
    new = zip_with("conversations-000 (1).zip", [conv("c1", "un", updated="2026-10-23T17:49:35Z")])
    site = tmp_path / "site"
    run(site, str(new))
    assert "23/10/2026 17:52 UTC (source : manifeste trouvé à côté : manifest-x-2026-10-23-17-52-35.json)" in (
        capsys.readouterr().out)
    run(site, str(old))
    assert "22/10/2026 18:20 UTC (source : manifeste trouvé à côté : manifest-x-2026-10-22-18-20-52.json)" in (
        capsys.readouterr().out)


def test_data_date_when_nothing_else(tmp_path: Path, capsys) -> None:
    path = tmp_path / "c.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("conversations.json", date_time=(1980, 1, 1, 0, 0, 0)),
                   json.dumps([conv("c1", "un", updated="2026-10-20T09:15:00Z")]))
    run(tmp_path / "site", str(path))
    assert "20/10/2026 09:15 UTC (source : date du message le plus récent de l'export)" in capsys.readouterr().out
