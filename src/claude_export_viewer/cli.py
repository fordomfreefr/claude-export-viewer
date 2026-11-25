"""Command line: import an export into the archive, (re)generate the site, serve it, export a conversation."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import backup, fetch, i18n, office_export, settings, system, userfiles, verify
from .archive import Archive, ArchiveError, ArchiveLock, DiskFull
from .html_builder import build_site_from_archive
from .i18n import t
from .loader import (
    BIG_MARK,
    DATE_MARK,
    ExportDate,
    classify,
    data_date,
    date_question,
    export_date,
    file_categories,
    iter_conversation_records,
    iter_conversation_spools,
    load_project_names,
    load_users,
    manifest_date,
    nearby_manifest_date,
    pop_left_out,
    pop_read_errors,
    pop_too_big,
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
    return export_date(found, manual)


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
    p = argparse.ArgumentParser(description=t("cli.help.description"), allow_abbrev=False)  # "--installer" ≠ "--installer-icone"
    add = p.add_argument
    add("inputs", type=Path, nargs="*", help=t("cli.help.inputs"))
    add("-o", "--output", type=Path, default=None, help=t("cli.help.output"))  # None: ~/claude_site (11/11)
    add("--garder-vides", "--keep-empty", dest="keep_empty", action="store_true", help=t("cli.help.keep_empty"))
    add("--date-export", "--export-date", dest="date_export", type=_parse_manual_date,
        metavar=t("cli.help.date_metavar"), help=t("cli.help.date_export"))
    add("--date-confirmee", "--date-confirmed", dest="date_confirmed", action="store_true",
        help=t("cli.help.date_confirmed"))
    add("--limite-message", "--message-limit", dest="message_limit", type=int, metavar="MO",
        help=t("cli.help.message_limit"))
    add("--reconstruire", "--rebuild", dest="rebuild", action="store_true", help=t("cli.help.rebuild"))
    add("--tout", "--all", dest="all_files", action="store_true", help=argparse.SUPPRESS)  # now the default
    add("--navigateur", "--browser", dest="browser", metavar=t("cli.help.command_metavar"), help=t("cli.help.browser"))
    add("--manuel", "--manual", dest="manual", action="store_true", help=t("cli.help.manual"))
    add("--delai", "--timeout", dest="timeout", type=float, default=None, metavar=t("cli.help.seconds_metavar"),
        help=t("cli.help.timeout"))
    add("--sans-navigateur", "--no-browser", dest="no_browser", action="store_true", help=t("cli.help.no_browser"))
    add("--odt", metavar=t("cli.help.conversation_metavar"), help=t("cli.help.odt"))
    add("--docx", metavar=t("cli.help.conversation_metavar"), help=t("cli.help.docx"))
    add("--txt", metavar=t("cli.help.conversation_metavar"), help=t("cli.help.txt"))
    add("--fil-principal", "--main-thread", dest="main_thread", action="store_true", help=t("cli.help.main_thread"))
    add("--dossier-export", "--export-dir", dest="export_dir", type=Path, default=Path("."),
        metavar=t("cli.help.folder_metavar"), help=t("cli.help.export_dir"))
    add("--serveur", "--serve", dest="serve", nargs="?", const=8000, type=int, metavar="PORT", help=t("cli.help.serve"))
    add("--ouvrir", "--open", dest="open_mode", action="store_true", help=t("cli.help.open"))
    add("--arret-auto", "--idle", dest="idle", type=float, default=30, metavar=t("cli.help.minutes_metavar"),
        help=t("cli.help.idle"))
    add("--installer", "--install", dest="installer", action="store_true", help=t("cli.help.installer"))
    add("--installer-icone", "--install-icon", dest="install_icon", action="store_true", help=t("cli.help.install_icon", name=t("desktop.name")))
    add("--structure", action="store_true", help=t("cli.help.structure"))
    add("--sauvegarder", "--backup", dest="backup", action="store_true", help=t("cli.help.backup"))
    add("--tout-exporter", "--export-all", dest="export_all", action="store_true", help=t("cli.help.export_all"))
    add("--verifier", "--verify", dest="verify", action="store_true", help=t("cli.help.verify"))
    add("--reparer", "--repair", dest="repair", action="store_true", help=t("cli.help.repair"))
    add("--desinstaller", "--uninstall", dest="uninstall", action="store_true", help=t("cli.help.uninstall"))
    add("--restaurer", "--restore", dest="restore", type=Path, metavar="ZIP", help=t("cli.help.restore"))
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
    if stats.incomplete:
        print("\n" + t("cli.import.incomplete") + "\n")
    if stats.date_before_newest:
        fmt = t("fmt.date") + " %H:%M"
        print("\n" + t("cli.import.date_before_newest", export=datetime.fromisoformat(stats.export_date).strftime(fmt),
                        newest=stats.newest.strftime(fmt), suggest=stats.newest.replace(microsecond=0).isoformat()) + "\n")


def _print_left_out(found, unused_categories: list[str]) -> None:
    """One line at the end of each import: what CEV did not take, and why (AE-f2)."""
    sep = t("fmt.list_sep")

    def counted(counter) -> str:
        return sep.join(k if n == 1 else f"{k} ×{n}" for k, n in sorted(counter.items()))

    left = pop_left_out()
    items = []
    if unused_categories:
        items.append(t("cli.left_out.categories", names=sep.join(unused_categories)))
    files = file_categories(found.others)
    if files:
        items.append(t("cli.left_out.files", names=counted(files)))
    if left.duplicates:
        items.append(t("cli.left_out.duplicates", n=left.duplicates))
    if left.unknown_blocks:
        items.append(t("cli.left_out.blocks", types=counted(left.unknown_blocks)))
    if left.broken_blocks:
        items.append(t("cli.left_out.broken", n=left.broken_blocks))
    print("  " + (t("cli.left_out", items=t("cli.left_out.sep").join(items)) if items else t("cli.left_out.nothing")))


def _find_user_files(archive: Archive, site: Path) -> None:
    """Associate the links of the conversations with the user's files and copy them into the site (see userfiles)."""
    def say(names: int, wanted: int, folders: list[Path]) -> None:
        print(t("cli.files.search", n=names, folders=" ; ".join(str(f) for f in folders) or "-"), flush=True)

    try:
        n = userfiles.update(archive, site, settings.file_folders(site), skip=[_program_path().parent], say=say)
    except OSError as exc:
        print("  " + t("cli.error", message=exc))
        return
    if n:
        print("  " + t("cli.files.found", n=n))


def _install_icon(site: Path, program: Path) -> None:
    """The icon of the archives (menu and desktop), opening ``site`` with ``program``."""
    from .desktop import install_launcher, install_windows

    if system.WINDOWS:
        try:
            written = install_windows(site, program)
        except OSError as exc:
            _err(str(exc))
            sys.exit(1)
        done = "cli.icon.done_windows"
    elif sys.platform.startswith("linux"):
        written, done = install_launcher(site, program), "cli.icon.done"
    else:
        _err(t("cli.icon.unsupported"))
        sys.exit(1)
    for path in written:
        print(t("cli.icon.created", path=path))
    print(t(done, name=t("desktop.name")))


def _install(args: argparse.Namespace) -> None:
    """--installer (P2, 11/11): the program to its place (an earlier version replaced), the icon, then the archives
    opened by the program installed (a server of the earlier version is stopped by that launch)."""
    import subprocess

    from . import install, office_export

    program = _program_path()
    dest = install.target()
    try:
        moved = install.place_program(program.parent, dest, args.output)
    except install.InstallError as exc:
        _err(t(exc.key, folder=exc.folder))
        sys.exit(1)
    except OSError as exc:
        _err(t("cli.error", message=exc))
        sys.exit(1)
    print(t("cli.install.copied" if moved else "cli.install.same", folder=dest))
    _install_icon(args.output, dest / install.LAUNCHER)
    if office_export.pandoc_path() is None:
        print(t("cli.install.pandoc", hint=system.pandoc_hint()))
    if not args.no_browser:
        print(t("cli.install.opening", folder=args.output))
        subprocess.Popen([system.windowless_python(), str(dest / install.LAUNCHER), "-o", str(args.output), "--ouvrir"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=not system.WINDOWS, **system.no_window())


def _ask(question: str, default: bool) -> bool:
    """A yes / no question in the terminal (the default with Enter)."""
    yes, no = t("cli.yes_letter"), t("cli.no_letter")
    answer = input(f"{question} [{yes.upper() if default else yes}/{no if default else no.upper()}] ").strip().lower()
    return default if not answer else answer.startswith(yes)


def _uninstall(args: argparse.Namespace) -> None:
    """--desinstaller (AF-m1, 14/11): the same steps as the button of the index, asked in the terminal."""
    from . import uninstall
    from .server import stop_running

    if not sys.stdin.isatty():
        _err(t("uninstall.needs_terminal"))
        sys.exit(1)
    for url in stop_running(args.output):
        print(t("cli.server.old_stopped", url=url))
    site = args.output.expanduser().resolve()
    if (site / "archive").is_dir():  # AE-m10: what is copied is checked first
        if verify.check(site, _say).problems:
            print(t("verify.uninstall_warn"))
            if not _ask(t("verify.uninstall_ask"), False):
                print(t("uninstall.cancelled"))
                return
    sizes = uninstall.copy_sizes(site)
    try:
        dest = uninstall.copies_dir(site)
    except backup.BackupError as exc:
        _err(t(exc.key))
        sys.exit(1)
    print(t("uninstall.copies_head", path=dest))
    what = [w for w in uninstall.COPIES
            if sizes[w] and _ask(t(f"uninstall.copy.{w}", size=_mb(sizes[w])), True)]
    entries = uninstall.targets(site)
    print(t("uninstall.removed_head"))
    for e in entries:
        print(f"  {e['path']}  ({_mb(e['size'])} Mo)")
    print(t("uninstall.browser_note"))
    if not _ask(t("uninstall.confirm"), False):
        print(t("uninstall.cancelled"))
        return
    say = lambda key, a: print("  " + t(key, **a), flush=True)  # noqa: E731
    lock = ArchiveLock(site).acquire(on_wait=lambda: print(t("cli.archive.busy"), flush=True))
    try:
        uninstall.make_copies(Archive(site), site, dest, what, say)
    except uninstall.UninstallError as exc:
        _err(t(exc.key, **exc.args_))
        _err(t("uninstall.nothing_removed"))
        sys.exit(1)
    finally:
        lock.release()
    failed = uninstall.remove(entries, say)
    print(t("uninstall.done_some" if failed else "uninstall.done", path=dest))


def _say(key: str, args: dict) -> None:
    print(("" if key == "verify.start" else "  ") + t(key, **args), flush=True)


def _ask_too_big(sizes: list[int]) -> None:
    """Messages set aside, too big for the free memory (21/11): how to read them all the same (the page asks)."""
    if not sizes:
        return
    from . import loader
    size = max(sizes) // 2**20 + 1
    need = size * loader._READ_FACTOR
    free = (system.available_memory() or 0) // 2**20
    print("\n" + t("cli.import.too_big", n=len(sizes), size=size, need=need, free=free) + "\n", flush=True)
    if os.environ.get("CEV_PROGRESS"):
        print(f"{BIG_MARK}{size} {need} {free}", flush=True)


def _ask_date(q) -> None:
    """An export date beyond the computer's clock: the three dates and the two ways out (the page asks instead)."""
    fmt = t("fmt.date") + " %H:%M"
    newest = q.newest.strftime(fmt) if q.newest else t("cli.import.date_unknown")
    suggest = q.newest.replace(microsecond=0).isoformat() if q.newest else "?"
    print("\n" + t("cli.import.date_future", export=q.export.strftime(fmt), clock=q.clock.strftime(fmt), newest=newest,
                    suggest=suggest) + "\n", flush=True)
    if os.environ.get("CEV_PROGRESS"):
        stamp = lambda d: d.replace(microsecond=0).isoformat() if d else "-"  # noqa: E731
        print(f"{DATE_MARK}{stamp(q.export)} {stamp(q.clock)} {stamp(q.newest)}", flush=True)


def _verify(args: argparse.Namespace) -> None:
    """--verifier / --reparer (AE-m10): every file of the archive read again (verify.py); the conversations unreadable
    or missing made again from the exports kept, asked in a terminal (--reparer: without asking), then their pages."""
    site = args.output
    if not (site / "archive").is_dir():
        _err(t("cli.no_input", folder=site))
        sys.exit(1)
    start = time.monotonic()
    lock = ArchiveLock(site).acquire(on_wait=lambda: print(t("cli.archive.busy"), flush=True))
    try:
        report = verify.check(site, _say)
        n = report.n_repairable  # conversations to make again, exports to redate (review of 21/11)
        if not n:
            return
        if os.environ.get("CEV_PROGRESS"):  # run by the server: the button "Réparer" of the page
            print(f"{verify.REPAIRABLE_MARK}{n}", flush=True)
        if not (args.repair or (sys.stdin.isatty() and _ask(t("verify.repair_ask", n=n), True))):
            return
        done = verify.redate(site, report.redate, _say) if report.redate else 0
        if report.repairable:
            done += verify.repair(site, report.repairable, _say)
        if done:
            _render_site(args, Archive(site), start)
    finally:
        lock.release()


def _mb(size: int) -> str:
    return f"{size / 1e6:.1f}".replace(".", t("fmt.decimal"))


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    system.safe_console()
    i18n.set_language(_language_from(argv) or i18n.detect())
    args = _parser().parse_args(argv)
    if args.output is None:  # the usual place of the archives (was "site/" in the current folder)
        args.output = Path.home() / "claude_site"

    if args.restore is not None:  # AF-m1 (14/11): the ZIP of a site put back, then the archives opened
        from . import uninstall

        try:
            uninstall.restore(args.restore, args.output, say=lambda key, a: print(t(key, **a)))
        except uninstall.UninstallError as exc:
            _err(t(exc.key, **exc.args_))
            sys.exit(1)
        args.open_mode = True
    if args.uninstall:
        _uninstall(args)
        return
    if args.verify or args.repair:
        _verify(args)
        return
    try:
        archive = Archive(args.output)
    except ArchiveError as exc:
        _err(t("cli.error", message=exc))
        sys.exit(1)
    if args.export_all:
        from . import allexport

        try:
            allexport.build_all(archive, args.output, say=lambda key, a: print(t(key, **a), flush=True))
        except (OSError, backup.BackupError) as exc:
            _err(t(exc.key) if isinstance(exc, backup.BackupError) else t("cli.error", message=exc))
            sys.exit(1)
        return
    if archive.interrupted_import:  # a cut import: the same export imported again completes the archive
        _err(t("cli.import.interrupted", date=i18n.Day(archive.interrupted_import["date"][:10])))
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
    if args.backup and not args.inputs:
        if not archive.exists:
            _err(t("cli.no_input", folder=args.output))
            sys.exit(1)
        held = ArchiveLock(args.output).acquire(on_wait=lambda: print(t("cli.archive.busy"), flush=True))  # noqa: F841 - kept while the ZIP is written
        if verify.check(args.output, _say).problems:  # AE-m10: the backup is made all the same
            print(t("verify.backup_warn"))
        try:
            backup.make_backup(args.output, say=lambda key, a: print(t(key, **a)))
        except backup.BackupError as exc:
            _err(t(exc.key))
            sys.exit(1)
        except OSError as exc:
            _err(t("backup.failed", error=exc))
            sys.exit(1)
        return
    if args.structure and not args.inputs:
        _err(t("cli.structure.no_input"))
        sys.exit(1)
    if (not args.inputs and not archive.exists and not (args.structure or args.install_icon or args.installer or args.backup
                                                        or args.odt or args.docx or args.txt or args.downloads)):
        args.open_mode = True  # nothing yet: the archives open on their welcome page, as with the icon
    first_run = not args.inputs and not archive.exists and (args.open_mode or args.serve is not None)
    if not args.inputs and not archive.exists and not args.structure and not args.install_icon and not args.installer and not first_run:
        _err(t("cli.no_input", folder=args.output))
        sys.exit(1)

    if args.structure:
        _print_structure(args.inputs)
        return

    if args.installer:
        _install(args)
        return
    if args.install_icon:
        _install_icon(args.output, _program_path())
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

    if args.odt or args.docx or args.txt:
        fmt = "odt" if args.odt else "docx" if args.docx else "txt"
        _export_one(archive, args.odt or args.docx or args.txt, fmt, args.export_dir, versions=not args.main_thread)
        return

    start = time.monotonic()
    open_index = False

    manifest = fetch.manifest_from_inputs(args.inputs) if args.inputs else None
    unused_categories: list[str] = []
    if manifest:
        print(t("cli.manifest.name", name=manifest.path.name))
        print("  " + t("cli.manifest.dates", created=manifest.created_at, expires=manifest.expires_at))
        timeout = args.timeout if args.timeout is not None else (900 if args.manual else 300)
        try:
            result = fetch.fetch_export(
                manifest,
                args.output,
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
        keep = set(fetch.USED_CATEGORIES)
        unused_categories = sorted(c for c in result.files if c and c not in keep)
        args.inputs = [p for c, paths in result.files.items() if c in keep for p in paths]
        if result.manifest_copy:
            args.inputs.append(result.manifest_copy)
        open_index = not args.no_browser

    if args.open_mode and not args.inputs:
        # AF-m1 (14/11): opened without an import (the icon, --installer): the server answers at once and the browser
        # shows the progress while the pages are made again (all of them after an update of the program)
        from .server import serve

        def build(report: Callable[[int, int], None]) -> None:
            lock = ArchiveLock(args.output).acquire(on_wait=lambda: print(t("cli.archive.busy"), flush=True))
            try:
                _render_site(args, Archive(args.output), start, report)
            finally:
                lock.release()

        serve(args.output, args.serve or 8000, None if args.no_browser else fetch.browser_opener(args.browser),
              idle_minutes=args.idle, launcher=_program_path(), build=build)
        return

    # Import and site: one program at a time (another import, a rebuild, the server's actions)
    lock = ArchiveLock(args.output).acquire(on_wait=lambda: print(t("cli.archive.busy"), flush=True))
    try:
        archive = Archive(args.output)  # read again: the other program may have changed it
    except ArchiveError as exc:
        _err(t("cli.error", message=exc))
        sys.exit(1)
    if args.message_limit:
        from . import loader
        loader.MESSAGE_LIMIT = args.message_limit << 20  # (21/11) the user agreed to read bigger messages
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
        question = None if args.date_confirmed else date_question(found, date)
        if question is not None:  # (review of 21/11) the export date or the clock is wrong: nothing imported, asked
            _ask_date(question)
            lock.release()
            sys.exit(3)

        users = {u.uuid: u.full_name for u in load_users(found)}
        pop_left_out()
        pop_read_errors()  # (the date may have been looked for in the same files)
        pop_too_big()
        try:
            stats = archive.import_export(
                iter_conversation_spools(found.conversations, archive.temp_dir),  # never a conversation whole (21/11)
                date,
                label=", ".join(s.label for s in found.conversations),
                skip_empty=not args.keep_empty,
                users=users,
                projects=load_project_names(found),
                read_ok=lambda: not pop_read_errors(),
            )
        except DiskFull as exc:  # (review of 21/11) the archive left as by an import cut short: imported again later
            _err(str(exc))
            lock.release()
            sys.exit(1)
        archive.save()
        print_warnings()
        _print_import_stats(stats, start)
        _ask_too_big(pop_too_big())
        _print_left_out(found, unused_categories)

    _render_site(args, archive, start)
    index = (args.output / "index.html").resolve()
    lock.release()
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


def _render_site(args: argparse.Namespace, archive: Archive, start: float,
                 report: Callable[[int, int], None] | None = None) -> None:
    """The pages and the index from the archive (changed pages only, all of them after an update of the program);
    report(n, total): the progress, for the page shown by the server meanwhile (AF-m1)."""
    render_start = time.monotonic()
    total = len(archive.conversations)
    marks = bool(os.environ.get("CEV_PROGRESS"))  # run by the server (an import): the bar of its page (15/11)
    if report is not None:
        report(0, total)  # (the search of the user's files comes first)
    if marks:
        print(f"\x1fCEV-PROGRESS 0 {total}", flush=True)

    def progress(n: int) -> None:
        if report is not None:
            report(n, total)
        if marks:
            print(f"\x1fCEV-PROGRESS {n} {total}", flush=True)
        if n % 50 == 0:
            print("  " + t("cli.render.progress", n=n, seconds=f"{time.monotonic() - render_start:.0f}"), flush=True)

    _find_user_files(archive, args.output)
    from . import speech

    speech.drop_old_cache(args.output)  # the sounds kept in the site up to 2026.11.7
    print(t("cli.render.start", folder=args.output))
    render = build_site_from_archive(archive, args.output, force=args.rebuild, progress=progress)
    summary = t("cli.render.done", seconds=f"{time.monotonic() - start:.0f}",
                pages=t("cli.render.pages", n=render.rendered), conversations=t("cli.render.total", n=render.total))
    if render.deleted:
        summary += " " + t("cli.render.deleted", n=render.deleted)
    print(summary + t("fmt.period"))
    if render.failed:
        print("  " + t("cli.render.failed", n=render.failed))


if __name__ == "__main__":
    main()
