"""Libraries of the Internet a page of Claude loads (Chart.js from cdnjs, the icons from jsdelivr…),
downloaded once with the user's agreement and kept in the archive (archive/cdn/), so that every visual or
HTML page using the same address runs afterwards without asking and without the Internet (run.js puts
them inline in the sandboxed frame).

archive/cdn/index.json: {url: {"file": name, "type": "js" | "css", "size": n, "date": iso}}; a style sheet
is kept with its fonts inline (woff2 as data: URIs, the other formats dropped). The site gets
cdn-cache.js (window.CEV_CDN = {url: text}), written at each build and after each download."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

FOLDER = "cdn"                 # in archive/
INDEX = "index.json"
DATA_JS = "cdn-cache.js"       # in the site folder
MAX_FILE = 20 * 1024 * 1024    # bytes, one file
TIMEOUT = 30                   # seconds, one download

Fetch = Callable[[str], bytes]


def _folder(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FOLDER


def load(site_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads((_folder(site_dir) / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def public_host(host: str | None) -> bool:
    """True when every address of ``host`` is a public one of the Internet (25/11, CodeQL SSRF alert): a trapped
    artifact must never make the server read localhost, the box, the local network (10.x, 192.168.x…) or an address
    reserved or link-local, written as a name or as a literal IP."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host.strip("[]"), 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    try:
        addrs = {ipaddress.ip_address(str(i[4][0]).split("%")[0]) for i in infos}
    except ValueError:
        return False
    return bool(addrs) and all(a.is_global and not a.is_multicast for a in addrs)


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Redirections followed only to https (and, when ``host`` is given, to that site only): a server answering
    with a redirection to http:// or to another site gets nothing (review of 21/11, B1)."""
    max_redirections = 5

    def __init__(self, host: str | None = None) -> None:
        super().__init__()
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        u = urlparse(newurl)
        if u.scheme != "https" or u.username or u.password or (self.host is not None and u.hostname != self.host) \
                or (self.host is None and not public_host(u.hostname)):
            raise urllib.error.HTTPError(newurl, code, f"redirection refusée vers {newurl}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_https(url: str, timeout: float, host: str | None = None):  # type: ignore[no-untyped-def]
    """``urlopen`` of an https address, its redirections kept to https (and to ``host`` when given; without ``host``,
    to public addresses only, as the address itself)."""
    u = urlparse(url)
    if u.scheme != "https" or (host is not None and u.hostname != host) or (host is None and not public_host(u.hostname)):
        raise OSError(f"adresse refusée : {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "claude-export-viewer"})
    return urllib.request.build_opener(_Redirects(host)).open(req, timeout=timeout)


def _fetch(url: str) -> bytes:
    with open_https(url, TIMEOUT) as r:
        data = r.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise OSError("fichier trop gros")
    return data


def valid_url(url: Any) -> bool:
    if not isinstance(url, str) or len(url) > 2000:
        return False
    u = urlparse(url)
    return u.scheme == "https" and bool(u.netloc) and not u.username and not u.password


_URL_IN_CSS = re.compile(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)")


def _inline_fonts(css: str, base: str, fetch: Fetch) -> str:
    """The fonts of a style sheet as data: URIs (woff2 only: every browser of today reads it)."""
    def one(m: re.Match[str]) -> str:
        ref = m.group(2).strip()
        if ref.startswith("data:"):
            return m.group(0)
        if not urlparse(ref).path.lower().endswith(".woff2"):
            return "url(data:,)"
        full = urljoin(base, ref)
        if not valid_url(full):
            return "url(data:,)"
        return f"url(data:font/woff2;base64,{base64.b64encode(fetch(full)).decode('ascii')})"
    return _URL_IN_CSS.sub(one, css)


def download(site_dir: Path, urls: list[str], fetch: Fetch | None = None) -> dict[str, str]:
    """Download what is not kept yet; returns {url: error} for the ones that failed. Writes the index and
    cdn-cache.js."""
    fetch = fetch or _fetch
    folder = _folder(site_dir)
    folder.mkdir(parents=True, exist_ok=True)
    index = load(site_dir)
    errors: dict[str, str] = {}
    for url in urls:
        if url in index or not valid_url(url):
            if not valid_url(url):
                errors[str(url)] = "adresse refusée"
            continue
        try:
            data = fetch(url)
            kind = "css" if urlparse(url).path.lower().endswith(".css") else "js"
            text = data.decode("utf-8", "replace")
            if kind == "css":
                text = _inline_fonts(text, url, fetch)
            name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + "." + kind
            tmp = folder / (name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, folder / name)
            index[url] = {"file": name, "type": kind, "size": len(text),
                          "date": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        except (OSError, ValueError) as exc:
            errors[url] = f"{type(exc).__name__}: {exc}"
    tmp = folder / (INDEX + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, folder / INDEX)
    write_data_js(site_dir)
    return errors


def write_data_js(site_dir: Path) -> None:
    folder = _folder(site_dir)
    data: dict[str, str] = {}
    for url, e in load(site_dir).items():
        try:
            data[url] = (folder / e["file"]).read_text(encoding="utf-8")
        except (OSError, KeyError, TypeError):
            continue
    text = "window.CEV_CDN = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";\n"
    path = Path(site_dir) / DATA_JS
    tmp = path.with_name(DATA_JS + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
