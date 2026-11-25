"""All the conversations in Markdown in one dated ZIP (AE-m11, 14/11; button "Tout exporter (Markdown)" of the index,
``--tout-exporter``, a copy offered before uninstalling): readable in any editor, years later, without CEV.

"<site>-markdown-AAAA-MM-JJ.zip" holds, at its root, one "AAAA-MM-JJ Titre.md" per conversation (all the versions,
with the notes, titles and highlighted passages) and a summary "Sommaire.md" linking them; the files each one names
(documents joined, files made by Claude) go to "fichiers/<name of the .md>/", linked from the text as in the export of
one conversation (zipexport.Bundle). Written under a temporary name and renamed at the end, as the backup.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from . import backup, i18n, office_export, zipexport

_SLOT = "\x00cev-folder\x00"  # where the folder of the files goes, once the name of the .md is known


def _text(title: str) -> str:
    """A title as the text of a link of the summary (its brackets kept as text)."""
    return title.replace("[", "\\[").replace("]", "\\]")


def zip_name(site_dir: Path, today: date | None = None) -> str:
    return f"{Path(site_dir).resolve().name}-markdown-{(today or date.today()).isoformat()}.zip"


def _markdowns(archive: Any, uuid: str, site_dir: Path, lang: str | None, bundle: Any):  # noqa: ANN202
    """(markdown, file name) of a conversation: one, or one per part of a very long one (html_builder.plan_of)."""
    from . import html_builder
    annot = office_export.annotations_of(site_dir, uuid)
    parts = html_builder.plan_of(archive, uuid)
    if parts is None:
        yield office_export.archived_markdown(archive, uuid, 1, True, lang, links=bundle, annot=annot)
        return
    n = len(parts.plan.ranges)
    for k, raw, leaf in html_builder.iter_part_raws(archive, uuid, parts):
        yield office_export.markdown_of_raw(archive, uuid, raw, leaf, office_export.part_suffix(k, n, lang), 1, True,
                                            lang, links=bundle, annot=annot)


def build_all(archive: Any, site_dir: Path, dest: Path | None = None, lang: str | None = None,
              today: date | None = None, say: Callable[[str, dict], None] | None = None) -> Path:
    """Write the ZIP in ``dest`` (default: the folder of the backups) and return it; ``say(key, args)``: the steps.
    A conversation that cannot be written is reported and left out: it never stops the others."""
    site_dir = Path(site_dir).resolve()
    dest = backup.destination(site_dir) if dest is None else Path(dest)
    target, n = dest / zip_name(site_dir, today), 1
    while target.exists():
        n += 1
        target = dest / f"{zip_name(site_dir, today)[:-4]} ({n}).zip"
    folder = i18n.t("zip.folder", lang)
    total = len(archive.conversations)
    if say:
        say("allexport.start", {"n": total, "path": str(target)})
    rows: list[tuple[str, str, str]] = []  # (date, title, file)
    used: set[str] = set()
    part = target.with_name(target.name + backup.PART)
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for done, (uuid, meta) in enumerate(sorted(archive.conversations.items(),
                                                       key=lambda kv: kv[1].get("created_at") or ""), 1):
                bundle = zipexport.Bundle(site_dir, uuid, _SLOT)
                try:
                    files = None
                    # a very long conversation gives one file per part (written as made: never whole in memory)
                    for md, name in _markdowns(archive, uuid, site_dir, lang, bundle):
                        base, k = name, 1
                        while base.lower() in used:
                            k += 1
                            base = f"{name} ({k})"
                        used.add(base.lower())
                        files = files or f"{folder}/{base}"  # the files of all the parts in the folder of the first
                        z.writestr(f"{base}.md", md.replace(_SLOT, files).encode("utf-8"))
                        rows.append(((meta.get("created_at") or "")[:10], meta.get("name") or i18n.t("web.untitled", lang),
                                     f"{base}.md"))
                        del md
                except Exception as exc:  # noqa: BLE001 - reported, the others go on
                    if say:
                        say("allexport.failed_one", {"name": meta.get("name") or uuid, "error": str(exc)})
                    continue
                for stored, content in bundle.files.items():
                    if isinstance(content, Path):
                        z.write(content, f"{files}/{stored}")
                    else:
                        z.writestr(f"{files}/{stored}", content)
                if say and done % 50 == 0:
                    say("allexport.progress", {"n": done, "total": total})
            title = i18n.t("allexport.summary_title", lang, name=i18n.t("web.site_title", lang), n=len(rows),
                           date=(today or date.today()).strftime(i18n.t("fmt.date", lang)))
            lines = [f"# {title}", ""] + [f"- {d} — [{_text(t)}](<{f}>)" for d, t, f in rows]
            z.writestr(i18n.t("allexport.summary_file", lang), "\n".join(lines) + "\n")
        os.replace(part, target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if say:
        say("allexport.done", {"n": len(rows), "path": str(target), "size": f"{target.stat().st_size / 1e6:.1f}"})
    return target
