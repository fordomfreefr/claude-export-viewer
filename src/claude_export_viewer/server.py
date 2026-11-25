"""Small local web server for the site.

    python3 claude-export-viewer.py -o ~/claude_site --serveur     (stays until Ctrl + C)
    python3 claude-export-viewer.py -o ~/claude_site --ouvrir      (what the desktop icon runs)

It listens on 127.0.0.1 only and:

- serves the site's pages (the raw archive is not served);
- answers /export/<page>.<md|odt|docx|txt> (Pandoc conversion);
- runs, on request from the index page, a background job importing a new
  export (latest manifest in the Downloads folder);
- with --ouvrir, stops by itself after a period without any open page.

The import (which changes the archive) requires a secret token that only
pages served by this server can read, and are refused when the request comes
from another site (Origin / Host checks), so that no web page opened in the
browser can trigger them.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import (__version__, allexport, annotations, attachments, backup, cdn_cache, drop, esm_cache, extras, fetch, i18n, office_export, settings, system, topics,
               speech, uninstall, userfiles, verify, zipexport)
from .loader import BIG_MARK, DATE_MARK
from .archive import Archive, ArchiveBusy, ArchiveError, ArchiveLock
from .i18n import t

CONTENT_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "odt": "application/vnd.oasis.opendocument.text",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain; charset=utf-8",
}
_EXPORT = re.compile(r"/export/([A-Za-z0-9_.-]{1,120})\.(md|odt|docx|txt)")
APP_ID = "claude-export-viewer"


# --- Background jobs (import, update) -------------------------------------------


class Job:
    def __init__(self, kind: str, lang: str | None = None) -> None:
        self.kind = kind
        self.lang = i18n.normalize(lang) or i18n.language()  # language of the page that started it
        self.lines: list[str] = []
        self.progress: list[int] | None = None  # [n, total]: the pages made again (15/11, run_streaming)
        self.extra: dict[str, Any] = {}  # AE-m10: {"repairable": n} (verification), {"problems": n} (uninstall)
        self.done = False
        self.ok = False
        self.lock = threading.Lock()

    def say(self, line: str) -> None:
        with self.lock:
            self.lines.append(line.rstrip("\n"))

    def finish(self, ok: bool) -> None:
        with self.lock:
            self.done, self.ok = True, ok

    def state(self, since: int = 0) -> dict:
        with self.lock:
            return {"kind": self.kind, "lines": self.lines[since:], "next": len(self.lines),
                    "done": self.done, "ok": self.ok, "progress": self.progress,
                    "extra": dict(self.extra)}


PROGRESS_MARK = "\x1fCEV-PROGRESS "


def run_streaming(cmd: list[str], job: Job) -> int:
    # UTF-8 both ways: on Windows a pipe would otherwise use the ANSI code page
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "CEV_LANG": job.lang,
           "CEV_PROGRESS": "1"}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                            env=env, bufsize=1, **system.no_window())
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.startswith(PROGRESS_MARK):  # "<mark> n total" (cli._render_site): the bar of the page, not the log
            try:
                n, total = map(int, line[len(PROGRESS_MARK):].split())
            except ValueError:
                continue
            with job.lock:
                job.progress = [n, total]
            continue
        if line.startswith(BIG_MARK):  # "<mark> size need free" (cli._ask_too_big): the question of the page
            parts = (line[len(BIG_MARK):].split() + ["0", "0", "0"])[:3]
            with job.lock:
                job.extra["big_message"] = dict(zip(("size", "need", "free"), (int(x) if x.isdigit() else 0 for x in parts)))
            continue
        if line.startswith(DATE_MARK):  # "<mark> export clock newest" (cli._ask_date): the question of the page
            parts = (line[len(DATE_MARK):].split() + ["-", "-", "-"])[:3]
            with job.lock:
                job.extra["date_question"] = {"export": parts[0], "clock": parts[1],
                                              "newest": "" if parts[2] == "-" else parts[2]}
            continue
        if line.startswith(verify.REPAIRABLE_MARK):  # "<mark> n" (cli._verify): the button "Réparer" of the page
            with job.lock:
                job.extra["repairable"] = int(line[len(verify.REPAIRABLE_MARK):].strip() or 0)
            continue
        job.say(line)
    return proc.wait()


def _folders(value: Path | list[Path]) -> list[Path]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _run_import(job: Job, ctx: ServerContext, args: list[str]) -> int:
    """The import of ``args`` (folders or files of the export); when the export date is beyond the clock, the
    command is kept for the answer of the page (POST /__cev__/import-date)."""
    code = run_streaming([system.console_python(), "-u", str(ctx.launcher), *args, "-o", str(ctx.site_dir),
                          "--sans-navigateur"], job)
    question, big = job.extra.get("date_question"), job.extra.get("big_message")
    ctx.pending_import = {"args": list(args), "newest": question["newest"] if question else "",
                          "big": big["size"] if big else 0} if question or big else None
    return code


def date_job(job: Job, ctx: ServerContext, choice: str) -> None:
    """The import asked again after the question on its date: with the date of the export ("export") or of its newest
    conversation ("newest"); either way confirmed (--date-confirmee)."""
    pending, ctx.pending_import = ctx.pending_import, None
    if pending is None:
        job.finish(False)
        return
    args = list(pending["args"])
    if choice == "big":  # a message set aside: read it all the same (21/11)
        args += ["--limite-message", str(pending["big"] + 1)]
    else:
        args.append("--date-confirmee")
        if choice == "newest" and pending["newest"]:
            args += ["--date-export", pending["newest"]]
    job.finish(_run_import(job, ctx, args) == 0)


def import_job(job: Job, ctx: ServerContext) -> None:
    folders = _folders(ctx.downloads())
    found = [m for m in (fetch.latest_manifest(f) for f in folders if f.is_dir()) if m is not None]
    manifest = max(found, key=lambda m: m.created_at) if found else None
    if manifest is None:
        job.say(t("server.no_manifest", job.lang, folder=" ; ".join(str(f) for f in folders)))
        for step in ("server.step1", "server.step2", "server.step3", "server.step4"):
            job.say(t(step, job.lang))
        job.finish(False)
        return
    job.finish(_run_import(job, ctx, [str(manifest.path.parent)]) == 0)


def files_job(job: Job, ctx: ServerContext) -> None:
    """Look again for the files of the conversations, then update the site (no import)."""
    code = run_streaming([system.console_python(), "-u", str(ctx.launcher), "-o", str(ctx.site_dir),
                          "--sans-navigateur"], job)
    job.finish(code == 0)


def backup_job(job: Job, ctx: ServerContext) -> None:
    """The whole site folder in one dated ZIP (see backup.py); never during an import (one job at a time)."""
    lock = ArchiveLock(ctx.site_dir).acquire(on_wait=lambda: job.say(t("cli.archive.busy", job.lang)))
    try:
        if verify.check(ctx.site_dir, lambda key, args: job.say(t(key, job.lang, **args))).problems:  # AE-m10
            job.say(t("verify.backup_warn", job.lang))
        backup.make_backup(ctx.site_dir, say=lambda key, args: job.say(t(key, job.lang, **args)))
    except backup.BackupError as exc:
        job.say(t(exc.key, job.lang))
        job.finish(False)
        return
    except OSError as exc:
        job.say(t("backup.failed", job.lang, error=exc))
        job.finish(False)
        return
    finally:
        lock.release()
    job.finish(True)


def verify_job(job: Job, ctx: ServerContext, repair: bool = False) -> None:
    """AE-m10: "Vérifier l'archive" (cli._verify); with repair, the conversations repairable made again, then their pages."""
    code = run_streaming([system.console_python(), "-u", str(ctx.launcher), "-o", str(ctx.site_dir),
                          "--reparer" if repair else "--verifier"], job)
    job.finish(code == 0)


def export_all_job(job: Job, ctx: ServerContext) -> None:
    """All the conversations in Markdown in one dated ZIP (AE-m11, allexport.py), in the folder of the backups."""
    lock = ArchiveLock(ctx.site_dir).acquire(on_wait=lambda: job.say(t("cli.archive.busy", job.lang)))
    try:
        allexport.build_all(Archive(ctx.site_dir), ctx.site_dir, lang=job.lang,
                            say=lambda key, args: job.say(t(key, job.lang, **args)))
    except backup.BackupError as exc:
        job.say(t(exc.key, job.lang))
        job.finish(False)
        return
    except OSError as exc:
        job.say(t("backup.failed", job.lang, error=exc))
        job.finish(False)
        return
    finally:
        lock.release()
    job.finish(True)


def uninstall_job(job: Job, ctx: ServerContext, data: dict[str, Any]) -> None:
    """AF-m1 (14/11): the copies ticked, then everything CEV wrote removed (uninstall.py); nothing is removed when a
    copy failed. The server stops a few seconds after the end (its page has read the last lines)."""
    say = lambda key, args: job.say(t(key, job.lang, **args))  # noqa: E731
    program = ctx.launcher.parent
    what = [w for w in data.get("copies") or [] if w in uninstall.COPIES]
    lock = ArchiveLock(ctx.site_dir).acquire(on_wait=lambda: job.say(t("cli.archive.busy", job.lang)))
    try:
        if (ctx.site_dir / "archive").is_dir() and not data.get("ignore_problems"):  # AE-m10: checked first
            problems = verify.check(ctx.site_dir, say).problems
            if problems:
                say("verify.uninstall_warn", {})
                say("verify.uninstall_stop", {})
                with job.lock:
                    job.extra["problems"] = problems  # the page asks "Désinstaller quand même ?"
                job.finish(False)
                return
        dest = Path(str(data.get("dest") or uninstall.copies_dir(ctx.site_dir)))
        uninstall.make_copies(Archive(ctx.site_dir), ctx.site_dir, dest, what, say, program=program, lang=job.lang)
    except uninstall.UninstallError as exc:
        say(exc.key, exc.args_)
        say("uninstall.nothing_removed", {})
        job.finish(False)
        return
    except backup.BackupError as exc:
        say(exc.key, {})
        job.finish(False)
        return
    finally:
        lock.release()
    failed = uninstall.remove(uninstall.targets(ctx.site_dir, program), say)
    say("uninstall.done_some" if failed else "uninstall.done", {"path": str(dest) if what else "—"})
    job.finish(True)
    if ctx.server is not None:
        threading.Timer(4.0, ctx.server.shutdown).start()


def restore_job(job: Job, ctx: ServerContext, zip_path: Path) -> None:
    """The ZIP of a site put back into an empty Library (uninstall.restore), then its pages made again."""
    try:
        uninstall.restore(zip_path, ctx.site_dir, say=lambda key, a: job.say(t(key, job.lang, **a)))
    except uninstall.UninstallError as exc:
        job.say(t(exc.key, job.lang, **exc.args_))
        job.finish(False)
        return
    code = run_streaming([system.console_python(), "-u", str(ctx.launcher), "-o", str(ctx.site_dir),
                          "--sans-navigateur"], job)
    job.finish(code == 0)


def drop_job(job: Job, ctx: ServerContext, drop_id: str) -> None:
    """Import the files dropped on the index (see drop.py); the staging folder is removed at the end."""
    try:
        folder = drop.staging(ctx.site_dir, drop_id)
        zips = [f for f in folder.iterdir() if f.suffix.lower() == ".zip"] if folder.is_dir() else []
        backups = [z for z in zips if uninstall.backup_root(z)]
        if backups:  # AF-m1 (14/11): the ZIP of a site (a backup): put back, then the pages made again
            restore_job(job, ctx, backups[0])
            return
        args = drop.plan(ctx.site_dir, drop_id, lambda key, **a: job.say(t(key, job.lang, **a)))
        if args is None:
            job.finish(False)
            return
        job.finish(_run_import(job, ctx, args) == 0)  # (args: the files stored in archive/exports)
    finally:
        shutil.rmtree(drop.staging(ctx.site_dir, drop_id), ignore_errors=True)


# --- Server --------------------------------------------------------------------


def _program_signature() -> str:
    from .html_builder import generator_signature

    return generator_signature()


class ServerContext:
    def __init__(self, site_dir: Path, launcher: Path, idle_minutes: float | None) -> None:
        self.site_dir = Path(site_dir).resolve()
        self.launcher = Path(launcher).resolve()
        self.idle = idle_minutes * 60 if idle_minutes else None
        self.token = secrets.token_urlsafe(24)
        self.instance = secrets.token_hex(8)  # changes at every (re)start
        # Code the server is running: compared by a new launch of the program, so that a
        # server started before a program update is replaced instead of reused.
        self.program = _program_signature()
        self.last_activity = time.monotonic()
        self.job: Job | None = None
        self.job_lock = threading.Lock()
        self.pending_import: dict[str, Any] | None = None  # an import waiting for the answer on its date
        # AF-m1 (14/11): the pages made again after an update, while the server already answers (serve(build=…)):
        # {"n", "total", "done", "error"}; the index is then a page of progress (_BUILDING_PAGE)
        self.building: dict[str, Any] | None = None
        self.server: ThreadingHTTPServer | None = None
        # folders searched for a manifest (the one set in the index first)
        self.downloads: Callable[[], Path | list[Path]] = lambda: settings.search_folders(self.site_dir)

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def start_job(self, kind: str, target: Callable[[Job, ServerContext], None],
                  lang: str | None = None) -> Job | None:
        with self.job_lock:
            if self.job is not None and not self.job.done:
                return None
            job = self.job = Job(kind, lang)

        def run() -> None:
            try:
                target(job, self)
            except Exception as exc:  # noqa: BLE001 - shown in the page
                job.say(t("server.unexpected", job.lang, error=exc))
                job.finish(False)

        threading.Thread(target=run, daemon=True).start()
        return job


class SiteHandler(SimpleHTTPRequestHandler):
    ctx: ServerContext

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    _cache_set = False

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "cache-control":
            self._cache_set = True
        super().send_header(keyword, value)

    def end_headers(self) -> None:
        # Pages and scripts change with each program version: the browser must check
        # them again instead of reusing an old copy from its cache.
        if not self._cache_set:
            self.send_header("Cache-Control", "no-cache")
        self._cache_set = False
        super().end_headers()

    # -- helpers
    def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _local_request(self) -> bool:
        """Host must be our own address (DNS rebinding), Origin absent or our own (other sites)."""
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in allowed:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{a}" for a in allowed}

    def _lang(self) -> str:
        """Language of the page making the request (X-CEV-Lang header or ?lang=)."""
        query = dict(p.split("=", 1) for p in urlparse(self.path).query.split("&") if "=" in p)
        return i18n.normalize(self.headers.get("X-CEV-Lang") or query.get("lang")) or i18n.language()

    def _in_archive(self) -> bool:
        """True for a request reaching the private archive folder, however the path is written
        ("/archive/…", "/x/../archive/…", "%2e%2e"…): checked on the file that would be served."""
        try:
            target = Path(self.translate_path(self.path)).resolve()
        except (OSError, ValueError):
            return True
        archive = (self.ctx.site_dir / "archive").resolve()
        return target == archive or archive in target.parents

    def _authorized(self) -> bool:
        return self._local_request() and secrets.compare_digest(self.headers.get("X-CEV-Token", ""), self.ctx.token)

    # -- routes
    def _host_ok(self) -> bool:
        """The Host header names this server (127.0.0.1 or localhost and its port), else 403 (11/11)."""
        port = self.server.server_address[1]
        if self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            return True
        self._text(403, t("server.refused", self._lang()))
        return False

    def list_directory(self, path: Any) -> None:  # no listing of a folder
        self._text(404, t("server.unknown", self._lang()))
        return None

    def do_HEAD(self) -> None:  # noqa: N802
        if not self._host_ok():
            return
        if self._in_archive():
            self._text(403, t("server.denied", self._lang()))
            return
        super().do_HEAD()

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return
        self.ctx.touch()
        url = urlparse(self.path)
        path = unquote(url.path)
        if path == "/__cev__/ping":
            self._json(200, {"app": APP_ID, "site": str(self.ctx.site_dir), "version": __version__,
                             "instance": self.ctx.instance, "program": self.ctx.program})
            return
        if path == "/__cev__/build-state":
            self._json(200, self.ctx.building or {"done": True})
            return
        building = self.ctx.building
        if building and not building["done"] and not building["error"] and path in ("/", "/index.html"):
            self._send(200, _building_page().encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/__cev__/token":
            if not self._local_request():
                self._text(403, t("server.refused", self._lang()))
                return
            self._json(200, {"token": self.ctx.token, "version": __version__, "instance": self.ctx.instance})
            return
        if path == "/__cev__/job":
            if not self._authorized():
                self._text(403, t("server.refused", self._lang()))
                return
            job = self.ctx.job
            try:
                since = max(0, int(dict(p.split("=", 1) for p in url.query.split("&") if "=" in p).get("since", "0")))
            except ValueError:
                since = 0
            self._json(200, job.state(since) if job else {"kind": None, "lines": [], "next": 0, "done": True})
            return
        if path == "/__cev__/settings":
            if not self._authorized():
                self._text(403, t("server.refused", self._lang()))
                return
            folder = settings.downloads_folder(self.ctx.site_dir)
            system = fetch.user_download_dirs()
            self._json(200, {"downloads": str(folder) if folder else "",
                             "system": str(system[0]) if system else str(Path.home()),
                             "file_folders": [str(f) for f in settings.file_folders(self.ctx.site_dir)],
                             "file_folders_set": settings.file_folders_set(self.ctx.site_dir),
                             "site_size": backup.site_size(self.ctx.site_dir)})  # the index may be older than the folder
            return
        if path == "/__cev__/orphans":
            if not self._authorized():
                self._text(403, t("server.refused", self._lang()))
                return
            try:
                found = userfiles.orphans(Archive(self.ctx.site_dir), self.ctx.site_dir)
            except (OSError, ArchiveError) as exc:
                self._text(500, t("cli.error", self._lang(), message=exc))
                return
            self._json(200, {"files": [[rel, size] for rel, size in found], "total": sum(s for _, s in found),
                             "folder": f"{self.ctx.site_dir.name}/{userfiles.FOLDER}"})
            return
        m = _EXPORT.fullmatch(path)
        if m:
            query = url.query.split("&")
            one = next((q[4:] for q in query if q.startswith("msg=")), None)  # one message (PT-m1)
            part = next((q[5:] for q in query if q.startswith("part=") and q[5:].isdigit()), None)  # (21/11)
            self._export(m.group(1), m.group(2), "versions=0" not in query, self._lang(), "annotations=1" in query,
                         unquote(one) if one else None, int(part) if part else None)
            return
        if self._in_archive():
            self._text(403, t("server.denied", self._lang()))
            return
        # Always send the file: a file rewritten within the same second as the copy in the
        # browser (topics-data.js after a change, index.html after an import) would
        # otherwise be answered "304 Not Modified" (dates have a precision of one second).
        del self.headers["If-Modified-Since"]
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            return
        self.ctx.touch()
        path = unquote(urlparse(self.path).path)
        if not self._authorized():  # every POST needs the token of the pages (one check for all, P10 11/11)
            self._text(403, t("server.refused", self._lang()))
            return
        if path == "/__cev__/stop":  # asked by a newer launch of the program
            self._json(200, {"stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == "/__cev__/settings":
            self._save_settings()
            return
        if path == "/__cev__/topics":
            self._change_topics()
            return
        if path == "/__cev__/annotations":
            self._change_annotations()
            return
        if path == "/__cev__/choose-folder":
            self._choose_folder()
            return
        if path == "/__cev__/export-zip":
            self._export_zip()
            return
        if path == "/__cev__/upload":
            self._receive_piece()
            return
        if path == "/__cev__/import-dropped":
            self._import_dropped()
            return
        if path == "/__cev__/open":
            self._open_attachment()
            return
        if path == "/__cev__/link":
            self._link()
            return
        if path == "/__cev__/link-file":
            self._link_file()
            return
        if path == "/__cev__/orphans":
            self._remove_orphans()
            return
        if path == "/__cev__/esm":
            self._esm()
            return
        if path == "/__cev__/artifact":
            self._artifact()
            return
        if path == "/__cev__/cdn":
            self._cdn()
            return
        if path == "/__cev__/speech-cache":
            self._speech_cache()
            return
        if path == "/__cev__/artifacts-cache":
            self._artifacts_cache()
            return
        if path == "/__cev__/has-manifest":
            self._has_manifest()
            return
        if path == "/__cev__/backup-found":  # 15/11: a backup offered on the welcome of an empty Library
            if self._json_body() is None:
                return
            found = None if Archive(self.ctx.site_dir).conversations else uninstall.find_backup(self.ctx.site_dir)
            name = f"{found.parent.name}/{found.name}" if found and found.parent.name.startswith("CEV-sauvegarde-") \
                else found.name if found else ""
            self._json(200, {"path": str(found), "name": name, "size": found.stat().st_size, "n": uninstall.backup_count(found),
                             "date": int(found.stat().st_mtime * 1000)} if found else {})
            return
        if path == "/__cev__/restore":
            data = self._json_body()
            if data is None:
                return
            zip_path = Path(str(data.get("path") or ""))
            if not zip_path.is_absolute() or not uninstall.backup_root(zip_path):
                self._text(400, t("restore.not_backup", self._lang(), path=str(zip_path)))
                return
            job = self.ctx.start_job("restore", lambda j, c: restore_job(j, c, zip_path), self._lang())
            if job is None:
                self._text(409, t("server.busy", self._lang()))
                return
            self._json(202, {"started": "restore"})
            return
        if path == "/__cev__/annotations-copies":  # AF-f5 (15/11): "Récupération des annotations…"
            data = self._json_body()
            if data is None:
                return
            try:
                if data.get("action") == "recover":
                    annotations.recover(self.ctx.site_dir, str(data.get("name") or ""))
            except annotations.AnnotationError as exc:
                self._text(400, t(exc.key, self._lang()))
                return
            except (OSError, ValueError) as exc:
                self._text(500, t("cli.error", self._lang(), message=exc))
                return
            self._json(200, {"now": annotations.counts(annotations.load(self.ctx.site_dir)),
                             "copies": annotations.copies(self.ctx.site_dir)})
            return
        if path == "/__cev__/verify":  # AE-m10: {"repair": bool}
            data = self._json_body()
            if data is None:
                return
            repair = bool(data.get("repair"))
            job = self.ctx.start_job("verify", lambda j, c: verify_job(j, c, repair), self._lang())
            if job is None:
                self._text(409, t("server.busy", self._lang()))
                return
            self._json(202, {"started": "verify"})
            return
        if path == "/__cev__/uninstall-plan":
            self._uninstall_plan()
            return
        if path == "/__cev__/uninstall":
            data = self._json_body()
            if data is None:
                return
            try:
                if data.get("copies"):
                    uninstall.check_dest(Path(str(data.get("dest") or uninstall.copies_dir(self.ctx.site_dir))),
                                         self.ctx.site_dir, self.ctx.launcher.parent)
            except (uninstall.UninstallError, backup.BackupError) as exc:
                self._text(400, t(exc.key, self._lang(), **getattr(exc, "args_", {})))
                return
            job = self.ctx.start_job("uninstall", lambda j, c: uninstall_job(j, c, data), self._lang())
            if job is None:
                self._text(409, t("server.busy", self._lang()))
                return
            self._json(202, {"started": "uninstall"})
            return
        if path == "/__cev__/speak" or path.startswith("/__cev__/speak/"):
            what = path[len("/__cev__/speak/"):] if path != "/__cev__/speak" else ""
            if what in ("", "status", "warm", "install", "voices", "choose", "check", "skip", "installed", "remove"):
                self._speak(what)
                return
        if path == "/__cev__/import-date":  # the answer to the question on the export date (review of 21/11)
            data = self._json_body()
            if data is None:
                return
            choice = data.get("choice")
            if choice not in ("export", "newest", "big") or self.ctx.pending_import is None:
                self._text(400, t("drop.bad_request", self._lang()))
                return
            job = self.ctx.start_job("import", lambda j, c: date_job(j, c, choice), self._lang())
            if job is None:
                self._text(409, t("server.busy", self._lang()))
                return
            self._json(202, {"started": "import"})
            return
        jobs = {"/__cev__/import": ("import", import_job), "/__cev__/files": ("files", files_job),
                "/__cev__/backup": ("backup", backup_job), "/__cev__/export-all": ("export-all", export_all_job)}
        if path not in jobs:
            self._text(404, t("server.unknown", self._lang()))
            return
        kind, target = jobs[path]
        job = self.ctx.start_job(kind, target, self._lang())
        if job is None:
            self._text(409, t("server.busy", self._lang()))
            return
        self._json(202, {"started": kind})

    def _json_body(self) -> dict[str, Any] | None:
        """The JSON object sent with a POST (at most 256 KB: a note of 20 000 characters, escaped); None (and a
        400 answer) otherwise."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= 262144:
                raise ValueError
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeDecodeError):
            self._text(400, t("server.bad_request", self._lang()))
            return None

    def _open_attachment(self) -> None:
        """POST {"path": "attachments/…"}: open a saved document with the program of the computer."""
        data = self._json_body()
        if data is None:
            return
        target = attachments.resolve(self.ctx.site_dir, unquote(str(data.get("path", ""))))
        if target is None:
            self._text(404, t("server.not_in_archive", self._lang()))
            return
        folder = system.runnable(target)  # (25/11) a file that could run: its folder only, never the file
        try:
            system.open_file(target.parent if folder else target)
        except OSError as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, {"opened": str(target), "folder": folder})

    def _change_links(self, key: str, change: Callable[[Archive, str], bool]) -> None:
        """Run ``change(archive, uuid)`` for the page ``key`` (never during a job), then
        regenerate the site (only that page changes); 404 when the page or the link is unknown."""
        with self.ctx.job_lock:
            if self.ctx.job is not None and not self.ctx.job.done:
                self._text(409, t("server.busy", self._lang()))
                return
            try:
                lock = ArchiveLock(self.ctx.site_dir).acquire(wait=False)  # another program writes the archive
            except ArchiveBusy:
                self._text(409, t("server.busy", self._lang()))
                return
            try:
                archive = Archive(self.ctx.site_dir)
                uuid = next((u for u, m in archive.conversations.items()
                             if m["filename"].removesuffix(".html") == key), None)
                if uuid is None or not change(archive, uuid):
                    self._text(404, t("server.not_in_archive", self._lang()))
                    return
                from .html_builder import build_site_from_archive
                build_site_from_archive(archive, self.ctx.site_dir)
            except (OSError, ArchiveError) as exc:
                self._text(500, t("cli.error", self._lang(), message=exc))
                return
            finally:
                lock.release()
        self._json(200, {"done": True})

    def _link(self) -> None:
        """POST {"page", "link", "action": "path" | "none" | "auto", "path"?}: the user's choice for a link
        (a file the menu offered, no file, or the automatic choice again); see userfiles.associate."""
        data = self._json_body()
        if data is None:
            return
        key, link, action, path = data.get("page"), data.get("link"), data.get("action"), data.get("path")
        if not isinstance(key, str) or not isinstance(link, str) or action not in userfiles.ACTIONS \
                or (path is not None and not isinstance(path, str)):
            self._text(400, t("server.bad_request", self._lang()))
            return
        self._change_links(key, lambda archive, uuid: userfiles.associate(archive, self.ctx.site_dir, uuid, link,
                                                                     action, path=path))

    MAX_LINK_FILE = 1024**3  # bytes

    def _link_file(self) -> None:
        """POST ?page=…&link=…&name=… with the file chosen by the user in the browser ("Autre fichier…")."""
        q = parse_qs(urlparse(self.path).query)
        arg = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not arg("page") or not arg("link") or not 0 < length <= self.MAX_LINK_FILE:
            self._text(400, t("server.bad_request", self._lang()))
            return
        folder = drop.depot_dir(self.ctx.site_dir) / ("lien-" + secrets.token_hex(8))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            received = folder / "fichier"
            with received.open("wb") as f:
                left = length
                while left:
                    block = self.rfile.read(min(left, 1 << 20))
                    if not block:
                        raise OSError("connexion interrompue")
                    f.write(block)
                    left -= len(block)
            name = Path(arg("name")).name[:200]

            def change(archive: Archive, uuid: str) -> bool:
                try:
                    return userfiles.associate(archive, self.ctx.site_dir, uuid, arg("link"), "path",
                                               upload=received, upload_name=name)
                finally:  # copied into the site: the staging goes before the answer, not after it
                    shutil.rmtree(folder, ignore_errors=True)

            self._change_links(arg("page"), change)
        except OSError as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _cdn(self) -> None:
        """POST {"urls": [...]}: the libraries of the Internet a page of Claude loads, downloaded once with
        the user's agreement and kept in the archive (cdn_cache.py); answers {"errors": {url: message}}."""
        data = self._json_body()
        if data is None:
            return
        urls = data.get("urls")
        if not isinstance(urls, list) or not 0 < len(urls) <= 20 or not all(cdn_cache.valid_url(u) for u in urls):
            self._text(400, t("server.bad_request", self._lang()))
            return
        self._json(200, {"errors": cdn_cache.download(self.ctx.site_dir, urls)})

    def _esm(self) -> None:
        """POST {"specs": [...]}: the packages of esm.sh a React program of Claude imports, downloaded once with the
        user's agreement and kept in the archive (esm_cache.py); answers {"errors": {specifier: message}}."""
        data = self._json_body()
        if data is None:
            return
        specs = data.get("specs")
        if not isinstance(specs, list) or not 0 < len(specs) <= 20 or not all(esm_cache.valid_spec(s) for s in specs):
            self._text(400, t("server.bad_request", self._lang()))
            return
        self._json(200, {"errors": esm_cache.download(self.ctx.site_dir, specs)})

    def _artifact(self) -> None:
        """POST {"id", "version"}: a version of an artifact of the export (extras.py), extracted once, served by the
        server of the artifacts (another port: another origin); answers {"port", "path"}."""
        data = self._json_body()
        if data is None:
            return
        try:
            folder = extras.extract(self.ctx.site_dir, str(data.get("id")), str(data.get("version")))
        except KeyError:
            self._text(404, t("server.not_in_archive", self._lang()))
            return
        except (ValueError, OSError) as exc:
            self._text(500, str(exc))
            return
        self._json(200, {"port": extras.artifact_server(folder)})

    def _speech_cache(self) -> None:
        """POST {"action": "state" | "clear" | "size", "mb"}: the sounds read aloud kept in the cache folder
        (speech.cache_dir), for the cleaning frame of the index; JSON of speech.cache_state."""
        data = self._json_body()
        if data is None:
            return
        site, action = self.ctx.site_dir, data.get("action")
        try:
            if action == "state":
                self._json(200, speech.cache_state(site))
            elif action == "clear":
                self._json(200, speech.clear_cache(site))
            elif action == "size":
                self._json(200, speech.set_cache_mb(site, data.get("mb")))
            else:
                self._text(400, t("server.bad_request", self._lang()))
        except speech.SpeechError as exc:
            self._text(400, t(exc.key, self._lang(), **exc.args_))

    def _uninstall_plan(self) -> None:
        """POST {} (AF-m1): what the frame "Désinstaller" shows: the copies (their sizes), their folder, what will be
        removed (path, size)."""
        if self._json_body() is None:
            return
        site, program = self.ctx.site_dir, self.ctx.launcher.parent
        try:
            dest = str(uninstall.copies_dir(site))
        except backup.BackupError:
            dest = ""
        self._json(200, {"copies": uninstall.copy_sizes(site, program), "dest": dest,
                         "targets": [{"key": e["key"], "path": str(e["path"]), "size": e["size"]}
                                     for e in uninstall.targets(site, program)]})

    def _has_manifest(self) -> None:
        """POST {} (14/11): is there a manifest in the folders of the downloads? The frame of the import starts the
        import then, or opens the window to choose the files."""
        if self._json_body() is None:
            return
        folders = _folders(self.ctx.downloads())
        found = any(fetch.latest_manifest(f) is not None for f in folders if f.is_dir())
        self._json(200, {"found": found})

    def _artifacts_cache(self) -> None:
        """POST {"action": "state" | "clear"} (AF-f1, 14/11): the versions of artifacts extracted (extras/artifacts/,
        extracted again when opened), for the cleaning frame of the index; JSON {"count", "size"} (+ "removed",
        "freed" after "clear")."""
        data = self._json_body()
        if data is None:
            return
        site, action = self.ctx.site_dir, data.get("action")
        if action == "state":
            self._json(200, extras.extracted_state(site))
        elif action == "clear":
            before = extras.extracted_state(site)
            freed = extras.clear_extracted(site)
            self._json(200, {**extras.extracted_state(site), "removed": before["count"], "freed": freed})
        else:
            self._text(400, t("server.bad_request", self._lang()))

    def _speak(self, what: str) -> None:
        """POST /__cev__/speak {"text", "lang", "role", "cached_only"}: the text read aloud by Piper (speech.py), a
        WAV sound (204: cached_only and not made yet); /speak/status, /speak/warm, /speak/install, /speak/voices
        {"lang"} and /speak/choose {"lang", "role", "voice"}: JSON. 503 and the message for the user when it
        cannot be done."""
        data = self._json_body()
        if data is None:
            return
        lang = i18n.normalize(str(data.get("lang") or ""))
        if not lang:
            self._text(400, t("server.bad_request", self._lang()))
            return
        site = self.ctx.site_dir
        try:
            if what == "status":
                self._json(200, speech.status(site, lang))
            elif what == "warm":
                speech.warm(site, lang)
                self._json(200, {"ok": True})
            elif what == "install":
                self._json(200, {"started": speech.install(site, lang, self._lang())})
            elif what == "voices":
                self._json(200, {"choices": speech.listed(site, lang), "voices": speech.voices(site, lang),
                                 "language": i18n.LANGUAGES.get(lang, lang), "skip": lang in speech.skipped(site)})
            elif what == "check":
                langs = data.get("langs")
                self._json(200, speech.check(site, [i18n.normalize(str(x)) or "" for x in langs]
                                             if isinstance(langs, list) else []))
            elif what == "skip":
                speech.set_skip(site, lang, bool(data.get("on")))
                self._json(200, {"skip": sorted(speech.skipped(site))})
            elif what == "installed":
                self._json(200, {"voices": speech.installed_voices(site)})
            elif what == "remove":
                self._json(200, {"voices": speech.remove_voice(site, data.get("name"), data.get("dir"))})
            elif what == "choose":
                speech.choose(site, lang, str(data.get("role")), str(data.get("voice")))
                self._json(200, speech.status(site, lang))
            else:
                text, role = data.get("text"), data.get("role")
                if not isinstance(text, str) or not text.strip() or role not in speech.ROLES:
                    self._text(400, t("server.bad_request", self._lang()))
                    return
                sound = speech.speak(site, text, lang, role, bool(data.get("cached_only")))
                if sound is None:
                    self.send_response(204)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self._send(200, sound, "audio/wav")
        except speech.SpeechError as exc:
            self._text(503 if exc.key != "server.bad_request" else 400, t(exc.key, self._lang(), **exc.args_))

    def _remove_orphans(self) -> None:
        """POST: remove the copies no link uses any more (see userfiles.orphans); never during a job."""
        with self.ctx.job_lock:
            if self.ctx.job is not None and not self.ctx.job.done:
                self._text(409, t("server.busy", self._lang()))
                return
            try:
                lock = ArchiveLock(self.ctx.site_dir).acquire(wait=False)  # another program writes the site
            except ArchiveBusy:
                self._text(409, t("server.busy", self._lang()))
                return
            try:
                n, size = userfiles.remove_orphans(Archive(self.ctx.site_dir), self.ctx.site_dir)
            except (OSError, ArchiveError) as exc:
                self._text(500, t("cli.error", self._lang(), message=exc))
                return
            finally:
                lock.release()
        self._json(200, {"removed": n, "size": size, "site_size": backup.site_size(self.ctx.site_dir)})

    def _change_topics(self) -> None:
        """POST a change of the topics (see topics.change); answers the new state."""
        data = self._json_body()
        if data is None:
            return
        try:
            known = set(Archive(self.ctx.site_dir).conversations)
            state = topics.change(self.ctx.site_dir, data, known)
        except topics.TopicError as exc:
            self._text(400, t(exc.key, self._lang(), **exc.params))
            return
        except (OSError, ArchiveError) as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, state)

    def _busy(self) -> bool:
        job = self.ctx.job
        return job is not None and not job.done

    def _receive_piece(self) -> None:
        """POST ?id=…&name=…&offset=…[&last=1&mtime=…] with a piece of a dropped file (8 MB at most)."""
        if self._busy():  # an import or a backup is running: the drop waits
            self._text(409, t("server.busy", self._lang()))
            return
        q = parse_qs(urlparse(self.path).query)
        arg = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        try:
            length = int(self.headers.get("Content-Length") or 0)
            offset = int(arg("offset") or 0)
            mtime = float(arg("mtime")) / 1000 if arg("mtime") else None
            if not 0 <= length <= 8 * 1024 * 1024:
                raise ValueError
        except ValueError:
            self._text(400, t("drop.bad_request", self._lang()))
            return
        try:
            size = drop.receive(self.ctx.site_dir, arg("id"), arg("name"), offset, self.rfile, length,
                                arg("last") == "1", mtime)
        except drop.DropError as exc:
            self._text(409 if exc.key == "drop.bad_offset" else 400, t(exc.key, self._lang(), **exc.params))
            return
        except OSError as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, {"size": size})

    def _import_dropped(self) -> None:
        """POST {"id": …}: import the files received for that drop (a job, as the import)."""
        data = self._json_body()
        if data is None:
            return
        try:
            drop_id = data.get("id")
            drop.staging(self.ctx.site_dir, drop_id)
        except drop.DropError as exc:
            self._text(400, t(exc.key, self._lang()))
            return
        job = self.ctx.start_job("drop", partial(drop_job, drop_id=drop_id), self._lang())
        if job is None:
            self._text(409, t("server.busy", self._lang()))
            return
        self._json(202, {"started": "drop"})

    def _change_annotations(self) -> None:
        """POST a change of the annotations (see annotations.change); answers the new state."""
        data = self._json_body()
        if data is None:
            return
        try:
            archive = Archive(self.ctx.site_dir)
            state = annotations.change(self.ctx.site_dir, data, archive.message_source)  # (21/11)
        except annotations.AnnotationError as exc:
            self._text(400, t(exc.key, self._lang()))
            return
        except (OSError, ValueError, ArchiveError) as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, state)

    def _choose_folder(self) -> None:
        """POST {"start": folder}: the folder chosen in a window of the system (ZIP of an export):
        {"folder": path}, {"cancelled": true}, or {"unavailable": true} when no window can be shown."""
        data = self._json_body()
        if data is None:
            return
        start = Path(str(data.get("start") or "")).expanduser()
        if not str(data.get("start") or "") or not start.is_dir():
            start = self.ctx.site_dir
        chosen = system.choose_folder(start, t("web.zip.choose", self._lang()))
        if chosen is None:
            self._json(200, {"unavailable": True, "start": str(start)})
        elif not chosen:
            self._json(200, {"cancelled": True})
        else:
            self._json(200, {"folder": chosen})

    def _export_zip(self) -> None:
        """POST {"key", "format", "versions", "folder"}: the export in a dated ZIP written in that
        folder, with the files it names (zipexport.py): {"path": file written, "warnings": n}."""
        data = self._json_body()
        if data is None:
            return
        lang = self._lang()
        key, fmt, folder = data.get("key"), data.get("format"), data.get("folder")
        if not isinstance(key, str) or fmt not in office_export.FORMATS or not isinstance(folder, str) or not folder:
            self._text(400, t("server.bad_request", lang))
            return
        try:
            archive = Archive(self.ctx.site_dir)
        except ArchiveError as exc:
            self._text(500, t("cli.error", lang, message=exc))
            return
        uuid = next((u for u, m in archive.conversations.items()
                     if m.get("filename", "").removesuffix(".html") == key), None)
        if uuid is None:
            self._text(404, t("server.not_in_archive", lang))
            return
        try:
            blob, name, warnings = zipexport.build(archive, self.ctx.site_dir, uuid, fmt, data.get("versions") is not False,
                                                   lang, data.get("annotations") is True,
                                                   data.get("part") if isinstance(data.get("part"), int) else None)
            out = zipexport.write(blob, Path(folder), name)
        except office_export.PandocMissing:
            self._text(503, t("server.no_pandoc", lang, install=system.pandoc_hint()))
            return
        except FileNotFoundError:
            self._text(400, t("web.zip.no_folder", lang, folder=folder))
            return
        except Exception as exc:  # noqa: BLE001
            self._text(500, t("server.conversion_failed", lang, error=exc))
            return
        self._json(200, {"path": str(out), "warnings": len(warnings)})

    def _save_settings(self) -> None:
        """POST {"downloads": "/path"} ("" = the folder of the system)."""
        data = self._json_body()
        if data is None:
            return
        if "file_folders" in data:
            self._save_file_folders(data["file_folders"])
            return
        value = data.get("downloads", "")
        if not isinstance(value, str):
            self._text(400, t("server.bad_request", self._lang()))
            return
        try:
            folder = settings.set_downloads_folder(self.ctx.site_dir, value)
        except ValueError:
            self._text(400, t("server.bad_folder", self._lang(), folder=value))
            return
        except OSError as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, {"downloads": str(folder) if folder else ""})

    def _save_file_folders(self, value: Any) -> None:
        """{"file_folders": [paths] or null (the default)}."""
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            self._text(400, t("server.bad_request", self._lang()))
            return
        try:
            folders = settings.set_file_folders(self.ctx.site_dir, value)
        except ValueError as exc:
            self._text(400, t("server.bad_folder", self._lang(), folder=exc.args[0]))
            return
        except OSError as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, {"file_folders": [str(f) for f in folders],
                         "file_folders_set": settings.file_folders_set(self.ctx.site_dir)})

    def _export(self, key: str, fmt: str, versions: bool = True, lang: str | None = None, annot: bool = False,
                message: str | None = None, part: int | None = None) -> None:
        lang = lang or i18n.language()
        try:
            archive = Archive(self.ctx.site_dir)
        except ArchiveError as exc:
            self._text(500, t("cli.error", lang, message=exc))
            return
        uuid = next((u for u, m in archive.conversations.items()
                     if m.get("filename", "").removesuffix(".html") == key), None)
        if uuid is None:
            self._text(404, t("server.not_in_archive", lang))
            return
        try:
            result = office_export.convert_archived(
                archive, uuid, fmt, versions, lang,
                annot=office_export.annotations_of(self.ctx.site_dir, uuid) if annot else None, message=message,
                part=part)
        except KeyError:
            self._text(404, t("server.not_in_archive", lang))
            return
        except office_export.PandocMissing:
            self._text(503, t("server.no_pandoc", lang, install=system.pandoc_hint()))
            return
        except Exception as exc:  # noqa: BLE001
            self._text(500, t("server.conversion_failed", lang, error=exc))
            return
        ascii_name = result.filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
        extra = {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(result.filename)}"}
        if result.warnings:
            extra["X-Formulas-Not-Converted"] = str(len(result.warnings))
        self._send(200, result.data, CONTENT_TYPES[fmt], extra)


class _Server(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a second server take a port already in use:
    # the next free port must be chosen instead.
    allow_reuse_address = not system.WINDOWS


def make_server(site_dir: Path, port: int = 8000, tries: int = 10, launcher: Path | None = None,
                idle_minutes: float | None = None) -> ThreadingHTTPServer:
    ctx = ServerContext(site_dir, launcher or Path(sys.argv[0]), idle_minutes)
    drop.clean_all(ctx.site_dir)  # files of a drop interrupted earlier
    handler = partial(type("Handler", (SiteHandler,), {"ctx": ctx}), directory=str(ctx.site_dir))
    last: OSError | None = None
    for p in range(port, port + tries):
        try:
            server = _Server(("127.0.0.1", p), handler)
            server.ctx = ctx  # type: ignore[attr-defined]
            ctx.server = server
            return server
        except OSError as exc:
            last = exc
    raise OSError(t("server.no_port", first=port, last=port + tries - 1)) from last


def _ping_all(site_dir: Path, port: int, tries: int):
    import urllib.request

    site = str(Path(site_dir).resolve())
    for p in range(port, port + tries):
        url = f"http://127.0.0.1:{p}/"
        try:
            with urllib.request.urlopen(url + "__cev__/ping", timeout=1) as r:
                data = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("app") == APP_ID and data.get("site") == site:
            yield url, data


def find_running(site_dir: Path, port: int = 8000, tries: int = 10) -> str | None:
    """URL of a server of this program, running the *current* code, already serving ``site_dir``."""
    current = _program_signature()
    for url, data in _ping_all(site_dir, port, tries):
        if data.get("program") == current:
            return url
    return None


def stop_running(site_dir: Path, port: int = 8000, tries: int = 10) -> list[str]:
    """Stop every server of ``site_dir`` (before uninstalling, AF-m1). Returns their URLs."""
    return stop_outdated(site_dir, port, tries, every=True)


def stop_outdated(site_dir: Path, port: int = 8000, tries: int = 10, every: bool = False) -> list[str]:
    """Stop the servers of ``site_dir`` started by an older version of the program (all of them: ``every``).
    Returns their URLs.

    A server started before an update keeps running the old code in memory (old
    messages, export options ignored): it must not be reused.
    """
    import urllib.request

    current = _program_signature()
    stopped = []
    for url, data in list(_ping_all(site_dir, port, tries)):
        if data.get("program") == current and not every:
            continue
        try:
            with urllib.request.urlopen(url + "__cev__/token", timeout=2) as r:
                token = json.loads(r.read().decode("utf-8"))["token"]
            req = urllib.request.Request(url + "__cev__/stop", method="POST", headers={"X-CEV-Token": token})
            urllib.request.urlopen(req, timeout=2).close()
        except (OSError, ValueError, KeyError):
            continue  # very old server without this route: it stops by itself when idle
        for _ in range(50):  # wait until the port is free
            try:
                urllib.request.urlopen(url + "__cev__/ping", timeout=0.5).close()
            except OSError:
                break
            time.sleep(0.1)
        stopped.append(url)
    return stopped


def _watch_idle(server: ThreadingHTTPServer) -> None:
    ctx: ServerContext = server.ctx  # type: ignore[attr-defined]
    while ctx.idle:
        time.sleep(min(30.0, ctx.idle / 4))
        busy = ctx.job is not None and not ctx.job.done
        if not busy and time.monotonic() - ctx.last_activity > ctx.idle:
            server.shutdown()
            return


_BUILD_KEYS = ("web.build.title", "web.build.why", "web.build.count", "web.build.failed", "web.build.open")


def _building_page() -> str:
    """The page shown instead of the index while the pages are made again (AF-m1, 14/11): self-contained (the site
    is being written), its texts in the 12 languages, the one of the index chosen (localStorage cev-lang, else the
    browser, else the system); it asks /__cev__/build-state twice a second and opens the index when done."""
    texts = {lang: {k: i18n.catalog(lang)[k] for k in _BUILD_KEYS} for lang in i18n.LANGUAGES}
    return (_BUILDING_PAGE.replace("__TEXTS__", json.dumps(texts, ensure_ascii=False))
            .replace("__LANG__", json.dumps(i18n.language())))


_BUILDING_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>…</title>
<style>
 :root { color-scheme: light dark; --bg: #f5f4ef; --text: #2b2a27; --muted: #6b6a65; --bar: #c96442; --track: #e3e1d8; }
 @media (prefers-color-scheme: dark) { :root { --bg: #1a1a1a; --text: #e8e6df; --muted: #a09e97; --track: #333; } }
 body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg);
   color: var(--text); font: 16px/1.5 system-ui, sans-serif; }
 main { width: min(30rem, 90vw); }
 h1 { font-size: 1.3rem; margin: 0 0 0.4rem; } p { color: var(--muted); margin: 0 0 1rem; }
 .track { height: 10px; border-radius: 5px; background: var(--track); overflow: hidden; }
 .bar { height: 100%; width: 0; background: var(--bar); transition: width 0.4s; }
 #count { margin-top: 0.5rem; font-size: 0.9rem; color: var(--muted); font-variant-numeric: tabular-nums; }
 a { color: var(--bar); }
</style></head>
<body><main><h1 id="title"></h1><p id="why"></p><div class="track"><div class="bar" id="bar"></div></div>
<div id="count"></div></main>
<script>
(function () {
  var T = __TEXTS__, lang = __LANG__;
  try { var s = localStorage.getItem("cev-lang"); if (T[s]) { lang = s; } else if (!s) {
    var nav = (navigator.language || "").slice(0, 2); if (T[nav]) { lang = nav; } } } catch (e) { /* no storage */ }
  var t = T[lang] || T.en;
  document.documentElement.lang = lang;
  document.title = t["web.build.title"];
  document.getElementById("title").textContent = t["web.build.title"];
  document.getElementById("why").textContent = t["web.build.why"];
  function fill(s, args) { return s.replace(/\\{(\\w+)\\}/g, function (m, k) { return k in args ? args[k] : m; }); }
  function ask() {
    fetch("/__cev__/build-state", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (st) {
      if (st.error) {
        document.getElementById("count").innerHTML = "";
        document.getElementById("count").appendChild(document.createTextNode(fill(t["web.build.failed"], { error: st.error }) + " "));
        var a = document.createElement("a"); a.href = "index.html"; a.textContent = t["web.build.open"];
        document.getElementById("count").appendChild(a);
        return;
      }
      if (st.done) { location.replace("index.html"); return; }
      var total = Math.max(st.total || 0, 1);
      document.getElementById("bar").style.width = Math.min(100, Math.round(100 * st.n / total)) + "%";
      document.getElementById("count").textContent = fill(t["web.build.count"], { n: st.n, total: st.total });
      setTimeout(ask, 500);
    }).catch(function () { setTimeout(ask, 1000); });
  }
  ask();
})();
</script></body></html>
"""


def serve(site_dir: Path, port: int, opener: Callable[[str], None] | None, idle_minutes: float | None = None,
          launcher: Path | None = None, build: Callable[[Callable[[int, int], None]], None] | None = None) -> None:
    """Serve the site; with build (AF-m1, 14/11): the pages are made again in a thread while the server already
    answers, the index being a page of progress until the end (the browser opened at once, not after the build)."""
    server = make_server(site_dir, port, launcher=launcher, idle_minutes=idle_minutes)
    ctx: ServerContext = server.ctx  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if build is not None:
        state = ctx.building = {"n": 0, "total": 0, "done": False, "error": None}

        def report(n: int, total: int) -> None:
            state["n"], state["total"] = n, total
            ctx.touch()

        def run() -> None:
            try:
                build(report)
            except Exception as exc:  # noqa: BLE001 - shown in the page; the former pages stay readable
                state["error"] = str(exc) or exc.__class__.__name__
                print(t("cli.error", message=state["error"]), file=sys.stderr)
            else:
                state["done"] = True

        builder = threading.Thread(target=run, daemon=True)
        builder.start()
        builder.join(1.5)  # nothing much to do: the index at once, without the page of progress
    print(t("server.available", url=url))
    if idle_minutes:
        print("  " + t("server.idle", minutes=f"{idle_minutes:g}"))
    if office_export.pandoc_path() is None:
        print("  " + t("server.pandoc_missing", install=system.pandoc_hint()))
    if ctx.idle:
        threading.Thread(target=_watch_idle, args=(server,), daemon=True).start()
    if opener:
        opener(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n" + t("server.stopped"), file=sys.stderr)
    finally:
        server.server_close()
