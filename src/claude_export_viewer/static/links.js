/* Links between conversations (annotations.py, "links"): both ways, never transitive.
 * Index: a conversation dragged (button held) onto another one links them (local server only);
 *   while dragging, the page scrolls by itself near its top and bottom edges; the icon and the
 *   number of links in the line of information, a click on it removes them all (after "Oui").
 * Conversation page: the frame "Liens (n)" between the export buttons and the favorites: the
 *   linked conversations in the order of their dates, a click opens one, the small cross removes
 *   that link (local server only).
 * AE-m3 (16/11), suites: a suite is a link with a direction (annotations "series": the conversations of one suite,
 *   read in the order of their dates; one suite at most for a conversation). Page: in "Liens", a link dragged onto
 *   another one makes the two and this conversation a suite (drawn in a frame, numbered, the icon "series"); one
 *   dragged out of the frame, or its cross, leaves the suite and stays a link; the line "Suite : fil k sur n · ←
 *   previous · next →" above the messages and below them. The index is unchanged (16/11, the user's choice: the
 *   links are made there, the suites on the pages). */
(function () {
  "use strict";
  var A = CEV.annot;
  var LINK = CEV.icon("link", 13, "link-icon");
  function links() { return A.data().links || {}; }
  var SERIES = CEV.icon("series", 15, "series-icon");
  function seriesOf(u) {
    var all = A.data().series || [];
    for (var i = 0; i < all.length; i++) { if (all[i].indexOf(u) >= 0) { return all[i]; } }
    return null;
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  // --- Index ---------------------------------------------------------------------------
  var items = Array.prototype.slice.call(document.querySelectorAll(".conversation-item[data-uuid]"));
  if (items.length) {
    var paintCounts = function () {
      var all = links();
      items.forEach(function (item) {
        var uuid = item.getAttribute("data-uuid");
        A.count(item, "link-count", LINK, (all[uuid] || []).length, "web.links.count_title", "web.links.clear_title",
          "web.links.clear_ask", { action: "clear_links", conversation: uuid });
      });
    };
    paintCounts();
    document.addEventListener("cev-annotations", paintCounts);


    A.ready(function (served) {
      if (!served) { return; }
      var TYPE = "application/x-cev-conversation";
      var source = null, target = null, edgeY = -1, rolling = false, dropped = false, lastOver = 0;
      var itemOf = function (e) { return e.target.closest ? e.target.closest(".conversation-item[data-uuid]") : null; };
      var mark = function (item) {
        if (target === item) { return; }
        if (target) { target.classList.remove("link-target"); }
        target = item;
        if (target) { target.classList.add("link-target"); }
      };
      // our own scrolling near the edges (the browser's zone is too thin): faster closer to the edge
      var roll = function () {
        if (!source) { rolling = false; return; }
        var zone = Math.max(60, window.innerHeight * 0.15), speed = 0;
        if (edgeY >= 0 && edgeY < zone) { speed = -Math.ceil(18 * (zone - edgeY) / zone); }
        else if (edgeY > window.innerHeight - zone) { speed = Math.ceil(18 * (edgeY - (window.innerHeight - zone)) / zone); }
        if (speed) { window.scrollBy(0, speed); }
        requestAnimationFrame(roll);
      };
      document.addEventListener("dragstart", function (e) {
        var item = itemOf(e);
        if (!item) { return; }
        source = item;
        item.classList.add("link-source");
        e.dataTransfer.setData(TYPE, item.getAttribute("data-uuid"));
        // "copy": the action "link" is refused by the drag and drop of some systems (Linux)
        e.dataTransfer.effectAllowed = "copy";
        dropped = false;
        if (!rolling) { rolling = true; requestAnimationFrame(roll); }
      });
      document.addEventListener("dragover", function (e) {
        if (!source) { return; }
        edgeY = e.clientY;
        var item = itemOf(e);
        if (item && item !== source) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
          mark(item);
          lastOver = Date.now();
        } else { mark(null); }
      });
      document.addEventListener("drop", function (e) {
        if (!source) { return; }
        var item = itemOf(e);
        if (item && item !== source) {
          e.preventDefault();
          dropped = true;
          A.post({ action: "link", a: source.getAttribute("data-uuid"), b: item.getAttribute("data-uuid") }).catch(A.failed);
        }
      });
      document.addEventListener("dragend", function () {
        // released over the dashed conversation but no "drop" received (some browsers and systems):
        // linked all the same; only just after a "dragover" on it (not released outside the window)
        if (source && target && !dropped && Date.now() - lastOver < 400) {
          A.post({ action: "link", a: source.getAttribute("data-uuid"), b: target.getAttribute("data-uuid") }).catch(A.failed);
        }
        if (source) { source.classList.remove("link-source"); }
        mark(null);
        source = null;
        edgeY = -1;
      });
    });
    return;
  }

  // --- Conversation page ----------------------------------------------------------------
  var box = document.getElementById("link-list");
  var root = document.querySelector(".messages[data-conversation]");
  if (!box || !root) { return; }
  var conv = root.getAttribute("data-conversation");
  var list = box.querySelector(".link-items");
  var served = false;
  function item(u, c, cls, extra) {
    return '<li class="fav-item' + cls + '" data-other="' + esc(u) + '"' + (served ? ' data-drag="1"' : "") + ">" + extra +
      '<a href="' + esc(encodeURIComponent(c[1])) + '" draggable="false">' +
      (c[2] ? '<time data-fmt="date" datetime="' + esc(c[2]) + '"></time> ' : "") +
      '<span class="fav-excerpt">' + (c[0] ? esc(c[0]) : '<span data-i18n="web.untitled"></span>') + "</span></a>" +
      (served ? '<button type="button" class="fav-remove" data-i18n-attr="title:' +
        (cls.indexOf("series-item") >= 0 ? "web.series.leave" : "web.links.remove") + '">' + CEV.icon("cross", 12) + "</button>" : "") +
      "</li>";
  }
  function byDate(convs) { return function (a, b) { return (convs[a][2] || "").localeCompare(convs[b][2] || ""); }; }
  function suite(convs) {  // this conversation's suite in its order (18/11: the order set by the user), or null
    var g = seriesOf(conv);
    g = g ? g.filter(function (u) { return convs[u]; }) : null;
    return g && g.length > 1 && g.indexOf(conv) >= 0 ? g : null;
  }
  function here(convs, num) {  // the row of this conversation: no link, no cross
    return '<li class="fav-item series-here' + (num ? " series-item" : "") + '" data-other="' + esc(conv) + '"' +
      (served ? ' data-drag="1"' : "") + ">" + (num || '<span class="series-spacer"></span>') +
      '<time data-fmt="date" datetime="' + esc(convs[conv][2] || "") + '"></time> <span class="fav-excerpt">' +
      esc(convs[conv][0] || "") + ' — <span data-i18n="web.series.here"></span></span></li>';
  }
  function paint() {
    var convs = A.data().convs || {};
    var g = suite(convs);
    var mine = (links()[conv] || []).filter(function (u) { return convs[u] && !(g && g.indexOf(u) >= 0); });
    mine.sort(byDate(convs));
    // "Liens (n)": the links only, as on the index (16/11); a conversation of the suite not linked is shown, not counted
    var n = (links()[conv] || []).filter(function (u) { return convs[u]; }).length, shown = mine.length + (g ? g.length - 1 : 0);
    box.classList.toggle("has-links", shown > 0);
    var label = box.querySelector(".fav-label [data-i18n]");
    label.setAttribute("data-i18n-args", JSON.stringify({ n: n }));
    var html = g ? '<li class="series-box" data-i18n-attr="title:web.series.frame_title"><div class="series-head">' + SERIES +
      ' <span data-i18n="web.series.frame"></span></div><ol class="series-items">' + g.map(function (u, i) {
        var num = '<span class="series-num">' + (i + 1) + "</span>" + SERIES;
        return u === conv ? here(convs, num) : item(u, convs[u], " series-item", num);
      }).join("") + "</ol></li>" : "";
    // 17/11: not yet in a suite, with a link at least: this conversation among the links (by date, no cross)
    var rows = mine.slice();
    if (served && !g && mine.length && convs[conv]) { rows.push(conv); rows.sort(byDate(convs)); }
    html += rows.map(function (u) { return u === conv ? here(convs) : item(u, convs[u], "", LINK); }).join("");
    if (served && mine.length) { html += '<li class="fav-none series-hint" data-i18n="web.series.hint"></li>'; }
    list.innerHTML = html || '<li class="fav-none link-none" data-i18n="web.links.none"></li>';
    picker(convs);
    CEV.apply(box);
    paintLines(convs, g);
  }
  // (22/11) a link made from the page too, by a list of the other conversations (before: only by dragging one
  // onto another in the index); local server only
  function picker(convs) {
    var old = box.querySelector(".link-pick");
    if (old) { old.remove(); }
    if (!served) { return; }
    var linked = links()[conv] || [];
    var others = Object.keys(convs).filter(function (u) { return u !== conv && linked.indexOf(u) < 0; });
    if (!others.length) { return; }
    others.sort(function (a, b) { return (convs[b][2] || "").localeCompare(convs[a][2] || ""); });  // the latest first
    var sel = document.createElement("select");
    sel.className = "link-pick";
    sel.innerHTML = '<option value="" data-i18n="web.links.pick"></option>' + others.map(function (u) {
      var day = (convs[u][2] || "").slice(0, 10);
      return '<option value="' + esc(u) + '">' + (day ? esc(day) + " · " : "") + esc(convs[u][0] || CEV.t("web.untitled")) + "</option>";
    }).join("");
    sel.addEventListener("change", function () {
      if (!sel.value) { return; }
      A.post({ action: "link", a: conv, b: sel.value }).catch(A.failed);
    });
    list.parentNode.insertBefore(sel, list.nextSibling);
  }
  // "Suite : fil k sur n · ← previous … next →" above the messages and below them
  function paintLines(convs, g) {
    document.querySelectorAll(".series-line").forEach(function (l) { l.remove(); });
    if (!g) { return; }
    var k = g.indexOf(conv), prev = g[k - 1], next = g[k + 1];
    var line = function (bottom) {
      var d = document.createElement("div");
      d.className = "series-line";
      d.innerHTML = SERIES + ' <span class="series-pos">' + esc(CEV.t("web.series.line", { k: k + 1, n: g.length })) + "</span>" +
        (prev ? '<a class="series-prev" href="' + esc(encodeURIComponent(convs[prev][1])) + '" title="' + esc(CEV.t("web.series.prev")) +
          '">← ' + esc(convs[prev][0] || CEV.t("web.untitled")) + "</a>" : "") + '<span class="series-gap"></span>' +
        (next ? '<a class="series-next" href="' + esc(encodeURIComponent(convs[next][1])) + '" title="' + esc(CEV.t("web.series.next")) +
          '">' + (bottom ? esc(CEV.t("web.series.next_label")) + " " : "") + esc(convs[next][0] || CEV.t("web.untitled")) + " →</a>" : "");
      return d;
    };
    var tabs = document.querySelector(".fav-tabs");
    if (tabs) { tabs.after(line(false)); }
    root.after(line(true));
  }
  paint();
  A.ready(function (s) { served = s; paint(); });
  document.addEventListener("cev-annotations", paint);
  document.addEventListener("cev-language", function () { paintLines(A.data().convs || {}, suite(A.data().convs || {})); });
  list.addEventListener("click", function (e) {
    var b = e.target.closest(".fav-remove");
    if (!b) { return; }
    e.preventDefault();
    b.disabled = true;
    var li = b.closest("li"), other = li.getAttribute("data-other");
    A.post(li.classList.contains("series-item") ? { action: "series_set", here: conv, order: order(li) }
      : { action: "unlink", a: conv, b: other }).catch(function (err) {
      b.disabled = false;
      A.failed(err);
    });
  });

  // --- Dragging in "Liens" (local server only; 18/11): the usual sortable list — while a row moves, an empty
  // place opens where it would go and follows the mouse; let go, the row takes it. In the suite: a new order (one
  // row out of the frame: out of the suite, it stays a link). Not yet a suite: a row let go next to another one
  // (or "ce fil") makes the suite of the two and this conversation, in the order shown. A conversation of another
  // suite moved here leaves it, after Oui / Non.
  function order(without) {  // the uuids of the suite as the frame shows them (without a row, the gap in place)
    return Array.prototype.map.call(list.querySelectorAll(".series-items > li"), function (x) {
      return x === without ? null : x.getAttribute("data-other");
    }).filter(Boolean);
  }
  var drag = null;  // {li, gap (the empty place), ghost, x0, y0, dx, dy, on, over}
  var swallow = false;
  list.addEventListener("click", function (e) {
    if (swallow) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  function rowsOf(zone) {
    return Array.prototype.filter.call(zone.children, function (x) {
      return x !== drag.li && x !== drag.gap && x.matches("li.fav-item[data-other]");
    });
  }
  function placeGap(zone, y) {  // the gap before the first row whose middle is below the mouse
    var rows = rowsOf(zone), at = null, over = null;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i].getBoundingClientRect();
      if (y >= r.top && y <= r.bottom) { over = rows[i]; }
      if (y < r.top + r.height / 2) { at = rows[i]; break; }
    }
    if (!over && rows.length) {  // between two rows: the nearest one
      var near = rows.reduce(function (best, x) {
        var r = x.getBoundingClientRect(), d = Math.min(Math.abs(y - r.top), Math.abs(y - r.bottom));
        return !best || d < best.d ? { x: x, d: d } : best;
      }, null);
      over = near && near.x;
    }
    var hint = zone.querySelector(":scope > .series-hint");
    zone.insertBefore(drag.gap, at || hint || null);
    drag.gap.hidden = false;
    drag.over = over;
  }
  function zoneAt(x, y) {  // where the gap goes: the frame of the suite, or (no suite) the list itself
    var frame = list.querySelector(".series-box");
    if (frame) {
      var r = frame.getBoundingClientRect();
      return x >= r.left - 8 && x <= r.right + 8 && y >= r.top - 8 && y <= r.bottom + 8 ? frame.querySelector(".series-items") : null;
    }
    var l = list.getBoundingClientRect();
    return x >= l.left && x <= l.right && y >= l.top && y <= l.bottom ? list : null;
  }
  list.addEventListener("pointerdown", function (e) {
    var li = e.target.closest && e.target.closest("li[data-drag]");
    if (!served || !li || e.button !== 0 || e.target.closest(".fav-remove")) { return; }
    var r = li.getBoundingClientRect();
    drag = { li: li, x0: e.clientX, y0: e.clientY, dx: e.clientX - r.left, dy: e.clientY - r.top, on: false };
  });
  window.addEventListener("pointermove", function (e) {
    if (!drag) { return; }
    if (!drag.on) {
      if (Math.abs(e.clientX - drag.x0) + Math.abs(e.clientY - drag.y0) < 6) { return; }
      drag.on = true;
      var r = drag.li.getBoundingClientRect();
      drag.ghost = drag.li.cloneNode(true);
      drag.ghost.className += " series-ghost";
      drag.ghost.style.width = r.width + "px";
      document.body.appendChild(drag.ghost);
      drag.gap = document.createElement("li");
      drag.gap.className = "series-slot";
      drag.gap.style.height = r.height + "px";
      drag.li.classList.add("series-lifted");
      drag.li.after(drag.gap);
      document.documentElement.classList.add("series-dragging");
    }
    e.preventDefault();
    drag.ghost.style.left = (e.clientX - drag.dx) + "px";
    drag.ghost.style.top = (e.clientY - drag.dy) + "px";
    var zone = zoneAt(e.clientX, e.clientY);
    drag.zone = zone;
    if (zone) { placeGap(zone, e.clientY); } else { drag.gap.hidden = true; drag.over = null; }
    drag.ghost.classList.toggle("series-out", !zone && drag.li.classList.contains("series-item"));
  });
  function stop() {
    if (!drag) { return; }
    if (drag.ghost) { drag.ghost.remove(); }
    if (drag.gap) { drag.gap.remove(); }
    drag.li.classList.remove("series-lifted");
    document.documentElement.classList.remove("series-dragging");
    drag = null;
  }
  window.addEventListener("keydown", function (e) { if (e.key === "Escape" && drag && drag.on) { stop(); paint(); } });
  window.addEventListener("pointerup", function () {
    if (!drag) { return; }
    var d = drag, moved = d.li.getAttribute("data-other"), next = null;
    if (!d.on) { drag = null; return; }  // a click: the link opens
    if (d.zone && d.zone.classList.contains("series-items")) {  // in the suite: its new order
      next = Array.prototype.map.call(d.zone.children, function (x) {
        return x === d.gap ? moved : x === d.li ? null : x.getAttribute("data-other");
      }).filter(Boolean);
    } else if (!d.zone && d.li.classList.contains("series-item")) {  // out of the frame: out of the suite
      next = order(d.li);
    } else if (d.zone === list && !list.querySelector(".series-box") && d.over) {  // not yet a suite
      var keep = [moved, d.over.getAttribute("data-other"), conv];
      next = Array.prototype.map.call(list.children, function (x) {
        return x === d.gap ? moved : x === d.li ? null : x.getAttribute("data-other");
      }).filter(function (u) { return u && keep.indexOf(u) >= 0; });
    }
    stop();
    swallow = true;  // the click that ends a drag (dispatched with the release) does not open the link
    setTimeout(function () { swallow = false; }, 0);
    if (!next) { paint(); return; }
    var mineNow = seriesOf(conv) || [];
    var others = next.filter(function (u) { var g = seriesOf(u); return g && g.indexOf(conv) < 0 && mineNow.indexOf(u) < 0; });
    var send = function () { A.post({ action: "series_set", here: conv, order: next }).catch(A.failed); };
    if (others.length) { CEV.confirm(CEV.t("web.series.move_ask"), send, paint); } else { send(); }
  });
})();
