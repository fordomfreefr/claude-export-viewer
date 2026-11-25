/* Reading a bubble aloud (served only), with Piper through the local server (speech.py):
 *   - a loudspeaker after the other icons of each message: a click reads its text, a second click stops;
 *     under the mouse, Piper is started (POST /__cev__/speak/warm) so that the reading starts sooner;
 *   - Piper not installed: CEV offers to install it (/speak/install), then reads;
 *   - only the text: a code block, a table, a formula are named ("Bloc de code."); the text goes in pieces of
 *     whole sentences growing in length (PIECES), the next one asked while the current one is heard; a list of
 *     links (the sources) is not read: "Sources à consulter en lien." once;
 *   - the round button "Lire" of the page (nav, under ← | →): every bubble shown, from the first one on the
 *     screen, each brought into view; a second click stops;
 *   - the chip "Voix" of the bar opens a box: the voice of "Moi" and of Claude among those of the language
 *     (/speak/voices, kept by the server: /speak/choose), each with "Écouter" (the sample of the site of Piper),
 *     and the speed of each voice (14/11; localStorage cev-speak-rate-human / -assistant, else the former common
 *     cev-speak-rate: the browser plays faster or slower, keeping the pitch);
 *     the same voice for both: "Question." / "Réponse." said first.
 * The language (08/11): each paragraph (line of the text read) gets the language detected by its frequent words
 * (or its script) among the languages of CEV, else the one of the line before; a passage in another language
 * than CEV's is announced once ("Passage en anglais :", in the voice of CEV) and read with the voice of that
 * language (chosen in "Voix", where a language can also be left unread: "Passage en anglais, non lu."); a voice
 * not downloaded yet is asked first (Non: not read this time); back to the language of CEV: a pause of 1 s. */
(function () {
  "use strict";
  var A = window.CEV && CEV.annot;
  var root = document.querySelector(".messages");
  if (!A || !root) { return; }
  var ENTRY = ".message-human[data-uuid], .message-assistant[data-uuid]";
  var ICON = CEV.icon("speaker", 14);
  var BLOCKS = "p, li, h1, h2, h3, h4, h5, h6, blockquote, div, tr, dt, dd";
  var PIECES = [120, 200, 300, 400];  // the longest piece, by rank (then the last one)
  var RATES = [0.75, 1.5];
  var reading = null;  // {msg, audio, stopped}
  var info = null;  // speech.status(): installed, voices, single, dir, job
  var warmed = false;  // Piper started (once, and again for other voices)

  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* no storage */ } }
  function rate(role) {  // the speed of the voice of "Moi" (human) or Claude (assistant)
    var r = parseFloat(get("cev-speak-rate-" + role) || get("cev-speak-rate"));
    return r >= RATES[0] && r <= RATES[1] ? r : 1;
  }
  function label(key) { return " " + CEV.t(key) + " "; }

  // --- The language of a paragraph -------------------------------------------------------------------------------
  // Frequent words (and letters) of the languages of CEV written with the Latin alphabet; the others by their script.
  var STOP = {
    en: "the and of to is in that it for you with as this are be on not or have can will an if was by but from at which would what there they we your",
    fr: "le la les et des est un une du que qui dans pour pas sur au il elle ce cette avec sont ne se mais ou plus nous vous je aux été être comme sa son ses leur très",
    de: "der die das und ist nicht ein eine zu mit den von sich auf für es dem im auch als wie dass sie wir ich oder aber wird sind kann",
    es: "el la los las es en que de un una por con para no se del al lo como más pero su sus está son muy también este esta",
    it: "il la le gli di che un una per non con del della sono si lo ma come più anche questo questa nel nella dell degli alla dei delle ha suo sua",
    nl: "de het een en van in is dat niet op te met voor zijn er die aan ook als bij maar wordt of uit dit naar je we kan om deze worden",
    pt: "os as de que um uma para com não do da dos das em no na por se mais como mas são está também isso você",
    pl: "na się nie jest to że do jak ale co po od za przez dla są już tak czy jego może tylko oraz które który być"
  };
  var LETTERS = { fr: /[éèêàçœù]/g, de: /[äöüß]/g, es: /[ñ¿¡áíóú]/g, pt: /[ãõâêôç]/g, pl: /[ąęłńśźżó]/g, it: /[àèìòù]/g };
  var STOPSETS = {}, SHARED = {};  // a word of several languages counts less (1 / how many have it)
  Object.keys(STOP).forEach(function (l) {
    STOPSETS[l] = new Set(STOP[l].split(" "));
    STOPSETS[l].forEach(function (w) { SHARED[w] = (SHARED[w] || 0) + 1; });
  });
  function detect(line) {
    if (/[\u3040-\u30ff]/.test(line)) { return "ja"; }
    if (/[\uac00-\ud7af]/.test(line)) { return "ko"; }
    if ((line.match(/[\u4e00-\u9fff]/g) || []).length >= 4) { return "zh"; }
    if ((line.match(/[\u0400-\u04ff]/g) || []).length >= 8) { return "ru"; }
    // the words of 2 letters or more, without the labels CEV puts for formulas, code… (08/11: the variables of
    // the formulas — a, e, o, i — made Portuguese or Italian of French lines)
    labelTexts().forEach(function (l) { line = line.split(l).join(" "); });
    var words = (line.toLowerCase().match(/[\p{L}]+/gu) || []).filter(function (w) { return w.length > 1; });
    if (words.length < 5) { return null; }  // too short to tell
    var score = {}, low = line.toLowerCase();
    Object.keys(STOPSETS).forEach(function (l) {
      var n = 0;
      words.forEach(function (w) { if (STOPSETS[l].has(w)) { n += 1 / SHARED[w]; } });
      score[l] = n + (LETTERS[l] ? Math.min(3, (low.match(LETTERS[l]) || []).length) * 0.5 : 0);
    });
    var order = Object.keys(score).sort(function (a, b) { return score[b] - score[a]; });
    var best = score[order[0]], second = score[order[1]], base = CEV.lang();
    if (!(best >= 2 && best >= 2 * second)) { return null; }
    // another language than CEV's only when clear: its words are frequent and those of CEV's language rare
    if (order[0] !== base && STOPSETS[base]) {
      var hits = words.filter(function (w) { return STOPSETS[order[0]].has(w); }).length;
      if (hits < 3 || hits < 0.2 * words.length || (score[base] || 0) * 3 > best) { return null; }
    }
    return order[0];
  }
  var LABELS = [];  // filled when CEV.t is ready (labelTexts)
  function langName(code) {
    try { return new Intl.DisplayNames([CEV.lang()], { type: "language" }).of(code); } catch (e) { return code; }
  }
  // The lines that CEV adds ("Bloc de code.", "Sources à consulter en lien."): said in the language of CEV
  function isLabel(line) {
    var l = line.replace(/[.\s]+$/, "").trim();
    return labelTexts().indexOf(l) >= 0;
  }
  // The texts CEV adds (without the final point), the longest first (taken out of a line before its language is told)
  var LABEL_TEXTS = null;
  function labelTexts() {
    if (!LABEL_TEXTS) {
      LABEL_TEXTS = ["web.speak.code", "web.speak.table", "web.speak.sources"].map(function (k) { return CEV.t(k); })
        .concat(variants("web.speak.formula_line"), variants("web.speak.formula_inline"))
        .map(function (x) { return x.replace(/[.\s]+$/, "").trim(); }).filter(Boolean)
        .sort(function (a, b) { return b.length - a.length; });
      LABELS.push.apply(LABELS, LABEL_TEXTS);
    }
    return LABEL_TEXTS;
  }
  // AE-f1 (15/11): the ways of naming a formula ("a|b|c" in the catalogue), one taken at random, the first one more
  // often (3 to 1), never the same twice in a row
  function variants(key) { return CEV.t(key).split("|").map(function (x) { return x.trim(); }).filter(Boolean); }
  var lastPick = {};
  function pick(key) {
    var list = variants(key), bag = [];
    list.forEach(function (x, i) { if (x !== lastPick[key] || list.length === 1) { bag.push(x); if (i === 0) { bag.push(x, x); } } });
    var x = bag[Math.floor(Math.random() * bag.length)];
    lastPick[key] = x;
    return x;
  }
  // The text in runs of one language: [{lang, label, start, end}]
  function segments(text, base) {
    var out = [], pos = 0, prev = base;
    text.split("\n").forEach(function (line) {
      var label = isLabel(line), lang = label ? base : (detect(line) || prev);
      if (!label) { prev = lang; }
      var last = out[out.length - 1];
      if (last && last.lang === lang && last.label === label) { last.end = pos + line.length; }
      else { out.push({ lang: lang, label: label, start: pos, end: pos + line.length }); }
      pos += line.length + 1;
    });
    return out;
  }

  // The words of a bubble: its text blocks (.content-text, between them the resources and the files are
  // not read), without what cannot be read; a list of links (the sources) said once
  function texts(msg) { return msg.querySelectorAll(":scope > .message-bubble > .content-text"); }
  function linkish(e) {
    var all = e.textContent.replace(/\s+/g, "").length, links = 0;
    e.querySelectorAll("a").forEach(function (a) { links += a.textContent.replace(/\s+/g, "").length; });
    return all > 0 && links / all >= 0.6;
  }
  // parse(): the text read and where each part of it comes from in the page ({pos, el}, for the scrolling that
  // follows the reading): a mark \u0001k\u0002 before each block of the copy, taken out at the end
  var TAG = BLOCKS + ", .code-block, pre, table, .math-display, .katex-display, ul, ol";
  var MARK = /\u0001(b|\d+)\u0002/g;
  function bare(l) { return l.replace(MARK, ""); }
  // A short formula as words, else null: letters, numbers, Greek letters (by their names), = + − < > (in words),
  // f(x) ("f de x"), commas, semicolons, an exponent or an index of one character (x^2 → "x 2"); at most 6 of them
  var GREEK_KEYS = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau " +
                    "upsilon phi chi psi omega").split(" ");
  var MATH_TOKEN = /\s+|\\([A-Za-z]+)|[\^_](?:\{([A-Za-z0-9])\}|([A-Za-z0-9]))|(\d+(?:[.,]\d+)?)|([A-Za-z])|([=+\-<>≤≥≠≈])|([(),;])/y;
  var MATH_CMD = { le: "≤", leq: "≤", leqslant: "≤", ge: "≥", geq: "≥", geqslant: "≥", ne: "≠", neq: "≠", approx: "≈",
                   simeq: "≈", lt: "<", gt: ">" };
  function mathOps() {
    var words = CEV.t("web.speak.math_words").split("|");
    return { "=": words[0], "+": words[1], "-": words[2], "<": words[3], ">": words[4], "≤": words[6], "≥": words[7],
             "≠": words[8], "≈": words[9], of: words[5] };
  }
  function mathSaid(tex) {
    var names = CEV.t("web.speak.greek").split("|"), ops = mathOps();
    var s = String(tex || "").replace(/\\[,;:! ]|~/g, " ").replace(/\\(left|right)\b/g, "").trim(), out = [], n = 0, i = 0, m, prev = "";
    if (!s) { return null; }
    while (i < s.length) {
      MATH_TOKEN.lastIndex = i;
      m = MATH_TOKEN.exec(s);
      if (!m) { return null; }
      i = MATH_TOKEN.lastIndex;
      var w = null, kind = "";
      if (m[1] !== undefined && MATH_CMD[m[1]]) { w = ops[MATH_CMD[m[1]]] || MATH_CMD[m[1]]; kind = "op"; }  // \le, \neq…
      else if (m[1] !== undefined) {  // a Greek letter (\alpha, \Gamma, \varepsilon…), else too long to say
        var g = GREEK_KEYS.indexOf(m[1].toLowerCase().replace(/^var/, ""));
        if (g < 0 || !names[g]) { return null; }
        w = names[g]; kind = "name";
      } else if (m[2] || m[3]) { w = m[2] || m[3]; kind = "name"; }
      else if (m[4]) { w = m[4]; kind = "num"; }
      else if (m[5]) { w = m[5]; kind = "name"; }
      else if (m[6]) { w = ops[m[6]] || m[6]; kind = "op"; }
      else if (m[7]) {
        if (m[7] === "(") { if (prev === "name" && ops.of) { out.push(ops.of); } prev = "("; continue; }  // f(x): "f de x"
        if (m[7] === ")") { continue; }
        if (out.length) { out[out.length - 1] += ","; }  // , and ;: a short pause
        prev = ","; continue;
      } else { continue; }  // spaces
      out.push(w);
      n += 1;
      prev = kind;
    }
    if (!n || n > 6) { return null; }
    return out.join(" ").replace(/,$/, "") + (n > 1 ? "," : "");  // a short pause after a formula of several items
  }
  function texOf(e) {
    var a = e.querySelector('annotation[encoding="application/x-tex"]');
    return a ? a.textContent : e.classList.contains("katex") ? "" : e.textContent;
  }
  function parse(msg) {
    var said = false, text = "", marks = [];
    Array.prototype.forEach.call(texts(msg), function (block) {
      var c = block.cloneNode(true), orig = block.querySelectorAll(TAG);
      c.querySelectorAll(TAG).forEach(function (e, k) { e.before("\u0001" + k + "\u0002"); });
      c.prepend("\u0001b\u0002");
      c.querySelectorAll(".code-block, pre").forEach(function (e) { e.replaceWith("\n" + label("web.speak.code") + "\n"); });
      c.querySelectorAll("table").forEach(function (e) { e.replaceWith("\n" + label("web.speak.table") + "\n"); });
      // AE-f1 (15/11): a formula on its own line named; one in a sentence read when short (α, x, n = 3, x²…),
      // named when longer; rendered (KaTeX) or not yet (lazy: its TeX source), the TeX decides
      c.querySelectorAll(".math-display, .katex-display").forEach(function (e) {
        if (e.parentNode) { e.replaceWith("\n" + pick("web.speak.formula_line") + "\n"); }
      });
      c.querySelectorAll(".math-inline, .katex").forEach(function (e) {
        if (!e.parentNode) { return; }
        var said = mathSaid(texOf(e));
        e.replaceWith(" " + (said || pick("web.speak.formula_inline")) + " ");
      });
      c.querySelectorAll("img, svg, button, script, style, .cut-note").forEach(function (e) { e.remove(); });
      // the sources: a list whose items are links (and its short title "Sources :" before it)
      c.querySelectorAll("ul, ol").forEach(function (l) {
        if (!l.parentNode || !Array.prototype.every.call(l.children, linkish)) { return; }
        var before = l.previousElementSibling;
        if (before && bare(before.textContent).trim().length < 40 && /[:：]\s*$/.test(bare(before.textContent))) { before.remove(); }
        l.replaceWith(said ? "" : "\n" + CEV.t("web.speak.sources") + "\n");
        said = true;
      });
      c.querySelectorAll("a").forEach(function (a) {  // an address written out: "lien"
        if (/^\s*(https?:\/\/|www\.)\S+\s*$/.test(bare(a.textContent))) { a.replaceWith(label("web.speak.link")); }
      });
      c.querySelectorAll("br").forEach(function (e) { e.replaceWith("\n"); });
      c.querySelectorAll(BLOCKS).forEach(function (e) { e.append("\n"); });
      var lines = c.textContent.replace(/https?:\/\/[^\s\u0001]+/g, CEV.t("web.speak.link")).split("\n")
        .map(function (l) {  // ≤ ≥ ≠ ≈ in words; no space before a comma, no comma before another mark or at the end
          var ops = mathOps();
          return l.replace(/\s*([≤≥≠≈])\s*/g, function (x, op) { return " " + (ops[op] || op) + " "; }).replace(/\s+/g, " ")
            .replace(/ ([,.;])/g, "$1").replace(/,+(\s*[,.;:!?…])/g, "$1").trim().replace(/,$/, "");
        })
        .filter(function (l) { return bare(l).trim(); })
        .map(function (l) { return /[.!?…:;。！？]["»”')\]]*$/.test(bare(l)) ? l : l + "."; })  // a pause at each line
        .join("\n");
      if (!bare(lines)) { return; }
      if (text) { text += "\n"; }
      var at = 0;
      lines.replace(MARK, function (m, k, i) {
        text += lines.slice(at, i);
        at = i + m.length;
        var el = k === "b" ? block : orig[+k];
        if (el) { marks.push({ pos: text.length, el: el }); }
        return "";
      });
      text += lines.slice(at);
    });
    return { text: text, marks: marks };
  }
  function words(msg) { return parse(msg).text; }

  // Pieces of whole sentences, longer and longer (the first one comes soon, the next ones in time), with
  // where each one starts in the text
  function split(text) {
    var re = /\s*[^.!?…。！？\n]+(?:[.!?…。！？]+["»”')\]]*|\n|$)/g, out = [], from = 0, to = 0, m;
    function add(a, b) {
      var raw = text.slice(a, b), lead = raw.length - raw.replace(/^\s+/, "").length;
      if (raw.trim()) { out.push({ text: raw.trim(), start: a + lead }); }
    }
    while ((m = re.exec(text)) !== null) {
      if (!m[0]) { re.lastIndex += 1; continue; }
      var end = m.index + m[0].length, cur = text.slice(from, to), next = text.slice(to, end);
      var max = PIECES[Math.min(out.length, PIECES.length - 1)];
      if (cur.trim() && (cur + next).length > max && /[.!?…。！？\n]["»”')\]]*\s*$/.test(cur) &&
          (/^\s/.test(next) || /[。！？]\s*$/.test(cur))) {
        add(from, to);
        from = to;
      }
      to = end;
    }
    add(from, text.length);
    return out;
  }
  function pieces(text) { return split(text).map(function (p) { return p.text; }); }

  // Where the scrolling should be (nav.js, while it runs): the line read a third down the screen
  function target() {
    var r = reading;
    if (!r || !r.item || !r.audio || !r.audio.duration) { return null; }
    var it = r.item, f = Math.min(1, r.audio.currentTime / r.audio.duration), c = it.start + f * it.text.length;
    var m = it.marks, k = -1;
    for (var j = 0; j < m.length && m[j].pos <= c; j++) { k = j; }
    var el = k >= 0 ? m[k].el : it.msg, rect = el.getBoundingClientRect();
    if (!rect.height) { el = it.msg; rect = el.getBoundingClientRect(); k = -1; }
    var from = k >= 0 ? m[k].pos : 0, to = it.total;
    for (var n = k + 1; n < m.length; n++) { if (m[n].pos > from) { to = m[n].pos; break; } }
    var g = to > from ? Math.min(1, (c - from) / (to - from)) : 0;
    return window.scrollY + rect.top + g * rect.height - window.innerHeight / 3;
  }

  function role(msg) { return msg.classList.contains("message-human") ? "human" : "assistant"; }

  function ask(path, body) {
    if (!body.lang) { body.lang = CEV.lang(); }
    return A.call(path, body).then(function (r) {
      if (!r.ok) { return r.text().then(function (t) { var e = new Error(t); e.server = true; throw e; }); }
      return r;
    });
  }
  function sound(text, msg, cachedOnly, lang) {
    return ask("/__cev__/speak", { text: text, role: msg ? role(msg) : "assistant", cached_only: Boolean(cachedOnly), lang: lang })
      .then(function (r) { return r.status === 204 ? null : r.blob(); });
  }
  function status() {
    return ask("/__cev__/speak/status", {}).then(function (r) { return r.json(); }).then(function (s) { info = s; return s; });
  }

  function state(msg, cls) {
    var b = msg.querySelector(".cev-speak");
    b.classList.remove("cev-speak-wait", "cev-speak-on");
    if (cls) { b.classList.add(cls); }
    var key = cls ? "web.speak.stop" : "web.speak.title";
    b.setAttribute("data-i18n-attr", "title:" + key);
    b.title = CEV.t(key);
  }

  function stop() {
    if (!reading) { return; }
    var r = reading;
    reading = null;
    r.stopped = true;
    if (r.audio) { r.audio.pause(); URL.revokeObjectURL(r.audio.src); }
    state(r.msg, null);
    pressed(false);
  }

  function play(r, blob) {
    return new Promise(function (done, fail) {
      if (r.audio) { URL.revokeObjectURL(r.audio.src); }
      r.audio = new Audio(URL.createObjectURL(blob));
      r.audio.playbackRate = rate(role(r.msg));
      r.audio.onended = done;
      r.audio.onerror = function () { fail(new Error("audio")); };
      r.audio.play().catch(fail);
    });
  }

  // Before reading: the paragraphs of each bubble with their language; the other languages checked with the
  // server (a voice? Piper able? left unread in "Voix"?), a voice not downloaded yet asked (Non: not read this
  // time); then go(parsed, skip)
  function prepare(msgs, go) {
    var base = CEV.lang(), langs = [];
    var parsed = msgs.map(function (msg) {
      var p = parse(msg), segs = segments(p.text, base);
      segs.forEach(function (sg) { if (sg.lang !== base && langs.indexOf(sg.lang) < 0) { langs.push(sg.lang); } });
      return { msg: msg, p: p, segs: segs };
    });
    if (!langs.length) { go(parsed, {}); return; }
    ask("/__cev__/speak/check", { langs: langs }).then(function (r) { return r.json(); }).then(function (c) {
      var skip = {}, queue = [];
      langs.forEach(function (l) {
        var st = c[l];
        if (!st || !st.readable || st.skip) { skip[l] = true; } else if (st.missing.length) { queue.push(l); }
      });
      (function next() {
        var l = queue.shift();
        if (!l) { go(parsed, skip); return; }
        var size = c[l].missing.reduce(function (n, v) { return n + (v.size || 0); }, 0);
        CEV.confirm(CEV.t("web.speak.download_ask", { lang: langName(l), size: size ? mb(size) : "?" }), next,
          function () { skip[l] = true; next(); });
      })();
    }, function () { var skip = {}; langs.forEach(function (l) { skip[l] = true; }); go(parsed, skip); });
  }

  // The list read: pieces of whole sentences of each run of one language, an announcement before a passage in
  // another language (once while it lasts), a pause of 1 s when the language of CEV comes back
  function build(parsed, skip) {
    var base = CEV.lang(), list = [], foreign = null;
    parsed.forEach(function (x) {
      var msg = x.msg, p = x.p, first = true;
      function add(text, said, lang, start) {
        if (first && info && info.single) { said = CEV.t(role(msg) === "human" ? "web.speak.question" : "web.speak.answer") + " " + said; }
        first = false;
        list.push({ msg: msg, text: text, said: said, lang: lang, start: start, marks: p.marks, total: p.text.length });
      }
      x.segs.forEach(function (sg) {
        var t = p.text.slice(sg.start, sg.end);
        if (!t.trim()) { return; }
        if (sg.lang !== base) {
          if (foreign !== sg.lang) {
            var key = skip[sg.lang] ? "web.speak.passage_skip" : "web.speak.passage", a = CEV.t(key, { lang: langName(sg.lang) });
            add(a, a, base, sg.start);
            foreign = sg.lang;
          }
          if (skip[sg.lang]) { return; }
        } else if (!sg.label) {
          if (foreign) { list.push({ msg: msg, pause: 1000 }); }
          foreign = null;
        }
        if (sg.label) { list.push({ msg: msg, pause: 450 }); }  // what CEV announces, apart from the text (08/11)
        split(t).forEach(function (piece) { add(piece.text, piece.text, sg.lang, sg.start + piece.start); });
        if (sg.label) { list.push({ msg: msg, pause: 450 }); }
      });
    });
    return list;
  }

  // Reading bubbles one after the other (one, or all from the button of the page): their pieces in a row,
  // the next one asked while the current one is heard, each bubble shown when its reading starts
  function read(msgs, all) {
    stop();
    prepare(msgs, function (parsed, skip) { start(build(parsed, skip), all); });
  }
  // the icons Claude writes (🎯 "dans le mille", ✅ "coche blanche"…) are not said (08/11)
  var ICONS = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{1F3FB}-\u{1F3FF}\u{FE0E}\u{FE0F}\u{200D}\u{20E3}]/gu;
  function unicons(text) {
    return text.replace(ICONS, "").replace(/[ \t]{2,}/g, " ").replace(/[ \t]+([.,])/g, "$1")  /* French keeps " :", " ?" */
      .replace(/([.!?])[ \t]*\.(?=\s|$)/g, "$1").trim();  // "lecture. 🎯." → "lecture."
  }
  function fetchItem(it) {
    if (it.pause) { return Promise.resolve(null); }
    var said = unicons(it.said);
    if (!/[\p{L}\p{N}]/u.test(said)) { it.pause = 1; return Promise.resolve(null); }  // nothing left to say
    return sound(said, it.msg, false, it.lang);
  }
  function start(list, all) {
    stop();
    if (!list.length) { return; }
    var r = { msg: list[0].msg, audio: null, stopped: false, all: Boolean(all) };
    reading = r;
    pressed(r.all);
    state(r.msg, "cev-speak-wait");
    var i = 0, next = fetchItem(list[0]);
    function step() {
      var cur = next, item = list[i];
      cur.then(function (blob) {
        if (r.stopped) { return null; }
        if (item.msg !== r.msg) {
          state(r.msg, null);
          r.msg = item.msg;
          var following = window.CEV.scrolling && CEV.scrolling();  // nav.js follows the reading itself
          if (r.all && !following) { item.msg.scrollIntoView({ behavior: "smooth", block: "start" }); }
        }
        i += 1;
        next = i < list.length ? fetchItem(list[i]) : null;
        if (next) { next.catch(function () { /* shown when its turn comes */ }); }
        state(item.msg, "cev-speak-on");
        var heard;
        if (item.pause) {
          heard = new Promise(function (ok) { setTimeout(ok, item.pause * timing.pause); });
        } else {
          r.item = item;
          heard = play(r, blob);
        }
        return heard.then(function () {
          if (r.stopped) { return; }
          if (next) { state(r.msg, "cev-speak-wait"); step(); } else { stop(); }
        });
      }).catch(function (err) {
        if (r.stopped) { return; }
        stop();
        tell(err && err.server ? err.message : CEV.t("web.fav.failed") + (err && err.message ? " : " + err.message : ""));
      });
    }
    step();
  }

  // The button "Lire" of the page: every bubble shown, from the first one on the screen
  var allB = document.querySelector('#page-nav [data-go="speak"]');
  function pressed(on) {
    if (!allB) { return; }
    allB.setAttribute("aria-pressed", on ? "true" : "false");
    var key = on ? "web.speak.stop" : "web.speak.all";
    allB.setAttribute("data-i18n-attr", "title:" + key);
    allB.title = CEV.t(key);
  }
  function shownEntries() {
    return Array.prototype.filter.call(root.querySelectorAll(ENTRY), function (m) {
      return m.querySelector(".cev-speak") && (m.checkVisibility ? m.checkVisibility() : m.offsetParent !== null);
    });
  }
  function readAll() {
    if (reading && reading.all) { stop(); return; }
    var msgs = shownEntries(), top = msgs.findIndex(function (m) { return m.getBoundingClientRect().bottom > 60; });
    ready(function () { read(msgs.slice(Math.max(0, top)), true); }, msgs[0]);
  }

  // A box of the page: a message (the server's, copyable), or the installation going on
  function box(text, title) {
    var b = document.createElement("dialog");
    b.className = "cev-confirm cev-speak-box";
    b.innerHTML = '<div class="cev-confirm-in">' + (title ? '<p class="cev-speak-head"></p>' : "") +
      '<p class="cev-confirm-text"></p><div class="cev-confirm-buttons"><button type="button" class="cev-confirm-yes"></button></div></div>';
    if (title) { b.querySelector(".cev-speak-head").textContent = title; }
    b.querySelector(".cev-confirm-text").textContent = text;
    b.querySelector(".cev-confirm-yes").textContent = CEV.t("web.close");
    b.addEventListener("click", function (e) {
      if (e.target.closest(".cev-confirm-yes") || e.target === b) { b.close(); }
    });
    b.addEventListener("close", function () { b.remove(); });
    document.body.appendChild(b);
    b.showModal();
    return b;
  }
  function tell(text) { box(text); }

  // Piper missing: install it (with the agreement of the user), following the steps, then read
  // the pauses (× pause) and the look at an installation (ms): shortened by the tests only (AF-f6 follow-up, 15/11)
  var timing = { pause: 1, poll: 1000 };

  function install(msg, go) {
    CEV.confirm(CEV.t("web.speak.install_ask").replace("{dir}", info.dir), function () {
      var b = box("…", CEV.t("web.speak.installing")), text = b.querySelector(".cev-confirm-text");
      state(msg, "cev-speak-wait");
      ask("/__cev__/speak/install", {}).then(function poll() {
        return status().then(function (s) {
          if (s.job.state === "running") {
            text.textContent = s.job.step || "…";
            return new Promise(function (ok) { setTimeout(ok, timing.poll); }).then(poll);
          }
          state(msg, null);
          if (s.job.state === "failed") { text.textContent = s.job.message; return null; }
          b.close();
          go();
          return null;
        });
      }).catch(function (err) { state(msg, null); text.textContent = err.message; });
    });
  }

  // Piper ready (installed, with the agreement of the user), then go
  function ready(go, msg) {
    (info ? Promise.resolve(info) : status()).then(function (st) {
      if (!st.voice) { tell(CEV.t("web.fav.failed")); return; }
      if (!st.installed) { if (msg) { install(msg, go); } return; }
      go();
    }, function (err) { tell(err.message); });
  }
  function click(msg) {
    if (reading && reading.msg === msg && !reading.all) { stop(); return; }
    ready(function () { read([msg]); }, msg);
  }

  // The chip "Voix" of the bar and its box: a voice for "Moi", one for Claude, and the speed
  var bar = document.getElementById("plan-bar"), panel = null, sample = null;
  function esc(x) { return String(x).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function mb(bytes) { return CEV.t("web.size_mb").replace("{size}", String(Math.round(bytes / 1048576))); }
  function named(c) {
    return c.name + (c.speaker ? " — " + c.speaker : "") + (c.region ? " (" + c.region + ")" : "") +
      (c.speakers ? " (" + c.speakers.length + ")" : "") + " · " + CEV.t("web.speak.q." + c.quality);
  }
  function chip() {
    var slot = document.getElementById("voices-slot") || bar;  // 22/11: in the tab "Bulles"
    if (!slot || slot.querySelector(".cev-voices")) { return; }
    var b = document.createElement("button");
    b.type = "button";
    b.className = "plan-chip cev-voices";
    b.innerHTML = ICON + ' <span data-i18n="web.speak.voices"></span>';
    b.setAttribute("data-i18n-attr", "title:web.speak.voices_title");
    slot.insertBefore(b, slot.firstChild);
    CEV.apply(b);
    b.addEventListener("click", function () { open(CEV.lang()); });
  }
  var LANGS = ["fr", "en", "de", "es", "it", "nl", "pt", "pl", "ru", "ja", "ko", "zh"];
  function quiet() { if (sample) { sample.pause(); sample = null; } }

  // The voices installed (speech.installed_voices): size, in two folders, in use; one removed after a yes
  function installedList(b) {
    var box = b.querySelector(".cev-voice-installed"), body = box.querySelector(".cev-voice-inst-list");
    function paint(list) {
      var total = list.reduce(function (n, v) { return n + v.size; }, 0);
      box.querySelector("summary").textContent = CEV.t("web.speak.installed", { n: list.length, size: mb(total) });
      body.textContent = "";
      if (!list.length) { body.textContent = CEV.t("web.speak.none_installed"); return; }
      list.forEach(function (v) {
        var row = document.createElement("div");
        row.className = "cev-voice-inst";
        var what = document.createElement("span");
        what.textContent = v.name + " · " + mb(v.size) + (v.duplicate ? " · " + CEV.t("web.speak.duplicate") : "") +
          (v.used ? " · " + CEV.t("web.speak.used") : "");
        what.title = v.where;
        if (v.duplicate) { what.classList.add("cev-voice-dup"); }
        var where = document.createElement("small");
        where.textContent = v.where;
        var del = document.createElement("button");
        del.type = "button";
        del.className = "cev-voice-del";
        del.textContent = "🗑";
        del.title = CEV.t("web.speak.remove");
        del.addEventListener("click", function () {
          var text = CEV.t("web.speak.remove_ask", { name: v.name, size: mb(v.size), dir: v.where }) +
            (v.used && !v.duplicate ? " " + CEV.t("web.speak.remove_used") : "");
          CEV.confirm(text, function () {
            ask("/__cev__/speak/remove", { name: v.name, dir: v.dir }).then(function (r) { return r.json(); })
              .then(function (res) { warmed = false; paint(res.voices); }, function (err) { tell(err.message); });
          });
        });
        row.appendChild(what);
        row.appendChild(where);
        row.appendChild(del);
        body.appendChild(row);
      });
    }
    function load() {
      ask("/__cev__/speak/installed", {}).then(function (r) { return r.json(); })
        .then(function (res) { paint(res.voices); }, function (err) { body.textContent = err.message; });
    }
    box.addEventListener("toggle", function () { if (box.open) { load(); } });
    load();
  }

  function open(lang) {
    stop();
    lang = lang || CEV.lang();
    ask("/__cev__/speak/voices", { lang: lang }).then(function (r) { return r.json(); }).then(function (d) {
      if (panel) { panel.close(); }
      var who = { human: "web.who.human", assistant: "web.who.assistant" };
      var groups = [["F", "♀ " + CEV.t("web.speak.women")], ["M", "♂ " + CEV.t("web.speak.men")], ["?", CEV.t("web.speak.others")]];
      var list = d.choices;
      function options(cur) {
        return groups.map(function (g) {
          var o = list.map(function (c, i) {
            if (c.sex !== g[0]) { return ""; }
            var on = c.speakers ? cur.split("#")[0] === c.voice : cur === c.voice;
            return '<option value="' + i + '"' + (on ? " selected" : "") + ">" + esc(named(c)) + "</option>";
          }).join("");
          return o ? '<optgroup label="' + esc(g[1]) + '">' + o + "</optgroup>" : "";
        }).join("");
      }
      var b = panel = document.createElement("dialog");
      b.className = "cev-confirm cev-voice-box";
      b.innerHTML = '<div class="cev-confirm-in"><p class="cev-speak-head"><span></span><button type="button" class="admin-close cev-voice-x" aria-label="">' + CEV.icon("cross", 16) + '</button></p>' +
        '<div class="cev-voice-lang"><span data-i18n="web.speak.lang"></span> <select class="cev-voice-langs">' +
        LANGS.map(function (l) { return '<option value="' + l + '"' + (l === lang ? " selected" : "") + ">" + esc(langName(l)) + "</option>"; }).join("") +
        '</select> <label class="cev-voice-skip"' + (lang === CEV.lang() ? " hidden" : "") + '><input type="checkbox"' + (d.skip ? " checked" : "") +
        "> <span></span></label></div>" +
        ["human", "assistant"].map(function (role) {
          return '<div class="cev-voice-row" data-role="' + role + '"><span class="cev-voice-who" data-i18n="' + who[role] + '"></span>' +
            '<select class="cev-voice-pick">' + options(d.voices[role]) + "</select>" +
            '<label class="cev-voice-n" hidden><span data-i18n="web.speak.number"></span> <input type="number" min="1" step="1"></label>' +
            '<button type="button" class="cev-voice-play">' + CEV.icon("speaker", 13) + ' <span data-i18n="web.speak.listen"></span></button></div>' +
            '<div class="cev-voice-rate" data-role="' + role + '"><span data-i18n="web.speak.speed"></span> <small data-i18n="web.speak.slow"></small>' +
            '<input type="range" min="' + RATES[0] + '" max="' + RATES[1] + '" step="0.05" value="' + rate(role) + '">' +
            '<small data-i18n="web.speak.fast"></small> <output></output></div>' +
            '<p class="cev-voice-note" data-role="' + role + '"></p>';
        }).join("") +
        '<details class="cev-voice-installed"><summary></summary><div class="cev-voice-inst-list"></div></details></div>';
      var langTitle = langName(lang);
      b.querySelector(".cev-speak-head span").textContent = CEV.t("web.speak.panel").replace("{lang}",
        langTitle && langTitle !== lang ? langTitle.charAt(0).toUpperCase() + langTitle.slice(1) : d.language);
      b.querySelector(".cev-voice-x").setAttribute("aria-label", CEV.t("web.close"));
      CEV.apply(b);
      b.querySelector(".cev-voice-skip span").textContent = CEV.t("web.speak.skip_lang", { lang: langName(lang) });
      b.querySelector(".cev-voice-langs").addEventListener("change", function (e) { b.close(); open(e.target.value); });
      b.querySelector(".cev-voice-skip input").addEventListener("change", function (e) {
        ask("/__cev__/speak/skip", { lang: lang, on: e.target.checked }).catch(function (err) { tell(err.message); });
      });
      installedList(b);
      // the voice of a row: the choice of the list, and the speaker by number for a voice with many
      function row(role) {
        var r = b.querySelector('.cev-voice-row[data-role="' + role + '"]'), c = list[+r.querySelector("select").value];
        var n = r.querySelector(".cev-voice-n"), input = n.querySelector("input");
        return { r: r, c: c, n: n, input: input };
      }
      function voiceOf(x) {
        if (!x.c) { return null; }
        if (!x.c.speakers) { return x.c.voice; }
        var k = Math.min(Math.max(1, parseInt(x.input.value, 10) || 1), x.c.speakers.length);
        return x.c.voice + "#" + x.c.speakers[k - 1];
      }
      function paint(role) {
        var x = row(role), note = b.querySelector('.cev-voice-note[data-role="' + role + '"]');
        if (!x.c) { return; }
        x.n.hidden = !x.c.speakers;
        if (x.c.speakers) {
          x.input.max = x.c.speakers.length;
          if (!x.input.value) {
            var cur = d.voices[role].split("#");
            x.input.value = cur[0] === x.c.voice ? x.c.speakers.indexOf(cur[1]) + 1 || 1 : 1;
          }
        }
        note.textContent = x.c.downloaded ? CEV.t("web.speak.downloaded") :
          x.c.size ? CEV.t("web.speak.to_download").replace("{size}", mb(x.c.size)) : CEV.t("web.speak.to_download_later");
      }
      function save(role) {
        var v = voiceOf(row(role));
        if (!v) { return; }
        d.voices[role] = v;
        ask("/__cev__/speak/choose", { role: role, voice: v, lang: lang }).then(function (r) { return r.json(); })
          .then(function (s) { if (lang === CEV.lang()) { info = s; } warmed = false; }, function (err) { tell(err.message); });
      }
      ["human", "assistant"].forEach(function (role) {
        var x = row(role);
        paint(role);
        x.r.querySelector("select").addEventListener("change", function () { x.input.value = ""; paint(role); save(role); });
        x.input.addEventListener("change", function () { paint(role); save(role); });
        x.r.querySelector(".cev-voice-play").addEventListener("click", function () {
          var y = row(role);
          if (!y.c) { return; }
          var url = y.c.sample;
          if (y.c.speakers) { url = url.replace("{id}", String(Math.min(Math.max(1, parseInt(y.input.value, 10) || 1), y.c.speakers.length) - 1)); }
          quiet();
          sample = new Audio(url);
          sample.playbackRate = rate(role);
          sample.role = role;
          sample.play().catch(function () { tell(CEV.t("web.speak.no_sample")); });
        });
      });
      ["human", "assistant"].forEach(function (role) {  // the speed of each voice, under its choice
        var box = b.querySelector('.cev-voice-rate[data-role="' + role + '"]');
        var range = box.querySelector("input"), out = box.querySelector("output");
        function shown() { out.textContent = "×" + String(rate(role).toFixed(2)).replace(/0$/, "").replace(".", CEV.t("fmt.decimal")); }
        shown();
        range.addEventListener("input", function () {
          put("cev-speak-rate-" + role, range.value);
          shown();
          if (sample && sample.role === role) { sample.playbackRate = rate(role); }
        });
      });
      b.addEventListener("click", function (e) { if (e.target.closest(".cev-voice-x") || e.target === b) { b.close(); } });
      b.addEventListener("close", function () { quiet(); b.remove(); if (panel === b) { panel = null; } });
      document.body.appendChild(b);
      b.showModal();
    }).catch(function (err) { tell(err.message); });
  }

  function button(msg) {
    var time = msg.querySelector(":scope > .message-time");
    if (!time || time.querySelector(".cev-speak") || !Array.prototype.some.call(texts(msg), function (x) { return x.textContent.trim(); })) { return; }
    var b = document.createElement("button");
    b.type = "button";
    b.className = "cev-speak";
    b.innerHTML = ICON;
    b.setAttribute("data-i18n-attr", "title:web.speak.title");
    b.title = CEV.t("web.speak.title");
    time.insertBefore(b, time.querySelector(".plan-dn"));
  }

  A.ready(function (served) {
    if (!served) { return; }
    root.querySelectorAll(ENTRY).forEach(button);
    chip();
    status().catch(function () { /* shown at the click */ });
    if (allB) {
      allB.hidden = false;
      allB.addEventListener("click", function () {
        if (!info || !info.installed) { status().then(readAll, function (err) { tell(err.message); }); } else { readAll(); }
      });
    }
    function warm() {  // Piper started under the mouse, once
      if (warmed || !info || !info.installed) { return; }
      warmed = true;
      ask("/__cev__/speak/warm", {}).catch(function () { warmed = false; });
    }
    root.addEventListener("pointerover", function (e) { if (e.target.closest(".cev-speak")) { warm(); } });
    if (allB) { allB.addEventListener("pointerenter", warm); }
    root.addEventListener("click", function (e) {
      var b = e.target.closest(".cev-speak");
      if (b) { click(b.closest(ENTRY)); }
    });
    document.addEventListener("cev-language", function () { stop(); warmed = false; status().catch(function () {}); });
  });
  window.CEV.speak = { words: words, pieces: pieces, split: split, stop: stop, target: target, timing: timing };
})();
