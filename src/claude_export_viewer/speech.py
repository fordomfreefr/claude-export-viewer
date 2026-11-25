"""Reading a bubble aloud (speak.js, POST /__cev__/speak*) with Piper (https://github.com/OHF-Voice/piper1-gpl).

Piper (GPL-3) is not part of CEV and is never imported by it: CEV installs it, when the user agrees, in a
Python environment of its own and runs its HTTP server (`piper.http_server`, a separate program, kept
running with the voices loaded while it is used, stopped after IDLE seconds without use).

Folder of Piper (settings.json "speech" "dir"), by default ~/.local/share/cev-piper (Windows:
%LOCALAPPDATA%\\cev-piper): env/ the Python environment (or bin/ at the top, an environment made by hand),
voices/ the voices (or at the top), downloaded when first needed (`piper.download_voices`).

The voices: the catalogue of Piper (voices.json of piper-voices, kept a week in the cache folder, `catalog`),
listed per language with the best quality of each voice, a speaker of a voice with several being one voice
(`choices`, the sex from the speaker's name or SEX, else unknown); one voice for "Moi", one for Claude, chosen
in the page (settings.json "speech" "voices" {lang: {"human": voice, "assistant": voice}}), else DEFAULTS. A
voice is "name" or "name#speaker". The same voice for both: "Question." / "Réponse." said first. Today the
language is the one of CEV for every bubble; later each bubble may have its own (`voices(lang)` takes it).

The sounds made are kept in the cache folder of the user, out of the site and of its backups (`cache_dir`:
~/.cache/cev-speech, Windows %LOCALAPPDATA%\\cev-speech; 08/11, before: archive/speech/, removed): WAV, the
oldest removed beyond the size chosen (settings.json "speech" "cache_mb", CACHE_MIN_MB at least).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import cdn_cache, i18n, settings, system
from .i18n import t

DEFAULTS = {  # "Moi", Claude
    "fr": ("fr_FR-siwis-medium", "fr_FR-upmc-medium#pierre"), "en": ("en_US-lessac-high", "en_US-ryan-high"),
    "de": ("de_DE-kerstin-low", "de_DE-thorsten-high"), "es": ("es_AR-daniela-high", "es_ES-davefx-medium"),
    "it": ("it_IT-paola-medium", "it_IT-riccardo-x_low"), "nl": ("nl_BE-nathalie-medium", "nl_NL-pim-medium"),
    "pt": ("pt_BR-faber-medium", "pt_BR-cadu-medium"), "pl": ("pl_PL-gosia-medium", "pl_PL-darkman-medium"),
    "ru": ("ru_RU-irina-medium", "ru_RU-denis-medium"), "zh": ("zh_CN-huayan-medium", "zh_CN-huayan-medium"),
    "ja": ("ja_JP-hi_fi_captain-medium#female", "ja_JP-hi_fi_captain-medium#male"),
    "ko": ("ko_KR-kss-medium", "ko_KR-kss-medium"),
}
# the sex of voices (name, or name#speaker) whose speakers do not say it
SEX = {
    "F": {"siwis", "upmc#jessica", "lessac", "amy", "kristin", "kathleen", "ljspeech", "alba", "cori", "jenny_dioco",
          "kerstin", "ramona", "eva_k", "daniela", "paola", "serena", "nathalie", "gosia", "irina", "huayan", "xiao_ya",
          "kss"},
    "M": {"tom", "gilles", "upmc#pierre", "ryan", "joe", "john", "bryce", "norman", "mike", "danny", "alan", "thorsten",
          "thorsten_emotional", "pavoque", "davefx", "carlfm", "riccardo", "pim", "ronnie", "rdh", "darkman", "faber",
          "cadu", "jeff", "edresson", "tugão", "denis", "dmitri", "ruslan"},
}
QUALITIES = ("x_low", "low", "medium", "high")
VOICES_JSON = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json?download=true"
SAMPLE = "https://rhasspy.github.io/piper-samples/samples/{family}/{code}/{name}/{quality}/speaker_{id}.mp3"
CATALOG_AGE = 7 * 24 * 3600
MANY = 8  # more speakers: one choice, its speakers by number
EXTRAS = {"ja": "ja"}  # what Piper needs more for a language: pip extra, and its module
EXTRA_MODULES = {"ja": "pyopenjtalk"}
VOICE = re.compile(r"^[a-z]{2,3}_[A-Z]{2}-[^-#/\\\s]+-(?:x_low|low|medium|high)(?:#[^/\\]{1,64})?$")
ROLES = ("human", "assistant")
OLD_CACHE = "speech"  # archive/speech/ of the versions up to 2026.11.7: removed (sounds made again when needed)
CACHE_MIN_MB, CACHE_DEFAULT_MB = 50, 100
TEXT_MAX = 2000
TIMEOUT = 180
IDLE = 600
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
# (review of 21/11) one version of Piper, not the latest of the day: a version broken or tampered with on PyPI is not
# installed by itself; raised by hand once a new version is tried
PIPER_MIN = "1.8.0"  # (21/11) at least the version of a real install that works with CEV; newer ones are taken


class SpeechError(Exception):
    """A message for the user: its i18n key and arguments."""

    def __init__(self, key: str, **args: str) -> None:
        super().__init__(key)
        self.key, self.args_ = key, args


# --- Where Piper is -------------------------------------------------------------------------------------------

def _config(site_dir: Path) -> dict:
    data = settings.load(site_dir).get("speech")
    return data if isinstance(data, dict) else {}


def cache_dir() -> Path:
    """Where the sounds made and the catalogue are kept: a cache, made again when needed."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cev-speech"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "cev-speech"


def _short(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def cache_mb(site_dir: Path) -> int:
    value = _config(site_dir).get("cache_mb")
    return max(CACHE_MIN_MB, value) if isinstance(value, int) and not isinstance(value, bool) else CACHE_DEFAULT_MB


def drop_old_cache(site_dir: Path) -> None:
    """The sounds kept in the site by the earlier versions (up to 200 MB, in every backup): removed."""
    old = Path(site_dir) / "archive" / OLD_CACHE
    if old.is_dir():
        shutil.rmtree(old, ignore_errors=True)


def _sounds() -> list[Path]:
    return [p for p in cache_dir().glob("*.wav") if p.is_file()]


def cache_state(site_dir: Path) -> dict:
    """For the cleaning frame of the index: the sounds kept, their size, the size chosen."""
    files = _sounds()
    return {"count": len(files), "size": sum(p.stat().st_size for p in files), "max_mb": cache_mb(site_dir),
            "min_mb": CACHE_MIN_MB, "folder": _short(cache_dir())}


def set_cache_mb(site_dir: Path, mb: Any) -> dict:
    if not isinstance(mb, int) or isinstance(mb, bool) or not CACHE_MIN_MB <= mb <= 100_000:
        raise SpeechError("server.bad_request")
    data = settings.load(site_dir)
    speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
    settings.save(site_dir, {**data, "speech": {**speech, "cache_mb": mb}})
    _prune(cache_dir(), mb)
    return cache_state(site_dir)


def clear_cache(site_dir: Path) -> dict:
    """Remove every sound kept (they are made again when read); answers how many and their size."""
    n = size = 0
    for p in _sounds():
        try:
            s = p.stat().st_size
            p.unlink()
        except OSError:
            continue
        n, size = n + 1, size + s
    return {"removed": n, "size": size, **cache_state(site_dir)}


def folder(site_dir: Path) -> Path:
    custom = _config(site_dir).get("dir")
    if isinstance(custom, str) and custom.strip():
        return Path(custom).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cev-piper"
    return Path.home() / ".local" / "share" / "cev-piper"


def _bin(env: Path, name: str) -> Path:
    return env / "Scripts" / f"{name}.exe" if sys.platform == "win32" else env / "bin" / name


def env_dir(where: Path) -> Path:
    """The Python environment: env/, or the folder itself when it was made there by hand."""
    return where if _bin(where, "python").is_file() and not (where / "env").is_dir() else where / "env"


def voice_dirs(where: Path) -> list[Path]:
    return [where / "voices", where]


def _site_packages(env: Path) -> list[Path]:
    return list(env.glob("lib/python*/site-packages")) + [env / "Lib" / "site-packages"]


def _has(env: Path, module: str) -> bool:
    return any((p / module).is_dir() for p in _site_packages(env))


def installed(where: Path, lang: str | None = None) -> bool:
    """Piper with its HTTP server (flask), and what the language needs more."""
    env = env_dir(where)
    need = ["piper", "flask"] + ([EXTRA_MODULES[lang]] if lang in EXTRA_MODULES else [])
    return _bin(env, "python").is_file() and all(_has(env, m) for m in need)


# --- The voices -------------------------------------------------------------------------------------------------

def catalog(site_dir: Path) -> dict:
    """The voices of Piper (voices.json), kept a week; the copy kept when it cannot be fetched."""
    kept = cache_dir() / "voices.json"
    if kept.is_file() and time.time() - kept.stat().st_mtime < CATALOG_AGE:
        try:
            return json.loads(kept.read_text(encoding="utf-8"))
        except ValueError:
            pass
    try:
        with urllib.request.urlopen(VOICES_JSON, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except (OSError, ValueError, urllib.error.URLError):
        try:
            return json.loads(kept.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


def _sex(name: str, speaker: str | None) -> str:
    key = f"{name}#{speaker}" if speaker else name
    low = (speaker or "").lower()
    if low in ("female", "f", "woman") or (not speaker and "female" in name):
        return "F"
    if low in ("male", "m", "man") or (not speaker and "male" in name):
        return "M"
    return next((sx for sx, names in SEX.items() if key in names or (not speaker and name in names)), "?")


def choices(site_dir: Path, lang: str) -> list[dict]:
    """The voices of a language: the best quality of each voice, every speaker of a voice with few of them;
    a voice with many (MANY) is one choice with its number of speakers."""
    where = folder(site_dir)
    best: dict[tuple[str, str], dict] = {}
    for key, v in catalog(site_dir).items():
        lg = v.get("language") or {}
        if lg.get("family") != lang or v.get("quality") not in QUALITIES:
            continue
        k = (lg.get("code", ""), v.get("name", ""))
        if k not in best or QUALITIES.index(v["quality"]) > QUALITIES.index(best[k]["quality"]):
            best[k] = {**v, "key": key}
    regions = {code for code, _ in best}
    out = []
    for (code, name), v in sorted(best.items(), key=lambda x: (x[0][1], x[0][0])):
        size = sum(f.get("size_bytes", 0) for p, f in (v.get("files") or {}).items() if p.endswith(".onnx"))
        base = {"name": name, "region": code.split("_")[-1] if len(regions) > 1 else "", "quality": v["quality"],
                "size": size, "downloaded": _model(where, v["key"]) is not None}
        fam = (v.get("language") or {}).get("family", lang)
        speakers = sorted((v.get("speaker_id_map") or {}).items(), key=lambda x: x[1])
        if len(speakers) > MANY:
            out.append({**base, "voice": v["key"], "sex": "?", "speakers": [n for n, _ in speakers],
                        "sample": SAMPLE.format(family=fam, code=code, name=name, quality=v["quality"], id="{id}")})
            continue
        for n, i in (speakers if len(speakers) > 1 else [(None, 0)]):
            out.append({**base, "voice": v["key"] + (f"#{n}" if n else ""), "speaker": n, "sex": _sex(name, n),
                        "sample": SAMPLE.format(family=fam, code=code, name=name, quality=v["quality"], id=i)})
    return out



def listed(site_dir: Path, lang: str) -> list[dict]:
    """choices(), with the voices in use even when the catalogue does not have them (offline, or chosen by hand)."""
    out = choices(site_dir, lang)
    have = {c["voice"] for c in out} | {c["voice"] + "#" + n for c in out for n in c.get("speakers", [])}
    where = folder(site_dir)
    for spec in dict.fromkeys((voices(site_dir, lang) or {}).values()):
        if spec in have:
            continue
        name, _, speaker = spec.partition("#")
        _, short, quality = name.split("-", 2)
        out.append({"voice": spec, "name": short, "speaker": speaker or None, "region": "", "quality": quality,
                    "size": 0, "downloaded": _model(where, name) is not None, "sex": _sex(short, speaker or None),
                    "sample": SAMPLE.format(family=lang, code=name.split("-")[0], name=short, quality=quality, id=0)})
    return out


def voices(site_dir: Path, lang: str) -> dict[str, str] | None:
    """{"human": voice, "assistant": voice} for that language (chosen in the page, else DEFAULTS), None when
    Piper has no voice in that language."""
    chosen = (_config(site_dir).get("voices") or {}).get(lang)
    if isinstance(chosen, str) and chosen:
        chosen = {"human": chosen, "assistant": chosen}
    default = DEFAULTS.get(lang)
    if not isinstance(chosen, dict):
        chosen = {}
    picked = {r: chosen[r] for r in ROLES if isinstance(chosen.get(r), str) and VOICE.match(chosen[r])}
    if not picked and not default:
        return None
    fill = default or (next(iter(picked.values())),) * 2
    return {r: picked.get(r) or fill[i] for i, r in enumerate(ROLES)}


def choose(site_dir: Path, lang: str, role: str, voice: str) -> None:
    """The voice of "Moi" (human) or of Claude (assistant) for a language, kept in settings.json."""
    if role not in ROLES or not VOICE.match(voice):
        raise SpeechError("server.bad_request")
    data = settings.load(site_dir)
    speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
    vs = speech.get("voices") if isinstance(speech.get("voices"), dict) else {}
    cur = vs.get(lang) if isinstance(vs.get(lang), dict) else {}
    vs[lang] = {**cur, role: voice}
    settings.save(site_dir, {**data, "speech": {**speech, "voices": vs}})


def skipped(site_dir: Path) -> set[str]:
    """The languages whose passages are not read (choice of the box "Voix", 08/11): « Passage en …, non lu. »"""
    value = _config(site_dir).get("skip")
    return {x for x in value if isinstance(x, str)} if isinstance(value, list) else set()


def set_skip(site_dir: Path, lang: str, on: bool) -> None:
    if lang not in i18n.LANGUAGES:
        raise SpeechError("server.bad_request")
    data = settings.load(site_dir)
    speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
    langs = (skipped(site_dir) | {lang}) if on else (skipped(site_dir) - {lang})
    settings.save(site_dir, {**data, "speech": {**speech, "skip": sorted(langs)}})


def _model_size(site_dir: Path, name: str) -> int:
    v = catalog(site_dir).get(name) or {}
    return sum(f.get("size_bytes", 0) for p, f in (v.get("files") or {}).items() if p.endswith(".onnx"))


def check(site_dir: Path, langs: list[str]) -> dict:
    """For a reading with passages in other languages (speak.js): for each language, whether it can be read
    (a voice, Piper able to), whether the user chose not to, and the voices still to download (with their size)."""
    where, skip, out = folder(site_dir), skipped(site_dir), {}
    for lang in langs:
        if lang not in i18n.LANGUAGES:
            continue
        v = voices(site_dir, lang)
        if not v:
            out[lang] = {"readable": False, "skip": lang in skip, "missing": []}
            continue
        names = list(dict.fromkeys(spec.partition("#")[0] for spec in v.values()))
        missing = [{"name": n, "size": _model_size(site_dir, n)} for n in names if _model(where, n) is None]
        out[lang] = {"readable": installed(where, lang), "skip": lang in skip, "missing": missing}
    return out


def installed_voices(site_dir: Path) -> list[dict]:
    """The voices on the disk (every folder of voice_dirs), their size, those in two folders, those in use
    (the voices of a language, chosen or by default)."""
    where = folder(site_dir)
    used = {spec.partition("#")[0] for lang in i18n.LANGUAGES for spec in (voices(site_dir, lang) or {}).values()}
    found = []
    for i, d in enumerate(voice_dirs(where)):
        for f in sorted(d.glob("*.onnx")) if d.is_dir() else []:
            if not VOICE.match(f.stem):
                continue
            size = f.stat().st_size + (f.with_suffix(".onnx.json").stat().st_size if f.with_suffix(".onnx.json").is_file() else 0)
            found.append({"name": f.stem, "lang": f.stem.split("_")[0], "dir": i, "where": _short(d), "size": size,
                          "used": f.stem in used})
    names = [x["name"] for x in found]
    for x in found:
        x["duplicate"] = names.count(x["name"]) > 1
    return found


def remove_voice(site_dir: Path, name: str, index: Any) -> list[dict]:
    """Remove a voice from one folder of voice_dirs (its .onnx and .onnx.json); Piper stopped first."""
    dirs = voice_dirs(folder(site_dir))
    if not isinstance(name, str) or "#" in name or not VOICE.match(name) or not isinstance(index, int) \
            or isinstance(index, bool) or not 0 <= index < len(dirs):
        raise SpeechError("server.bad_request")
    _piper.stop()
    for f in (dirs[index] / f"{name}.onnx", dirs[index] / f"{name}.onnx.json"):
        f.unlink(missing_ok=True)
    return installed_voices(site_dir)


def single(site_dir: Path, lang: str) -> bool:
    """Both speakers with the same voice: "Question." / "Réponse." are said."""
    v = voices(site_dir, lang)
    return bool(v) and v["human"] == v["assistant"]


def _model(where: Path, name: str) -> Path | None:
    return next((d / f"{name}.onnx" for d in voice_dirs(where) if (d / f"{name}.onnx").is_file()), None)


# --- Commands -------------------------------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 1800) -> str:
    """Run a command; SpeechError with its last lines when it fails."""
    try:
        run = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **system.no_window())
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpeechError("server.speak.failed", message=str(exc)) from exc
    if run.returncode != 0:
        lines = (run.stderr or run.stdout or "").strip().splitlines()
        raise SpeechError("server.speak.failed", message="\n".join(lines[-6:]) or str(run.returncode))
    return run.stdout


def manual_command(where: Path, lang: str) -> str:
    """What the user types when CEV cannot install Piper itself."""
    env = where / "env"
    steps = ["sudo apt install python3-venv"] if Path("/etc/debian_version").is_file() else []
    steps.append(system.command_line([system.python_command(), "-m", "venv", str(env)]))
    extra = ",".join(["http"] + ([EXTRAS[lang]] if lang in EXTRAS else []))
    steps.append(system.command_line([str(_bin(env, "python")), "-m", "pip", "install", "--upgrade", f"piper-tts[{extra}]>={PIPER_MIN}"]))
    return "\n".join(steps)


# --- Installation (a job of the server: POST /__cev__/speak/install, its state in status()) -------------------

_job: dict = {"state": "idle", "step": "", "message": ""}
_job_lock = threading.Lock()


def _venv(env: Path) -> None:
    py = _bin(env, "python")
    if py.is_file() and _bin(env, "pip").is_file():
        return
    try:
        _run([sys.executable, "-m", "venv", "--clear", str(env)])
    except SpeechError:
        # Debian / Ubuntu without python3-venv: no ensurepip; an environment without pip, then get-pip.py
        _run([sys.executable, "-m", "venv", "--clear", "--without-pip", str(env)])
    if not _bin(env, "pip").is_file():
        script = env / "get-pip.py"
        try:
            # (25/11) https only, redirections kept to bootstrap.pypa.io (a fingerprint is impossible: the file
            # changes with every version of pip)
            with cdn_cache.open_https(GET_PIP, 120, host="bootstrap.pypa.io") as r:
                script.write_bytes(r.read())
        except (OSError, urllib.error.URLError) as exc:
            raise SpeechError("server.speak.failed", message=f"{GET_PIP}: {exc}") from exc
        _run([str(py), str(script)])
        script.unlink(missing_ok=True)


def _install_steps(site_dir: Path, lang: str):
    """The steps of the installation, (i18n key of the step, function): replaced in the tests."""
    where = folder(site_dir)
    env = env_dir(where)
    extra = ",".join(["http"] + ([EXTRAS[lang]] if lang in EXTRAS else []))
    yield "server.speak.step_env", lambda: _venv(env)
    yield "server.speak.step_piper", lambda: _run(
        [str(_bin(env, "python")), "-m", "pip", "install", "--upgrade", f"piper-tts[{extra}]>={PIPER_MIN}"])
    v = voices(site_dir, lang) or {}
    for name in dict.fromkeys(spec.split("#")[0] for spec in v.values()):
        yield "server.speak.step_voice", (lambda n=name: download(site_dir, n))


def install(site_dir: Path, lang: str, ui: str) -> bool:
    """Start the installation in the background (False: one is already running)."""
    with _job_lock:
        if _job["state"] == "running":
            return False
        _job.update(state="running", step="", message="")

    def work() -> None:
        try:
            for key, step in _install_steps(site_dir, lang):
                _job["step"] = t(key, ui)
                step()
            _job.update(state="done", step="")
        except SpeechError as exc:
            _job.update(state="failed", message=t(exc.key, ui, **exc.args_) + "\n\n" +
                        t("server.speak.manual", ui, cmd=manual_command(folder(site_dir), lang)))
        except Exception as exc:  # noqa: BLE001 - shown to the user
            _job.update(state="failed", message=str(exc))

    threading.Thread(target=work, daemon=True).start()
    return True


def status(site_dir: Path, lang: str) -> dict:
    v = voices(site_dir, lang)
    return {"installed": installed(folder(site_dir), lang), "voice": bool(v), "dir": str(folder(site_dir)),
            "voices": v, "single": single(site_dir, lang), "job": dict(_job)}


_downloads: dict[str, threading.Lock] = {}


def download(site_dir: Path, name: str) -> Path:
    """The model of a voice, downloaded the first time (piper.download_voices, into voices/)."""
    where = folder(site_dir)
    lock = _downloads.setdefault(name, threading.Lock())
    with lock:
        found = _model(where, name)
        if found:
            return found
        target = where / "voices"
        target.mkdir(parents=True, exist_ok=True)
        try:
            _run([str(_bin(env_dir(where), "python")), "-m", "piper.download_voices", "--data-dir", str(target), name])
        except SpeechError as exc:
            raise SpeechError("server.speak.no_voice", voice=name, message=exc.args_.get("message", "")) from exc
        found = _model(where, name)
        if not found:
            raise SpeechError("server.speak.no_voice", voice=name, message="")
        return found


# --- The server of Piper, kept running -------------------------------------------------------------------------

class _Piper:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.where: Path | None = None
        self.used = 0.0
        self.lock = threading.Lock()
        self.watch: threading.Thread | None = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, site_dir: Path, first: str) -> None:
        where = folder(site_dir)
        with self.lock:
            if self.alive() and self.where == where:
                return
            self.stop()
            model = download(site_dir, first)
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                self.port = s.getsockname()[1]
            log = cache_dir() / "piper.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            cmd = [str(_bin(env_dir(where), "python")), "-m", "piper.http_server", "-m", str(model),
                   "--host", "127.0.0.1", "--port", str(self.port)]
            for d in voice_dirs(where):
                cmd += ["--data-dir", str(d)]
            with open(log, "w", encoding="utf-8") as out:
                self.proc = subprocess.Popen(cmd, cwd=where, stdout=out, stderr=subprocess.STDOUT, **system.no_window())
            self.where = where
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    lines = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                    self.proc = None
                    raise SpeechError("server.speak.failed", message="\n".join(lines[-6:]))
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/voices", timeout=2):
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            else:
                self.stop()
                raise SpeechError("server.speak.failed", message="timeout")
            self.used = time.monotonic()
            if not self.watch or not self.watch.is_alive():
                self.watch = threading.Thread(target=self._idle, daemon=True)
                self.watch.start()

    def _idle(self) -> None:
        while self.alive():
            time.sleep(5)
            if time.monotonic() - self.used > IDLE:
                with self.lock:
                    if time.monotonic() - self.used > IDLE:
                        self.stop()

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def synthesize(self, text: str, model: Path, speaker: str | None) -> bytes:
        self.used = time.monotonic()
        body = {"text": text, "voice": model.name[:-len(".onnx")]}
        if speaker:
            body["speaker"] = speaker
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/synthesize", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
        except (OSError, urllib.error.URLError) as exc:
            raise SpeechError("server.speak.failed", message=str(exc)) from exc
        self.used = time.monotonic()
        return data


_piper = _Piper()
atexit.register(_piper.stop)


def _speaker(model: Path, speaker: str | None) -> str | None:
    """A speaker of a voice with several, checked in its .onnx.json."""
    if not speaker:
        return None
    try:
        names = json.loads(Path(f"{model}.json").read_text(encoding="utf-8")).get("speaker_id_map") or {}
    except (OSError, ValueError):
        names = {}
    if speaker not in names:
        raise SpeechError("server.speak.no_voice", voice=f"{model.stem}#{speaker}", message="")
    return speaker


def warm(site_dir: Path, lang: str) -> None:
    """Start Piper with the voices of that language (in the background)."""
    v = voices(site_dir, lang)
    if not v or not installed(folder(site_dir), lang):
        return

    def work() -> None:
        try:
            for spec in dict.fromkeys(v.values()):  # the voices downloaded before the first reading
                download(site_dir, spec.split("#")[0])
            _piper.start(site_dir, v["assistant"].split("#")[0])
        except SpeechError:
            pass

    threading.Thread(target=work, daemon=True).start()


def _prune(cache: Path, mb: int) -> None:
    files = sorted(cache.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for p in files:
        total += p.stat().st_size
        if total > mb * 1024 * 1024:
            p.unlink(missing_ok=True)


def _cache_file(site_dir: Path, spec: str, text: str) -> Path:
    return cache_dir() / (hashlib.sha256(f"{spec}\n{text}".encode()).hexdigest()[:24] + ".wav")


def speak(site_dir: Path, text: str, lang: str, role: str, cached_only: bool = False) -> bytes | None:
    """The WAV sound of a text read by the voice of that language, pair and speaker; with cached_only, only
    a sound already made (None otherwise). SpeechError when it cannot be made."""
    text = " ".join(text.split())[:TEXT_MAX]
    v = voices(site_dir, lang)
    if not v:
        raise SpeechError("server.speak.no_voice_lang", lang=lang)
    spec = v[role]
    out = _cache_file(site_dir, spec, text)
    if out.is_file():
        os.utime(out)
        return out.read_bytes()
    if cached_only:
        return None
    where = folder(site_dir)
    if not installed(where, lang):
        raise SpeechError("server.speak.not_installed")
    name, _, speaker = spec.partition("#")
    model = download(site_dir, name)
    speaker = _speaker(model, speaker or None)
    _piper.start(site_dir, name)
    data = _piper.synthesize(text, model, speaker)
    if data[:4] != b"RIFF":
        raise SpeechError("server.speak.failed", message=data[:200].decode("utf-8", "replace"))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, out)
    _prune(out.parent, cache_mb(site_dir))
    return data
