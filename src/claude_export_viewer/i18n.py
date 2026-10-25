"""Translations of everything the program shows: console, pages, exports, desktop icon.

One JSON file per language in ``i18n/`` (key -> text). English is the reference
and the fallback: a key missing from a language is shown in English.

Texts may hold ``{name}`` placeholders. A text that depends on a number is an
object of plural forms (CLDR categories: "one", "few", "many", "other"), chosen
with the ``n`` argument.

The console uses the language of the system (``LANGUAGE``, ``LC_ALL``,
``LC_MESSAGES``, ``LANG``), or ``--langue``. Pages are written in that language
and switched in the browser by ``static/i18n.js`` to the language chosen in the
index (remembered by the browser).
"""

from __future__ import annotations

import functools
import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import dates

LANGUAGES = {
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
}
DEFAULT = "en"
_DIR = Path(__file__).parent / "i18n"


def normalize(code: str | None) -> str | None:
    """"fr_FR.UTF-8" -> "fr", "zh-Hans-CN" -> "zh"; None if not one of LANGUAGES."""
    if not code:
        return None
    base = code.strip().replace("-", "_").split(".")[0].split("@")[0].split("_")[0].lower()
    return base if base in LANGUAGES else None


def detect(env: dict[str, str] | None = None) -> str:
    """Language of the system, English if it is not one of LANGUAGES."""
    env = dict(os.environ) if env is None else env
    for var in ("CEV_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for part in (env.get(var) or "").split(":"):  # LANGUAGE may list several: "fr:en"
            code = normalize(part)
            if code:
                return code
    return DEFAULT


_current = detect()  # the command line may change it (--langue)


def set_language(code: str | None) -> str:
    global _current
    _current = normalize(code) or DEFAULT
    return _current


def language() -> str:
    return _current


@functools.lru_cache(maxsize=None)
def catalog(lang: str) -> dict[str, Any]:
    path = _DIR / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --- Plural rules (CLDR, integers) ------------------------------------------------


def plural_category(lang: str, n: int) -> str:
    n = abs(int(n))
    if lang in ("zh", "ja", "ko"):
        return "other"
    if lang in ("fr", "pt"):
        return "one" if n in (0, 1) else "other"
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "pl":
        if n == 1:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "one" if n == 1 else "other"  # en, es, de, it, nl


# --- Texts ---------------------------------------------------------------------


class Day(str):
    """An ISO date shown as a day, as written (the date of an export): "20/10/2026"."""


class LocalDate:
    """A moment shown as a day in local time (no hour): "23/10/2026"."""

    def __init__(self, d: datetime) -> None:
        self.d = d


class _Args(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _pick(value: Any, lang: str, args: dict[str, Any]) -> str | None:
    if isinstance(value, dict):
        n = args.get("n", 0)
        return value.get(plural_category(lang, n)) or value.get("other")
    return value if isinstance(value, str) else None


def _format_arg(value: Any, lang: str) -> Any:
    if isinstance(value, Day):
        return format_date(str(value), lang, to_local=False)
    if isinstance(value, LocalDate):
        return format_date(value.d, lang)
    if isinstance(value, datetime):
        return format_datetime(value, lang)
    if isinstance(value, float):
        return format_number(value, lang)
    return value


def t(key: str, lang: str | None = None, **args: Any) -> str:
    """Text of ``key`` in ``lang`` (default: the current language), English if missing."""
    lang = lang or _current
    text = _pick(catalog(lang).get(key), lang, args)
    if text is None and lang != DEFAULT:
        text = _pick(catalog(DEFAULT).get(key), DEFAULT, args)
    if text is None:
        return key
    shown = {k: _format_arg(v, lang) for k, v in args.items()}
    return text.format_map(_Args(shown))


# --- Dates and numbers (same patterns as the pages, see static/i18n.js) ------------


def format_date(d: datetime | str | None, lang: str | None = None, to_local: bool = True) -> str:
    lang = lang or _current
    parsed = dates.parse(d)
    if parsed is None:
        return ""
    if to_local:
        parsed = dates.local(parsed)
    return parsed.strftime(t("fmt.date", lang))


def format_datetime(d: datetime | str | None, lang: str | None = None) -> str:
    lang = lang or _current
    parsed = dates.parse(d)
    if parsed is None:
        return ""
    parsed = dates.local(parsed)
    return t("fmt.datetime", lang, date=parsed.strftime(t("fmt.date", lang)), time=parsed.strftime("%H:%M"))


def format_number(x: float, lang: str | None = None) -> str:
    return f"{x:.1f}".replace(".", t("fmt.decimal", lang or _current))


# --- Texts in the pages ----------------------------------------------------------
#
# A translatable text is written in the language of the build and marked with
# its key and arguments, so that static/i18n.js can rewrite it in the language
# chosen in the index. Dates are passed as {"$day": iso} (export days, as
# written), {"$date": iso} (local day), {"$datetime": iso}; numbers as {"$num": x}.


def _js_arg(value: Any) -> Any:
    if isinstance(value, Day):
        return {"$day": str(value)}
    if isinstance(value, LocalDate):
        return {"$date": dates.utc(value.d).isoformat()}
    if isinstance(value, datetime):
        return {"$datetime": dates.utc(value).isoformat()}
    if isinstance(value, float):
        return {"$num": value}
    return value


def html_args(**args: Any) -> str:
    """`` data-i18n-args='{…}'`` (arguments of the texts of an element), or "" without arguments."""
    if not args:
        return ""
    payload = json.dumps({k: _js_arg(v) for k, v in args.items()}, ensure_ascii=False)
    return f" data-i18n-args='{html.escape(payload, quote=True)}'"


def html_text(key: str, tag: str = "span", attrs: str = "", **args: Any) -> str:
    """``<span data-i18n="key" …>text</span>`` (text HTML-escaped)."""
    data = f' data-i18n="{html.escape(key)}"' + html_args(**args)
    return f"<{tag}{attrs}{data}>{html.escape(t(key, **args), quote=False)}</{tag}>"


def html_date(d: datetime | None, with_time: bool = False, to_local: bool = True) -> str:
    """``<time>`` shown in the build language, reformatted by the browser."""
    if d is None:
        return ""
    kind = "datetime" if with_time else ("date" if to_local else "day")
    text = format_datetime(d) if with_time else format_date(d, to_local=to_local)
    return f'<time datetime="{html.escape(dates.utc(d).isoformat())}" data-fmt="{kind}">{html.escape(text, quote=False)}</time>'


def web_catalogs() -> dict[str, dict[str, Any]]:
    """Texts needed in the browser (keys "web.", "md." and "fmt."), for every language."""
    out = {}
    for lang in LANGUAGES:
        out[lang] = {k: v for k, v in catalog(lang).items() if k.startswith(("web.", "md.", "fmt."))}
    return out


def web_data_script() -> str:
    """Content of i18n-data.js, written in the site folder."""
    data = {"languages": LANGUAGES, "default": DEFAULT, "build": _current, "texts": web_catalogs()}
    return "window.CEV_I18N = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
