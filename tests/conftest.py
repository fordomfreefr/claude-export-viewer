import pytest


@pytest.fixture(autouse=True)
def _own_cache(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test has its own cache folder (the sounds read aloud, speech.cache_dir), never the user's."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    # (15/11) and its own cache of the coloured code and of the Markdown read (codecache), opened in that folder
    from claude_export_viewer import codecache
    monkeypatch.setattr(codecache, "_db", None)
    monkeypatch.setattr(codecache, "_broken", False)
