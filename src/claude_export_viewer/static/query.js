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
  function ranges(text, words) {
    var out = [];
    words.forEach(function (w) {
      var j = text.indexOf(w);
      while (j >= 0) { out.push([j, j + w.length]); j = text.indexOf(w, j + w.length); }
    });
    out.sort(function (a, b) { return a[0] - b[0]; });
    var merged = [];
    out.forEach(function (r) {
      var last = merged[merged.length - 1];
      if (last && r[0] <= last[1]) { last[1] = Math.max(last[1], r[1]); } else { merged.push(r.slice()); }
    });
    return merged;
  }

  // Index: passages of a conversation ({t, m} of searchdata.py), 0 unless every term is found.
  function passages(e, terms) {
    var found = terms.every(function (term) {
      return term.text.some(function (w) { return e.t.indexOf(w) >= 0; }) ||
        e.m.some(function (f) { return term.tex.some(function (c) { return texHas(f, c); }); });
    });
    if (!found) { return 0; }
    return ranges(e.t, textWords(terms)).length +
      e.m.filter(function (f) { return formulaHit(f, terms); }).length;
  }

  return { norm: norm, parse: parse, enough: enough, formulaHit: formulaHit, textWords: textWords,
    ranges: ranges, passages: passages };
})();
