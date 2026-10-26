"""Search in the content of the conversations: data written with the site, index filter and
highlighted words on the page (browser tests skipped without Chromium)."""

import json
from pathlib import Path

from claude_export_viewer import searchdata
from claude_export_viewer.archive import Archive
from claude_export_viewer.html_builder import build_site_from_archive

from .helpers import ExportData, build_site
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def _conv(uuid: str, name: str, *texts: str) -> dict:
    msgs, parent = [], ROOT
    for i, text in enumerate(texts):
        mid = f"{uuid}m{i}"
        msgs.append({"uuid": mid, "parent_message_uuid": parent, "sender": "human" if i % 2 == 0 else "assistant",
                     "created_at": f"2026-09-06T10:{i:02d}:00Z", "content": [{"type": "text", "text": text}]})
        parent = mid
    return {"uuid": uuid, "name": name, "created_at": "2026-09-06T10:00:00Z", "chat_messages": msgs}


LONG = "Remplissage du texte de la réponse.\n\n" * 40
INJECTED = {"type": "injected_prompt_block", "prompt": "Mémoire : événement, loi stable, zanzibar.",
            "injection_source": {"type": "memory_block_head"}}
CONVS = [
    _conv("c1", "Premier", "Un Événement rare ?", LONG + "Oui, cet événement est rare.", "Et la loi stable ?", LONG),
    _conv("c2", "Second", "Parlons poker", "La loi stable de Lévy apparaît ici."),
    _conv("c3", "Troisième", "Rien à voir", "Vraiment rien."),
]


TOOLS = [{"type": "thinking", "thinking": "Réflexion : zanzibar et événement."},
         {"type": "tool_use", "name": "read_conversation", "input": {"query": "zanzibar événement"}},
         {"type": "tool_result", "name": "read_conversation", "content": [{"type": "text", "text": "Résultat : zanzibar, événement."}]}]
# not part of the conversation: claude.ai's instructions (first message of c1 and c3), Claude's
# thinking, tool calls and results (second message of c1 and c3)
for _c in (CONVS[0], CONVS[2]):
    _c["chat_messages"][0]["content"].insert(0, INJECTED)
    _c["chat_messages"][1]["content"][0:0] = TOOLS


def _data(site: Path) -> dict:
    text = (site / "search-data.js").read_text(encoding="utf-8")
    return json.loads(text.removeprefix("window.CEV_SEARCH = ").rstrip().removesuffix(";"))


def test_search_data(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build_site(ExportData(conversations=CONVS), site)
    data = _data(site)
    assert set(data) == {"c1", "c2", "c3"}
    assert "un evenement rare ?" in data["c1"]["t"] and "levy" in data["c2"]["t"]  # lower case, no accents
    assert not any("zanzibar" in e["t"] or any("zanzibar" in f for f in e["m"]) for e in data.values())
    assert searchdata.normalize("Événement À Lévy") == "evenement a levy"

    # a conversation gone from the archive leaves the data; the others are kept from the cache
    archive = Archive(site)
    del archive.conversations["c3"]
    build_site_from_archive(archive, site)
    assert set(_data(site)) == {"c1", "c2"}
    assert set(json.loads((site / "archive" / "search.json").read_text(encoding="utf-8"))) == {"c1", "c2"}


def test_search_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    site = tmp_path / "site"
    build_site(ExportData(conversations=CONVS), site)
    pg.goto((site / "index.html").as_uri())

    def shown() -> list[str]:
        return sorted(pg.locator(".conversation-item:visible").evaluate_all("l => l.map(e => e.dataset.key)"))

    box = pg.locator("#content-search")
    box.fill("zanzibar")  # only in claude.ai's instructions: nothing found
    pg.wait_for_timeout(600)
    assert shown() == []
    box.fill("ev")  # fewer than 3 letters: nothing filtered
    pg.wait_for_timeout(500)
    assert shown() == ["c1", "c2", "c3"]
    box.fill("evenement")  # accents and case ignored
    pg.wait_for_timeout(600)
    assert shown() == ["c1"]
    assert pg.inner_text('[data-key="c1"] .content-hits') == "2 passages trouvés"
    assert pg.get_attribute('[data-key="c1"] a', "href").endswith("c1.html?q=evenement")
    box.fill("loi stable")  # every word
    pg.wait_for_timeout(600)
    assert shown() == ["c1", "c2"]
    box.fill("loi poker")  # every word, not any of them
    pg.wait_for_timeout(600)
    assert shown() == ["c2"]
    box.fill("loi stable")
    pg.wait_for_timeout(600)
    pg.fill("#search", "second")  # with the search in the titles
    pg.wait_for_timeout(300)
    assert shown() == ["c2"]
    pg.fill("#search", "")
    box.fill("ÉVÉNEMENT")  # typed with accents and capitals
    pg.wait_for_timeout(600)
    assert shown() == ["c1"]
    assert pg.get_attribute('[data-key="c2"] a', "href").endswith("c2.html")  # not found: plain link

    pg.goto((site / "conversations" / "c1.html").as_uri())
    pg.click("#fold-all")  # answers hidden: the passage found in one is shown anyway
    pg.goto((site / "conversations" / "c1.html").as_uri() + "?q=" + "Événement")
    pg.wait_for_timeout(900)
    assert "Mémoire : événement" in pg.locator(".injected").first.text_content()  # shown, not highlighted
    assert pg.locator(".injected mark").count() == 0
    for other in (".tool-use", ".tool-result", ".thinking"):  # shown on the page, never highlighted
        assert pg.locator(other).count() >= 1 and pg.locator(f"{other} mark").count() == 0, other
    assert pg.locator("mark.cev-hit").count() == 2
    assert [m.lower() for m in pg.locator("mark.cev-hit").all_inner_texts()] == ["événement", "événement"]
    assert pg.inner_text(".hit-pos") == "1 / 2"
    pg.click('.hit-bar [data-step="1"]')
    pg.wait_for_timeout(700)
    assert pg.inner_text(".hit-pos") == "2 / 2"
    current = pg.locator("mark.cev-hit.current")
    assert current.is_visible()  # its answer was shown again
    box_top = current.evaluate("e => e.getBoundingClientRect().top")
    assert 0 < box_top < pg.viewport_size["height"]
    pg.click('.hit-bar [data-step="0"]')  # removes the highlighting
    assert pg.locator("mark.cev-hit").count() == 0 and pg.locator(".hit-bar").count() == 0
    assert "Oui, cet événement est rare." in pg.inner_text(".messages")
    assert pg.errors == []


def test_search_in_formulas(tmp_path: Path, page) -> None:  # noqa: F811
    """A word: the text only; a TeX command: the formulas only (whole command); a symbol: both.
    Formulas are drawn later by KaTeX: a formula found is highlighted as a whole."""
    from urllib.parse import quote
    pg = page
    site = tmp_path / "site"
    long = "Texte sans le mot.\n\n" * 60
    conv = _conv("m1", "Signes", "Le paramètre alpha ?",
                 long + "Pour $0 < \\alpha < 2$ la loi est stable, α aussi.\n\n" + long
                 + "$$\\int_0^1 x^{\\alpha} dx$$\n\nFin alpha.")
    build_site(ExportData(conversations=[conv]), site)

    def open_(query: str) -> str:
        pg.goto((site / "conversations" / "m1.html").as_uri() + "?q=" + quote(query))
        pg.wait_for_timeout(900)
        return pg.inner_text(".hit-pos")

    assert open_("alpha") == "1 / 2" and pg.locator(".math.cev-hit").count() == 0  # text only
    assert open_("\\alpha") == "1 / 2" and pg.locator("mark.cev-hit").count() == 0  # formulas only
    assert open_("\\in") == "absent de cette page"  # \in is not \int
    assert open_("∫") == "1 / 1" and pg.locator(".math.cev-hit").count() == 1
    assert open_("α") == "1 / 5"  # "alpha" twice and "α" in the text, two formulas
    for i in range(2, 6):
        pg.click('.hit-bar [data-step="1"]')
        pg.wait_for_timeout(900)
        assert pg.inner_text(".hit-pos") == f"{i} / 5"
        current = pg.locator(".cev-hit.current")
        assert current.count() == 1
        top = current.evaluate("e => e.getBoundingClientRect().top")
        assert 0 < top < pg.viewport_size["height"], i
    assert pg.locator(".math.cev-hit .katex").count() == 2  # drawn, still highlighted
    pg.click('.hit-bar [data-step="0"]')
    assert pg.locator(".cev-hit").count() == 0 and pg.locator(".katex").count() >= 2
    assert pg.errors == []


TRICKY = _conv("t1", "Pièges",
               "Formule $\\alpha + \\alpha^2$ et le mot alpha, puis **alpha** en gras ; motif coupé : om*ega*.",
               "Un [lien](https://exemple.org/alpha) dont l'adresse contient le mot, et alphabet.\n\n"
               "```python\nalpha = 1  # alpha\n```\n\n$$\\beta \\neq \\alpha$$ Fin : alp alpha.")
TRICKY["chat_messages"][1]["content"][0:0] = TOOLS


def test_index_and_page_count_the_same(tmp_path: Path, page) -> None:  # noqa: F811
    """The number shown in the index is the number of passages highlighted on the page."""
    from urllib.parse import quote
    pg = page
    site = tmp_path / "site"
    build_site(ExportData(conversations=[*CONVS, TRICKY]), site)
    # address of a link, tool blocks, word cut by the formatting, \ne is not \neq
    # beta: only as \beta in a formula; \ne is not \neq
    none = ("exemple", "zanzibar", "omega", "beta", "\\ne")
    for query in ("alpha", "alp alpha", "evenement", "loi stable", "Lévy", "\\alpha", "alpha \\alpha", "α", "≠",
                  "\\beta alpha", *none):
        pg.goto((site / "index.html").as_uri())
        pg.fill("#content-search", query)
        pg.wait_for_timeout(600)
        counts = pg.locator(".conversation-item:visible").evaluate_all(
            "l => l.map(e => [e.dataset.key, parseInt(e.querySelector('.content-hits').textContent, 10)])")
        assert bool(counts) != (query in none), (query, counts)
        for key, n in counts:
            pg.goto((site / "conversations" / f"{key}.html").as_uri() + "?q=" + quote(query))
            pg.wait_for_timeout(500)
            assert pg.locator(".cev-hit").count() == n, (query, key, n)
            assert pg.inner_text(".hit-pos") == f"1 / {n}", (query, key)
    assert pg.errors == []


def test_first_passage_far_below_formulas(tmp_path: Path, page) -> None:  # noqa: F811
    """The first passage, far down the page past many formulas drawn on the way (which change
    the height of the page): the page reaches it."""
    pg = page
    site = tmp_path / "site"
    formulas = "".join(f"Ligne {i} : $$\\\\sum_{{k=0}}^{{{i}}} \\\\frac{{x^k}}{{k!}} \\\\int_0^1 t^k dt$$\\n\\n" for i in range(150))
    conv = _conv("f1", "Loin", "Début", formulas + "Le mot zircon est ici.\\n\\n" + "Suite.\\n\\n" * 30)
    build_site(ExportData(conversations=[conv]), site)
    # every frame, the position of the page: no jump (a step larger than a fifth of the way)
    pg.add_init_script("window.__ys = []; (function f() { window.__ys.push(scrollY); requestAnimationFrame(f); })();")
    pg.goto((site / "conversations" / "f1.html").as_uri() + "?q=zircon")
    pg.wait_for_timeout(4000)
    top = pg.locator("mark.cev-hit.current").evaluate("e => e.getBoundingClientRect().top")
    assert 0 < top < pg.viewport_size["height"], top
    ys = pg.evaluate("window.__ys")
    steps = [b - a for a, b in zip(ys, ys[1:])]
    assert max(steps) <= 0.2 * ys[-1] + 50, (max(steps), ys[-1])
    assert min(steps) >= -50  # never back up
    assert pg.errors == []
