"""Packages of esm.sh a React program of Claude imports beyond those CEV bundles (three, framer-motion…),
downloaded once with the user's agreement and kept in the archive (archive/esm/), so that the program runs
afterwards without asking and without the Internet (PT-m3, 08/11).

An esm.sh package is a small entry module importing others by absolute paths ("/three@0.170.0/es2022/three.mjs"):
every module it reaches is downloaded (static imports, ``export … from``, dynamic ``import()``), and each path is
written out as a full https://esm.sh/ address, which the import map of the frame (run.js) points to the kept
text. Bare names ("react", "react-dom") stay: CEV gives them (external=react,react-dom, as run.js asks).

archive/esm/index.json: {specifier: {"entry": url, "modules": [url…], "size": n, "date": iso}}, one file per module
(sha256 of its address). The site gets esm-cache.js (window.CEV_ESM = {specifier: {"entry": url, "modules":
{url: text}}}), written at each build and after each download."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from .cdn_cache import open_https

FOLDER = "esm"                 # in archive/
INDEX = "index.json"
DATA_JS = "esm-cache.js"       # in the site folder
BASE = "https://esm.sh/"
QUERY = "?external=react,react-dom&target=es2022"
MAX_MODULES = 400              # one package
MAX_TOTAL = 40 * 1024 * 1024   # bytes, one package
MAX_FILE = 20 * 1024 * 1024
TIMEOUT = 30

Fetch = Callable[[str], bytes]

# a bare specifier as Claude writes it: "three", "@react-three/fiber", "three/examples/jsm/controls/OrbitControls",
# with a version or not
SPEC = re.compile(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*(?:@[\w.^~<>=-]+)?(?:/[\w.@-]+)*$", re.I)
# what a module imports: from "x", import "x", import("x"), export * from "x" (minified or not)
_IMPORT = re.compile(r"""(\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)(["'])([^"'\s]+)\2""")


def _folder(site_dir: Path) -> Path:
    return Path(site_dir) / "archive" / FOLDER


def valid_spec(spec: Any) -> bool:
    return isinstance(spec, str) and len(spec) <= 200 and bool(SPEC.match(spec)) and ".." not in spec


def entry_url(spec: str) -> str:
    return BASE + spec + QUERY


def load(site_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads((_folder(site_dir) / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _fetch(url: str) -> bytes:
    if not url.startswith(BASE):
        raise OSError(f"adresse refusée : {url}")
    with open_https(url, TIMEOUT, host="esm.sh") as r:  # redirections: esm.sh only (review of 21/11, B1)
        data = r.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise OSError("fichier trop gros")
    return data


def _resolve(ref: str, base: str) -> str | None:
    """The esm.sh address of what a module imports; None for a bare name (given by CEV) or another site."""
    if ref.startswith(("/", "./", "../")):
        url = urljoin(base, ref)
    elif ref.startswith(BASE):
        url = ref
    else:
        return None
    return url if urlparse(url).netloc == "esm.sh" and urlparse(url).scheme == "https" else None


def _crawl(spec: str, fetch: Fetch) -> dict[str, str]:
    """Every module of a package, its imports written as full addresses: {url: text}."""
    entry = entry_url(spec)
    queue, modules, total = [entry], {}, 0
    while queue:
        url = queue.pop(0)
        if url in modules:
            continue
        if len(modules) >= MAX_MODULES:
            raise OSError(f"plus de {MAX_MODULES} modules")
        text = fetch(url).decode("utf-8", "replace")
        total += len(text)
        if total > MAX_TOTAL:
            raise OSError("paquet trop gros")

        def full(m: re.Match[str], base: str = url) -> str:
            target = _resolve(m.group(3), base)
            if target is None:
                return m.group(0)
            if target not in modules and target not in queue:
                queue.append(target)
            return f"{m.group(1)}{m.group(2)}{target}{m.group(2)}"

        modules[url] = _IMPORT.sub(full, text)
    return modules


def download(site_dir: Path, specs: list[str], fetch: Fetch | None = None) -> dict[str, str]:
    """Download the packages not kept yet; returns {specifier: error} for the ones that failed. Writes the index
    and esm-cache.js."""
    fetch = fetch or _fetch
    folder = _folder(site_dir)
    folder.mkdir(parents=True, exist_ok=True)
    index = load(site_dir)
    errors: dict[str, str] = {}
    for spec in specs:
        if not valid_spec(spec):
            errors[str(spec)] = "nom refusé"
            continue
        if spec in index:
            continue
        try:
            modules = _crawl(spec, fetch)
        except (OSError, ValueError) as exc:
            errors[spec] = f"{type(exc).__name__}: {exc}"
            continue
        for url, text in modules.items():
            name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + ".js"
            tmp = folder / (name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, folder / name)
        index[spec] = {"entry": entry_url(spec), "modules": list(modules), "size": sum(len(x) for x in modules.values()),
                       "date": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    tmp = folder / (INDEX + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, folder / INDEX)
    write_data_js(site_dir)
    return errors


def write_data_js(site_dir: Path) -> None:
    folder = _folder(site_dir)
    data: dict[str, Any] = {}
    for spec, e in load(site_dir).items():
        try:
            modules = {url: (folder / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:16] + ".js")).read_text(encoding="utf-8")
                       for url in e["modules"]}
            data[spec] = {"entry": e["entry"], "modules": modules}
        except (OSError, KeyError, TypeError):
            continue
    text = "window.CEV_ESM = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";\n"
    path = Path(site_dir) / DATA_JS
    tmp = path.with_name(DATA_JS + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
