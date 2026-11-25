/* Conversation pages:
 * - the icon after the date copies the message as Markdown (formulas as LaTeX source);
 * - keyboard (and the arrow buttons on the right): right / left arrows (4 / 6 of the numeric
 *   keypad when it is off) go to your next / previous message, M hides or shows all of
 *   Claude's answers, ? shows the list of keys. Only on this page: elsewhere the keys keep
 *   their usual role. */
(function () {
  "use strict";

  // --- Copy a message -------------------------------------------------------------
  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(area);
    return ok ? Promise.resolve() : Promise.reject(new Error("copy"));
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () { return fallbackCopy(text); });
    }
    return fallbackCopy(text);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest(".copy-msg") : null;
    if (!button) { return; }
    copyText(button.getAttribute("data-md")).then(function () {
      button.classList.add("copied");
      button.title = CEV.t("web.copied");
      clearTimeout(button._timer);
      button._timer = setTimeout(function () {
        button.classList.remove("copied");
        button.title = CEV.t("web.copy_msg");
      }, 1600);
    }, function () { button.title = CEV.t("web.copy_failed"); });
  });

  document.addEventListener("click", function (event) {
    var b = event.target.closest ? event.target.closest('#page-nav [data-go="next"], #page-nav [data-go="back"]') : null;
    if (b && !b.closest(".page-nav.short")) { go(b.getAttribute("data-go") === "next" ? 1 : -1); }  // greyed when short
  });

  // --- Keyboard ---------------------------------------------------------------------
  var help = null;

  function toggleHelp() {
    if (!help) {
      help = document.createElement("div");
      help.className = "keys-help";
      help.setAttribute("role", "dialog");
      var rows = [["→  6", "web.keys.next_pad"], ["←  4", "web.keys.prev_pad"], ["7  5  1", "web.keys.page"], ["M", "web.keys.fold"],
                  ["+  −", "web.keys.speed"], ["?", "web.keys.help"]];
      var html = '<strong data-i18n="web.keys.title">' + CEV.t("web.keys.title") + "</strong><dl>";
      rows.forEach(function (r) {
        html += "<dt>" + r[0].split("  ").map(function (k) { return "<kbd>" + k + "</kbd>"; }).join(" ") +
          '</dt><dd data-i18n="' + r[1] + '">' + CEV.t(r[1]) + "</dd>";
      });
      help.innerHTML = html + "</dl>";
      help.addEventListener("click", toggleHelp);
      document.body.appendChild(help);
      return;
    }
    help.hidden = !help.hidden;
  }

  function visibleQuestions() {
    return Array.prototype.filter.call(document.querySelectorAll(".messages > .message-human"),
      function (el) { return el.offsetParent !== null; });
  }

  // Your message the button or the arrow key goes to; null: nothing to go to (the button greyed).
  // Next: none at the bottom of the page either (the page cannot move any further).
  function targetOf(step) {
    var list = visibleQuestions();
    if (!list.length) { return null; }
    var tops = list.map(function (el) { return el.getBoundingClientRect().top; });
    if (step > 0) {
      if (window.scrollY >= document.documentElement.scrollHeight - window.innerHeight - 2) { return null; }
      for (var i = 0; i < tops.length; i++) { if (tops[i] > 8) { return list[i]; } }
    } else {
      for (var j = tops.length - 1; j >= 0; j--) { if (tops[j] < -8) { return list[j]; } }
    }
    return null;
  }

  function go(step) {
    var target = targetOf(step);
    if (target) { target.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }

  // Next / Back greyed when they have nowhere to go: checked after a scroll, a resize, a click
  // (answers hidden or shown, frames opened) and a change of the versions shown
  var nextB = document.querySelector('#page-nav [data-go="next"]'), backB = document.querySelector('#page-nav [data-go="back"]');
  var pending = false;
  function updateButtons() {
    pending = false;
    if (nextB) { nextB.disabled = !targetOf(1); }
    if (backB) { backB.disabled = !targetOf(-1); }
  }
  function later() { if (!pending) { pending = true; requestAnimationFrame(updateButtons); } }
  window.addEventListener("scroll", later, { passive: true });
  window.addEventListener("resize", later);
  document.addEventListener("click", function () { setTimeout(later, 60); });
  document.addEventListener("cev-versions", later);
  window.addEventListener("load", later);
  later();

  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.altKey || event.metaKey || event.defaultPrevented) { return; }
    var t = event.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) { return; }
    var key = event.key.toLowerCase();
    if (event.key === "ArrowRight") { go(1); }
    else if (event.key === "ArrowLeft") { go(-1); }
    else if (key === "m") {
      var all = document.getElementById("fold-all");
      if (all && !all.hidden) { all.click(); } else { return; }
    } else if (event.key === "?") { toggleHelp(); }
    else if (event.key === "Escape" && help && !help.hidden) { help.hidden = true; }
    else { return; }
    event.preventDefault();
  });
})();

/* Words searched in the page: from the index (?q=…), or typed in the bar at the top, which
 * can be changed in place (Enter or a short pause searches again) and closed; the magnifier
 * of the right column opens or closes it. Highlighted passages, buttons to go from one to the
 * next. Case and accents ignored, as in the index (search.js); "Mots entiers" (checked): whole words only. Only the text of the
 * messages: not the tool calls and results, the thinking or claude.ai's instructions. */
(function () {
  "use strict";
  var root = document.querySelector(".messages");
  if (!root) { return; }
  var norm = CEVQuery.norm;
  var marks = [], current = -1;

  var bar = document.createElement("div");
  bar.className = "hit-bar";
  bar.hidden = true;
  // the position "1 / 22" on the line of the box, under the field: the bar keeps its width
  bar.innerHTML = '<span class="hit-field"><input type="search" class="hit-words" spellcheck="false" autocomplete="off">' +
    '<span class="hit-line"><label class="hit-whole"><input type="checkbox" checked> <span data-i18n="web.hits.whole"></span></label>' +
    '<span class="hit-pos"></span></span></span>' +
    '<button type="button" data-step="-1"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M18 15l-6-6-6 6"/></svg></button>' +
    '<button type="button" data-step="1">' + CEV.icon("chevron", 14) + '</button>' +
    '<button type="button" data-step="0">' + CEV.icon("cross", 14) + '</button>';
  [["-1", "web.hits.prev"], ["1", "web.hits.next"], ["0", "web.hits.close"]].forEach(function (b) {
    var el = bar.querySelector('[data-step="' + b[0] + '"]');
    el.setAttribute("data-i18n-attr", "title:" + b[1]);
    el.title = CEV.t(b[1]);
  });
  var input = bar.querySelector(".hit-words");
  var whole = bar.querySelector(".hit-whole input");  // whole words only (checked on every page)
  bar.querySelector('[data-i18n="web.hits.whole"]').textContent = CEV.t("web.hits.whole");
  input.setAttribute("data-i18n-attr", "placeholder:web.hits.placeholder");
  input.placeholder = CEV.t("web.hits.placeholder");
  document.body.appendChild(bar);
  var pos = bar.querySelector(".hit-pos");
  // "Tolérance ◂ n ▸" (approximate search, query.js; the level of the index, ?f=n) and the words found besides
  var fuzzyBox = CEVQuery.counter(function () { searched = null; search(input.value); input.focus(); });
  var line2 = document.createElement("span");  // a second line under the field: the level, the words found besides
  line2.className = "hit-line hit-line2";
  line2.appendChild(fuzzyBox);
  bar.querySelector(".hit-field").appendChild(line2);
  var also = document.createElement("span");  // the words found besides, on the same line (full list as tooltip)
  also.className = "hit-also";
  also.hidden = true;
  line2.appendChild(also);

  function clear() {
    aiming++;  // the passages go away: no more scrolling to them (08/11: the page went up by itself on closing)
    marks.forEach(function (m) {
      if (m.tagName === "MARK") { m.replaceWith(document.createTextNode(m.textContent)); }
      else { m.classList.remove("cev-hit", "current"); }  // a formula
    });
    root.normalize();
    marks = [];
    current = -1;
    also.hidden = true;
    told();
  }
  // the plan view (plan.js) follows the passages found: event "cev-hits" {marks, current}
  function told() {
    document.dispatchEvent(new CustomEvent("cev-hits", { detail: { marks: marks.slice(), current: marks[current] || null } }));
  }

  // the other versions hidden (export.js): not searched
  function mainOnly() { return document.body.classList.contains("cev-main-only"); }

  function highlight(terms) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {  // the text of the messages only (as in the index)
        var p = n.parentNode;
        return p.closest(".content-text") && !p.closest(".tool-use, .tool-result, .thinking, .unknown-block, .math, button")
          && !(mainOnly() && p.closest(".removed-part"))
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) { nodes.push(walker.currentNode); }
    var n = CEVQuery.level(), found = [];
    if (n) {  // the words of the page close enough to the words searched
      var f = CEVQuery.fuzzy(terms, CEVQuery.wordsOf(nodes.map(function (x) { return norm(x.nodeValue); }).join(" \n ")), n);
      terms = f.terms;
      found = f.also;
    }
    also.hidden = !found.length;
    also.textContent = found.length ? CEV.t("web.fuzzy.also", { words: found.slice(0, 12).join(", ") + (found.length > 12 ? "…" : "") }) : "";
    also.title = also.textContent;
    var words = CEVQuery.textWords(terms);  // searched in the text; the formulas: CEVQuery.formulaHit
    nodes.forEach(function (node) {
      var text = node.nodeValue, normed = "", map = [];
      for (var i = 0; i < text.length; i++) {
        var c = norm(text[i]);
        for (var k = 0; k < c.length; k++) { normed += c[k]; map.push(i); }
      }
      var merged = CEVQuery.ranges(normed, words, whole.checked).map(function (r) { return [map[r[0]], map[r[1] - 1] + 1]; });
      for (var m = merged.length - 1; m >= 0; m--) {  // from the end: the offsets stay right
        node.splitText(merged[m][1]);
        var hit = node.splitText(merged[m][0]);
        var mark = document.createElement("mark");
        mark.className = "cev-hit";
        hit.parentNode.replaceChild(mark, hit);
        mark.appendChild(hit);
        marks.push(mark);
      }
    });
    // A formula is drawn by KaTeX when it comes near the screen, which replaces its content:
    // a formula whose TeX holds a word (\alpha for "alpha") is highlighted as a whole.
    Array.prototype.forEach.call(root.querySelectorAll(".content-text .math"), function (el) {
      if (el.closest(".tool-use, .tool-result, .thinking, .unknown-block") || (mainOnly() && el.closest(".removed-part"))) { return; }
      if (CEVQuery.formulaHit(norm(el.textContent), terms)) {
        el.classList.add("cev-hit");
        marks.push(el);
      }
    });
    marks.sort(function (a, b) { return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1; });
  }

  function reveal(mark) {
    // a hidden answer (fold.js): show it with its own button; a closed frame: open it.
    var top = mark.closest(".messages > *");
    if (top && top.classList.contains("cev-folded")) {
      var q = top.previousElementSibling;
      while (q && !q.classList.contains("message-human")) { q = q.previousElementSibling; }
      var b = q && q.querySelector(".fold-one");
      if (b) { b.click(); }
    }
    for (var d = mark.parentNode.closest("details"); d; d = d.parentNode.closest("details")) {
      if (!d.open) { d.open = true; }
    }
    if (window.CEV && CEV.showCode) { CEV.showCode(mark); }  // the code of a program (run.js)
    for (var f = mark.closest(".cev-long"); f; f = f.parentNode.closest(".cev-long")) {
      f.classList.add("cev-open");  // a long code frame (code.js)
    }
  }

  // Scrolling to a passage, done here frame by frame: the formulas met on the way are drawn
  // while the page scrolls and move the passage; the target is computed again at every frame,
  // so the movement follows it smoothly instead of stopping short. Scrolling by hand stops it.
  var aiming = 0;
  ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (type) {
    window.addEventListener(type, function (e) {
      if (!(e.target.closest && e.target.closest(".hit-bar"))) { aiming++; }
    }, { passive: true });
  });

  function scrollTo(mark) {
    var id = ++aiming, start = Date.now(), settled = 0, arrived = 0;
    (function frame() {
      // stopped by another aim, by the hand, or when the passage is no longer marked (bar closed, new search)
      if (id !== aiming || Date.now() - start > 12000 || !mark.isConnected) { return; }
      var r = mark.getBoundingClientRect();
      var max = document.documentElement.scrollHeight - window.innerHeight;
      var target = Math.max(0, Math.min(max, window.scrollY + r.top + r.height / 2 - window.innerHeight / 2));
      var gap = target - window.scrollY;
      if (Math.abs(gap) < 1) {
        // arrived: still watched 1.5 s, as the formulas and messages drawn late above move the passage (08/11)
        if (++settled > 10 && !arrived) { arrived = Date.now(); }
        if (arrived && Date.now() - arrived > 1500) { return; }
      } else {
        settled = 0;
        var step = gap * 0.14;  // a fraction of what is left: fast far away, slow at the end
        if (Math.abs(step) < 1) { step = gap > 0 ? Math.min(gap, 1) : Math.max(gap, -1); }
        window.scrollTo(0, window.scrollY + step);
      }
      requestAnimationFrame(frame);
    })();
  }

  function show(i) {
    if (!marks.length) {
      told();
      if (input.value.trim()) { pos.setAttribute("data-i18n", "web.hits.none"); pos.textContent = CEV.t("web.hits.none"); }
      else { pos.removeAttribute("data-i18n"); pos.textContent = ""; }
      return;
    }
    if (current >= 0) { marks[current].classList.remove("current"); }
    current = (i + marks.length) % marks.length;
    var mark = marks[current];
    reveal(mark);
    mark.classList.add("current");
    scrollTo(mark);
    pos.removeAttribute("data-i18n");
    pos.textContent = (current + 1) + " / " + marks.length;
    told();
  }

  var searched = null;
  function search(q) {  // highlights q and goes to its first passage; the address keeps it
    q = q.trim();
    if (q === searched) { return; }
    searched = q;
    clear();
    var terms = CEVQuery.parse(q);
    if (terms.length && CEVQuery.enough(terms)) { highlight(terms); }
    var lv = CEVQuery.level();
    history.replaceState(null, "", q ? location.pathname + "?q=" + encodeURIComponent(q) + (lv ? "&f=" + lv : "") : location.pathname);
    show(0);
  }

  function open() {
    bar.hidden = false;
    input.focus();
    input.select();
  }
  function close() {
    clear();
    searched = null;
    bar.hidden = true;
    history.replaceState(null, "", location.pathname);  // a reload no longer highlights
  }

  var typing = null;
  input.addEventListener("input", function () {
    clearTimeout(typing);
    typing = setTimeout(function () { search(input.value); }, 600);
  });
  whole.addEventListener("change", function () { searched = null; search(input.value); input.focus(); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      clearTimeout(typing);
      if (input.value.trim() === searched && marks.length) { show(current + (e.shiftKey ? -1 : 1)); }
      else { search(input.value); }
      e.preventDefault();
    } else if (e.key === "Escape") { close(); e.preventDefault(); }
  });
  bar.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b || b.closest(".cev-fuzzy")) { return; }  // "Tolérance ◂ ▸" has its own handler
    var step = +b.getAttribute("data-step");
    if (step) { show(current + step); } else { close(); }
  });
  document.addEventListener("cev-versions", function () {
    if (!bar.hidden && searched !== null) { searched = null; search(input.value); }
  });
  var find = document.querySelector('#page-nav [data-go="find"]');
  if (find) { find.addEventListener("click", function () { if (bar.hidden) { open(); } else { close(); } }); }

  var params = new URLSearchParams(location.search), q = params.get("q");
  var fz = parseInt(params.get("f"), 10);
  if (fz >= 0 && fz <= CEVQuery.FUZZY_MAX) { CEVQuery.setLevel(fz); fuzzyBox.paint(); }
  if (q) {
    input.value = q;
    bar.hidden = false;
    setTimeout(function () { search(q); }, 300);  // after the fonts and the formulas
  }
})();
