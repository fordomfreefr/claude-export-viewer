/* The bar above the messages of a conversation (plan.css) and what the reading view keeps of the plan view,
 * removed on 17/11 (the user's choice, Structure preferred; AE-c1):
 * - the switch "Vue : Lecture · Structure" (Structure: structure.js);
 * - "Lignes : 1 · 3 · 5 · Tout": the bubbles cut at N lines (only their text: thinking, resources, code, files
 *   are seen once opened or with "Tout"; from 2 lines the last line fades), the icons of what a cut bubble
 *   holds after its date (a click opens it) and the arrow that opens it or cuts it again;
 * - the titles of the bubbles (annotation "titles", one line, icon "T") and the frame "Titres (n)".
 * Settings kept by the browser (localStorage cev-view, cev-read-lines), set on <html> before drawing (head of
 * the page); a view "plan" kept from before opens the reading. */
(function () {
  "use strict";
  var root = document.querySelector(".messages[data-conversation]");
  var bar = document.getElementById("plan-bar");
  if (!root || !bar) { return; }
  var html = document.documentElement, conv = root.getAttribute("data-conversation");
  var A = window.CEV && CEV.annot, served = false;
  var ENTRY = ".message-human[data-uuid], .message-assistant[data-uuid]";
  function svg(cls, w, paths) {
    return '<svg class="' + cls + '" viewBox="0 0 24 24" width="' + w + '" height="' + w + '" aria-hidden="true">' + paths + "</svg>";
  }
  var TITLE = CEV.icon("title", 13, "title-icon"), ARROW = CEV.icon("fold", 15, "fold-icon");
  // what a bubble holds: [icon, text of the tooltip, counted]
  var HOLDS = {
    attach: [svg("", 13, '<path d="M21 12l-8.5 8.5a5 5 0 0 1-7-7L14 5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L15.5 8"/>'), "web.plan.icon_attach", true],
    files: [svg("", 13, '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'), "web.plan.icon_files", true],
    run: [svg("", 13, '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M10 9l5 3-5 3z"/>'), "web.plan.icon_run", true],
    cut: [svg("", 13, '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>'), "web.plan.icon_cut", false]
  };

  function put(key, v) { try { localStorage.setItem(key, v); } catch (e) { /* no storage */ } }
  function el(tag, cls) { var e = document.createElement(tag); e.className = cls; return e; }
  function entries() { return Array.prototype.slice.call(root.querySelectorAll(ENTRY)); }
  function shownView() { return html.classList.contains("cev-structure") ? "structure" : "reading"; }
  // "Lignes : 1 · 3 · 5 · Tout": the reading (and the bubbles shown by the structure)
  function lines() { return html.getAttribute("data-read-lines") || "all"; }
  function readCut() { html.classList.toggle("cev-read-cut", lines() !== "all"); }  // plan.css
  function bubble(m) { return m.querySelector(":scope > .message-bubble"); }

  // --- What a bubble holds, as icons ------------------------------------------------------------------------
  function holds(m) {
    var b = bubble(m);
    if (!b) { return {}; }
    return {
      attach: b.querySelectorAll(":scope > .attachment, :scope > .files:not(.created-files) > *").length,
      files: b.querySelectorAll(":scope > .created-files > *").length + b.querySelectorAll(".artifact:not(.cev-runnable)").length,
      run: b.querySelectorAll(".cev-runnable").length,
      cut: m.classList.contains("cev-cut") ? 1 : 0
    };
  }
  function icons(counts, cls) {
    var box = el("span", cls);
    Object.keys(HOLDS).forEach(function (k) {
      var n = counts[k];
      if (!n) { return; }
      var ic = el("span", "plan-ic");
      ic.innerHTML = HOLDS[k][0] + (HOLDS[k][2] && n > 1 ? "<b>" + n + "</b>" : "");
      ic.title = CEV.t(HOLDS[k][1], { n: n });
      box.appendChild(ic);
    });
    return box;
  }

  // --- Entries: icons, arrow, title -------------------------------------------------------------------------
  function titles() { return ((A ? A.data() : window.CEV_ANNOTATIONS || {}).titles || {})[conv] || {}; }

  function prepare(msg) {
    var b = bubble(msg), time = msg.querySelector(":scope > .message-time");
    if (!b || !time) { return; }
    var text = b.querySelector(".content-text");
    if (!text || !text.textContent.trim()) { msg.classList.add("plan-notext"); }
    // plan-more: what the cut hides beside the text (thinking, files, code…), whatever the length of the text
    msg.classList.toggle("plan-more", Boolean(b.querySelector(":scope > :not(.content-text):not(.cut-note)") ||
      (text && text.querySelector(".code-block, pre, table, img, .katex-display, .cev-runnable, hr"))));
    msg._holds = holds(msg);
    var date = time.querySelector(":scope > time");  // after the date (in the plan: on the left of the row)
    time.insertBefore(icons(msg._holds, "plan-only plan-icons"), date ? date.nextSibling : time.firstChild);
    var dn = el("button", "plan-only plan-dn");
    dn.type = "button";
    dn.innerHTML = ARROW;
    time.appendChild(dn);
  }

  // the title icon, in every view (after the star; the note icon of notes.js comes between them)
  function titleButton(msg) {
    var time = msg.querySelector(":scope > .message-time");
    if (!time || time.querySelector(".plan-add-title")) { return; }
    var t = el("button", "plan-add-title");
    t.type = "button";
    t.hidden = true;
    // 14/11: always there, coloured when the bubble has a title (as the note icon); while its title is written,
    // its click saves (so the field must not lose the focus first)
    t.addEventListener("mousedown", function (e) { if (writingTitle === msg) { e.preventDefault(); } });
    t.innerHTML = TITLE;
    t.setAttribute("data-i18n-attr", "title:web.title.add");
    t.title = CEV.t("web.title.add");
    var after = time.querySelector(".note-btn") || time.querySelector(".fav-star");  // star, note, T (11/11)
    time.insertBefore(t, after ? after.nextSibling : null);
  }

  function clamped(msg) { return (lines() !== "all") !== msg.classList.contains("plan-flip"); }
  function arrow(msg) {  // down when the bubble is cut, up when it is whole
    var dn = msg.querySelector(".plan-dn");
    if (!dn) { return; }
    var key = clamped(msg) ? "web.plan.open" : "web.plan.close";
    dn.classList.toggle("open", !clamped(msg));
    dn.setAttribute("data-i18n-attr", "title:" + key);
    dn.title = CEV.t(key);
  }
  function flip(msg, open) {
    if (open !== undefined && open === !clamped(msg)) { return; }
    msg.classList.toggle("plan-flip");
    arrow(msg);
    soon();
  }

  function showTitle(msg, text) {
    var box = msg.querySelector(":scope > .cev-title");
    if (!text) { if (box) { box.remove(); } return; }
    if (!box) {
      box = el("div", "cev-title");
      msg.insertBefore(box, msg.firstChild);
    }
    box.textContent = "";
    var s = el("span", "plan-title-text");
    s.textContent = text;
    box.appendChild(s);
    box.classList.toggle("editable", served);
    if (served) { s.setAttribute("data-i18n-attr", "title:web.title.edit"); s.title = CEV.t("web.title.edit"); }
  }

  var writingTitle = null, finishTitle = null;  // the entry whose title is written, and its "save"
  function editTitle(msg) {  // Enter or leaving the field: saved; Escape: cancelled; empty: removed
    var id = msg.getAttribute("data-uuid"), old = (titles()[id] || {}).text || "";
    var box = msg.querySelector(":scope > .cev-title");
    if (!box) { box = el("div", "cev-title"); msg.insertBefore(box, msg.firstChild); }
    box.classList.remove("editable");
    box.textContent = "";
    var input = el("input", "cev-title-edit");
    input.type = "text";
    input.value = old;
    input.placeholder = CEV.t("web.title.placeholder");
    box.appendChild(input);
    input.focus();
    var done = false;
    var stop = function () { done = true; if (writingTitle === msg) { writingTitle = finishTitle = null; } };
    var cancel = function () { if (done) { return; } stop(); showTitle(msg, old); paint(); };
    var save = function () {
      if (done) { return; }
      var text = input.value.replace(/\s+/g, " ").trim();
      if (text === old) { cancel(); return; }
      stop();
      input.disabled = true;
      A.post({ action: "title", conversation: conv, message: id, text: text }).then(function () {
        showTitle(msg, text);
        paint();
      }, function (err) { showTitle(msg, old); paint(); A.failed(err); });
    };
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); cancel(); }
      else if (e.key === "Enter") { e.preventDefault(); save(); }
    });
    input.addEventListener("blur", save);
    writingTitle = msg;
    finishTitle = save;
    paint();
  }

  function paint() {  // the titles, the title icon (coloured where there is one)
    var t = titles();
    entries().forEach(function (msg) {
      var id = msg.getAttribute("data-uuid"), box = msg.querySelector(":scope > .cev-title");
      var writing = Boolean(box && box.querySelector("input"));
      if (!writing) { showTitle(msg, (t[id] || {}).text || ""); }
      var b = msg.querySelector(".plan-add-title");
      if (b) {
        var has = Boolean(t[id]), key = !served ? "web.title.readonly" : has ? "web.title.edit" : "web.title.add";
        b.hidden = !served && !has;
        b.classList.toggle("has-title", has);
        b.classList.toggle("readonly", !served);
        b.setAttribute("data-i18n-attr", "title:" + key);
        b.title = CEV.t(key);
      }
    });
    paintList();
    soon();
  }

  // --- The frame "Titres (n)" of the head of the page, as "Notes (n)": the titles in the order of the page ----
  var list = document.getElementById("title-list"), listItems = list && list.querySelector(".title-items");
  var CROSS = CEV.icon("cross", 12);
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  var listed = null;
  function paintList() {
    if (!list) { return; }
    var t = titles(), msgs = entries().filter(function (m) { return t[m.getAttribute("data-uuid")]; });
    var key = JSON.stringify([served, msgs.map(function (m) { var id = m.getAttribute("data-uuid"); return [id, t[id].text]; })]);
    if (key === listed) { return; }
    listed = key;
    list.classList.toggle("has-titles", msgs.length > 0);
    list.querySelector(".fav-label [data-i18n]").setAttribute("data-i18n-args", JSON.stringify({ n: msgs.length }));
    listItems.innerHTML = msgs.length ? msgs.map(function (m) {
      var id = m.getAttribute("data-uuid"), time = m.querySelector(".message-time time");
      var text = t[id].text.replace(/\s+/g, " ");
      return '<li class="fav-item" data-message="' + esc(id) + '"><a href="#msg=' + esc(id) + '">' +
        '<b data-i18n="web.who.' + (m.classList.contains("message-human") ? "human" : "assistant") + '"></b> ' +
        (time ? '<time data-fmt="datetime" datetime="' + esc(time.getAttribute("datetime")) + '"></time> ' : "") +
        '<span class="fav-excerpt">' + esc(text.length > 160 ? text.slice(0, 159) + "…" : text) + "</span></a>" +
        (served ? '<button type="button" class="fav-remove" data-i18n-attr="title:web.title.erase">' + CROSS + "</button>" : "") +
        "</li>";
    }).join("") : '<li class="fav-none title-none" data-i18n="web.title.none"></li>';
    CEV.apply(list);
  }
  if (listItems) {
    listItems.addEventListener("click", function (e) {
      var b = e.target.closest(".fav-remove");
      if (!b) { return; }
      e.preventDefault();
      b.disabled = true;
      A.post({ action: "title", conversation: conv, message: b.closest("li").getAttribute("data-message"), text: "" })
        .then(function () { paint(); }, function (err) { b.disabled = false; A.failed(err); });
    });
  }

  // plan-cut: the text goes beyond what is shown (its last line fades, plan.css)
  function cuts() {
    var list = entries(), cut = list.map(function (m) {
      var b = bubble(m);
      return Boolean(b && clamped(m) && b.scrollHeight > b.scrollTop + b.clientHeight + 2);
    });
    list.forEach(function (m, i) { m.classList.toggle("plan-cut", cut[i]); });
  }
  // --- Everything that depends on the layout, once a change is done -------------------------------------------
  var timer = null;
  function refresh() {
    clearTimeout(timer);
    readCut();
    cuts();  // the reading cut at N lines: the fade
  }
  function soon() { clearTimeout(timer); timer = setTimeout(refresh, 60); }

  // --- Settings -------------------------------------------------------------------------------------------
  var LINES = ["1", "3", "5", "all"];
  function marks() {
    document.querySelectorAll(".plan-view .plan-opt").forEach(function (o) {  // (22/11: out of the bar)
      o.classList.toggle("on", o.getAttribute("data-v") === shownView());
    });
    document.querySelectorAll(".plan-lines .plan-opt").forEach(function (o) { o.classList.toggle("on", o.getAttribute("data-v") === lines()); });
  }
  function anchor() {  // the first entry in sight, to keep it in sight when the view changes
    var top = Math.max(0, bar.getBoundingClientRect().bottom);
    return entries().find(function (m) { var r = m.getBoundingClientRect(); return r.height > 0 && r.bottom > top + 10; }) || null;
  }
  function keep(m) {
    if (!m) { return; }
    var r = m.getBoundingClientRect();
    if (r.height > 0 && (r.top < 0 || r.top > window.innerHeight)) { m.scrollIntoView({ block: "center" }); }
  }

  var VIEWS = ["reading", "structure"];
  function view(v) {  // "reading" or "structure" (structure.js)
    if (VIEWS.indexOf(v) < 0) { v = "reading"; }
    var m = shownView() === "structure" ? null : anchor();
    root.querySelectorAll(".message.plan-flip").forEach(function (x) { x.classList.remove("plan-flip"); });
    html.classList.toggle("cev-structure", v === "structure");
    put("cev-view", v);
    if (v === "structure" && CEV.structure) { CEV.structure.show(); }
    entries().forEach(arrow);
    refresh();
    marks();
    if (v !== "structure") { keep(m); }
  }

  // a click on a name of the switch shows that view; elsewhere on it, the next one
  document.querySelector(".plan-view").addEventListener("click", function (e) {
    var o = e.target.closest(".plan-opt");
    view(o ? o.getAttribute("data-v") : VIEWS[(VIEWS.indexOf(shownView()) + 1) % VIEWS.length]);
  });
  // the charter (11/11): a click on a value chooses it, on the title (or a dot) the next one
  document.querySelector(".plan-lines").addEventListener("click", function (e) {
    var o = e.target.closest(".plan-opt");
    var m = shownView() === "structure" ? null : anchor(), v = o ? o.getAttribute("data-v") : LINES[(LINES.indexOf(lines()) + 1) % LINES.length];
    html.setAttribute("data-read-lines", v);
    put("cev-read-lines", v);
    root.querySelectorAll(".message.plan-flip").forEach(function (x) { x.classList.remove("plan-flip"); });
    entries().forEach(arrow);
    refresh();
    marks();
    keep(m);
  });
  root.addEventListener("click", function (e) {
    var msg = e.target.closest(ENTRY);
    if (!msg) { return; }
    // the title, in every view (through the local server)
    if (e.target.closest(".plan-add-title")) {
      if (!served) { return; }
      if (writingTitle === msg && finishTitle) { finishTitle(); } else { editTitle(msg); }
      return;
    }
    if (served && e.target.closest(".cev-title.editable .plan-title-text") && !(window.getSelection && String(window.getSelection()))) {
      editTitle(msg);
      return;
    }
    if (e.target.closest(".plan-dn")) { flip(msg); return; }
    if (e.target.closest(".plan-icons")) { flip(msg, true); return; }
    // (22/11) a click in a bubble cut at N lines opens it, as the arrow does (not on a link or a button, nor at the
    // end of a selection)
    if (msg.classList.contains("plan-cut") && e.target.closest(".message-bubble") &&
        !e.target.closest("a, button, input, select, textarea, summary, label") &&
        !(window.getSelection && String(window.getSelection()))) { flip(msg, true); }
  });
  // the search of the page (msg.js): the bubble cut at N lines holding the passage found opens
  document.addEventListener("cev-hits", function (e) {
    var current = e.detail.current, c = current && current.closest(ENTRY);
    if (c && clamped(c)) { flip(c, true); }
  });

  function cutting() { return lines() !== "all"; }
  root.addEventListener("toggle", function () { if (cutting()) { soon(); } }, true);  // a branch opened
  window.addEventListener("resize", function () { if (cutting()) { soon(); } });
  window.addEventListener("load", soon);  // fonts, formulas
  if (window.ResizeObserver) { new ResizeObserver(soon).observe(root); }
  document.addEventListener("cev-annotations", paint);

  entries().forEach(titleButton);
  entries().forEach(prepare);
  entries().forEach(arrow);
  paint();
  marks();
  if (shownView() !== "reading") { view(shownView()); }
  if (A) { A.ready(function (s) { served = s; paint(); }); }
})();
