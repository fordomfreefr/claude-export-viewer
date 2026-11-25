"""Reading a bubble aloud (speech.py, static/speak.js) with a stand-in for Piper: a program in the place of
the Python of its environment, which installs nothing, "downloads" empty voices and runs a small HTTP server
answering as piper.http_server, writing what it is asked to read."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from claude_export_viewer import settings, speech
from claude_export_viewer.server import make_server

from .test_admin import PROGRAM
from .test_plan import _site
from .test_topics_browser import page  # noqa: F401 - fixture

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX stand-in")

FAKE = f"""#!{sys.executable}
import json, sys, wave, io, pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer
home = pathlib.Path(__file__).resolve().parent.parent.parent  # <folder>/env/bin/python
a = sys.argv[1:]
def log(name, line):
    with open(home / name, "a", encoding="utf-8") as f:
        f.write(line + "\\n")
if a[:2] == ["-m", "pip"]:
    site = pathlib.Path(__file__).resolve().parent.parent / "lib" / "python3.14" / "site-packages"
    for m in ("piper", "flask"):
        (site / m).mkdir(parents=True, exist_ok=True)
    log("pip.txt", " ".join(a[2:]))
elif a[:2] == ["-m", "piper.download_voices"]:
    target, name = pathlib.Path(a[a.index("--data-dir") + 1]), a[-1]
    (target / (name + ".onnx")).write_bytes(b"x")
    speakers = {{"jessica": 0, "pierre": 1}} if "upmc" in name else {{str(1000 + i): i for i in range(12)}} if "-mls-" in name else {{}}
    (target / (name + ".onnx.json")).write_text(json.dumps({{"speaker_id_map": speakers}}))
    log("downloads.txt", name)
elif a[:2] == ["-m", "piper.http_server"]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *x): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{{}}")
        def do_POST(self):
            d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            log("said.txt", d["voice"] + ("#" + d["speaker"] if d.get("speaker") else "") + "|" + d["text"])
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                n = int(22050 * 0.01 * len(d["text"])) if (home / "slow").exists() else 441  # slow: 10 ms a character; else 20 ms
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b"\\0\\0" * n)
            body = buf.getvalue()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    HTTPServer(("127.0.0.1", int(a[a.index("--port") + 1])), H).serve_forever()
"""


def _env(where: Path) -> None:
    """The environment of Piper as speech._venv makes it (the stand-in for its Python)."""
    py = where / "env" / "bin" / "python"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text(FAKE, encoding="utf-8")
    py.chmod(0o755)
    (where / "env" / "bin" / "pip").write_text("", encoding="utf-8")


def _piper(tmp: Path, site: Path, installed: bool = True, voices: dict | None = None) -> Path:
    where = tmp / "piper"
    where.mkdir()
    if installed:
        _env(where)
        speech._run([str(where / "env" / "bin" / "python"), "-m", "pip", "install", "piper-tts[http]"])
    settings.save(site, {"speech": {"dir": str(where), **({"voices": voices} if voices else {})}})
    return where


def lines(where: Path, name: str) -> list[str]:
    f = where / name
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


@pytest.fixture(autouse=True)
def _clean():
    yield
    speech._piper.stop()
    speech._job.update(state="idle", step="", message="")


CATALOG = {  # a part of voices.json of Piper
    f"fr_FR-{n}-{q}": {"name": n, "quality": q, "language": {"code": "fr_FR", "family": "fr"},
                       "speaker_id_map": sp, "files": {f"fr/fr_FR/{n}/{q}/fr_FR-{n}-{q}.onnx": {"size_bytes": 63 * 1048576}}}
    for n, q, sp in [("siwis", "low", {}), ("siwis", "medium", {}), ("tom", "medium", {}), ("gilles", "low", {}),
                     ("upmc", "medium", {"jessica": 0, "pierre": 1}), ("mls_1840", "low", {}),
                     ("mls", "medium", {str(1000 + i): i for i in range(12)})]
}
CATALOG["en_US-lessac-high"] = {"name": "lessac", "quality": "high", "language": {"code": "en_US", "family": "en"}}


@pytest.fixture
def voices_json(tmp_path: Path, monkeypatch) -> Path:
    f = tmp_path / "voices.json"
    f.write_text(json.dumps(CATALOG), encoding="utf-8")
    monkeypatch.setattr(speech, "VOICES_JSON", f.as_uri())
    return f


def test_voices_of_a_language(tmp_path: Path, voices_json: Path) -> None:
    site = tmp_path / "site"
    (site / "archive").mkdir(parents=True)
    # the best quality of each voice, a speaker of a few one voice, many speakers one choice; the sex
    got = {c["voice"]: (c["sex"], c["quality"]) for c in speech.choices(site, "fr")}
    assert got == {"fr_FR-gilles-low": ("M", "low"), "fr_FR-mls-medium": ("?", "medium"), "fr_FR-mls_1840-low": ("?", "low"),
                   "fr_FR-siwis-medium": ("F", "medium"), "fr_FR-tom-medium": ("M", "medium"),
                   "fr_FR-upmc-medium#jessica": ("F", "medium"), "fr_FR-upmc-medium#pierre": ("M", "medium")}
    mls = next(c for c in speech.choices(site, "fr") if c["voice"] == "fr_FR-mls-medium")
    assert len(mls["speakers"]) == 12 and mls["sample"].endswith("/fr/fr_FR/mls/medium/speaker_{id}.mp3")
    pierre = next(c for c in speech.choices(site, "fr") if c.get("speaker") == "pierre")
    assert pierre["sample"] == "https://rhasspy.github.io/piper-samples/samples/fr/fr_FR/upmc/medium/speaker_1.mp3"
    assert pierre["size"] == 63 * 1048576 and not pierre["downloaded"]
    # the voices in use listed even when the catalogue does not have them
    assert {c["voice"]: c["quality"] for c in speech.listed(site, "en")} == {"en_US-lessac-high": "high", "en_US-ryan-high": "high"}
    voices_json.unlink()  # kept a week by CEV
    assert len(speech.choices(site, "fr")) == 7
    # the defaults, the choice kept per language and speaker
    assert speech.voices(site, "fr") == {"human": "fr_FR-siwis-medium", "assistant": "fr_FR-upmc-medium#pierre"}
    assert speech.single(site, "zh") and speech.single(site, "ko") and not speech.single(site, "ja")
    assert speech.voices(site, "xx") is None
    speech.choose(site, "fr", "assistant", "fr_FR-mls-medium#1003")
    speech.choose(site, "en", "human", "en_US-lessac-high")
    assert speech.voices(site, "fr") == {"human": "fr_FR-siwis-medium", "assistant": "fr_FR-mls-medium#1003"}
    assert speech.voices(site, "en") == {"human": "en_US-lessac-high", "assistant": "en_US-ryan-high"}
    for bad in ("../x", "fr_FR-x", "fr_FR-a/b-medium"):
        with pytest.raises(speech.SpeechError):
            speech.choose(site, "fr", "human", bad)
    speech.choose(site, "fr", "human", "fr_FR-mls-medium#1003")
    assert speech.single(site, "fr")  # the same voice for both
    for lang, pair in speech.DEFAULTS.items():  # every voice named lang_REGION-name-quality
        assert all(speech.VOICE.match(v) and v.startswith(lang + "_") for v in pair)


def test_speak_with_piper_kept_running(tmp_path: Path) -> None:
    site = tmp_path / "site"
    (site / "archive").mkdir(parents=True)
    where = _piper(tmp_path, site, installed=False)
    st = speech.status(site, "fr")
    assert not st["installed"] and st["voice"] and st["dir"] == str(where) and not st["single"]
    with pytest.raises(speech.SpeechError) as e:
        speech.speak(site, "Bonjour.", "fr", "human")
    assert e.value.key == "server.speak.not_installed"
    assert "piper-tts[http]" in speech.manual_command(where, "fr") and "piper-tts[http,ja]" in speech.manual_command(where, "ja")
    _env(where)
    speech._run([str(where / "env" / "bin" / "python"), "-m", "pip", "install", "x"])
    assert speech.installed(where, "fr") and not speech.installed(where, "ja")  # ja needs pyopenjtalk more
    # the voices downloaded when first needed, one Piper for all, its speakers by name
    wav = speech.speak(site, "  Bonjour   Dom. ", "fr", "human")
    assert wav[:4] == b"RIFF" and lines(where, "said.txt") == ["fr_FR-siwis-medium|Bonjour Dom."]
    speech.speak(site, "Salut.", "fr", "assistant")
    proc = speech._piper.proc
    speech.choose(site, "fr", "assistant", "fr_FR-upmc-medium#jessica")
    speech.speak(site, "Encore.", "fr", "assistant")
    assert speech._piper.proc is proc  # kept running
    assert lines(where, "said.txt")[1:] == ["fr_FR-upmc-medium#pierre|Salut.", "fr_FR-upmc-medium#jessica|Encore."]
    assert lines(where, "downloads.txt") == ["fr_FR-siwis-medium", "fr_FR-upmc-medium"]
    assert (where / "voices" / "fr_FR-upmc-medium.onnx").is_file()
    # kept: the same text again is not asked; cached_only: only what is kept
    n = len(lines(where, "said.txt"))
    assert speech.speak(site, "Bonjour Dom.", "fr", "human") == wav and len(lines(where, "said.txt")) == n
    assert speech.speak(site, "Jamais dit.", "fr", "human", cached_only=True) is None
    # a speaker the voice does not have
    speech.choose(site, "fr", "human", "fr_FR-upmc-medium#paul")
    with pytest.raises(speech.SpeechError) as e:
        speech.speak(site, "Bonjour.", "fr", "human")
    assert e.value.key == "server.speak.no_voice"
    # stopped after some time without use, started again when needed
    speech._piper.stop()
    speech.choose(site, "fr", "human", "fr_FR-tom-medium")
    speech.speak(site, "Après l'arrêt.", "fr", "human")
    assert speech._piper.alive() and lines(where, "said.txt")[-1] == "fr_FR-tom-medium|Après l'arrêt."


def test_speak_in_the_browser(tmp_path: Path, page, monkeypatch, voices_json: Path) -> None:  # noqa: F811
    site = _site(tmp_path)
    where = _piper(tmp_path, site, installed=False)
    monkeypatch.setattr(speech, "_venv", lambda env: _env(where))
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        played = []
        url = f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html"
        pg.goto(url)
        entry = '.message[data-uuid="{}"]'
        speaking = "!document.querySelector('.cev-speak-on, .cev-speak-wait')"
        pg.wait_for_selector("#voices-slot .cev-voices", state="attached")  # (22/11: in the tab Bulles)
        pg.evaluate("CEV.speak.timing.pause = 0.05; CEV.speak.timing.poll = 100")  # the pauses are not what is tested here
        # after the other icons, before the arrow of the bubble; none on a bubble without text (a3)
        assert pg.eval_on_selector(entry.format("a1") + " .cev-speak", "b => b.nextElementSibling.classList.contains('plan-dn')")
        assert pg.locator(entry.format("a3") + " .cev-speak").count() == 0
        assert pg.get_attribute(entry.format("a1") + " .cev-speak", "title") == "Lire à voix haute"
        # Piper missing: installed after a yes, then the bubble is read
        pg.click(entry.format("a1") + " .cev-speak")
        assert str(where) in pg.inner_text(".cev-confirm-text")
        pg.click(".cev-confirm-yes")
        pg.wait_for_function(speaking + " && !document.querySelector('.cev-speak-box')", timeout=30000)
        assert lines(where, "pip.txt") == ["install --upgrade piper-tts[http]>=" + speech.PIPER_MIN]
        said = lines(where, "said.txt")
        texts = [x.split("|", 1)[1] for x in said]
        whole = " ".join(texts)
        # Claude with its voice; every sentence once and in order, the code named
        assert {x.split("|")[0] for x in said} == {"fr_FR-upmc-medium#pierre"}
        assert whole.startswith("Phrase numéro 0 pour allonger la réponse.") and whole.endswith("Bloc de code.")
        assert all(f"Phrase numéro {i} pour" in whole for i in range(60)) and "girafe" not in whole and "Je réfléchis" not in whole
        assert [whole.index(f"numéro {i} ") for i in range(60)] == sorted(whole.index(f"numéro {i} ") for i in range(60))
        sizes = [len(x) for x in texts]
        assert sizes[0] <= 120 and max(sizes[:2]) <= 200 and max(sizes) <= 400 and len(sizes) > 4
        # the box of the voices: the current ones, women / men / others, the speed
        pg.route("https://rhasspy.github.io/**", lambda route: (played.append(route.request.url), route.abort()))
        pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
        pg.click(".cev-voices")
        pg.wait_for_selector(".cev-voice-box")
        assert pg.inner_text(".cev-voice-box .cev-speak-head span") == "Voix — Français"
        pick = '.cev-voice-row[data-role="{}"] select'
        chosen = lambda role: pg.eval_on_selector(pick.format(role), "s => s.selectedOptions[0].textContent")  # noqa: E731
        assert chosen("human") == "siwis · moyenne" and chosen("assistant") == "upmc — pierre · moyenne"
        assert pg.eval_on_selector_all(pick.format("human") + " optgroup", "l => l.map(g => g.label)") == ["♀ Femmes", "♂ Hommes", "Autres voix"]
        assert pg.inner_text('.cev-voice-note[data-role="assistant"]') == "Téléchargée."  # by the installation
        # Moi: tom; Claude: the 4th speaker of mls (listened to)
        pg.select_option(pick.format("human"), label="tom · moyenne")
        assert pg.inner_text('.cev-voice-note[data-role="human"]') == \
            "Pas encore téléchargée (63 Mo) : elle le sera à la première lecture."
        assert not pg.is_visible('.cev-voice-row[data-role="human"] .cev-voice-n')
        pg.select_option(pick.format("assistant"), label="mls (12) · moyenne")
        pg.fill('.cev-voice-row[data-role="assistant"] .cev-voice-n input', "4")
        pg.dispatch_event('.cev-voice-row[data-role="assistant"] .cev-voice-n input', "change")
        pg.click('.cev-voice-row[data-role="assistant"] .cev-voice-play')
        pg.wait_for_selector(".cev-speak-box")  # no connection here: said so
        assert played == ["https://rhasspy.github.io/piper-samples/samples/fr/fr_FR/mls/medium/speaker_3.mp3"]
        pg.click(".cev-speak-box .cev-confirm-yes")
        for _ in range(50):
            if speech.voices(site, "fr") == {"human": "fr_FR-tom-medium", "assistant": "fr_FR-mls-medium#1003"}:
                break
            pg.wait_for_timeout(100)
        assert speech.voices(site, "fr") == {"human": "fr_FR-tom-medium", "assistant": "fr_FR-mls-medium#1003"}
        # 14/11: a speed for each voice, under its choice
        rate = '.cev-voice-rate[data-role="{}"]'
        pg.eval_on_selector(rate.format("human") + " input", "r => { r.value = '1.25'; r.dispatchEvent(new Event('input')); }")
        pg.eval_on_selector(rate.format("assistant") + " input", "r => { r.value = '0.8'; r.dispatchEvent(new Event('input')); }")
        assert pg.inner_text(rate.format("human") + " output") == "×1,25"
        assert pg.inner_text(rate.format("assistant") + " output") == "×0,8"
        assert pg.evaluate("[localStorage.getItem('cev-speak-rate-human'), localStorage.getItem('cev-speak-rate-assistant')]") \
            == ["1.25", "0.8"]
        pg.click(".cev-voice-x")
        pg.wait_for_selector(".cev-voice-box", state="detached")
        # read with the voices chosen, at that speed; a line without a final mark gets one (a pause)
        n = len(lines(where, "said.txt"))
        pg.evaluate("window._rates = []; const P = HTMLMediaElement.prototype.play;"
                    "HTMLMediaElement.prototype.play = function () { window._rates.push(this.playbackRate); return P.call(this); }; 0")
        pg.click(entry.format("q1") + " .cev-speak")
        pg.wait_for_function(speaking, timeout=20000)
        assert lines(where, "said.txt")[n:] == ["fr_FR-tom-medium|Première question. sur plusieurs. lignes. et encore une."]
        assert pg.evaluate("window._rates") == [1.25]
        # Piper started under the mouse: Claude's voice downloaded already, nothing said
        for _ in range(50):
            if "fr_FR-mls-medium" in lines(where, "downloads.txt"):
                break
            pg.wait_for_timeout(100)
        assert "fr_FR-mls-medium" in lines(where, "downloads.txt")
        assert not any("prépare" in x for x in lines(where, "said.txt"))
        # the whole conversation from the button of the page: every bubble shown, in order, each voice
        allb = '#page-nav [data-go="speak"]'
        assert pg.get_attribute(allb, "title").startswith("Lire toute la conversation")
        n = len(lines(where, "said.txt"))
        pg.evaluate("window.scrollTo(0, 0)")
        pg.click(allb)
        assert pg.get_attribute(allb, "aria-pressed") == "true"
        pg.wait_for_function(speaking + " && document.querySelector('#page-nav [data-go=speak]').getAttribute('aria-pressed') === 'false'",
                             timeout=30000)
        got = lines(where, "said.txt")[n:]
        shown = pg.eval_on_selector_all(".message[data-uuid]", "l => l.filter(m => m.checkVisibility() && m.querySelector('.cev-speak'))"
                                        ".map(m => m.getAttribute('data-uuid'))")
        assert shown == ["q1", "a1", "q2b", "a2b", "q3", "q4", "a4"]
        firsts = [x for x in got if x.split("|", 1)[1].startswith(("Première", "Phrase numéro 0", "Version deux", "Réponse à la version deux",
                                                                    "Question interrompue", "Question reprise", "Réponse reprise"))]
        # (q1 was read before with the same voice: kept, not asked again)
        seq = iter(x.split("|", 1)[1][:12] for x in firsts)  # in this order (a2b holds "Phrase numéro 0…" too)
        assert all(any(y == w for y in seq) for w in ["Phrase numér", "Version deux", "Réponse à la",
                                                      "Question int", "Question rep", "Réponse repr"])
        assert {x.split("|")[0] for x in got} == {"fr_FR-tom-medium", "fr_FR-mls-medium#1003"}
        # a second click stops
        pg.click(allb)
        pg.wait_for_selector(".cev-speak-on, .cev-speak-wait")  # from the bubble at the top of the screen
        pg.click(allb)
        assert pg.get_attribute(allb, "aria-pressed") == "false" and pg.locator(".cev-speak-on, .cev-speak-wait").count() == 0
        # a second click stops
        pg.click(entry.format("a2b") + " .cev-speak")
        pg.wait_for_selector(entry.format("a2b") + " .cev-speak-on")
        pg.click(entry.format("a2b") + " .cev-speak")
        assert pg.locator(".cev-speak-on, .cev-speak-wait").count() == 0
        assert pg.get_attribute(entry.format("a2b") + " .cev-speak", "title") == "Lire à voix haute"
        # a language with one voice: "Question." / "Réponse." said first (in that language)
        pg.evaluate("localStorage.setItem('cev-lang', 'zh')")
        pg.goto(url)
        pg.wait_for_selector(entry.format("q4") + " .cev-speak")
        n = len(lines(where, "said.txt"))
        pg.click(entry.format("q4") + " .cev-speak")
        pg.wait_for_function(speaking, timeout=20000)
        assert lines(where, "said.txt")[n:] == ["zh_CN-huayan-medium|问题。 Question reprise."]
        # what is read: every text block of a bubble, not the files between them; the sources said once
        words = pg.evaluate("""() => {
          const m = document.createElement('div'); m.className = 'message message-assistant';
          m.innerHTML = '<div class="message-bubble"><div class="content-text"><p>Je vous écris un script.</p></div>' +
            '<div class="file-card">claude_export_md.py Aucun fichier associé</div>' +
            '<div class="content-text"><p>Voici le script, voir https://example.org/x</p><p>Sources :</p>' +
            '<ul><li><a href="u">Page un</a></li><li><a href="v">Page deux</a> — 2025</li></ul>' +
            '<ul><li><a href="w">Autre</a></li></ul><ul><li>Point <a href="z">avec lien</a> et du texte autour</li></ul></div></div>';
          return CEV.speak.words(m); }""")
        assert words == ("Je vous écris un script.\nVoici le script, voir 链接.\n来源请查看链接。\n"
                         "Point avec lien et du texte autour.")
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


def test_scrolling_follows_the_reading(tmp_path: Path, page) -> None:  # noqa: F811
    """Reading aloud with the slow scrolling on: the scrolling follows the line read; scrolled by hand, it
    stops and the reading goes on; on again, it follows again. The slow scrolling alone: as before."""
    site = _site(tmp_path)
    where = _piper(tmp_path, site)
    (where / "slow").write_text("", encoding="utf-8")
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html")
        pg.evaluate("localStorage.setItem('cev-scroll-speed', '4'); localStorage.removeItem('cev-scroll-level')")
        pg.reload()
        a1 = '.message[data-uuid="a1"]'
        scroll = '#page-nav [data-go="scroll"]'
        pg.wait_for_selector(a1 + " .cev-speak")
        # the speeds: two slower ones first, the one chosen before kept
        pg.click(scroll)
        assert pg.inner_text("#nav-speed") == "Vitesse 7 / 9"
        pg.click(scroll)
        # the pieces: where each one starts in the text read
        assert pg.evaluate("""() => { const t = CEV.speak.words(document.querySelector('.message[data-uuid="a1"]'));
          return CEV.speak.split(t).every(p => t.slice(p.start, p.start + p.text.length) === p.text); }""")
        pg.evaluate("window._a = null; const P = HTMLMediaElement.prototype.play;"
                    "HTMLMediaElement.prototype.play = function () { window._a = this; return P.call(this); }; 0")
        pg.evaluate("scrollTo(0, 0)")
        pg.click(a1 + " .cev-speak")
        pg.wait_for_selector(a1 + " .cev-speak-on")
        pg.wait_for_function("window._a && window._a.duration > 0")
        pg.click(scroll)  # both on: the scrolling follows the reading
        line = "() => CEV.speak.target() + innerHeight / 3"
        top = pg.evaluate("document.querySelector('.message[data-uuid=\"a1\"] p').getBoundingClientRect().top + scrollY")

        def at(f: float) -> float:
            pg.evaluate(f"window._a.pause(); window._a.currentTime = window._a.duration * {f}")
            pg.wait_for_function("Math.abs(scrollY - CEV.speak.target()) < 25")  # reached (AF-f6: no fixed wait)
            return pg.evaluate(line)

        y1, y2 = at(0.2), at(0.9)
        assert top <= y1 < y2  # in the paragraph read, further on as the reading goes
        # scrolled by hand: the scrolling stops, the reading goes on
        pg.mouse.move(300, 300)
        pg.mouse.wheel(0, 400)
        pg.wait_for_function("sel => document.querySelector(sel).getAttribute('aria-pressed') === 'false'", arg=scroll)
        assert pg.locator(a1 + " .cev-speak-on").count() == 1
        moved = pg.evaluate("scrollY")
        pg.wait_for_timeout(500)
        assert pg.evaluate("scrollY") == moved
        # on again: it follows the reading again
        pg.click(scroll)
        pg.wait_for_function("Math.abs(scrollY - CEV.speak.target()) < 25")
        pg.click(a1 + " .cev-speak")  # the reading stopped: the slow scrolling goes on at its speed
        assert pg.get_attribute(scroll, "aria-pressed") == "true" and pg.evaluate("CEV.speak.target()") is None
        y = pg.evaluate("scrollY")
        pg.wait_for_timeout(1000)
        assert 40 < pg.evaluate("scrollY") - y < 100  # 70 px/s
        assert pg.errors == []
    finally:
        server.shutdown()
        server.server_close()


def test_speak_needs_the_token(tmp_path: Path) -> None:
    site = tmp_path / "site"
    (site / "archive").mkdir(parents=True)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for path in ("speak", "speak/status", "speak/install", "speak/warm", "speak/voices", "speak/choose"):
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/__cev__/{path}",
                                         data=json.dumps({"text": "x", "lang": "fr", "role": "human"}).encode(),
                                         headers={"Content-Type": "application/json"})
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req, timeout=5)
            assert e.value.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_sounds_kept_out_of_the_site(tmp_path: Path) -> None:
    """08/11: the sounds go to the cache folder of the user, their largest size is chosen (50 MB at least),
    the cleaning removes them; the sounds kept in the site by the earlier versions are removed."""
    site = tmp_path / "site"
    (site / "archive" / "speech").mkdir(parents=True)
    (site / "archive" / "speech" / "old.wav").write_bytes(b"RIFF")
    where = _piper(tmp_path, site)
    speech.speak(site, "Bonjour.", "fr", "human")
    st = speech.cache_state(site)
    assert st["count"] == 1 and st["max_mb"] == 100 and Path(st["folder"]).expanduser() == speech.cache_dir()
    assert [p.name for p in site.rglob("*.wav")] == ["old.wav"]  # the new sound is out of the site
    speech.drop_old_cache(site)
    assert not (site / "archive" / "speech").exists()
    with pytest.raises(speech.SpeechError):
        speech.set_cache_mb(site, 49)
    assert speech.set_cache_mb(site, 60)["max_mb"] == 60 and speech.cache_mb(site) == 60
    res = speech.clear_cache(site)
    assert res["removed"] == 1 and res["count"] == 0
    n = len(lines(where, "said.txt"))
    speech.speak(site, "Bonjour.", "fr", "human")  # made again
    assert len(lines(where, "said.txt")) == n + 1
    speech._piper.stop()


def test_languages_and_voices_installed(tmp_path: Path, voices_json: Path) -> None:
    """08/11: what a reading in another language needs (check), the languages left unread (skip), the voices on the
    disk with those in two folders and those in use, a voice removed from one folder."""
    site = tmp_path / "site"
    (site / "archive").mkdir(parents=True)
    where = _piper(tmp_path, site)
    c = speech.check(site, ["en", "xx", "fr"])
    assert set(c) == {"en", "fr"} and c["en"]["readable"] and not c["en"]["skip"]
    assert [m["name"] for m in c["en"]["missing"]] == ["en_US-lessac-high", "en_US-ryan-high"]
    assert c["en"]["missing"][0]["size"] == 0 and c["fr"]["missing"][0] == {"name": "fr_FR-siwis-medium", "size": 63 * 1048576}
    speech.set_skip(site, "en", True)
    assert speech.check(site, ["en"])["en"]["skip"] and speech.skipped(site) == {"en"}
    speech.set_skip(site, "en", False)
    assert speech.skipped(site) == set()
    with pytest.raises(speech.SpeechError):
        speech.set_skip(site, "xx", True)
    # siwis twice (in voices/ and at the top, as an installation made by hand), tom not in use
    speech.download(site, "fr_FR-siwis-medium")
    speech.download(site, "fr_FR-tom-medium")
    (where / "fr_FR-siwis-medium.onnx").write_bytes(b"yy")
    got = {(v["name"], v["dir"]): (v["duplicate"], v["used"], v["size"] > 0) for v in speech.installed_voices(site)}
    assert got == {("fr_FR-siwis-medium", 0): (True, True, True), ("fr_FR-tom-medium", 0): (False, False, True),
                   ("fr_FR-siwis-medium", 1): (True, True, True)}
    left = speech.remove_voice(site, "fr_FR-siwis-medium", 1)
    assert not (where / "fr_FR-siwis-medium.onnx").exists() and (where / "voices" / "fr_FR-siwis-medium.onnx").exists()
    assert [(v["name"], v["duplicate"]) for v in left] == [("fr_FR-siwis-medium", False), ("fr_FR-tom-medium", False)]
    for bad in (("../x", 0), ("fr_FR-tom-medium", 5), ("fr_FR-tom-medium#a", 0), ("fr_FR-tom-medium", True)):
        with pytest.raises(speech.SpeechError):
            speech.remove_voice(site, *bad)


def test_passage_in_another_language(tmp_path: Path, page, voices_json: Path) -> None:  # noqa: F811
    """08/11: a paragraph in English in a French reading: announced once in the voice of CEV, read with the voice
    of English after a yes to download it; French again after it; left unread when chosen so."""
    from .test_plan import ROOT, _m, _t
    import zipfile

    from claude_export_viewer.cli import main
    text = ("✅ Voici une réponse qui est en français pour la lecture. 🎯\n\n"
            "Soit X une variable de paramètres a, b, c et e, avec o = 2.\n\n"
            "This is a paragraph that is written in English for the test of the reading.\n\n"
            "And this second paragraph is also in English with the words of the language.\n\n"
            "Et nous revenons au français pour la fin de la réponse.")
    z = tmp_path / "l.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([{"uuid": "c1", "name": "Langues", "created_at": "2026-10-31T09:12:00Z",
                   "chat_messages": [_m("q1", ROOT, "human", "09:12", _t("Question")), _m("a1", "q1", "assistant", "09:13", _t(text))]}]))
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-11-01"])
    where = _piper(tmp_path, site)
    server = make_server(site, 0, launcher=PROGRAM / "claude-export-viewer.py")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pg = page
        pg.goto(f"http://127.0.0.1:{server.server_address[1]}/conversations/c1.html")
        pg.wait_for_selector('.message[data-uuid="a1"] .cev-speak')
        speaking = "!document.querySelector('.cev-speak-on, .cev-speak-wait')"
        pg.click('.message[data-uuid="a1"] .cev-speak')
        pg.wait_for_selector(".cev-confirm-text")
        assert "en anglais" in pg.inner_text(".cev-confirm-text")
        pg.click(".cev-confirm-yes")
        pg.wait_for_function(speaking, timeout=30000)
        said = lines(where, "said.txt")
        assert said == [
            # no icon said; the line of variables stays French (not Portuguese)
            "fr_FR-upmc-medium#pierre|Voici une réponse qui est en français pour la lecture. "
            "Soit X une variable de paramètres a, b, c et e, avec o = 2.",
            "fr_FR-upmc-medium#pierre|Passage en anglais :",
            "en_US-ryan-high|This is a paragraph that is written in English for the test of the reading.",
            "en_US-ryan-high|And this second paragraph is also in English with the words of the language.",
            "fr_FR-upmc-medium#pierre|Et nous revenons au français pour la fin de la réponse."], said
        # English left unread (box "Voix"): announced, not read
        pg.evaluate("document.getElementById('bubbles-tab').open = true")  # (22/11: in the tab Bulles)
        pg.click(".cev-voices")
        pg.wait_for_selector(".cev-voice-box")
        pg.select_option(".cev-voice-langs", "en")
        pg.wait_for_selector(".cev-voice-skip:not([hidden]) input")
        pg.check(".cev-voice-skip input")
        for _ in range(50):
            if speech.skipped(site) == {"en"}:
                break
            pg.wait_for_timeout(100)
        assert "Voix installées : " in pg.inner_text(".cev-voice-installed summary")
        pg.click(".cev-voice-x")
        (where / "said.txt").unlink()
        pg.click('.message[data-uuid="a1"] .cev-speak')
        pg.wait_for_timeout(300)
        pg.wait_for_function(speaking, timeout=30000)
        # the French already made comes from the cache: only the new sentence is asked
        assert [x.split("|", 1)[1] for x in lines(where, "said.txt")] == ["Passage en anglais, non lu."]
        assert pg.errors == []
    finally:
        speech._piper.stop()
        server.shutdown()


def test_formulas_said(tmp_path: Path, page) -> None:  # noqa: F811
    """AE-f1 (15/11): a short formula in a sentence is read in words (rendered by KaTeX or not yet: its TeX; Greek
    letters by their names, = + − in words, f(x) "f de x"), a longer one named in one of ten ways (at random, never
    twice in a row); a formula on its own line announced by one of ten short sentences."""
    from .test_plan import ROOT, _m, _t
    import zipfile

    from claude_export_viewer.cli import main
    z = tmp_path / "m.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps([{"uuid": "c1", "name": "Maths", "created_at": "2026-10-31T09:12:00Z",
                   "chat_messages": [_m("q1", ROOT, "human", "09:12", _t("Question")),
                                     _m("a1", "q1", "assistant", "09:13", _t("Soit \\(\\alpha\\) un paramètre."))]}]))
    site = tmp_path / "site"
    main([str(z), "-o", str(site), "--date-export", "2026-11-01"])
    pg = page
    pg.goto((site / "conversations" / "c1.html").as_uri())
    pg.wait_for_function("window.katex && window.CEV && CEV.speak")
    words = pg.evaluate("""() => {
      Math.random = () => 0;  // the first way of naming a formula that was not just said
      const m = document.createElement('div'); m.className = 'message message-assistant';
      m.innerHTML = '<div class="message-bubble"><div class="content-text"><p>Soit <span class="math math-inline">\\\\beta</span>' +
        ' et <span class="math math-inline">x^2 - 1</span>, avec <span class="math math-inline" id="r"></span>' +
        ' puis <span class="math math-inline">\\\\frac{a}{b}</span> et <span class="math math-inline">\\\\sqrt{2}</span>.</p>' +
        '<p>Le terme <span class="math math-inline">g(0;\\\\alpha,\\\\beta)</span> s\\'annule.</p>' +
        '<p>Pour <span class="math math-inline">0 \\\\le x</span> et a ≥ b.</p>' +
        '<div class="math math-display">E = mc^2</div></div></div>';
      katex.render('n = 3', m.querySelector('#r'));
      return CEV.speak.words(m); }""")
    assert words == ("Soit bêta et x 2 moins 1, avec n égale 3, puis formule et expression.\n"  # a short pause after
                     "Le terme g de 0, alpha, bêta, s'annule.\n"
                     "Pour 0 inférieur ou égal à x, et a supérieur ou égal à b.\nFormule.")
    assert pg.errors == []
