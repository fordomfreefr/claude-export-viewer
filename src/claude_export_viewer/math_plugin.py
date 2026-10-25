"""Mistune plugin that protects LaTeX formulas from Markdown processing.

Recognised delimiters (the ones Claude uses):

    $...$        inline
    $$...$$      display (on its own lines, or inside a paragraph)
    \\(...\\)    inline
    \\[...\\]    display

The formula source is kept verbatim (only HTML-escaped) inside
``<span class="math math-inline">`` / ``<span|div class="math math-display">``;
KaTeX renders it in the browser (see ``static/katex/render.js``).

Written independently of ``mistune.plugins.math`` so that it behaves the same
with every mistune 3.x (Ubuntu 26.04 ships 3.1.4). Rules:

- code spans and code blocks are never touched;
- ``\\$`` stays a literal dollar sign;
- amounts such as "$5 and $10" are not formulas: the opening ``$`` must not be
  followed by a space, the closing ``$`` must not follow a space nor be
  followed by a digit, and inline ``$...$`` cannot span lines.
"""

from __future__ import annotations

import re
from typing import Any

from mistune.util import escape as _escape

_BLOCK_PATTERN = (
    # $$ formula $$ on a single line
    r"^ {0,3}\$\$(?P<cevm_bs>[^\n]+?)\$\$[ \t]*(?:\n|$)|"
    # $$ alone on a line, formula, $$ alone on a line
    r"^ {0,3}\$\$[ \t]*\n(?P<cevm_bm>[\s\S]+?)\n {0,3}\$\$[ \t]*(?:\n|$)|"
    # \[ formula \] on a single line
    r"^ {0,3}\\\[(?P<cevm_ks>[^\n]+?)\\\][ \t]*(?:\n|$)|"
    # \[ alone on a line, formula, \] alone on a line
    r"^ {0,3}\\\[[ \t]*\n(?P<cevm_km>[\s\S]+?)\n {0,3}\\\][ \t]*(?:\n|$)"
)

_INLINE_PATTERN = (
    r"\$\$(?P<cevm_dd>(?:[^$\\]|\\.)+?)\$\$|"
    r"\\\((?P<cevm_p>[\s\S]+?)\\\)|"
    r"\\\[(?P<cevm_k>[\s\S]+?)\\\]|"
    r"\$(?!\s)(?P<cevm_d>(?:[^$\\\n]|\\.)+?)(?<!\s)\$(?!\d)"
)

_HAS_MATH = re.compile(r'class="math math-')


def _parse_block(block: Any, m: re.Match[str], state: Any) -> int:
    text = next(t for t in (m.group(g) for g in ("cevm_bs", "cevm_bm", "cevm_ks", "cevm_km")) if t is not None)
    state.append_token({"type": "cev_math_block", "raw": text.strip()})
    return m.end()


# "\[1\]" or "\(2024\)" in prose are escaped brackets/parentheses, not formulas.
_NOT_A_FORMULA = re.compile(r"[\d\s.,;:\-–]*")


def _parse_inline(inline: Any, m: re.Match[str], state: Any) -> int:
    for group, kind in (
        ("cevm_dd", "cev_math_display"),
        ("cevm_k", "cev_math_display"),
        ("cevm_p", "cev_math_inline"),
        ("cevm_d", "cev_math_inline"),
    ):
        text = m.group(group)
        if text is None:
            continue
        if group in ("cevm_k", "cevm_p") and _NOT_A_FORMULA.fullmatch(text):
            opening, closing = ("[", "]") if group == "cevm_k" else ("(", ")")
            state.append_token({"type": "text", "raw": opening + text + closing})
        else:
            state.append_token({"type": kind, "raw": text.strip()})
        break
    return m.end()


def _render_block(renderer: Any, text: str) -> str:
    return f'<div class="math math-display" translate="no">{_escape(text)}</div>\n'


def _render_display(renderer: Any, text: str) -> str:
    return f'<span class="math math-display" translate="no">{_escape(text)}</span>'


def _render_inline(renderer: Any, text: str) -> str:
    return f'<span class="math math-inline" translate="no">{_escape(text)}</span>'


def latex_math(md: Any) -> None:
    """Register the plugin on a mistune.Markdown instance."""
    md.block.register("cev_math_block", _BLOCK_PATTERN, _parse_block, before="list")
    # Formulas are also common inside lists and quotes.
    for rules in (getattr(md.block, "list_rules", None), getattr(md.block, "block_quote_rules", None)):
        if isinstance(rules, list) and "cev_math_block" not in rules:
            md.block.insert_rule(rules, "cev_math_block", before="list")
    # Before "escape": at a backslash, "\(" must be read as math, not as an escaped "(".
    md.inline.register("cev_math_inline", _INLINE_PATTERN, _parse_inline, before="escape")
    if md.renderer and getattr(md.renderer, "NAME", "") == "html":
        md.renderer.register("cev_math_block", _render_block)
        md.renderer.register("cev_math_display", _render_display)
        md.renderer.register("cev_math_inline", _render_inline)


def contains_math(rendered_html: str) -> bool:
    return bool(_HAS_MATH.search(rendered_html))
