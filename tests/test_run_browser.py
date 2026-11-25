"""F2: "Lancer" runs a .jsx / .tsx / .html of Claude in a sandboxed frame under it (run.js): with the bundled
libraries, without access to the site, its storage or the network, unless the user agrees."""

import threading
from pathlib import Path

from .helpers import ExportData, build_site
from .test_topics_browser import page  # noqa: F401 - fixture

ROOT = "00000000-0000-4000-8000-000000000000"

DEMO = r'''import React, { useState } from "react";
import { LineChart, Line, XAxis, YAxis } from "recharts";
import { Camera } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import debounce from "lodash/debounce";
import * as d3 from "d3";
type Point = { x: number; y: number };
export default function App() {
  const [n, setN] = useState<number>(0);
  const data: Point[] = [{x: 1, y: 2}, {x: 2, y: 5}, {x: 3, y: 3}];
  return (<Card className="m-4"><CardHeader><CardTitle>Démo</CardTitle></CardHeader><CardContent>
    <button id="plus" className="bg-blue-600 text-white px-3 py-1 rounded" onClick={() => setN(n + 1)}><Camera size={16} /> compte {n}</button>
    <LineChart width={300} height={150} data={data}><XAxis dataKey="x" /><YAxis /><Line dataKey="y" isAnimationActive={false} /></LineChart>
    <p id="libs">{typeof debounce} {d3.max([1, 7, 3])}</p>
    <Tabs defaultValue="a"><TabsList><TabsTrigger value="a">A</TabsTrigger><TabsTrigger value="b">B</TabsTrigger></TabsList>
      <TabsContent value="a"><span id="tab">contenu A</span></TabsContent><TabsContent value="b"><span id="tab">contenu B</span></TabsContent></Tabs>
  </CardContent></Card>);
}'''

# What a program could try against the user: each attempt is written in the page of the frame
SPY = r'''import React, { useEffect, useState } from "react";
export default function Spy() {
  const [r, setR] = useState({});
  const add = (k, v) => setR((o) => ({ ...o, [k]: v }));
  useEffect(() => {
    document.addEventListener("securitypolicyviolation", (e) => add("bloqué:" + e.blockedURI, e.violatedDirective.split(" ")[0]));
    try { add("parent", String(window.parent.document.title)); } catch (e) { add("parent", "bloqué"); }
    try { localStorage.setItem("x", "1"); add("storage", "ouvert"); } catch (e) { add("storage", "bloqué"); }
    fetch("https://example.com/").catch(() => {});
    fetch("../index.html").catch(() => {});
  }, []);
  return <pre id="spy">{JSON.stringify(r)}</pre>;
}'''

HTML = '''<!doctype html><html><head><title>t</title><script src="https://cdn.example.com/lib.js"></script></head>
<body><p id="p">avant</p><script>document.getElementById("p").textContent = "script interne " + (typeof window.LIB);</script></body></html>'''


def art(id_: str, kind: str, title: str, content: str) -> dict:
    return {"type": "tool_use", "name": "artifacts",
            "input": {"id": id_, "type": kind, "title": title, "command": "create", "content": content}}


def site(tmp: Path, *blocks: dict) -> Path:
    msgs = [{"uuid": "q", "parent_message_uuid": ROOT, "sender": "human", "text": "q", "content": [{"type": "text", "text": "q"}]},
            {"uuid": "a", "parent_message_uuid": "q", "sender": "assistant", "text": "r",
             "content": [{"type": "text", "text": "Voici :"}, *blocks]}]
    out = tmp / "site"
    build_site(ExportData(conversations=[{"uuid": "c1", "name": "Essai", "chat_messages": msgs}]), out)
    return out


def test_react_with_bundled_libraries(tmp_path: Path, page) -> None:  # noqa: F811
    out = site(tmp_path, art("d", "application/vnd.ant.react", "Démo", DEMO))
    page.goto((out / "conversations" / "c1.html").as_uri())
    assert page.locator(".artifact .run-btn").count() == 1
    page.click(".run-btn")
    fr = page.frame_locator(".cev-run-frame")
    fr.locator("#plus").click(timeout=30000)
    assert fr.locator("#plus").text_content().strip() == "compte 1"          # React state (TSX types removed)
    assert fr.locator(".recharts-line").count() == 1                       # Recharts
    assert fr.locator("svg.lucide-camera").count() == 1                    # lucide-react
    assert fr.locator("#libs").text_content() == "function 7"              # lodash/debounce, d3
    assert "oklch" in fr.locator("#plus").evaluate("e => getComputedStyle(e).backgroundColor")  # Tailwind
    fr.get_by_text("B", exact=True).click()                                # shadcn Tabs stand-in
    assert fr.locator("#tab").text_content() == "contenu B"
    page.locator(".artifact-title").click()                                # the bar folds the strip
    assert not page.locator(".cev-run").is_visible()


def test_frame_is_isolated(tmp_path: Path, page) -> None:  # noqa: F811
    out = site(tmp_path, art("s", "application/vnd.ant.react", "Espion", SPY))
    page.goto((out / "conversations" / "c1.html").as_uri())
    page.evaluate("localStorage.setItem('secret', 'x')")
    page.click(".run-btn")
    spy = page.frame_locator(".cev-run-frame").locator("#spy")
    spy.filter(has_text="bloqué:file").wait_for(timeout=30000)  # file:// is reported without its path
    r = spy.text_content()
    assert '"parent":"bloqué"' in r and '"storage":"bloqué"' in r
    assert '"bloqué:https://example.com/":"connect-src"' in r and '"bloqué:file":"connect-src"' in r  # its own rules


def test_html_and_missing_library(tmp_path: Path, page) -> None:  # noqa: F811
    """What must come from the Internet is asked first (the one confirmation box): "Non" runs nothing."""
    out = site(tmp_path, art("h", "text/html", "Page", HTML))
    page.goto((out / "conversations" / "c1.html").as_uri())
    page.click(".run-btn")
    assert "cdn.example.com" in page.locator(".cev-confirm-text").text_content()
    page.click(".cev-confirm-no")
    assert page.locator(".cev-run").count() == 0 and page.locator(".cev-runnable").get_attribute("data-state") == "closed"
    page.click(".run-btn")
    page.click(".cev-confirm-yes")
    rule = page.locator(".cev-run-frame").get_attribute("srcdoc").split('Content-Security-Policy" content="')[1].split('"')[0]
    assert "script-src 'unsafe-inline' 'unsafe-eval' blob: data: https:" in rule        # opened to https after "Oui"
    assert page.locator(".cev-run-netnote").count() == 1
    p = page.frame_locator(".cev-run-frame").locator("#p")
    p.wait_for(timeout=10000)
    assert p.text_content() == "script interne undefined"                 # no network here: its own script runs


def test_one_strip_and_its_buttons(tmp_path: Path, page) -> None:  # noqa: F811
    """Folded at first; Lancer: the result (again on a second click); Code: 10 lines; ↓: all and back;
    the bar: fold / unfold; a button with nothing to do is greyed out."""
    code = "export default function A() { return <p id='ok'>résultat</p>; }\n" + "// ligne\n" * 30
    out = site(tmp_path, art("x", "application/vnd.ant.react", "Prog", code))
    page.goto((out / "conversations" / "c1.html").as_uri())
    box = page.locator(".cev-runnable")
    state = lambda: box.get_attribute("data-state")  # noqa: E731
    grey = lambda sel: page.locator(sel).evaluate("e => getComputedStyle(e).pointerEvents") == "none"  # noqa: E731
    pre = page.locator(".cev-pane pre")
    title = lambda sel: page.locator(sel).get_attribute("title")  # noqa: E731
    assert state() == "closed" and not pre.is_visible()
    assert page.locator(".run-btn").text_content().strip().endswith("Visualisation") and title(".run-btn") == "Visualiser ici"
    assert title(".code-btn") == "Affiche les 10 premières lignes (↓ pour le code entier)"
    assert title(".full-btn") == "10 premières lignes de code"
    bar_top = page.locator(".cev-bar").evaluate("e => e.getBoundingClientRect().top - e.parentNode.getBoundingClientRect().top")
    assert bar_top <= 1.5                                                  # against the line of the frame
    page.click(".full-btn")                                                # folded: ↓ shows the 10 lines
    assert state() == "code" and title(".full-btn") == "Code entier"
    page.locator(".artifact-title").click()
    page.click(".code-btn")
    assert state() == "code" and pre.is_visible() and pre.evaluate("e => e.clientHeight") < 250 and grey(".code-btn")
    assert "gradient" in pre.evaluate("e => getComputedStyle(e).maskImage")   # the cut is seen: the last line fades
    page.click(".full-btn")
    assert state() == "full" and pre.evaluate("e => e.clientHeight") > 400
    assert pre.evaluate("e => getComputedStyle(e).maskImage") == "none"
    assert title(".full-btn") == "10 premières lignes de code"
    page.click(".full-btn")
    assert state() == "code"
    page.click(".run-btn")
    fr = page.frame_locator(".cev-run-frame")
    assert fr.locator("#ok").text_content(timeout=30000) == "résultat"
    assert state() == "result" and not pre.is_visible() and grey(".full-btn") and not grey(".code-btn")
    assert page.locator(".cev-run").count() == 1
    page.click(".run-btn")                                                 # runs it again, still one strip
    fr.locator("#ok").wait_for(timeout=30000)
    assert page.locator(".cev-run").count() == 1
    page.locator(".artifact-title").click()
    assert state() == "closed" and not page.locator(".cev-run").is_visible()
    page.locator(".artifact-title").click()                                # folded: the bar does nothing
    assert state() == "closed" and not page.locator(".cev-run").is_visible()
    page.click(".code-btn")
    assert state() == "code" and not page.locator(".cev-run").is_visible()


def test_through_the_server(tmp_path: Path, page) -> None:  # noqa: F811
    from claude_export_viewer.server import make_server
    out = site(tmp_path, art("d", "application/vnd.ant.react", "Démo", DEMO))
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html")
        page.click(".run-btn")
        fr = page.frame_locator(".cev-run-frame")
        fr.locator("#plus").click(timeout=30000)
        assert fr.locator("#plus").text_content().strip() == "compte 1"
    finally:
        server.shutdown()
        server.server_close()


def test_files_of_claude_get_the_button(tmp_path: Path, page) -> None:  # noqa: F811
    """A .jsx / .html handed over by Claude (created.py) gets "Lancer", runs from its folded content; a .py none."""
    from .test_created_page import OUT, conv, site_with, use
    jsx = 'export default function A() { return <p id="ok">depuis un fichier</p>; }\n'
    raw = conv([use("t1", "create_file", path=OUT + "A.jsx", file_text=jsx),
                use("t2", "create_file", path=OUT + "f.py", file_text="a = 1\n"),
                use("t3", "present_files", filepaths=[OUT + "A.jsx", OUT + "f.py"])])
    out, _ = site_with(tmp_path, raw)
    page.goto(next((out / "conversations").glob("*.html")).as_uri())
    assert page.locator('.created-file[data-file="A.jsx"] .run-btn').count() == 1
    assert page.locator('.created-file[data-file="f.py"] .run-btn').count() == 0
    page.click(".run-btn")
    assert page.frame_locator(".cev-run-frame").locator("#ok").text_content(timeout=30000) == "depuis un fichier"
    page.click('.created-file[data-file="A.jsx"] .code-btn')
    assert page.locator(".created-file .cev-pane pre").is_visible() and page.locator(".cev-run").is_hidden()


def test_tailwind_3_defaults(tmp_path: Path, page) -> None:  # noqa: F811
    code = 'export default function A() { return <div id="b" className="border p-2">x</div>; }'
    out = site(tmp_path, art("b", "application/vnd.ant.react", "Bord", code))
    page.goto((out / "conversations" / "c1.html").as_uri())
    page.click(".run-btn")
    b = page.frame_locator(".cev-run-frame").locator("#b")
    b.wait_for(timeout=30000)
    assert b.evaluate("e => getComputedStyle(e).borderTopColor") != b.evaluate("e => getComputedStyle(e).color")


WIDGET = '''<h2 class="sr-only">Séries</h2>
<div style="display:flex;gap:12px;align-items:center"><label id="lab" style="color: var(--text-secondary)">Mains</label>
<input type="range" id="n" min="10" max="100" value="50"><span id="out">50</span></div>
<svg viewBox="0 0 300 600" xmlns="http://www.w3.org/2000/svg"><g class="c-blue"><rect id="r" x="10" y="10" width="100" height="40" rx="4"/>
<text class="th" x="20" y="35">Gains</text></g></svg>
<script>document.getElementById("n").oninput = (e) => { document.getElementById("out").textContent = e.target.value; };</script>'''


def widget(code: str, title: str = "series_gagnantes") -> list[dict]:
    """The blocks claude.ai leaves for a visual shown in the chat."""
    return [{"type": "tool_use", "name": "show_widget", "integration_name": "visualize", "message": "show_widget",
             "input": {"loading_messages": ["Calcul"], "title": title, "widget_code": code}},
            {"type": "tool_result", "name": "show_widget", "content": [{"type": "text", "text": "Content rendered and shown to the user."}]}]


def test_widget_in_the_conversation(tmp_path: Path, page) -> None:  # noqa: F811
    out = site(tmp_path, *widget(WIDGET))
    page.goto((out / "conversations" / "c1.html").as_uri())
    assert page.locator(".widget .artifact-title").text_content().strip().endswith("Series gagnantes")
    assert page.locator(".widget").get_attribute("data-state") == "closed"  # folded at first
    page.locator(".widget .artifact-title").click()                        # folded: the bar does nothing
    assert page.locator(".widget").get_attribute("data-state") == "closed" and page.locator(".cev-run").count() == 0
    assert not page.locator(".widget .cev-pane pre").is_visible()          # its code is never shown
    assert page.locator(".cev-resources").count() == 1                     # the result stays with the resources
    page.click(".widget .run-btn")
    fr = page.frame_locator(".cev-run-frame")
    out_ = fr.locator("#out")
    out_.wait_for(timeout=30000)
    fr.locator("#n").fill("70")
    assert out_.text_content() == "70"                                      # its script runs
    assert fr.locator("#lab").evaluate("e => getComputedStyle(e).color") == "rgb(95, 94, 90)"  # --text-secondary
    assert fr.locator("#r").evaluate("e => getComputedStyle(e).fill") == "rgb(230, 241, 251)"  # c-blue 50
    page.wait_for_function("() => document.querySelector('.cev-run-frame').offsetHeight > 500")  # fits its content
    width = lambda sel: page.locator(sel).evaluate("e => e.getBoundingClientRect().width")  # noqa: E731
    assert width(".cev-run-frame") > 0.9 * width(".messages") - 60          # the whole width, even after a short text


def test_widget_dark(tmp_path: Path, page) -> None:  # noqa: F811
    out = site(tmp_path, *widget(WIDGET))
    page.emulate_media(color_scheme="dark")
    page.goto((out / "conversations" / "c1.html").as_uri())
    page.click(".widget .run-btn")
    r = page.frame_locator(".cev-run-frame").locator("#r")
    r.wait_for(timeout=30000)
    assert r.evaluate("e => getComputedStyle(e).fill") == "rgb(12, 68, 124)"   # c-blue 800 in dark


SAVED_CSS = (':root{--text-primary:#101010;--text-secondary:#123456;--surface-1:#fafafa}'
             '[data-mode="dark"]{--text-secondary:#abcdef}.c-blue>rect{fill:#E6F1FB}')


def saved(code: str) -> str:
    """A visual saved from claude.ai: its page, with its style sheet and the code in #vis-container."""
    return (f'<!doctype html>\n<html data-saved=""><head><meta charset="utf-8"><style>\n{SAVED_CSS}\n</style>'
            '<style>body { padding: 16px; }</style></head><body><div id="vis-container">\n' + code + '\n</div></body></html>\n')


def test_saved_visual_linked_and_run(tmp_path: Path, page) -> None:  # noqa: F811
    """The file saved from claude.ai (<title>.html) is found like the other files: link "html", Lancer runs
    it as it is; its style sheet is learnt (archive, never shipped) for the visuals not saved."""
    from .test_userfiles import update
    out = site(tmp_path, *widget(WIDGET), *widget(WIDGET.replace('id="', 'id="b'), "autre_visuel"))
    dl = tmp_path / "dl"
    dl.mkdir()
    (dl / "series_gagnantes.html").write_text(saved(WIDGET.replace(">Mains<", ">Mains enregistrées<")), encoding="utf-8")
    update(out, [dl])
    assert (out / "archive" / "claude-widget.css").read_text(encoding="utf-8").strip() == SAVED_CSS
    page.goto((out / "conversations" / "c1.html").as_uri())
    first, second = page.locator(".widget").nth(0), page.locator(".widget").nth(1)
    assert first.locator("a.cev-html").get_attribute("href").endswith("/series_gagnantes.html")
    assert second.locator("a.cev-html").count() == 0 and second.locator(".cev-html").text_content() == "html ?"
    assert second.locator(".cf-link").count() == 1                         # to associate it by hand
    first.locator(".run-btn").click()
    lab = first.frame_locator(".cev-run-frame").locator("#lab")
    assert lab.text_content(timeout=30000) == "Mains enregistrées"         # the saved file itself
    rule = first.locator(".cev-run-frame").get_attribute("srcdoc")
    assert "Content-Security-Policy" in rule and "connect-src 'none'" in rule  # under the rules of the frame
    page.wait_for_function("() => document.querySelector('.widget .cev-run-frame').offsetHeight > 500")  # its height
    assert second.locator(".cf-link").get_attribute("title") == "Choisir le fichier html"
    assert second.locator(".artifact-type").text_content() == ""           # no "Visualisation" in the bar
    second.locator(".run-btn").click()
    blab = second.frame_locator(".cev-run-frame").locator("#blab")
    blab.wait_for(timeout=30000)
    assert blab.evaluate("e => getComputedStyle(e).color") == "rgb(18, 52, 86)"  # #123456: claude.ai's sheet



def test_choosing_the_html_closes_the_strip(tmp_path: Path, page) -> None:  # noqa: F811
    """Through the server, 🔗 folds the strip first: its menu is then the only strip."""
    from claude_export_viewer.server import make_server
    out = site(tmp_path, *widget(WIDGET))
    server = make_server(out, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html")
        box = page.locator(".widget")
        top = box.locator(".cev-bar").evaluate("e => e.getBoundingClientRect().top - e.parentNode.getBoundingClientRect().top")
        assert top <= 1.5                                                  # the bar against the line of the frame
        assert box.locator(".code-btn, .full-btn").count() == 0             # a visual: no Code, no ↓
        page.click(".widget .run-btn")
        box.locator(".cev-run-frame").wait_for()
        assert box.get_attribute("data-state") == "result"
        page.click(".widget .cf-link")
        assert box.get_attribute("data-state") == "closed" and page.locator(".cf-menu").is_visible()
        assert not page.locator(".widget .cev-pane").is_visible() and not box.locator(".cev-run").is_visible()
        page.locator(".widget .artifact-title").click()                    # the bar closes the menu, opens nothing
        assert not page.locator(".cf-menu").is_visible()
        assert box.get_attribute("data-state") == "closed" and not box.locator(".cev-run").is_visible()
    finally:
        server.shutdown()
        server.server_close()



def test_short_code_does_not_fade(tmp_path: Path, page) -> None:  # noqa: F811
    code = "export default function A() { return <p>court</p>; }\n"
    out = site(tmp_path, art("c", "application/vnd.ant.react", "Court", code),
               {"type": "text", "text": "```python\n" + "x = 1\n" * 20 + "```"})
    page.goto((out / "conversations" / "c1.html").as_uri())
    page.click(".code-btn")
    assert page.locator(".cev-pane pre").evaluate("e => getComputedStyle(e).maskImage") == "none"   # 1 line: nothing cut
    long_pre = page.locator(".content-text .code-block.cev-long > pre")
    assert "gradient" in long_pre.evaluate("e => getComputedStyle(e).maskImage")                     # a code of the text
