"""AF-f5 (15/11): states of the annotations kept by themselves, "Récupération des annotations…"."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from claude_export_viewer import annotations
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401 - fixture
from .test_uninstall import _site


def _note(site: Path, text: str | None) -> None:
    data = annotations.load(site)
    if text is None:
        data["notes"].pop("c1", None)
    else:
        data["notes"]["c1"] = {"a": {"text": text, "updated": "2026-11-15T08:00:00"}}
    annotations.save(site, data)


def test_states_kept_spaced_bulk_and_at_most_five(tmp_path: Path, monkeypatch) -> None:
    site = _site(tmp_path)  # one note already
    _note(site, "deux")
    _note(site, "trois")  # within SPACING of the copy before: not kept again (a note written in steps)
    assert len(annotations.copies(site)) == 1
    data = annotations.load(site)
    data["favorites"]["c1"] = {"a": {"added": "x"}, "q": {"added": "x"}}
    annotations.save(site, data)
    data["favorites"] = {}  # two at once go: always kept, even within SPACING
    annotations.save(site, data)
    kept = annotations.copies(site)
    assert len(kept) == 2 and kept[0]["counts"]["favorites"] == 2
    monkeypatch.setattr(annotations, "SPACING", 0.0)
    for i in range(6):
        _note(site, f"n{i}")
    assert len(annotations.copies(site)) == annotations.KEEP
    # put back the oldest state kept; the current one is kept first
    name = annotations.copies(site)[-1]["name"]
    before = annotations.counts(annotations.load(site))
    annotations.recover(site, name)
    assert annotations.copies(site)[0]["counts"] == before
    with pytest.raises(annotations.AnnotationError):
        annotations.recover(site, "../annotations.json")


def test_recovery_in_the_index(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    _note(site, None)  # the note removed by mistake: the state with it is kept
    assert annotations.counts(annotations.load(site))["notes"] == 0
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        pg.wait_for_selector("#tab-data:visible")
        pg.click("#tab-data")
        pg.click("#admin-annot")
        pg.wait_for_selector(".annot-list li")
        assert "notes : 0" in pg.inner_text("#annot-body") and "notes : 1" in pg.inner_text(".annot-list li")
        pg.click(".annot-list li button")
        pg.click(".cev-confirm-yes")
        pg.wait_for_selector(".annot-list li >> nth=1")  # reloaded, the frame opened again; the state left is kept
        assert annotations.load(site)["notes"]["c1"]["a"]["text"] == "Ma note à garder"
        assert pg.inner_text("#annot-body").startswith("Actuellement : notes : 1")
        assert pg.errors == []
    finally:
        server.shutdown()
