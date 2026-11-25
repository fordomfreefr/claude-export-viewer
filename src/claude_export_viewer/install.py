"""Installing and updating CEV in one command (P2, 11/11): ``claude-export-viewer.py --installer``, run from the folder
where the ZIP of the program was unpacked (the downloads, say). The program is copied to its place,
``~/claude-export-viewer`` (the earlier version there is replaced: only the program, never the site with its archive),
then the icon is made and the archives open. Run again from a newer ZIP, it is the update."""

from __future__ import annotations

import secrets
import shutil
import tempfile
from pathlib import Path

LAUNCHER = "claude-export-viewer.py"
_SKIP = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "*.pyc")


class InstallError(Exception):
    """Nothing was replaced; ``key`` is the message (i18n) and ``folder`` its argument."""

    def __init__(self, key: str, folder: Path) -> None:
        super().__init__(key)
        self.key, self.folder = key, folder


def target() -> Path:
    return Path.home() / "claude-export-viewer"


def place_program(source: Path, dest: Path, site: Path) -> bool:
    """Copy the program folder ``source`` to ``dest`` (True), or nothing when it already runs from there (False).
    A ``dest`` that is not a CEV program folder, or that holds the site, is never replaced (InstallError)."""
    source, dest, site = source.resolve(), dest.resolve(), site.resolve()
    if source == dest:
        return False
    if site == dest or dest in site.parents:
        raise InstallError("cli.install.site_inside", dest)
    if dest.exists() and not (dest / LAUNCHER).is_file():
        raise InstallError("cli.install.not_cev", dest)
    # Review of 21/11 (B6): folders of unique names (a folder of the user named like them is never touched), a
    # leftover of an install cut short removed only when it is a CEV program folder, and the old program put back
    # when the new one cannot take its place.
    for left in (dest.with_name(dest.name + ".nouveau"), dest.with_name(dest.name + ".ancien")):
        if left.is_dir() and (left / LAUNCHER).is_file():
            shutil.rmtree(left, ignore_errors=True)
    new = Path(tempfile.mkdtemp(prefix=dest.name + ".nouveau-", dir=dest.parent))
    try:
        shutil.copytree(source, new, ignore=_SKIP, dirs_exist_ok=True)  # whole, before anything is removed
        if dest.exists():
            old = dest.with_name(f"{dest.name}.ancien-{secrets.token_hex(4)}")
            dest.rename(old)
            try:
                new.rename(dest)
            except OSError:
                old.rename(dest)  # the program as it was
                raise
            shutil.rmtree(old, ignore_errors=True)
        else:
            new.rename(dest)
    finally:
        if new.exists():
            shutil.rmtree(new, ignore_errors=True)
    return True
