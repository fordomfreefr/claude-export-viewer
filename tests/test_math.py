"""LaTeX formulas: recognised, protected from Markdown, and KaTeX bundled."""

from pathlib import Path

from claude_export_viewer.models import ChatMessage, Conversation, TextContent
from claude_export_viewer.renderer import render_markdown
from tests.helpers import ExportData, build_site


def test_inline_dollar_keeps_underscores_and_stars() -> None:
    out = render_markdown("Soit $x_1 + x_2 = a_i * b_i$ ici")
    assert '<span class="math math-inline" translate="no">x_1 + x_2 = a_i * b_i</span>' in out
    assert "<em>" not in out


def test_display_block_keeps_double_backslash() -> None:
    out = render_markdown("$$\n\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}\n$$")
    assert '<div class="math math-display" translate="no">\\begin{pmatrix} a &amp; b \\\\ c &amp; d \\end{pmatrix}</div>' in out


def test_display_dollars_inside_paragraph() -> None:
    out = render_markdown("On a $$\\int_0^1 x\\,dx$$ donc")
    assert '<span class="math math-display" translate="no">\\int_0^1 x\\,dx</span>' in out


def test_backslash_delimiters() -> None:
    out = render_markdown("Inline \\(\\alpha < 2\\) et display \\[\\beta \\in [-1,1]\\]")
    assert '<span class="math math-inline" translate="no">\\alpha &lt; 2</span>' in out
    assert '<span class="math math-display" translate="no">\\beta \\in [-1,1]</span>' in out
    block = render_markdown("\\[\n\\varphi(t) = e^{i\\delta t}\n\\]")
    assert '<div class="math math-display" translate="no">\\varphi(t) = e^{i\\delta t}</div>' in block


def test_code_is_never_math() -> None:
    out = render_markdown("Code `$x_1$`\n\n```\n$y_2$ \\(z\\)\n```")
    assert "math" not in out
    assert "<code>$x_1$</code>" in out


def test_prices_and_escaped_dollars_are_not_math() -> None:
    for text in ("Il coûte $5 et $10", "5 $ et 10 $", "Échappé \\$ ici \\$", "Voir \\[1\\] et \\(2024\\)"):
        assert "math" not in render_markdown(text), text
    assert "[1]" in render_markdown("Voir \\[1\\]")


def test_math_in_lists_and_tables() -> None:
    out = render_markdown("- terme $\\alpha$\n- bloc :\n\n  $$\n  \\sum_k x_k\n  $$\n")
    assert '<span class="math math-inline" translate="no">\\alpha</span>' in out
    assert '<div class="math math-display" translate="no">\\sum_k x_k</div>' in out
    table = render_markdown("| a |\n|---|\n| $x^2$ |")
    assert '<td><span class="math math-inline" translate="no">x^2</span></td>' in table


def test_katex_assets_only_loaded_when_needed(tmp_path: Path) -> None:
    data = ExportData(
        conversations=[
            Conversation(
                uuid="avec",
                chat_messages=[ChatMessage(sender="assistant", content=[TextContent(text="Soit $\\alpha$.")])],
            ),
            Conversation(
                uuid="sans",
                chat_messages=[ChatMessage(sender="human", content=[TextContent(text="Bonjour")])],
            ),
        ]
    )
    build_site(data, tmp_path)
    katex = tmp_path / "conversations" / "katex"
    for name in ("katex.min.js", "katex.min.css", "render.js", "copy-tex.min.js", "LICENSE"):
        assert (katex / name).is_file(), name
    assert (katex / "fonts" / "KaTeX_Main-Regular.woff2").is_file()
    avec = (tmp_path / "conversations" / "avec.html").read_text(encoding="utf-8")
    sans = (tmp_path / "conversations" / "sans.html").read_text(encoding="utf-8")
    assert 'src="katex/katex.min.js"' in avec and 'href="katex/katex.min.css"' in avec
    assert "katex" not in sans.replace(str(tmp_path), "")  # (the temporary folder may be named after the test)
