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
    return searchdata.read_all(site)


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
    assert not (site / "archive" / "search.json").exists() and not (site / "search-data.js").exists()  # one storage


def _armed(pg) -> None:
    """AF-f6 (15/11): count the searches done (search.js says "cev-content" at the end of each one)."""
    pg.evaluate("window.__searched = 0; document.addEventListener('cev-content', () => { window.__searched++; })")


def _content(pg, box, text: str) -> None:
    """Fill the content search and wait for its end (the debounce and the parts read), not a fixed delay."""
    n = pg.evaluate("window.__searched")
    box.fill(text)
    pg.wait_for_function("n => window.__searched > n", arg=n)


def _pos(pg) -> str:
    """The position "i / n" once the passages are counted (written once, after the whole count)."""
    pg.wait_for_function("Boolean((document.querySelector('.hit-pos') || {}).textContent)")
    return pg.inner_text(".hit-pos")


def _aimed(pg) -> None:
    """Wait until the page has reached the current passage (the aim follows the formulas drawn on the way)."""
    pg.wait_for_function("() => { const m = document.querySelector('.cev-hit.current');"
                         " if (!m) { return false; } const t = m.getBoundingClientRect().top;"
                         " return t > 0 && t < innerHeight; }")


def test_search_in_the_browser(tmp_path: Path, page) -> None:  # noqa: F811
    pg = page
    site = tmp_path / "site"
    build_site(ExportData(conversations=CONVS), site)
    pg.goto((site / "index.html").as_uri())
    pg.click("#tab-filters")  # 14/11: the filters in their tab

    def shown() -> list[str]:
        return sorted(pg.locator(".conversation-item:visible").evaluate_all("l => l.map(e => e.dataset.key)"))

    box = pg.locator("#content-search")
    _armed(pg)
    _content(pg, box, "zanzibar")  # only in claude.ai's instructions: nothing found
    assert shown() == []
    _content(pg, box, "ev")  # fewer than 3 letters: nothing filtered
    assert shown() == ["c1", "c2", "c3"]
    _content(pg, box, "evenement")  # accents and case ignored
    assert shown() == ["c1"]
    assert pg.inner_text('[data-key="c1"] .content-hits') == "2 passages trouvés"
    assert pg.get_attribute('[data-key="c1"] a', "href").endswith("c1.html?q=evenement")
    _content(pg, box, "loi stable")  # every word
    assert shown() == ["c1", "c2"]
    _content(pg, box, "loi poker")  # every word, not any of them
    assert shown() == ["c2"]
    _content(pg, box, "loi stable")
    pg.fill("#search", "second")  # with the search in the titles (applied as one types)
    assert shown() == ["c2"]
    pg.fill("#search", "")
    _content(pg, box, "ÉVÉNEMENT")  # typed with accents and capitals
    assert shown() == ["c1"]
    assert pg.get_attribute('[data-key="c2"] a', "href").endswith("c2.html")  # not found: plain link

    pg.goto((site / "conversations" / "c1.html").as_uri())
    pg.click("#fold-all")  # answers hidden: the passage found in one is shown anyway
    pg.goto((site / "conversations" / "c1.html").as_uri() + "?q=" + "Événement")
    assert _pos(pg) == "1 / 2"
    assert "Mémoire : événement" in pg.locator(".injected").first.text_content()  # shown, not highlighted
    assert pg.locator(".injected mark").count() == 0
    for other in (".tool-use", ".tool-result", ".thinking"):  # shown on the page, never highlighted
        assert pg.locator(other).count() >= 1 and pg.locator(f"{other} mark").count() == 0, other
    assert pg.locator("mark.cev-hit").count() == 2
    assert [m.lower() for m in pg.locator("mark.cev-hit").all_inner_texts()] == ["événement", "événement"]
    pg.click('.hit-bar [data-step="1"]')
    assert pg.inner_text(".hit-pos") == "2 / 2"
    _aimed(pg)
    current = pg.locator("mark.cev-hit.current")
    assert current.is_visible()  # its answer was shown again
    box_top = current.evaluate("e => e.getBoundingClientRect().top")
    assert 0 < box_top < pg.viewport_size["height"]
    pg.click('.hit-bar [data-step="0"]')  # removes the highlighting
    assert pg.locator("mark.cev-hit").count() == 0 and not pg.locator(".hit-bar").is_visible()
    assert "Oui, cet événement est rare." in pg.inner_text(".messages")
    assert "?" not in pg.evaluate("location.href")  # a reload no longer highlights
    # the magnifier of the right column opens the bar again; the words can be changed in place
    pg.click('#page-nav [data-go="find"]')
    assert pg.locator(".hit-bar").is_visible() and pg.evaluate("document.activeElement.className") == "hit-words"
    pg.fill(".hit-words", "stable")
    pg.press(".hit-words", "Enter")
    pg.wait_for_function("document.querySelectorAll('mark.cev-hit').length === 1")
    assert pg.locator("mark.cev-hit").all_inner_texts() == ["stable"]  # counter-check: "événement" is no longer marked
    assert pg.inner_text(".hit-pos") == "1 / 1" and pg.evaluate("location.search") == "?q=stable"
    pg.press(".hit-words", "Enter")  # Enter again on the same words: the next passage (only one here)
    assert pg.inner_text(".hit-pos") == "1 / 1"
    pg.fill(".hit-words", "zzzintrouvable")
    pg.press(".hit-words", "Enter")
    assert pg.locator("mark.cev-hit").count() == 0 and pg.inner_text(".hit-pos") == "Introuvable dans cette page"
    pg.press(".hit-words", "Escape")
    assert not pg.locator(".hit-bar").is_visible()
    # the magnifier also closes it, highlighting removed
    pg.click('#page-nav [data-go="find"]')
    pg.fill(".hit-words", "stable")
    pg.press(".hit-words", "Enter")
    assert pg.locator("mark.cev-hit").count() == 1
    pg.click('#page-nav [data-go="find"]')
    assert not pg.locator(".hit-bar").is_visible() and pg.locator("mark.cev-hit").count() == 0
    # claude.ai's instructions in the user's message: in a frame "Ressources de claude.ai", hidden
    # as on claude.ai; once shown (body.cev-show-resources), closed and opened by a click
    frame = pg.locator(".cev-resources").first
    assert frame.locator(".injected").count() == 1 and not frame.is_visible()
    pg.evaluate("document.body.classList.add('cev-show-resources')")
    assert frame.is_visible() and not frame.locator(".injected").is_visible()
    frame.locator("> summary").click()
    assert frame.locator(".injected").is_visible()
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
        return _pos(pg)

    assert open_("alpha") == "1 / 2" and pg.locator(".math.cev-hit").count() == 0  # text only
    assert open_("\\alpha") == "1 / 2" and pg.locator("mark.cev-hit").count() == 0  # formulas only
    assert open_("\\in") == "Introuvable dans cette page"  # \in is not \int
    assert open_("∫") == "1 / 1" and pg.locator(".math.cev-hit").count() == 1
    assert open_("α") == "1 / 5"  # "alpha" twice and "α" in the text, two formulas
    for i in range(2, 6):
        pg.click('.hit-bar [data-step="1"]')
        assert pg.inner_text(".hit-pos") == f"{i} / 5"
        _aimed(pg)
        assert pg.locator(".cev-hit.current").count() == 1
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
    plans = []  # the index first (opened once, AF-f6), the pages then
    pg.goto((site / "index.html").as_uri())
    pg.click("#tab-filters")  # 14/11: the filters in their tab
    _armed(pg)
    for query in ("alpha", "alp alpha", "evenement", "loi stable", "Lévy", "\\alpha", "alpha \\alpha", "α", "≠",
                  "\\beta alpha", *none):
        _content(pg, pg.locator("#content-search"), query)
        counts = pg.locator(".conversation-item:visible").evaluate_all(
            "l => l.map(e => [e.dataset.key, parseInt(e.querySelector('.content-hits').textContent, 10)])")
        assert bool(counts) != (query in none), (query, counts)
        plans += [(query, key, n) for key, n in counts]
    for query, key, n in plans:
        pg.goto((site / "conversations" / f"{key}.html").as_uri() + "?q=" + quote(query))
        pg.wait_for_function("want => (document.querySelector('.hit-pos') || {}).textContent === want", arg=f"1 / {n}")
        assert pg.locator(".cev-hit").count() == n, (query, key, n)
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
    _aimed(pg)
    pg.wait_for_timeout(400)  # settled (the aim watches the passage a moment after arriving)
    top = pg.locator("mark.cev-hit.current").evaluate("e => e.getBoundingClientRect().top")
    assert 0 < top < pg.viewport_size["height"], top
    ys = pg.evaluate("window.__ys")
    steps = [b - a for a, b in zip(ys, ys[1:])]
    assert max(steps) <= 0.2 * ys[-1] + 50, (max(steps), ys[-1])
    assert min(steps) >= -50  # never back up
    assert pg.errors == []


def test_approximate_search(tmp_path: Path, page) -> None:  # noqa: F811
    """AE-m1 (08/11): "Tolérance ◂ n ▸" in the index and on the page (shared, ?f=n): the words of the text
    that differ by at most n letters are found too (less than 4 letters: exact; 4 to 6 letters: 1 at most),
    and listed ("Aussi trouvé : …"); the index and the page count the same passages."""
    pg = page
    site = tmp_path / "site"
    build_site(ExportData(conversations=[
        _conv("a1", "Lois", "Une loi alpha-stable ?", "Oui, alpha-stable de Lévy."),
        _conv("a2", "Autre", "Rien de stable ici.", "Non."),
    ]), site)

    def search(query: str, level: int) -> list:
        pg.goto((site / "index.html").as_uri())
        pg.click("#tab-filters")  # 14/11: the filters in their tab
        box = pg.locator(".filter-searches .cev-fuzzy")
        while int(box.locator(".cev-fuzzy-n").inner_text()) != level:
            box.locator('[data-d="1"]' if int(box.locator(".cev-fuzzy-n").inner_text()) < level else '[data-d="-1"]').click()
        _armed(pg)
        _content(pg, pg.locator("#content-search"), query)
        return pg.locator(".conversation-item:visible").evaluate_all(
            "l => l.map(e => [e.dataset.key, parseInt(e.querySelector('.content-hits').textContent, 10)])")

    assert search("alpah-stable", 0) == []
    assert search("alpah-stable", 1) == []             # 2 letters swapped = 2 differences
    found = search("alpah-stable", 2)
    assert [k for k, _ in found] == ["a1"] and found[0][1] == 2
    assert "Aussi trouvé : alpha-stable" in pg.get_attribute("#content-search", "title")  # a tooltip, no line under
    assert pg.locator(".content-also").count() == 0
    href = pg.locator(".conversation-item:visible a").first.get_attribute("href")
    assert href.endswith("?q=alpah-stable&f=2")
    pg.goto((site / "conversations" / "a1.html").as_uri() + "?q=alpah-stable&f=2")
    assert _pos(pg) == "1 / 2" and pg.locator(".cev-hit").count() == 2
    assert "alpha-stable" in pg.inner_text(".hit-also")
    pg.locator(".hit-bar .cev-fuzzy [data-d='-1']").click()   # 1 on the page: none, the bar stays open (08/11)
    pg.wait_for_function("document.querySelectorAll('.cev-hit').length === 0")
    assert pg.is_visible(".hit-bar") and pg.input_value(".hit-bar input") == "alpah-stable"
    assert "f=1" in pg.url
    assert [k for k, _ in search("levi", 2)] == ["a1"]   # 4 letters: 1 difference ("levy")
    assert search("lui", 2) == []                       # 3 letters: exact ("loi" not found)
    assert pg.locator(".filter-searches .cev-fuzzy [data-d='1']").is_disabled()  # 2 at most (08/11)
    assert pg.errors == []


def test_closing_the_bar_does_not_move_the_page(tmp_path: Path, page) -> None:  # noqa: F811
    """08/11: closing the bar right after a jump to a passage left the page going up by itself (it still aimed at
    the passage, gone)."""
    pg = page
    site = tmp_path / "site"
    long = "\n\n".join(f"Paragraphe {i} sans rien de particulier." for i in range(120))
    build_site(ExportData(conversations=[_conv("b1", "Long", "Question", long + "\n\nLe mot cible est ici.")]), site)
    pg.set_viewport_size({"width": 1366, "height": 700})
    pg.goto((site / "conversations" / "b1.html").as_uri() + "?q=cible")
    pg.wait_for_timeout(1200)                                  # arrived (and still watched 1.5 s)
    y = pg.evaluate("scrollY")
    assert y > 1000
    # the close button of the bar itself (a click outside the bar would stop the scrolling anyway)
    pg.click('.hit-bar [data-step="0"]')
    pg.wait_for_timeout(1500)
    assert pg.is_hidden(".hit-bar") and abs(pg.evaluate("scrollY") - y) < 2


def test_an_update_of_the_program_does_not_read_the_pages_again(tmp_path: Path, monkeypatch) -> None:
    """15/11: after an update that leaves the reading of the messages alone, the pages are made again but their
    text for the search is kept (half of a rebuild, measured); a changed conversation is read again."""
    from claude_export_viewer import html_builder, renderer, searchdata
    site = tmp_path / "site"
    build_site(ExportData(conversations=CONVS), site)
    before = _data(site)
    calls = []
    real = searchdata.from_page
    monkeypatch.setattr(searchdata, "from_page", lambda html: calls.append(1) or real(html))
    monkeypatch.setattr(html_builder, "generator_signature", lambda: "autre-version")
    archive = Archive(site)
    stats = build_site_from_archive(archive, site)
    assert stats.rendered == len(CONVS) and calls == [] and _data(site) == before
    build_site_from_archive(Archive(site), site, force=True)  # --reconstruire: the pages, not the text (its own key)
    assert calls == []
    monkeypatch.setattr(html_builder, "search_signature", lambda: "autre-lecture")  # the reading changed: read again
    build_site_from_archive(Archive(site), site)
    assert len(calls) == len(CONVS) and _data(site) == before
    # an unknown language of code: Pygments asked once, not at every block (15/11)
    asked = []
    monkeypatch.setattr(renderer, "get_lexer_by_name", lambda *a, **k: asked.append(a) or (_ for _ in ()).throw(ValueError()))
    renderer._lexer_for.cache_clear()
    for _ in range(3):
        assert renderer._highlight_code("x = 1", "inconnu-de-pygments") == "x = 1"
    assert len(asked) == 1
    renderer._lexer_for.cache_clear()


def test_pygments_plugins_looked_for_once(monkeypatch) -> None:
    """15/11: the plugins of Pygments looked for once per run, also by a file name (created.language): older
    Pygments scan every installed package at each lookup. Counted through the namespace the functions really use."""
    import pygments.lexers as lexers
    from claude_export_viewer import created, renderer
    names = lexers.find_lexer_class_for_filename.__globals__
    looks = []
    monkeypatch.setitem(names, "find_plugin_lexers", lambda: looks.append(1) or iter(()))
    renderer._plugins_once()
    for name in ("a.py", "b.unknownext", "Makefile", "c.js"):
        created.language(name)
    renderer._lexer_for.cache_clear()
    renderer._lexer_for("inconnu-de-pygments")
    renderer._lexer_for.cache_clear()
    assert looks == [1]


def test_coloured_code_kept_between_rebuilds(monkeypatch) -> None:
    """15/11: the same code gives the same colours: Pygments colours it once, the next rebuilds read it back."""
    from claude_export_viewer import codecache, renderer
    monkeypatch.setattr(codecache, "_db", None)  # (the cache of this test)
    monkeypatch.setattr(codecache, "_broken", False)
    calls = []
    real = renderer.highlight
    monkeypatch.setattr(renderer, "highlight", lambda *a: calls.append(1) or real(*a))
    first = renderer._highlight_code("def f(x):\n    return x * 2\n", "python")
    assert renderer._highlight_code("def f(x):\n    return x * 2\n", "python") == first and len(calls) == 1
    assert codecache.path().is_file() and "<span" in first
    renderer._highlight_code("def g():\n    pass\n", "python")
    assert len(calls) == 2  # other code: coloured


def test_markdown_read_kept_between_rebuilds(monkeypatch) -> None:
    """15/11: the HTML of a Markdown text is kept; mistune reads it once; another language reads it again."""
    from claude_export_viewer import i18n, renderer
    calls = []
    real = renderer._md
    monkeypatch.setattr(renderer, "_md", lambda text: calls.append(1) or real(text))
    text = "Un **texte** avec $x^2$ et\n\n```python\nx = 1\n```\n"
    first = renderer.render_markdown(text)
    assert renderer.render_markdown(text) == first and len(calls) == 1
    monkeypatch.setattr(i18n, "language", lambda: "en")  # its texts (the button "Copy"…) differ
    renderer.render_markdown(text)
    assert len(calls) == 2


def test_a_page_does_each_thing_once(tmp_path: Path, monkeypatch) -> None:
    """15/11 (PT-m6): each message validated once per page, written once for both Markdown versions,
    and the files handed over by Claude rebuilt only when the conversation changes."""
    from claude_export_viewer import created, html_builder, markdown_export, userfiles
    site = tmp_path / "site"
    build_site(ExportData(conversations=CONVS), site)
    files = userfiles.load(site)  # the links of the conversations, as after a use of the page Fichiers
    for c in CONVS:
        userfiles._links(files, Archive(site), c["uuid"])
    userfiles.save(site, files)
    n = sum(len(c["chat_messages"]) for c in CONVS)
    rebuilt, parsed, written = [], [], []
    real_r, real_p, real_m = created.reconstruct, html_builder.parse_message, markdown_export.message_body
    monkeypatch.setattr(created, "reconstruct", lambda raw: rebuilt.append(1) or real_r(raw))
    monkeypatch.setattr(html_builder, "parse_message", lambda raw: parsed.append(1) or real_p(raw))
    monkeypatch.setattr(markdown_export, "message_body", lambda *a, **k: written.append(1) or real_m(*a, **k))
    before = {p.name: p.read_text(encoding="utf-8") for p in site.glob("conversations/*.html")}
    build_site_from_archive(Archive(site), site, force=True)
    assert rebuilt == [] and len(parsed) == n and len(written) == n
    assert {p.name: p.read_text(encoding="utf-8") for p in site.glob("conversations/*.html")} == before
    monkeypatch.setattr(created, "_signature", lambda: "created:autre")  # created.py changed: rebuilt
    build_site_from_archive(Archive(site), site, force=True)
    assert len(rebuilt) == len(CONVS)
    assert created.language("a/b/x.py") == created.language("x.py") == "python"
