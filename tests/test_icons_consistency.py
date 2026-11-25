"""One drawing, one meaning (audit of the interface, 22/11): two controls of the pages that show the same icon
must do the same thing. (The export of a message showed the arrow that folds a bubble.)"""
import json
import re
import threading
import zipfile
from pathlib import Path

from claude_export_viewer.cli import main
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_topics_browser import page  # noqa: F401

R = "00000000-0000-4000-8000-000000000000"
LONG = ("Une réponse détaillée sur plusieurs lignes pour plier les bulles. " * 8 + "\n\n") * 4
CODE = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(14)) + "\n```"

# Families of controls that share a drawing on purpose: the same meaning in several places (the panel that lists
# the favorites shows the star of "add to favorites", "close" and "remove" are both the cross…). The keys of the
# titles, so that the test does not depend on the language.
FAMILIES = [
    {"web.close", "web.hits.close", "web.highlight_remove"},                 # close / remove (the cross)
    {"web.copy_title", "web.copy_msg", "web.created.copy"},                  # copy
    {"web.export_msg", "web.created.save"},                                  # export, save as a file
    {"web.fav.add", "tab:fav-list"},                                         # favorites: the button, its panel
    {"web.note.add", "tab:note-list"},                                       # notes
    {"web.title.add", "tab:title-list"},                                     # titles
    {"web.speak.title", "web.speak.all", "web.speak.voices_title"},          # voice
    {"web.fold.answer_hide", "web.fold.answer_show", "web.fold.all_hide", "web.fold.all_show"},  # hide the answers
    {"web.plan.close", "web.plan.open", "web.fold.bubble", "web.run.full_less", "class:plan-only plan-dn"},  # fold
]

JS = r"""() => {
  const out = [];
  for (const el of document.querySelectorAll('button, a, summary, [role=button]')) {
    const svg = el.querySelector('svg');
    if (!svg) continue;
    const shown = Array.from(svg.querySelectorAll('path,line,polyline,polygon,circle,rect'))
      .filter(e => getComputedStyle(e).display !== 'none' && (!e.closest('g') || getComputedStyle(e.closest('g')).display !== 'none'));
    const drawing = shown.map(e => e.tagName + (e.getAttribute('d') || e.getAttribute('points') ||
      ['x', 'y', 'width', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2'].map(a => e.getAttribute(a)).join(','))).join('|');
    const attr = (el.getAttribute('data-i18n-attr') || '').match(/(?:title|aria-label):([\w.]+)/);
    const key = attr ? attr[1] : el.tagName === 'SUMMARY' ? 'tab:' + el.parentElement.id : 'class:' + el.getAttribute('class');
    if (drawing) out.push([drawing, key]);
  }
  return out;
}"""


def _site(tmp: Path) -> Path:
    def msg(u, p, who, text):
        return {"uuid": u, "parent_message_uuid": p, "sender": who, "created_at": "2026-11-10T10:00:00Z",
                "content": [{"type": "text", "text": text}]}
    conv = {"uuid": "c1", "name": "Icônes", "created_at": "2026-11-10T09:00:00Z", "updated_at": "2026-11-10T10:00:00Z",
            "chat_messages": [msg("a1", R, "human", "Une question"), msg("a2", "a1", "assistant", LONG + CODE),
                              msg("a3", "a2", "human", "Une autre"), msg("a4", "a3", "assistant", "Une réponse.")]}
    conv["chat_messages"][3]["content"][:0] = [   # a file handed over: its "open" and "save" buttons
        {"type": "tool_use", "id": "t1", "name": "create_file", "input": {"path": "/mnt/user-data/outputs/f.py", "file_text": "a = 1\n"}},
        {"type": "tool_use", "id": "t2", "name": "present_files", "input": {"filepaths": ["/mnt/user-data/outputs/f.py"]}}]
    z = tmp / "e.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([conv]))
    site = tmp / "site"
    main([str(z), "-o", str(site), "--sans-navigateur", "--date-export", "2026-11-10"])
    return site


def test_one_drawing_one_meaning(tmp_path: Path, page) -> None:  # noqa: F811
    site = _site(tmp_path)
    server = make_server(site, 0, launcher=PROGRAM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        seen: dict[str, set[str]] = {}
        for url, lines in (("index.html", "all"), ("conversations/c1.html", "all"), ("conversations/c1.html", "1")):
            page.goto(base + url)   # (then the bubbles folded to one line: their "unfold" buttons appear)
            page.evaluate(f"() => localStorage.setItem('cev-read-lines', '{lines}')")
            page.reload()
            page.wait_for_timeout(400)
            for drawing, key in page.evaluate(JS):
                seen.setdefault(drawing, set()).add(re.sub(r"\s+", " ", key)[:60])
    finally:
        server.shutdown()
    clashes = {d[:50]: sorted(keys) for d, keys in seen.items()
               if len(keys) > 1 and not any(keys <= family for family in FAMILIES)}
    assert not clashes, clashes
