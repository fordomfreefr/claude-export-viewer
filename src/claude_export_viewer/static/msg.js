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
    if (b) { go(b.getAttribute("data-go") === "next" ? 1 : -1); }
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

  function go(step) {
    var list = visibleQuestions();
    if (!list.length) { return; }
    var tops = list.map(function (el) { return el.getBoundingClientRect().top; });
    var target = null;
    if (step > 0) {
      for (var i = 0; i < tops.length; i++) { if (tops[i] > 8) { target = list[i]; break; } }
    } else {
      for (var j = tops.length - 1; j >= 0; j--) { if (tops[j] < -8) { target = list[j]; break; } }
    }
    if (target) { target.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }

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

/* Words searched from the index (?q=…): highlighted, with a small bar to go from one
 * passage to the next. Case and accents ignored, as in the index (search.js). Only the text
 * of the messages: not the tool calls and results, the thinking or claude.ai's instructions. */
(function () {
  "use strict";
  var q = new URLSearchParams(location.search).get("q");
  var root = document.querySelector(".messages");
  if (!q || !root) { return; }
  var norm = CEVQuery.norm;
  var terms = CEVQuery.parse(q);
  var words = CEVQuery.textWords(terms);  // searched in the text; the formulas: CEVQuery.formulaHit
  if (!terms.length) { return; }

  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (n) {  // the text of the messages only (as in the index)
      var p = n.parentNode;
      return p.closest(".content-text") && !p.closest(".tool-use, .tool-result, .thinking, .unknown-block, .math, button")
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  var nodes = [];
  while (walker.nextNode()) { nodes.push(walker.currentNode); }
  var marks = [];
  nodes.forEach(function (node) {
    var text = node.nodeValue, normed = "", map = [];
    for (var i = 0; i < text.length; i++) {
      var c = norm(text[i]);
      for (var k = 0; k < c.length; k++) { normed += c[k]; map.push(i); }
    }
    var merged = CEVQuery.ranges(normed, words).map(function (r) { return [map[r[0]], map[r[1] - 1] + 1]; });
    if (!merged.length) { return; }
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
    if (el.closest(".tool-use, .tool-result, .thinking, .unknown-block")) { return; }
    if (CEVQuery.formulaHit(norm(el.textContent), terms)) {
      el.classList.add("cev-hit");
      marks.push(el);
    }
  });
  marks.sort(function (a, b) { return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1; });

  var bar = document.createElement("div");
  bar.className = "hit-bar";
  bar.innerHTML = '<span class="hit-words"></span> <span class="hit-pos"></span>' +
    '<button type="button" data-step="-1"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M18 15l-6-6-6 6"/></svg></button>' +
    '<button type="button" data-step="1"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>' +
    '<button type="button" data-step="0"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>';
  bar.querySelector(".hit-words").textContent = "« " + q + " »";
  [["-1", "web.hits.prev"], ["1", "web.hits.next"], ["0", "web.hits.close"]].forEach(function (b) {
    var el = bar.querySelector('[data-step="' + b[0] + '"]');
    el.setAttribute("data-i18n-attr", "title:" + b[1]);
    el.title = CEV.t(b[1]);
  });
  document.body.appendChild(bar);
  var pos = bar.querySelector(".hit-pos");
  var current = -1;

  function reveal(mark) {
    // a hidden answer (fold.js): show it with its own button; a closed frame: open it.
    // True when the page changed.
    var changed = false;
    var top = mark.closest(".messages > *");
    if (top && top.classList.contains("cev-folded")) {
      var q = top.previousElementSibling;
      while (q && !q.classList.contains("message-human")) { q = q.previousElementSibling; }
      var b = q && q.querySelector(".fold-one");
      if (b) { b.click(); changed = true; }
    }
    for (var d = mark.parentNode.closest("details"); d; d = d.parentNode.closest("details")) {
      if (!d.open) { d.open = true; changed = true; }
    }
    return changed;
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
    var id = ++aiming, start = Date.now(), settled = 0;
    (function frame() {
      if (id !== aiming || Date.now() - start > 8000) { return; }
      var r = mark.getBoundingClientRect();
      var max = document.documentElement.scrollHeight - window.innerHeight;
      var target = Math.max(0, Math.min(max, window.scrollY + r.top + r.height / 2 - window.innerHeight / 2));
      var gap = target - window.scrollY;
      if (Math.abs(gap) < 1) {
        if (++settled > 10) { return; }  // stayed in place for 10 frames: arrived
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
    if (!marks.length) { pos.setAttribute("data-i18n", "web.hits.none"); pos.textContent = CEV.t("web.hits.none"); return; }
    if (current >= 0) { marks[current].classList.remove("current"); }
    current = (i + marks.length) % marks.length;
    var mark = marks[current];
    reveal(mark);
    mark.classList.add("current");
    scrollTo(mark);
    pos.removeAttribute("data-i18n");
    pos.textContent = (current + 1) + " / " + marks.length;
  }

  bar.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) { return; }
    var step = +b.getAttribute("data-step");
    if (step) { show(current + step); return; }
    marks.forEach(function (m) {
      if (m.tagName === "MARK") { m.replaceWith(document.createTextNode(m.textContent)); }
      else { m.classList.remove("cev-hit", "current"); }  // a formula
    });
    root.normalize();
    bar.remove();
    history.replaceState(null, "", location.pathname);  // a reload no longer highlights
  });
  setTimeout(function () { show(0); }, 300);  // after the fonts and the formulas
})();
