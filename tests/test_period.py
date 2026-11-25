"""Filter of the index by period, combined with the other filters, and the overview (browser
tests, skipped without Chromium). Dates are relative to today, so that "7 derniers jours" etc.
stay right."""

from datetime import datetime, timedelta
from pathlib import Path

from .helpers import ExportData, build_site
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"


def _iso(d: datetime) -> str:
    return d.astimezone().isoformat()


def _conv(uuid: str, name: str, *days: datetime) -> dict:
    msgs, parent = [], ROOT
    for i, d in enumerate(days):
        msgs.append({"uuid": f"{uuid}m{i}", "parent_message_uuid": parent, "sender": "human" if i % 2 == 0 else "assistant",
                     "created_at": _iso(d), "content": [{"type": "text", "text": f"Texte {i}"}]})
        parent = msgs[-1]["uuid"]
    return {"uuid": uuid, "name": name, "created_at": _iso(days[0]), "chat_messages": msgs}


def _shown(pg) -> list[str]:
    return pg.eval_on_selector_all(".conversation-item",
                                   "els => els.filter(e => e.style.display !== 'none').map(e => e.dataset.uuid).sort()")


def test_period_filter(tmp_path: Path, page) -> None:  # noqa: F811
    now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    last_jan = now.replace(year=now.year - 1, month=1, day=15)
    convs = [
        _conv("recent", "Récente", now - timedelta(days=2)),
        _conv("old", "Ancienne reprise", now - timedelta(days=400), now - timedelta(days=3)),  # created long ago, active lately
        _conv("lastyear", "Janvier dernier", last_jan),
        _conv("twenty", "Vingt jours", now - timedelta(days=20)),
    ]
    site = tmp_path / "site"
    build_site(ExportData(conversations=convs), site)
    pg = page
    pg.goto((site / "index.html").as_uri())
    pg.click("#tab-filters")  # 14/11: the filters in their tab

    def shown() -> list[str]:
        return _shown(pg)

    assert shown() == ["lastyear", "old", "recent", "twenty"]
    pg.select_option("#filter-period", "7d")
    # "old" was created 400 days ago but had an exchange 3 days ago: kept (activity in the period)
    assert shown() == ["old", "recent"]
    pg.select_option("#filter-period", "30d")
    assert shown() == ["old", "recent", "twenty"]
    pg.select_option("#filter-period", "lastyear")
    expected = sorted(u for u, d in (("lastyear", last_jan), ("old", now - timedelta(days=400)))
                      if d.year == now.year - 1)
    assert shown() == expected
    pg.select_option("#filter-period", "year")
    assert "lastyear" not in shown() and "recent" in shown() or now.month == 1  # counter-check: last year left out
    # dates chosen by hand, the end day included
    assert pg.is_hidden("#period-dates")
    pg.select_option("#filter-period", "custom")
    assert pg.is_visible("#period-dates")
    assert shown() == ["lastyear", "old", "recent", "twenty"]  # empty: no limit
    day = (now - timedelta(days=20)).strftime("%Y-%m-%d")
    pg.fill("#period-from", day)
    pg.fill("#period-to", day)
    # the rule: created before the end and last exchange after the start; "old" (from -400 to -3
    # days) spans that day even without a message on it
    assert shown() == ["old", "twenty"]
    pg.fill("#period-from", (now - timedelta(days=19)).strftime("%Y-%m-%d"))
    assert shown() == ["old"]  # counter-check: the day after, "twenty" is out
    pg.fill("#period-from", day)
    pg.fill("#period-to", "")
    assert shown() == ["old", "recent", "twenty"]
    # combined with the search in the titles; the counter follows
    pg.fill("#search", "ancienne")
    assert shown() == ["old"] and pg.inner_text("#result-count") == "1 sur 4 conversations"
    # kept when coming back to the index
    pg.reload()
    pg.click("#tab-filters")  # 14/11: the filters in their tab
    assert pg.input_value("#filter-period") == "custom" and pg.input_value("#period-from") == day
    assert shown() == ["old"]
    pg.fill("#search", "")
    pg.select_option("#filter-period", "")
    assert shown() == ["lastyear", "old", "recent", "twenty"] and pg.is_hidden("#period-dates")
    assert not pg.errors


def test_overview(tmp_path: Path, page) -> None:  # noqa: F811
    now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    convs = [_conv("recent", "Récente", now - timedelta(days=1)),
             _conv("old", "Ancienne reprise", now - timedelta(days=400), now - timedelta(days=3)),
             _conv("twenty", "Vingt jours", now - timedelta(days=20), now - timedelta(days=20))]
    site = tmp_path / "site"
    build_site(ExportData(conversations=convs), site)
    pg = page
    pg.goto((site / "index.html").as_uri())
    assert pg.inner_text(".site-version").startswith("version ")
    # 14/11: three tabs (15/11: the data one always shown), the overview open at each opening of the page
    assert pg.locator(".index-tab:visible").all_inner_texts() == ["Vue d'ensemble", "Gestion des données", "Filtres"]
    assert pg.get_attribute("#tab-overview", "aria-selected") == "true" and pg.is_visible("#dash-body")
    line = pg.inner_text("#dash-sum")
    assert line.startswith("3 conversations · 5 messages · ≈ ") and line.endswith("(évaluation grossière)")
    assert pg.locator(".dash-tile").count() == 4 and pg.locator(".dash-bar").count() == 52  # no tile of the topics
    assert pg.locator("#dash-spark, .dash-line .fold-icon").count() == 0
    assert pg.locator(".dash-tile .v").first.inner_text() == "3"
    pg.click("#tab-overview")  # the open tab clicked: closed, nothing open
    assert pg.is_hidden("#overview") and pg.is_hidden("#filter-bar")
    pg.click("#tab-overview")
    pg.focus("#tab-overview")
    pg.keyboard.press("ArrowRight")  # the keyboard: the next tab (the data, here as a file: it says why it is empty)
    assert pg.is_visible("#admin-noserver") and pg.evaluate("document.activeElement.id") == "tab-data"
    pg.keyboard.press("ArrowRight")
    assert pg.is_visible("#filter-bar") and pg.is_hidden("#overview") and pg.evaluate("document.activeElement.id") == "tab-filters"
    pg.reload()
    assert pg.is_visible("#dash-body") and pg.is_hidden("#filter-bar")  # the overview again
    # AF-f4 (15/11): never backed up: the tile of the size says a backup is advised; a click opens the tab of the data
    assert pg.inner_text("#dash-save-due .s") == "Sauvegarde conseillée : aucune pour l'instant"
    pg.click("#dash-save-due")
    assert pg.get_attribute("#tab-data", "aria-selected") == "true"
    # 15/11: "<" ">" after the title: the history of the browser, greyed when there is nothing there
    assert pg.is_disabled("#hist-forward")
    pg.click(".conversation-item a >> nth=0")
    pg.wait_for_selector("#page-nav #hist-back:enabled")  # (greyed until the script has looked)
    assert pg.is_disabled("#hist-forward")
    pg.click("#hist-back")
    pg.wait_for_selector("#hist-forward:enabled")
    # the bar of this week counts the conversations active this week (computed here independently)
    weekday = now.weekday()
    this_monday = now.date() - timedelta(days=weekday)
    expected = sum(1 for last in (now - timedelta(days=1), now - timedelta(days=3)) if last.date() >= this_monday)
    assert pg.get_attribute(".dash-bar:last-child", "title").endswith(f" : {expected}")
    assert pg.inner_text("#dash-week") == f"cette semaine : {expected} conversation" + ("s" if expected > 1 else "")
    # a click on the bar of the week 20 days ago filters the list on that week
    twenty = (now - timedelta(days=20)).date()
    week = 51 - (this_monday - (twenty - timedelta(days=twenty.weekday()))).days // 7
    pg.locator(".dash-bar").nth(week).click()
    assert pg.input_value("#filter-period") == "custom"
    frm = datetime.strptime(pg.input_value("#period-from"), "%Y-%m-%d")
    to = datetime.strptime(pg.input_value("#period-to"), "%Y-%m-%d")
    assert frm.weekday() == 0 and (to - frm).days == 6 and frm.date() <= twenty <= to.date()
    assert _shown(pg) == ["old", "twenty"]  # "old" spans that week too (overlap rule of the period filter)
    assert pg.inner_text("#tab-filters") == "Filtres (1)"  # a filter set: said by its tab, even closed
    # < and >: 26 weeks back and forth, down to the oldest conversation (400 days ago)
    assert pg.is_disabled("#dash-next") and pg.is_enabled("#dash-prev")
    last_title = pg.get_attribute(".dash-bar:last-child", "title")
    pg.click("#dash-prev")
    assert pg.is_enabled("#dash-next") and pg.get_attribute(".dash-bar:last-child", "title") != last_title
    assert pg.get_attribute(".dash-bar:nth-child(26)", "title") != last_title
    # the window now starts 77 weeks back: 400 days (57 weeks) ago is inside, nothing older
    assert pg.is_disabled("#dash-prev")
    pg.click("#dash-next")
    assert pg.get_attribute(".dash-bar:last-child", "title") == last_title and pg.is_disabled("#dash-next")
    assert not pg.errors
