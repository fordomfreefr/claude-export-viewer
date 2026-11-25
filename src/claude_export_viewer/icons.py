"""The drawings of the icons used in several places (AF-f3, 14/11): written once here, for the templates
(``icon(name, size, cls)``), renderer.py (``svg``) and the scripts of the pages (``icons.js``, written with the
site: ``CEV.icon(name, size, cls)``). Each one is the inside of an SVG of 24×24 drawn with lines (style.css)."""

from __future__ import annotations

import json

ICONS = {
    "cross": '<path d="M6 6l12 12M18 6L6 18"/>',
    "fold": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',            # fold / unfold (frames, bubbles, code) only
    # (22/11, audit of the interface: one drawing, one meaning) export / save as a file: a page with an arrow going
    # down (the fold arrow before; an arrow into a tray still looked like it at 12 px); "open with the program of
    # the computer" keeps its arrow leaving a box (renderer._open_link)
    "export": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14l3 3 3-3"/>',
    # hide / show again Claude's answers (one message, or all: the chevron and the arrows before)
    "hide": '<path d="M3 3l18 18"/><path d="M10.6 6.2A9.8 9.8 0 0 1 12 6c5 0 8.5 4.3 9.5 6a15 15 0 0 1-2.6 3.3M6.5 7.6A15 15 0 0 0 2.5 12c1 1.7 4.5 6 9.5 6a9.6 9.6 0 0 0 4.4-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "show": '<path d="M2.5 12c1-1.7 4.5-6 9.5-6s8.5 4.3 9.5 6c-1 1.7-4.5 6-9.5 6s-8.5-4.3-9.5-6z"/><circle cx="12" cy="12" r="3"/>',
    "chevron": '<path d="M6 9l6 6 6-6"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',     # the page before / after in the history of the browser (15/11)
    "forward": '<path d="M9 5l7 7-7 7"/>',
    "star": '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
    "note": '<path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 7h4"/>',
    "title": '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
    # AE-m3 (16/11): a suite of conversations (two pages and an arrow), never the chain of a link
    "series": '<rect x="2" y="6" width="7" height="12" rx="1.5"/><rect x="15" y="6" width="7" height="12" rx="1.5"/>'
              '<path d="M10.5 12h3M12.2 10.3l1.5 1.7-1.5 1.7"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
    "speaker": '<path d="M4 9h4l5-4v14l-5-4H4z"/><path class="cev-speak-w1" d="M16.5 9.5a3.5 3.5 0 0 1 0 5"/>'
               '<path class="cev-speak-w2" d="M19 7a7 7 0 0 1 0 10"/>',
}


def svg(name: str, size: int = 16, cls: str = "") -> str:
    """The whole <svg> of an icon (KeyError for an unknown name: a typing error shows in the tests)."""
    klass = f' class="{cls}"' if cls else ""
    return (f'<svg{klass} viewBox="0 0 24 24" width="{size}" height="{size}" aria-hidden="true">'
            f"{ICONS[name]}</svg>")


def script() -> str:
    """icons.js: ``CEV.icon(name, size, cls)``, the same drawings for the scripts (loaded after i18n.js)."""
    return ("/* Written by the program (icons.py): the drawings of the icons used in several places. */\n"
            "(function () {\n  \"use strict\";\n"
            f"  var ICONS = {json.dumps(ICONS, ensure_ascii=False, indent=1)};\n"
            "  window.CEV.icon = function (name, size, cls) {\n"
            "    return '<svg' + (cls ? ' class=\"' + cls + '\"' : '') + ' viewBox=\"0 0 24 24\" width=\"' + (size || 16) +\n"
            "      '\" height=\"' + (size || 16) + '\" aria-hidden=\"true\">' + ICONS[name] + '</svg>';\n"
            "  };\n})();\n")
