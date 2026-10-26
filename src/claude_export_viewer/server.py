"""Small local web server for the site.

    python3 claude-export-viewer.py -o ~/claude_site --serveur     (stays until Ctrl + C)
    python3 claude-export-viewer.py -o ~/claude_site --ouvrir      (what the desktop icon runs)

It listens on 127.0.0.1 only and:

- serves the site's pages (the raw archive is not served);
- answers /export/<page>.<md|odt|docx> (Pandoc conversion);
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
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from . import __version__, attachments, fetch, i18n, office_export, settings, system, topics, userfiles
from .archive import Archive, ArchiveError
from .i18n import t

CONTENT_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "odt": "application/vnd.oasis.opendocument.text",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_EXPORT = re.compile(r"/export/([A-Za-z0-9_.-]{1,120})\.(md|odt|docx)")
APP_ID = "claude-export-viewer"


# --- Background jobs (import, update) -------------------------------------------


class Job:
    def __init__(self, kind: str, lang: str | None = None) -> None:
        self.kind = kind
        self.lang = i18n.normalize(lang) or i18n.language()  # language of the page that started it
        self.lines: list[str] = []
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
                    "done": self.done, "ok": self.ok}


def run_streaming(cmd: list[str], job: Job) -> int:
    # UTF-8 both ways: on Windows a pipe would otherwise use the ANSI code page
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "CEV_LANG": job.lang}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                            env=env, bufsize=1, **system.no_window())
    assert proc.stdout is not None
    for line in proc.stdout:
        job.say(line)
    return proc.wait()


def _folders(value: Path | list[Path]) -> list[Path]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


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
    code = run_streaming([system.console_python(), "-u", str(ctx.launcher), str(manifest.path.parent), "-o",
                          str(ctx.site_dir), "--sans-navigateur"], job)
    job.finish(code == 0)


def files_job(job: Job, ctx: ServerContext) -> None:
    """Look again for the files of the conversations, then update the site (no import)."""
    code = run_streaming([system.console_python(), "-u", str(ctx.launcher), "-o", str(ctx.site_dir),
                          "--sans-navigateur"], job)
    job.finish(code == 0)


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
    def do_GET(self) -> None:  # noqa: N802
        self.ctx.touch()
        url = urlparse(self.path)
        path = unquote(url.path)
        if path == "/__cev__/ping":
            self._json(200, {"app": APP_ID, "site": str(self.ctx.site_dir), "version": __version__,
                             "instance": self.ctx.instance, "program": self.ctx.program})
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
                             "file_folders_set": settings.file_folders_set(self.ctx.site_dir)})
            return
        m = _EXPORT.fullmatch(path)
        if m:
            self._export(m.group(1), m.group(2), "versions=0" not in url.query.split("&"), self._lang())
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
        self.ctx.touch()
        path = unquote(urlparse(self.path).path)
        if path == "/__cev__/stop":  # asked by a newer launch of the program
            if not self._authorized():
                self._text(403, t("server.refused", self._lang()))
                return
            self._json(200, {"stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == "/__cev__/settings":
            self._save_settings()
            return
        if path == "/__cev__/topics":
            self._change_topics()
            return
        if path == "/__cev__/open":
            self._open_attachment()
            return
        if path == "/__cev__/file":
            self._decide_file()
            return
        jobs = {"/__cev__/import": ("import", import_job), "/__cev__/files": ("files", files_job)}
        if path not in jobs:
            self._text(404, t("server.unknown", self._lang()))
            return
        if not self._authorized():
            self._text(403, t("server.refused", self._lang()))
            return
        kind, target = jobs[path]
        job = self.ctx.start_job(kind, target, self._lang())
        if job is None:
            self._text(409, t("server.busy", self._lang()))
            return
        self._json(202, {"started": kind})

    def _json_body(self) -> dict[str, Any] | None:
        """The JSON object sent with a POST (at most 8 KB); None (and a 400 answer) otherwise."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= 8192:
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
        if not self._authorized():
            self._text(403, t("server.refused", self._lang()))
            return
        data = self._json_body()
        if data is None:
            return
        target = attachments.resolve(self.ctx.site_dir, unquote(str(data.get("path", ""))))
        if target is None:
            self._text(404, t("server.not_in_archive", self._lang()))
            return
        try:
            system.open_file(target)
        except OSError as exc:
            self._text(500, t("cli.error", self._lang(), message=exc))
            return
        self._json(200, {"opened": str(target)})

    def _decide_file(self) -> None:
        """POST {"page": key, "name": file name, "action": "ok" | "reject" | "undo"}: the file found is (not) the right one."""
        if not self._authorized():
            self._text(403, t("server.refused", self._lang()))
            return
        data = self._json_body()
        if data is None:
            return
        key, name, action = data.get("page"), data.get("name"), data.get("action")
        if not isinstance(key, str) or not isinstance(name, str) or action not in userfiles.ACTIONS:
            self._text(400, t("server.bad_request", self._lang()))
            return
        with self.ctx.job_lock:
            if self.ctx.job is not None and not self.ctx.job.done:
                self._text(409, t("server.busy", self._lang()))
                return
            try:
                archive = Archive(self.ctx.site_dir)
                uuid = next((u for u, m in archive.conversations.items()
                             if m["filename"].removesuffix(".html") == key), None)
                if uuid is None or not userfiles.decide(self.ctx.site_dir, uuid, name, action):
                    self._text(404, t("server.not_in_archive", self._lang()))
                    return
                from .html_builder import build_site_from_archive
                build_site_from_archive(archive, self.ctx.site_dir)  # only that page changes
            except (OSError, ArchiveError) as exc:
                self._text(500, t("cli.error", self._lang(), message=exc))
                return
        self._json(200, {"action": action})

    def _change_topics(self) -> None:
        """POST a change of the topics (see topics.change); answers the new state."""
        if not self._authorized():
            self._text(403, t("server.refused", self._lang()))
            return
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

    def _save_settings(self) -> None:
        """POST {"downloads": "/path"} ("" = the folder of the system)."""
        if not self._authorized():
            self._text(403, t("server.refused", self._lang()))
            return
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

    def _export(self, key: str, fmt: str, versions: bool = True, lang: str | None = None) -> None:
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
            result = office_export.convert_archived(archive, uuid, fmt, versions, lang)
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


def stop_outdated(site_dir: Path, port: int = 8000, tries: int = 10) -> list[str]:
    """Stop the servers of ``site_dir`` started by an older version of the program. Returns their URLs.

    A server started before an update keeps running the old code in memory (old
    messages, export options ignored): it must not be reused.
    """
    import urllib.request

    current = _program_signature()
    stopped = []
    for url, data in list(_ping_all(site_dir, port, tries)):
        if data.get("program") == current:
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


def serve(site_dir: Path, port: int, opener: Callable[[str], None] | None, idle_minutes: float | None = None,
          launcher: Path | None = None) -> None:
    server = make_server(site_dir, port, launcher=launcher, idle_minutes=idle_minutes)
    ctx: ServerContext = server.ctx  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{server.server_address[1]}/"
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
