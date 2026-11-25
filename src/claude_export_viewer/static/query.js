/* What a search in the content looks for: shared by the index (search.js) and the
 * conversation pages (msg.js), so that both count the same passages.
 * - a word ("alpha"): in the text only, formulas left out;
 * - a TeX command ("\alpha"): in the formulas only, as a whole command ("\in" is not "\int");
 * - a symbol ("α", "∞", "≤"…): the symbol in the text (and the name of a Greek letter,
 *   "alpha"), and its TeX commands in the formulas.
 * Case and accents ignored: NFD, accents U+0300-U+036F removed (not the overlays U+0334-U+0338:
 * "≠" must not become "="), lower case (as searchdata.py). */
window.CEVQuery = (function () {
  "use strict";
  function norm(s) { return s.normalize("NFD").replace(/[̀-̳̹-ͯ]/g, "").toLowerCase(); }

  var GREEK = { "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta",
    "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "ο": "omicron",
    "π": "pi", "ρ": "rho", "σ": "sigma", "ς": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "χ": "chi",
    "ψ": "psi", "ω": "omega", "ϵ": "epsilon", "ϕ": "phi", "ϑ": "theta", "ϱ": "rho", "ϖ": "pi" };
  var VARIANTS = { "epsilon": ["varepsilon"], "phi": ["varphi"], "theta": ["vartheta"], "rho": ["varrho"],
    "pi": ["varpi"], "sigma": ["varsigma"] };
  var SYMBOLS = { "∞": ["infty"], "∫": ["int"], "∬": ["iint"], "∮": ["oint"], "∑": ["sum"], "∏": ["prod"],
    "√": ["sqrt"], "∂": ["partial"], "∇": ["nabla"], "≤": ["le", "leq"], "≥": ["ge", "geq"], "≠": ["ne", "neq"],
    "≈": ["approx"], "≡": ["equiv"], "∼": ["sim"], "∝": ["propto"], "∈": ["in"], "∉": ["notin"],
    "⊂": ["subset"], "⊆": ["subseteq"], "∪": ["cup"], "∩": ["cap"], "∅": ["emptyset", "varnothing"],
    "∀": ["forall"], "∃": ["exists"], "¬": ["neg", "lnot"], "∧": ["wedge", "land"], "∨": ["vee", "lor"],
    "→": ["to", "rightarrow"], "←": ["leftarrow", "gets"], "↔": ["leftrightarrow"], "⇒": ["rightarrow", "implies"],
    "⇔": ["leftrightarrow", "iff"], "↦": ["mapsto"], "±": ["pm"], "∓": ["mp"], "×": ["times"], "÷": ["div"],
    "·": ["cdot"], "∘": ["circ"], "⊗": ["otimes"], "⊕": ["oplus"], "ℓ": ["ell"], "ℏ": ["hbar"], "…": ["dots", "ldots"] };

  // [{text: [strings searched in the text], tex: ["\\command" searched in the formulas]}]
  function parse(query) {
    return norm(query).split(/\s+/).filter(Boolean).map(function (w) {
      if (w.charAt(0) === "\\" && w.length > 1) { return { text: [], tex: [w] }; }
      var key = w.normalize("NFC");  // the tables hold composed characters ("≠", not "=" + overlay)
      var name = GREEK[key];
      if (name) {
        return { text: [w, name], tex: [name].concat(VARIANTS[name] || []).map(function (c) { return "\\" + c; }) };
      }
      if (SYMBOLS[key]) { return { text: [w], tex: SYMBOLS[key].map(function (c) { return "\\" + c; }) }; }
      return { text: [w], tex: [] };
    });
  }

  // Enough to search: 3 characters, or a symbol / a TeX command.
  function enough(terms) {
    return terms.some(function (t) { return t.tex.length; }) ||
      terms.map(function (t) { return t.text[0]; }).join("").length >= 3;
  }

  function texHas(formula, command) {  // the whole command: not followed by a letter
    var j = formula.indexOf(command);
    while (j >= 0) {
      if (!/[a-z]/.test(formula.charAt(j + command.length))) { return true; }
      j = formula.indexOf(command, j + 1);
    }
    return false;
  }

  function formulaHit(formula, terms) {
    return terms.some(function (t) { return t.tex.some(function (c) { return texHas(formula, c); }); });
  }

  function textWords(terms) {
    var out = [];
    terms.forEach(function (t) { t.text.forEach(function (w) { if (out.indexOf(w) < 0) { out.push(w); } }); });
    return out;
  }

  // Places of the words in a normalized text, overlapping ones merged: [[start, end], …]
  // A letter or a digit (accents are taken off by norm, so "caf" is not a whole word of "café");
  // Chinese and Japanese characters do not count: no space separates their words.
  var LETTER = /[\p{L}\p{N}]/u, NO_SPACES = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u;
  function letter(c) { return !!c && LETTER.test(c) && !NO_SPACES.test(c); }

  // ``whole``: only the words found whole (no letter just before or just after)
  function ranges(text, words, whole) {
    var out = [];
    words.forEach(function (w) {
      var j = text.indexOf(w);
      while (j >= 0) {
        if (!whole || (!letter(text[j - 1]) && !letter(text[j + w.length]))) {
          out.push([j, j + w.length]);
          j = text.indexOf(w, j + w.length);
        } else { j = text.indexOf(w, j + 1); }
      }
    });
    out.sort(function (a, b) { return a[0] - b[0]; });
    var merged = [];
    out.forEach(function (r) {
      var last = merged[merged.length - 1];
      if (last && r[0] <= last[1]) { last[1] = Math.max(last[1], r[1]); } else { merged.push(r.slice()); }
    });
    return merged;
  }

  // Index: passages of a conversation ({t, m} of searchdata.py), 0 unless every term is found;
  // whole words only, as the search of a page with "Mots entiers" checked (its default).
  function passages(e, terms) {
    var found = terms.every(function (term) {
      return term.text.some(function (w) { return ranges(e.t, [w], true).length > 0; }) ||
        e.m.some(function (f) { return term.tex.some(function (c) { return texHas(f, c); }); });
    });
    if (!found) { return 0; }
    return ranges(e.t, textWords(terms), true).length +
      e.m.filter(function (f) { return formulaHit(f, terms); }).length;
  }

  // --- Approximate search (AE-m1, 08/11): "Tolérance" n = how many letters may differ (Levenshtein: a letter
  // changed, added or removed counts 1, two letters swapped count 2); words of less than 4 letters stay exact,
  // words of 4 to 6 letters admit 1 at most. The words of the text that are close enough are searched too.
  var WORD = /[\p{L}\p{N}]+(?:['’_-][\p{L}\p{N}]+)*/gu;
  var FUZZY_KEY = "cev-fuzzy", FUZZY_MAX = 2;  // 3 was too wide (08/11)
  function level() {
    try { var n = parseInt(localStorage.getItem(FUZZY_KEY), 10); return n > 0 && n <= FUZZY_MAX ? n : 0; } catch (e) { return 0; }
  }
  function setLevel(n) { try { localStorage.setItem(FUZZY_KEY, String(n)); } catch (e) { /* no storage */ } }
  function allowed(len, n) { return n <= 0 || len < 4 ? 0 : len <= 6 ? Math.min(1, n) : n; }
  // The distinct words of a normalized text, compound words ("alpha-stable") and their parts
  function wordsOf(text) {
    var out = new Set(), m;
    WORD.lastIndex = 0;
    while ((m = WORD.exec(text))) {
      out.add(m[0]);
      if (/['’_-]/.test(m[0])) { m[0].split(/['’_-]/).forEach(function (w) { if (w) { out.add(w); } }); }
    }
    return out;
  }
  function distance(a, b, max) {  // Levenshtein, max + 1 as soon as it goes beyond max
    if (Math.abs(a.length - b.length) > max) { return max + 1; }
    var prev = [], cur = [], i, j;
    for (j = 0; j <= b.length; j++) { prev[j] = j; }
    for (i = 1; i <= a.length; i++) {
      cur = [i];
      var best = i;
      for (j = 1; j <= b.length; j++) {
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        if (cur[j] < best) { best = cur[j]; }
      }
      if (best > max) { return max + 1; }
      prev = cur;
    }
    return prev[b.length];
  }
  // The terms with, for each plain word, the words of ``words`` (wordsOf) close enough; and those words.
  function fuzzy(terms, words, n) {
    var also = [];
    if (!n) { return { terms: terms, also: also }; }
    var out = terms.map(function (t) {
      if (t.tex.length || t.text.length !== 1) { return t; }  // a TeX command, a symbol, a Greek letter: exact
      var w = t.text[0], max = allowed(w.length, n);
      if (!max) { return t; }
      var extra = [];
      words.forEach(function (x) {
        if (x !== w && distance(w, x, max) <= max) { extra.push(x); if (also.indexOf(x) < 0) { also.push(x); } }
      });
      return extra.length ? { text: [w].concat(extra), tex: [], fuzzy: true } : t;
    });
    return { terms: out, also: also };
  }

  // The control "Tolérance ◂ 0 ▸" (index and pages share the level, localStorage cev-fuzzy); onChange(n)
  function counter(onChange) {
    var box = document.createElement("span");
    box.className = "cev-fuzzy";
    box.innerHTML = '<span class="cev-fuzzy-label" data-i18n="web.fuzzy.label"></span><span class="cev-fuzzy-set">' +
      '<button type="button" data-d="-1" data-i18n-attr="title:web.fuzzy.less">−</button>' +
      '<span class="cev-fuzzy-n"></span><button type="button" data-d="1" data-i18n-attr="title:web.fuzzy.more">+</button></span>';  // (22/11) − n +, no longer ◂ n ▸ (tiny)
    box.setAttribute("data-i18n-attr", "title:web.fuzzy.title");
    box.title = CEV.t("web.fuzzy.title");
    box.querySelector(".cev-fuzzy-label").textContent = CEV.t("web.fuzzy.label");
    box.querySelector('[data-d="-1"]').title = CEV.t("web.fuzzy.less");
    box.querySelector('[data-d="1"]').title = CEV.t("web.fuzzy.more");
    var shown = box.querySelector(".cev-fuzzy-n");
    function paint(n) {
      shown.textContent = String(n);
      box.classList.toggle("on", n > 0);
      box.querySelector('[data-d="-1"]').disabled = n <= 0;
      box.querySelector('[data-d="1"]').disabled = n >= FUZZY_MAX;
    }
    paint(level());
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) { return; }
      var n = Math.max(0, Math.min(FUZZY_MAX, level() + Number(b.getAttribute("data-d"))));
      setLevel(n);
      paint(n);
      onChange(n);
    });
    box.paint = function () { paint(level()); };
    return box;
  }

  return { norm: norm, parse: parse, enough: enough, formulaHit: formulaHit, textWords: textWords,
    ranges: ranges, passages: passages, wordsOf: wordsOf, distance: distance, fuzzy: fuzzy, level: level,
    setLevel: setLevel, FUZZY_MAX: FUZZY_MAX, counter: counter };
})();
