"""Languages: detection, plural rules, complete catalogs, console, pages, exports and import log."""

import json
import os
import re
import zipfile
from pathlib import Path

from claude_export_viewer import i18n
from claude_export_viewer.cli import main
from claude_export_viewer.desktop import desktop_entry

ROOT = "00000000-0000-4000-8000-000000000000"
CATALOGS = Path(i18n.__file__).parent / "i18n"
CATEGORIES = {"pl": {"one", "few", "many", "other"}, "ru": {"one", "few", "many", "other"},
              "zh": {"other"}, "ja": {"other"}, "ko": {"other"}}


class lang_env:
    """Run with another system language (the tests run in French by default)."""

    def __init__(self, code: str) -> None:
        self.code = code

    def __enter__(self):
        self.saved = os.environ.get("CEV_LANG")
        os.environ["CEV_LANG"] = self.code
        i18n.set_language(self.code)

    def __exit__(self, *exc):
        os.environ["CEV_LANG"] = self.saved or "fr"
        i18n.set_language(os.environ["CEV_LANG"])


def export(tmp: Path, convs: list[dict], name: str = "e") -> Path:
    z = tmp / f"{name}.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(convs))
    return z


def conv() -> dict:
    return {"uuid": "c1", "name": "Essai", "created_at": "2026-10-01T08:00:00Z", "chat_messages": [
        {"uuid": "q", "parent_message_uuid": ROOT, "sender": "human", "created_at": "2026-10-01T08:00:00Z",
         "content": [{"type": "text", "text": "Question"}]},
        {"uuid": "r1", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-01T08:01:00Z",
         "content": [{"type": "text", "text": "Old answer"}]},
        {"uuid": "r2", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-01T08:02:00Z",
         "content": [{"type": "text", "text": "New answer"}]}]}


# --- detection and rules -------------------------------------------------------


def test_language_of_the_system() -> None:
    assert i18n.detect({"LANG": "fr_FR.UTF-8"}) == "fr"
    assert i18n.detect({"LANGUAGE": "de:en", "LANG": "fr_FR.UTF-8"}) == "de"  # LANGUAGE first
    assert i18n.detect({"LANG": "zh_CN.UTF-8"}) == "zh"
    assert i18n.detect({"LANG": "pt_BR.UTF-8"}) == "pt"
    assert i18n.detect({"LANG": "sv_SE.UTF-8"}) == "en"  # not available: English
    assert i18n.detect({}) == "en"
    assert i18n.detect({"CEV_LANG": "ja", "LANG": "fr_FR.UTF-8"}) == "ja"  # set by the server for its jobs


def test_plural_rules() -> None:
    ru = {n: i18n.plural_category("ru", n) for n in (1, 2, 4, 5, 11, 12, 21, 22, 25, 111, 112)}
    assert ru == {1: "one", 2: "few", 4: "few", 5: "many", 11: "many", 12: "many", 21: "one", 22: "few",
                  25: "many", 111: "many", 112: "many"}
    pl = {n: i18n.plural_category("pl", n) for n in (1, 2, 5, 12, 21, 22, 25)}
    assert pl == {1: "one", 2: "few", 5: "many", 12: "many", 21: "many", 22: "few", 25: "many"}
    assert [i18n.plural_category("fr", n) for n in (0, 1, 2)] == ["one", "one", "other"]
    assert [i18n.plural_category("en", n) for n in (0, 1, 2)] == ["other", "one", "other"]
    assert i18n.plural_category("ja", 1) == "other"
    assert i18n.t("web.messages", "ru", n=21) == "21 сообщение" and i18n.t("web.messages", "ru", n=5) == "5 сообщений"


def test_every_catalog_is_complete() -> None:
    en = json.loads((CATALOGS / "en.json").read_text(encoding="utf-8"))
    names = lambda s: set(re.findall(r"\{(\w+)\}", s))  # noqa: E731
    for lang in i18n.LANGUAGES:
        d = json.loads((CATALOGS / f"{lang}.json").read_text(encoding="utf-8"))
        assert set(d) == set(en), lang
        for key, ref in en.items():
            ref_names = names(ref["other"] if isinstance(ref, dict) else ref)
            value = d[key]
            if isinstance(ref, dict):
                assert set(value) == CATEGORIES.get(lang, {"one", "other"}), (lang, key)
                assert all(names(v) == ref_names for v in value.values()), (lang, key)
            else:
                assert isinstance(value, str) and names(value) == ref_names, (lang, key)


def test_missing_text_falls_back_to_english() -> None:
    i18n.catalog.cache_clear()
    saved = i18n.catalog("de").pop("web.back")
    try:
        assert i18n.t("web.back", "de") == "All conversations"
        assert i18n.t("no.such.key", "de") == "no.such.key"
    finally:
        i18n.catalog("de")["web.back"] = saved


# --- console -------------------------------------------------------------------


def test_console_follows_the_language(tmp_path: Path, capsys) -> None:
    z = export(tmp_path, [conv()])
    main([str(z), "-o", str(tmp_path / "en"), "--date-export", "2026-10-20", "--lang", "en"])
    out = capsys.readouterr().out
    assert "1 conversation read: 1 new, 0 updated, 0 unchanged" in out and "Done in" in out
    main([str(z), "-o", str(tmp_path / "ru"), "--date-export", "2026-10-20", "--langue", "ru"])
    out = capsys.readouterr().out
    assert "прочитана 1 беседа: 1 новая" in out and "создана 1 страница" in out
    i18n.set_language("fr")


def test_help_is_translated(capsys) -> None:
    try:
        main(["--help", "--lang", "de"])
    except SystemExit:
        pass
    assert "Sprache der Meldungen" in capsys.readouterr().out
    i18n.set_language("fr")


def test_desktop_icon_names_every_language(tmp_path: Path) -> None:
    entry = desktop_entry(tmp_path, tmp_path / "x.py", tmp_path / "i.svg")
    assert "Name=Claude Archives\n" in entry and "Name[fr]=Archives Claude\n" in entry
    assert "Name[ja]=Claude アーカイブ\n" in entry and "Comment[de]=" in entry


# --- pages and exports -----------------------------------------------------------


def test_pages_are_written_in_the_system_language(tmp_path: Path) -> None:
    with lang_env("de"):
        main([str(export(tmp_path, [conv()])), "-o", str(tmp_path / "s"), "--date-export", "2026-10-20"])
    index = (tmp_path / "s" / "index.html").read_text(encoding="utf-8")
    page = (tmp_path / "s" / "conversations" / "c1.html").read_text(encoding="utf-8")
    assert '<html lang="de">' in index and ">Claude-Unterhaltungen</span>" in index
    assert ">Andere Version — 1 Nachricht, begonnen am 01.10.2026" in page
    data = (tmp_path / "s" / "i18n-data.js").read_text(encoding="utf-8")
    assert data.startswith("window.CEV_I18N = ") and '"build":"de"' in data
    texts = json.loads(data[len("window.CEV_I18N = "):].rstrip().rstrip(";"))["texts"]
    assert set(texts) == set(i18n.LANGUAGES) and "cli.error" not in texts["fr"]  # only what pages need


def test_office_export_in_the_language_of_the_page(tmp_path: Path) -> None:
    from claude_export_viewer import office_export
    from claude_export_viewer.archive import Archive

    main([str(export(tmp_path, [conv()])), "-o", str(tmp_path / "s"), "--date-export", "2026-10-20"])
    archive = Archive(tmp_path / "s")
    md, name = office_export.archived_markdown(archive, "c1", versions=False, lang="es")
    from datetime import datetime, timezone

    when = i18n.format_datetime(datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc), "es")  # local time
    assert re.fullmatch(r"01/10/2026, \d\d:00", when)
    assert f"**Usted** — {when}" in md
    assert "(solo el hilo principal)" in md and name.endswith("Essai (hilo principal)")
    md_en, _ = office_export.archived_markdown(archive, "c1", lang="en")
    assert "*Other version — 1 message, started on" in md_en


def test_import_log_in_the_language_of_the_page(tmp_path: Path) -> None:
    import http.client
    import threading
    import time

    from claude_export_viewer.server import make_server

    main([str(export(tmp_path, [conv()])), "-o", str(tmp_path / "s"), "--date-export", "2026-10-20"])
    downloads = tmp_path / "dl"
    downloads.mkdir()
    server = make_server(tmp_path / "s", 0)
    server.ctx.downloads = lambda: downloads
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        host = {"Host": f"127.0.0.1:{port}"}
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/__cev__/token", headers=host)
        tok = json.loads(c.getresponse().read())["token"]
        c.request("POST", "/__cev__/import", headers={**host, "X-CEV-Token": tok, "X-CEV-Lang": "it"})
        r = c.getresponse()
        r.read()
        assert r.status == 202
        for _ in range(50):
            c.request("GET", "/__cev__/job", headers={**host, "X-CEV-Token": tok})
            state = json.loads(c.getresponse().read())
            if state["done"]:
                break
            time.sleep(0.1)
        assert state["lines"][0] == f"Nessun manifesto trovato in {downloads}."
        assert state["lines"][-1].startswith("4. Torna qui")
    finally:
        server.shutdown()
