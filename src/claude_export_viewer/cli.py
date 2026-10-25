"""Command line: import an export into the archive, (re)generate the site, serve it, export a conversation."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import fetch, i18n, office_export, settings, system
from .archive import Archive, ArchiveError
from .html_builder import build_site_from_archive
from .i18n import t
from .loader import (
    ExportDate,
    classify,
    data_date,
    iter_conversation_records,
    load_project_names,
    load_users,
    manifest_date,
    nearby_manifest_date,
    print_warnings,
    zip_date,
)


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _parse_manual_date(value: str) -> datetime:
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(t("cli.bad_date", value=value)) from None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def _export_date(found, manual: datetime | None) -> ExportDate:
    if manual:
        return ExportDate(manual, t("cli.date_source.manual"))
    d = manifest_date(found)
    if d:
        return ExportDate(d, t("cli.date_source.manifest"))
    latest = data_date(found)
    nearby = nearby_manifest_date(found, latest)
    if nearby:
        return ExportDate(nearby[0], t("cli.date_source.nearby", name=nearby[1]))
    d = zip_date(found)
    if d and (latest is None or d >= latest):
        return ExportDate(d, t("cli.date_source.zip"))
    if latest:
        return ExportDate(latest, t("cli.date_source.data"))
    return ExportDate(datetime.now(timezone.utc), t("cli.date_source.today"))


_KNOWN_BLOCKS = {"text", "thinking", "tool_use", "tool_result", "token_budget"}


def _print_structure(inputs: list[Path]) -> None:
    """Field names, counts and conversation shape only: no content, safe to share."""
    from collections import Counter

    from .loader import _iter_raw

    found = classify(inputs)
    convo_keys: Counter[str] = Counter()
    msg_keys: Counter[str] = Counter()
    block_types: Counter[str] = Counter()
    unknown_block_keys: dict[str, Counter[str]] = {}
    senders: Counter[str] = Counter()
    sibling_senders: Counter[str] = Counter()
    n_convos = n_msgs = branched = off_main = sibling_groups = unordered = multi_root = 0

    for c in _iter_raw(found.conversations):
        if not isinstance(c, dict):
            continue
        n_convos += 1
        convo_keys.update(c.keys())
        msgs = [m for m in c.get("chat_messages") or [] if isinstance(m, dict)]
        for m in msgs:
            n_msgs += 1
            msg_keys.update(m.keys())
            senders[str(m.get("sender"))] += 1
            for b in m.get("content") or []:
                if isinstance(b, dict):
                    kind = str(b.get("type"))
                    block_types[kind] += 1
                    if kind not in _KNOWN_BLOCKS:
                        unknown_block_keys.setdefault(kind, Counter()).update(b.keys())

        # Shape of the conversation: tree built from parent_message_uuid
        by_uuid = {m.get("uuid"): m for m in msgs if m.get("uuid")}
        children: dict[object, list[dict]] = {}
        for m in msgs:
            children.setdefault(m.get("parent_message_uuid"), []).append(m)
        groups = [kids for kids in children.values() if len(kids) > 1]
        if groups:
            branched += 1
            sibling_groups += len(groups)
            for kids in groups:
                sibling_senders.update(str(k.get("sender")) for k in kids)
        roots = {m.get("parent_message_uuid") for m in msgs if m.get("parent_message_uuid") not in by_uuid}
        multi_root += len(roots) > 1
        leaves = [m for m in msgs if m.get("uuid") not in children]
        if leaves:
            leaf = max(leaves, key=lambda m: str(m.get("created_at") or ""))
            path, cur, guard = 0, leaf, 0
            while cur is not None and guard <= len(msgs):
                path, guard = path + 1, guard + 1
                cur = by_uuid.get(cur.get("parent_message_uuid"))
            off_main += len(msgs) - path
        stamps = [str(m.get("created_at") or "") for m in msgs]
        unordered += stamps != sorted(stamps)

    none = t("cli.structure.none")
    print(t("cli.structure.files"), ", ".join(s.label for s in found.conversations) or none)
    d_zip, d_manifest = zip_date(found), manifest_date(found)
    print(t("cli.structure.zip_date"), i18n.format_datetime(d_zip) if d_zip else none)
    if found.manifests:
        print(t("cli.structure.manifest_date"), i18n.format_datetime(d_manifest) if d_manifest else none)
    print(t("cli.structure.counts", conversations=n_convos, messages=n_msgs))
    for title, counter in (
        (t("cli.structure.convo_fields"), convo_keys),
        (t("cli.structure.message_fields"), msg_keys),
        (t("cli.structure.senders"), senders),
        (t("cli.structure.block_types"), block_types),
    ):
        print(title)
        for key, n in sorted(counter.items()):
            print(f"  {key} : {n}")
    for kind, keys in sorted(unknown_block_keys.items()):
        print(t("cli.structure.block_fields", type=kind) + " " + ", ".join(sorted(keys)))
    print(t("cli.structure.shape"))
    print(t("cli.structure.branched", n=branched))
    print(t("cli.structure.sibling_groups", n=sibling_groups) + " " + (
        ", ".join(f"{k} {v}" for k, v in sorted(sibling_senders.items())) or none))
    print(t("cli.structure.off_main", n=off_main))
    print(t("cli.structure.multi_root", n=multi_root))
    print(t("cli.structure.unordered", n=unordered))
    print_warnings()


def _export_one(archive: Archive, query: str, fmt: str, folder: Path, versions: bool = True) -> None:
    if not archive.exists:
        _err(t("cli.export.no_archive"))
        sys.exit(1)
    matches = office_export.find_conversations(archive, query)
    if not matches:
        _err(t("cli.export.no_match", query=query))
        sys.exit(1)
    if len(matches) > 1:
        _err(t("cli.export.several", query=query))
        for uuid, meta in sorted(matches, key=lambda x: x[1].get("created_at", ""), reverse=True)[:20]:
            _err(f"  {uuid}  {meta.get('created_at', '')[:10]}  {meta.get('name') or t('web.untitled')}")
        sys.exit(1)
    uuid, meta = matches[0]
    try:
        result = office_export.convert_archived(archive, uuid, fmt, versions)
    except RuntimeError as exc:  # PandocMissing included
        _err(t("cli.error", message=exc))
        sys.exit(1)
    folder = folder.expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / result.filename
    out.write_bytes(result.data)
    print(t("cli.export.done", name=meta.get("name") or t("web.untitled"), path=out.resolve()))
    if result.warnings:
        print(t("cli.export.formulas", n=len(result.warnings)))
        for w in result.warnings[:10]:
            print(f"    {w}")


def _program_path() -> Path:
    """The launcher script (claude-export-viewer.py), whose folder is the program."""
    candidate = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if candidate and candidate.name == "claude-export-viewer.py":
        return candidate
    return Path(__file__).resolve().parents[2] / "claude-export-viewer.py"


def _language_from(argv: list[str]) -> str | None:
    """--langue / --lang read before the parser is built, so that its help is translated too."""
    for i, a in enumerate(argv):
        for opt in ("--langue", "--lang"):
            if a == opt and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(opt + "="):
                return a.split("=", 1)[1]
    return None


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=t("cli.help.description"))
    add = p.add_argument
    add("inputs", type=Path, nargs="*", help=t("cli.help.inputs"))
    add("-o", "--output", type=Path, default=Path("site"), help=t("cli.help.output"))
    add("--garder-vides", "--keep-empty", dest="keep_empty", action="store_true", help=t("cli.help.keep_empty"))
    add("--date-export", "--export-date", dest="date_export", type=_parse_manual_date,
        metavar=t("cli.help.date_metavar"), help=t("cli.help.date_export"))
    add("--reconstruire", "--rebuild", dest="rebuild", action="store_true", help=t("cli.help.rebuild"))
    add("--tout", "--all", dest="all_files", action="store_true", help=t("cli.help.all"))
    add("--navigateur", "--browser", dest="browser", metavar=t("cli.help.command_metavar"), help=t("cli.help.browser"))
    add("--manuel", "--manual", dest="manual", action="store_true", help=t("cli.help.manual"))
    add("--delai", "--timeout", dest="timeout", type=float, default=None, metavar=t("cli.help.seconds_metavar"),
        help=t("cli.help.timeout"))
    add("--sans-navigateur", "--no-browser", dest="no_browser", action="store_true", help=t("cli.help.no_browser"))
    add("--odt", metavar=t("cli.help.conversation_metavar"), help=t("cli.help.odt"))
    add("--docx", metavar=t("cli.help.conversation_metavar"), help=t("cli.help.docx"))
    add("--fil-principal", "--main-thread", dest="main_thread", action="store_true", help=t("cli.help.main_thread"))
    add("--dossier-export", "--export-dir", dest="export_dir", type=Path, default=Path("."),
        metavar=t("cli.help.folder_metavar"), help=t("cli.help.export_dir"))
    add("--serveur", "--serve", dest="serve", nargs="?", const=8000, type=int, metavar="PORT", help=t("cli.help.serve"))
    add("--ouvrir", "--open", dest="open_mode", action="store_true", help=t("cli.help.open"))
    add("--arret-auto", "--idle", dest="idle", type=float, default=30, metavar=t("cli.help.minutes_metavar"),
        help=t("cli.help.idle"))
    add("--installer-icone", "--install-icon", dest="install_icon", action="store_true", help=t("cli.help.install_icon", name=t("desktop.name")))
    add("--structure", action="store_true", help=t("cli.help.structure"))
    add("--telechargements", "--downloads", dest="downloads", metavar=t("cli.help.folder_metavar"),
        help=t("cli.help.downloads"))
    add("--langue", "--lang", dest="language", metavar="CODE",
        help=t("cli.help.language", codes=", ".join(i18n.LANGUAGES)))
    return p


def _print_import_stats(stats, start: float) -> None:
    print(t("cli.import.title", seconds=f"{time.monotonic() - start:.0f}"))
    read = t("cli.import.read", n=stats.seen)
    print("  " + read + ("" if read.endswith("：") else " ") + t("fmt.list_sep").join(
        (t("cli.import.new", n=stats.new), t("cli.import.updated", n=stats.updated),
         t("cli.import.unchanged", n=stats.unchanged))))
    if stats.skipped_empty:
        print("  " + t("cli.import.skipped_empty", n=stats.skipped_empty))
    if stats.emptied:
        print("  " + t("cli.import.emptied", n=stats.emptied))
    if stats.with_removed_parts:
        print("  " + t("cli.import.removed_parts", n=stats.with_removed_parts))
    if stats.newly_deleted:
        print("  " + t("cli.import.newly_deleted", n=len(stats.newly_deleted)))
    if stats.restored:
        print("  " + t("cli.import.restored", n=len(stats.restored)))
    if not stats.is_latest:
        print("  " + t("cli.import.older"))
    if stats.suspicious:
        print("\n" + t("cli.import.suspicious", n=len(stats.newly_deleted)) + "\n")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    system.safe_console()
    i18n.set_language(_language_from(argv) or i18n.detect())
    args = _parser().parse_args(argv)

    try:
        archive = Archive(args.output)
    except ArchiveError as exc:
        _err(t("cli.error", message=exc))
        sys.exit(1)
    missing = [p for p in args.inputs if not p.expanduser().exists()]
    if missing:
        for p in missing:
            _err(t("cli.not_found", path=p))
        sys.exit(1)
    if args.downloads is not None:
        try:
            folder = settings.set_downloads_folder(args.output, args.downloads)
        except ValueError:
            _err(t("cli.downloads.bad", folder=args.downloads))
            sys.exit(1)
        print(t("cli.downloads.set", folder=folder) if folder else
              t("cli.downloads.reset", folder=settings.search_folders(args.output)[0]))
        if not args.inputs:
            return
    if args.structure and not args.inputs:
        _err(t("cli.structure.no_input"))
        sys.exit(1)
    if not args.inputs and not archive.exists and not args.structure:
        _err(t("cli.no_input", folder=args.output))
        sys.exit(1)

    if args.structure:
        _print_structure(args.inputs)
        return

    if args.install_icon:
        from .desktop import install_launcher, install_windows

        if system.WINDOWS:
            try:
                written = install_windows(args.output, _program_path())
            except OSError as exc:
                _err(str(exc))
                sys.exit(1)
            done = "cli.icon.done_windows"
        elif sys.platform.startswith("linux"):
            written, done = install_launcher(args.output, _program_path()), "cli.icon.done"
        else:
            _err(t("cli.icon.unsupported"))
            sys.exit(1)
        for path in written:
            print(t("cli.icon.created", path=path))
        print(t(done, name=t("desktop.name")))
        return

    if args.open_mode or args.serve is not None:
        from .server import stop_outdated

        for url in stop_outdated(args.output):
            print(t("cli.server.old_stopped", url=url))
    if args.open_mode:
        from .server import find_running

        running = find_running(args.output)
        if running:
            if not args.no_browser:
                fetch.browser_opener(args.browser)(running)
            print(t("cli.server.already_open", url=running))
            return

    if args.odt or args.docx:
        _export_one(archive, args.odt or args.docx, "odt" if args.odt else "docx", args.export_dir,
                    versions=not args.main_thread)
        return

    start = time.monotonic()
    open_index = False

    manifest = fetch.manifest_from_inputs(args.inputs) if args.inputs else None
    if manifest:
        print(t("cli.manifest.name", name=manifest.path.name))
        print("  " + t("cli.manifest.dates", created=manifest.created_at, expires=manifest.expires_at))
        categories = [f.category for f in manifest.files] if args.all_files else fetch.DEFAULT_CATEGORIES
        timeout = args.timeout if args.timeout is not None else (900 if args.manual else 300)
        try:
            result = fetch.fetch_export(
                manifest,
                args.output,
                categories=categories,
                opener=fetch.browser_opener(args.browser),
                folders=fetch.download_folders(
                    manifest, [f for f in [settings.downloads_folder(args.output)] if f is not None]),
                timeout=timeout,
                manual=args.manual,
            )
        except KeyboardInterrupt:
            _err("\n" + t("cli.manifest.interrupted"))
            sys.exit(130)
        if "conversations" not in result.files:
            _err("\n" + t("cli.manifest.no_conversations"))
            _err(t("cli.manifest.expired") if manifest.expired else t("cli.manifest.check_browser"))
            sys.exit(1)
        if result.missing:
            print("  " + t("cli.manifest.missing", files=", ".join(result.missing)))
        print("  " + t("cli.manifest.stored", folder=result.export_dir))
        keep = set(fetch.DEFAULT_CATEGORIES)
        args.inputs = [p for c, paths in result.files.items() if c in keep for p in paths]
        if result.manifest_copy:
            args.inputs.append(result.manifest_copy)
        open_index = not args.no_browser

    if args.inputs:
        found = classify(args.inputs)
        if not found.conversations:
            _err(t("cli.import.no_conversations"))
            for p in args.inputs:
                _err(f"  {p}")
            _err(t("cli.import.hint"))
            print_warnings()
            sys.exit(1)

        print(t("cli.import.files"))
        for s in found.conversations:
            print(f"  {s.label}")
        date = _export_date(found, args.date_export)
        print(t("cli.import.date", date=date.value.strftime(t("fmt.date") + " %H:%M"), source=date.source))

        users = {u.uuid: u.full_name for u in load_users(found)}
        stats = archive.import_export(
            iter_conversation_records(found.conversations),
            date,
            label=", ".join(s.label for s in found.conversations),
            skip_empty=not args.keep_empty,
            users=users,
            projects=load_project_names(found),
        )
        archive.save()
        print_warnings()
        _print_import_stats(stats, start)

    render_start = time.monotonic()

    def progress(n: int) -> None:
        if n % 50 == 0:
            print("  " + t("cli.render.progress", n=n, seconds=f"{time.monotonic() - render_start:.0f}"), flush=True)

    print(t("cli.render.start", folder=args.output))
    render = build_site_from_archive(archive, args.output, force=args.rebuild, progress=progress)
    summary = t("cli.render.done", seconds=f"{time.monotonic() - start:.0f}",
                pages=t("cli.render.pages", n=render.rendered), conversations=t("cli.render.total", n=render.total))
    if render.deleted:
        summary += " " + t("cli.render.deleted", n=render.deleted)
    print(summary + t("fmt.period"))
    if render.failed:
        print("  " + t("cli.render.failed", n=render.failed))
    index = (args.output / "index.html").resolve()
    if args.serve is not None or args.open_mode:
        from .server import serve

        serve(
            args.output,
            args.serve or 8000,
            None if args.no_browser else fetch.browser_opener(args.browser),
            idle_minutes=args.idle if args.open_mode else None,
            launcher=_program_path(),
        )
        return
    if open_index:
        print(t("cli.open_index", path=index))
        fetch.browser_opener(args.browser)(index.as_uri())
    elif sys.stdout.isatty():
        print(t("cli.open_hint", path=index))


if __name__ == "__main__":
    main()
