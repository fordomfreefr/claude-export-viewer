/* Highlighted passages (annotations.py, "marks"), like a highlighter pen: select a passage with the
 * mouse, then the round button "Surligner" (first frame of buttons, first place): yellow. Select a
 * highlighted passage again and click the same button: the highlighting goes. A selection over
 * several messages makes one passage per message. Text only: formulas and code are skipped.
 * The button is greyed while nothing to highlight is selected (and on a page opened as a file:
 * changes only through the local server). Index: the icon and the number of passages in the line
 * of information, a click on it removes them all (after "Oui").
 * A passage is kept as {s, q[, c]}: its start and its text in "the text of the message", the text of
 * its eligible text nodes put end to end (marks.js only); a text moved since is found again; c = its colour
 * (11/11, the charter: y yellow (default, not written), g green, r red, p pink, c cyan). The colour is chosen
 * with the wheel over the button (a box of 5 squares beside it, the current one ringed; a click on a square
 * chooses it), kept in localStorage cev-hl-color; the button shows it while a text is selected or under the
 * mouse, grey otherwise (class "off", never disabled: the wheel must reach it). Clicking on highlighted
 * passages of the colour chosen removes them; of another colour, gives them that colour. */
(function () {
  "use strict";
  var A = CEV.annot;
  var PEN = '<svg class="mark-icon" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">' +
    '<path d="M15 4l5 5-8 8H7v-5z"/><path d="M4 20h7"/></svg>';
  function marks() { return A.data().marks || {}; }

  // --- Index ---------------------------------------------------------------------------
  var items = Array.prototype.slice.call(document.querySelectorAll(".conversation-item[data-uuid]"));
  if (items.length) {
    var paintCounts = function () {
      var all = marks();
      items.forEach(function (item) {
        var uuid = item.getAttribute("data-uuid"), mine = all[uuid] || {}, n = 0;
        Object.keys(mine).forEach(function (m) { n += mine[m].length; });
        A.count(item, "mark-count", PEN, n, "web.mark.count_title", "web.mark.clear_title", "web.mark.clear_ask",
          { action: "clear_marks", conversation: uuid });
      });
    };
    paintCounts();
    document.addEventListener("cev-annotations", paintCounts);
    return;
  }

  // --- Conversation page ----------------------------------------------------------------
  var root = document.querySelector(".messages[data-conversation]");
  var button = document.querySelector('#page-nav [data-go="mark"]');
  if (!root || !button) { return; }
  var conv = root.getAttribute("data-conversation");
  var served = false;
  var COLORS = ["y", "g", "r", "p", "c"];
  var color = "y";
  try { if (COLORS.indexOf(localStorage.getItem("cev-hl-color")) >= 0) { color = localStorage.getItem("cev-hl-color"); } } catch (e) { /* no storage */ }
  var SKIP = "pre, code, .math, .katex, button, .cev-note, .tool-use, .tool-result, .thinking, .unknown-block, .message-time";

  // the eligible text nodes of a message, and their text end to end
  function textOf(msg) {
    var nodes = [], text = "";
    var walker = document.createTreeWalker(msg, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        var p = n.parentNode;
        return p.closest(".content-text") && !p.closest(SKIP) && p.closest(".message") === msg
          ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    while (walker.nextNode()) {
      nodes.push({ node: walker.currentNode, at: text.length });
      text += walker.currentNode.nodeValue;
    }
    return { nodes: nodes, text: text };
  }

  // where a kept passage is now: at its place, else its nearest copy in the message, else nowhere
  function locate(text, p) {
    if (text.substr(p.s, p.q.length) === p.q) { return p.s; }
    var best = -1, i = text.indexOf(p.q);
    while (i >= 0) {
      if (best < 0 || Math.abs(i - p.s) < Math.abs(best - p.s)) { best = i; }
      i = text.indexOf(p.q, i + 1);
    }
    return best;
  }

  function unwrap(msg) {
    Array.prototype.forEach.call(msg.querySelectorAll("mark.cev-hl"), function (m) {
      var parent = m.parentNode;
      while (m.firstChild) { parent.insertBefore(m.firstChild, m); }
      parent.removeChild(m);
      parent.normalize();
    });
  }

  // White space that only separates blocks (between list items, table cells, paragraphs…): a
  // <mark> there would be a box of its own, an extra line or a broken table. It counts in the text
  // of the message but is never wrapped.
  var CONTAINERS = /^(UL|OL|DL|MENU|TABLE|THEAD|TBODY|TFOOT|TR|COLGROUP)$/;
  function between(node) {
    if (/\S/.test(node.nodeValue)) { return false; }
    if (CONTAINERS.test(node.parentNode.nodeName)) { return true; }
    return [node.previousSibling, node.nextSibling].some(function (s) {
      return s && s.nodeType === 1 && !/^inline/.test(getComputedStyle(s).display);
    });
  }

  function wrap(msg, start, end, c) {
    textOf(msg).nodes.forEach(function (x) {
      var len = x.node.nodeValue.length, a = Math.max(start, x.at), b = Math.min(end, x.at + len);
      if (a >= b || between(x.node)) { return; }
      var node = x.node;
      if (b - x.at < len) { node.splitText(b - x.at); }
      if (a > x.at) { node = node.splitText(a - x.at); }
      var mark = document.createElement("mark");
      mark.className = "cev-hl" + (c && c !== "y" ? " hl-" + c : "");
      node.parentNode.replaceChild(mark, node);
      mark.appendChild(node);
    });
  }

  function paint() {
    var mine = marks()[conv] || {};
    Array.prototype.forEach.call(root.querySelectorAll(".message[data-uuid]"), function (msg) {
      if (msg.querySelector("mark.cev-hl")) { unwrap(msg); }
      (mine[msg.getAttribute("data-uuid")] || []).forEach(function (p) {
        var at = locate(textOf(msg).text, p);
        if (at >= 0) { wrap(msg, at, at + p.q.length, p.c); }
      });
    });
  }

  // the passages of the selection, one per message: {message, s, q, msg}
  function selected() {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { return []; }
    var range = sel.getRangeAt(0), out = [];
    Array.prototype.forEach.call(root.querySelectorAll(".message[data-uuid]"), function (msg) {
      if (!range.intersectsNode(msg)) { return; }
      var t = textOf(msg), start = -1, end = -1;
      t.nodes.forEach(function (x) {
        var len = x.node.nodeValue.length;
        var before = range.comparePoint(x.node, 0), after = range.comparePoint(x.node, len);
        if (before === 1 || after === -1) { return; }  // all after or all before the selection
        var s = before === -1 && range.startContainer === x.node ? range.startOffset : 0;
        var e = after === 1 && range.endContainer === x.node ? range.endOffset : len;
        if (e <= s) { return; }
        if (start < 0) { start = x.at + s; }
        end = x.at + e;
      });
      if (start < 0) { return; }
      while (start < end && /\s/.test(t.text[start])) { start++; }
      while (end > start && /\s/.test(t.text[end - 1])) { end--; }
      if (end > start) { out.push({ message: msg.getAttribute("data-uuid"), s: start, q: t.text.slice(start, end), msg: msg }); }
    });
    return out;
  }

  // the highlighted passages a selection touches
  function touched(passages) {
    var mine = marks()[conv] || {}, out = [];
    passages.forEach(function (p) {
      var text = textOf(p.msg).text;
      (mine[p.message] || []).forEach(function (k) {
        var at = locate(text, k);
        if (at >= 0 && at < p.s + p.q.length && p.s < at + k.q.length) { out.push({ message: p.message, s: k.s, q: k.q, c: k.c || "y", at: at }); }
      });
    });
    return out;
  }

  // (22/11) the same pen beside the end of the selection: the round button is far, at the bottom right
  var near = document.createElement("button");
  near.type = "button";
  near.className = "hl-near";
  near.hidden = true;
  near.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path class="mark-tip" d="M15 4l5 5-8 8H7v-5z"/><path d="M4 20h8"/></svg>';
  near.setAttribute("data-i18n-attr", "title:web.mark.button");
  near.title = CEV.t("web.mark.button");
  near.addEventListener("mousedown", function (e) { e.preventDefault(); });  // keeps the selection
  near.addEventListener("click", function () { button.click(); });
  document.body.appendChild(near);
  function placeNear(ok) {
    var sel = window.getSelection(), rects = ok && sel.rangeCount ? sel.getRangeAt(sel.rangeCount - 1).getClientRects() : [];
    near.hidden = !rects.length;
    if (!rects.length) { return; }
    var r = rects[rects.length - 1];
    near.style.left = Math.round(Math.min(window.scrollX + r.right + 4, window.scrollX + document.documentElement.clientWidth - 34)) + "px";
    near.style.top = Math.round(window.scrollY + r.bottom + 2) + "px";
    near.style.setProperty("--hl", "var(--hl-" + color + ")");
  }

  function state() {
    var ok = served && selected().length > 0;
    placeNear(ok);
    button.classList.toggle("off", !ok);
    button.setAttribute("aria-disabled", ok ? "false" : "true");
    button.style.setProperty("--hl", "var(--hl-" + color + ")");
    var key = !served ? "web.mark.readonly" : "web.mark.button";
    if (button.getAttribute("data-i18n-attr") !== "title:" + key) {
      button.setAttribute("data-i18n-attr", "title:" + key);
      button.title = CEV.t(key);
    }
  }

  // --- the colour: wheel over the button, a box of squares beside it ----------------------
  var nav = button.closest("#page-nav") || document.body;
  var box = document.createElement("span");
  box.className = "nav-speed nav-hl-box";
  box.hidden = true;
  COLORS.forEach(function (c) {
    var sq = document.createElement("button");
    sq.type = "button";
    sq.className = "hl-sq nav-keep";
    sq.setAttribute("data-c", c);
    sq.style.background = "var(--hl-" + c + ")";
    sq.title = CEV.t("web.mark.color_" + c);
    sq.addEventListener("mousedown", function (e) { e.preventDefault(); });  // keeps the selection
    sq.addEventListener("click", function () { choose(c); });
    box.appendChild(sq);
  });
  nav.appendChild(box);
  var hideTimer = null;
  function showBox() {
    box.hidden = false;
    Array.prototype.forEach.call(box.children, function (sq) { sq.classList.toggle("on", sq.getAttribute("data-c") === color); });
    var n = nav.getBoundingClientRect(), r = button.getBoundingClientRect();
    box.style.top = Math.round(r.top - n.top + (r.height - box.offsetHeight) / 2) + "px";
    box.style.right = Math.round(n.right - r.left + 6) + "px";
    clearTimeout(hideTimer);
  }
  function hideSoon() { clearTimeout(hideTimer); hideTimer = setTimeout(function () { box.hidden = true; }, 400); }
  function choose(c) {
    color = c;
    try { localStorage.setItem("cev-hl-color", c); } catch (e) { /* no storage */ }
    state();
    if (!box.hidden) { showBox(); }
  }
  button.addEventListener("wheel", function (e) {
    e.preventDefault();
    var k = COLORS.indexOf(color) + (e.deltaY < 0 ? 1 : -1);
    choose(COLORS[Math.max(0, Math.min(COLORS.length - 1, k))]);
    showBox();
  }, { passive: false });
  [button, box].forEach(function (el) {
    el.addEventListener("mouseenter", function () { if (!box.hidden) { clearTimeout(hideTimer); } });
    el.addEventListener("mouseleave", hideSoon);
  });

  button.addEventListener("mousedown", function (e) { e.preventDefault(); });  // keeps the selection
  button.addEventListener("click", function () {
    var passages = selected();
    if (!served || !passages.length) { return; }
    var hit = touched(passages), body;
    if (hit.length && hit.every(function (k) { return k.c === color; })) {
      body = { action: "unmark", conversation: conv, passages: hit.map(function (k) { return { message: k.message, s: k.s, q: k.q }; }) };
    } else {
      // the passages touched take the colour; the selection too, unless it lies inside one of them
      var inside = function (p) {
        return hit.some(function (k) { return k.message === p.message && k.at <= p.s && p.s + p.q.length <= k.at + k.q.length; });
      };
      var add = hit.map(function (k) { return { message: k.message, s: k.s, q: k.q, c: color }; })
        .concat(passages.filter(function (p) { return !inside(p); }).map(function (p) { return { message: p.message, s: p.s, q: p.q, c: color }; }));
      body = { action: "mark", conversation: conv, passages: add,
               replace: hit.map(function (k) { return { message: k.message, s: k.s, q: k.q }; }) };
    }
    button.classList.add("off");
    near.hidden = true;
    A.post(body).then(function () {
      window.getSelection().removeAllRanges();
      paint();
      state();
    }, function (err) { state(); A.failed(err); });
  });
  var timer = null;
  document.addEventListener("selectionchange", function () { clearTimeout(timer); timer = setTimeout(state, 120); });
  paint();
  state();
  A.ready(function (s) { served = s; state(); });
  window.addEventListener("load", paint);  // the fonts and the formulas drawn: same text, found again
})();
