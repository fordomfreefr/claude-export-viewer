/* Notes (annotations.py, "notes"): one per message, yours and Claude's.
 * Page: the small icon after the date of a message adds or changes its note, shown in a yellow
 *   frame under the bubble (right for yours, left for Claude's); a click on the note changes it.
 *   The head of the frame: the icon and "Note", then (while writing, 11/11 the charter) the icons undo, redo,
 *   save, erase, and a thin line under it. The text is written in the colours of the note (no white field);
 *   it is saved by a click elsewhere (focus leaving the note while the window keeps it), Ctrl+Enter, the save
 *   icon or the icon of the note again; Escape cancels; an empty note is removed. Undo / redo (Ctrl+Z,
 *   Ctrl+Shift+Z or Ctrl+Y): the steps of the typing (pauses of 0.6 s). Erasing a note longer than 7 s of
 *   reading (`readSeconds`) asks first. One note is written at a time: opening another one saves the first
 *   (a selection elsewhere leaves it open). The grip in its free corner (the left for yours, the right
 *   for Claude's) widens it up to the width of the column, and makes the text taller while writing;
 *   the width is kept by the browser.
 *   The frame "Notes (n)" at the top of the page lists them: a click goes to the message, the small
 *   cross removes the note. Changed only through the local server; a page opened as a file shows
 *   the notes. The text of the notes is searched like the text of the messages.
 * Index: the icon and the number of notes in the line of information of the conversation; a click
 *   on it removes them all (after "Oui"), like the other icons. */
(function () {
  "use strict";
  var A = CEV.annot;
  var NOTE = CEV.icon("note", 13, "note-icon"), CROSS = CEV.icon("cross", 12);
  function notes() { return A.data().notes || {}; }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  // --- Index ---------------------------------------------------------------------------
  var items = Array.prototype.slice.call(document.querySelectorAll(".conversation-item[data-uuid]"));
  if (items.length) {
    var paintCounts = function () {
      var all = notes();
      items.forEach(function (item) {
        var uuid = item.getAttribute("data-uuid");
        A.count(item, "note-count", NOTE, Object.keys(all[uuid] || {}).length, "web.note.count_title",
          "web.note.clear_title", "web.note.clear_ask", { action: "clear_notes", conversation: uuid });
      });
    };
    paintCounts();
    document.addEventListener("cev-annotations", paintCounts);
    return;
  }

  // --- Conversation page ----------------------------------------------------------------
  var root = document.querySelector(".messages[data-conversation]");
  if (!root) { return; }
  var conv = root.getAttribute("data-conversation");
  var served = false, writing = null, finish = null;  // the note being written, and its "Enregistrer"

  function side(msg) { return msg.classList.contains("message-human") ? "human" : "assistant"; }
  function savedWidth(s) { try { return localStorage.getItem("cev-note-width-" + s) || ""; } catch (e) { return ""; } }

  // The grip in the free corner (the left for yours, the right for Claude's): dragged sideways it
  // changes the width (up to the width of the column), downwards the height of the text while
  // writing; the width is kept for the next notes of that side.
  var GRIP = '<svg viewBox="0 0 18 18" width="18" height="18" aria-hidden="true"><path d="M16 6L6 16M16 10.5l-5.5 5.5M16 15l-1 1"/></svg>';
  function grip(box, msg) {
    var g = document.createElement("span");
    g.className = "cev-note-grip";
    g.innerHTML = GRIP;
    g.setAttribute("data-i18n-attr", "title:web.note.grip");
    g.title = CEV.t("web.note.grip");
    box.appendChild(g);
    g.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var left = side(msg) === "human", x0 = e.clientX, y0 = e.clientY;
      var w0 = box.getBoundingClientRect().width, max = msg.getBoundingClientRect().width - 4;
      var area = box.querySelector("textarea"), h0 = area ? area.getBoundingClientRect().height : 0;
      g.setPointerCapture(e.pointerId);
      var move = function (ev) {
        var dx = ev.clientX - x0;
        box.style.width = Math.round(Math.max(192, Math.min(max, w0 + (left ? -dx : dx)))) + "px";
        if (area) { area.style.height = Math.round(Math.max(48, h0 + ev.clientY - y0)) + "px"; }
      };
      var up = function () {
        g.removeEventListener("pointermove", move);
        g.removeEventListener("pointerup", up);
        g.removeEventListener("pointercancel", up);
        try { localStorage.setItem("cev-note-width-" + side(msg), box.style.width); } catch (err) { /* no storage */ }
      };
      g.addEventListener("pointermove", move);
      g.addEventListener("pointerup", up);
      g.addEventListener("pointercancel", up);
    });
    g.addEventListener("click", function (e) { e.stopPropagation(); });  // not a click on the note
  }

  // the frame of a note: the last child of its message, under the bubble
  function frame(msg) {
    var box = msg.querySelector(":scope > .cev-note");
    if (!box) {
      box = document.createElement("div");
      box.className = "cev-note";
      box.setAttribute("data-for", msg.getAttribute("data-uuid"));
      var w = savedWidth(side(msg));
      if (w) { box.style.width = w; }
      msg.appendChild(box);
    }
    return box;
  }

  var LABEL = '<span class="cev-note-label">' + NOTE + ' <span data-i18n="web.note.label"></span></span>';
  var HEAD = '<div class="cev-note-head">' + LABEL + '</div>';
  function icon(cls, key, path) {
    return '<button type="button" class="cev-note-tool ' + cls + '" data-i18n-attr="title:' + key + '">' +
      '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">' + path + "</svg></button>";
  }
  var TOOLS = icon("cev-note-undo", "web.note.undo", '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>') +
    icon("cev-note-redo", "web.note.redo", '<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>') +
    // (22/11) a tick "finished": the note is saved by itself (a click elsewhere), the floppy disk (14/11) let think that
    // without it nothing was saved
    icon("cev-note-save", "web.note.save", '<path d="M5 12.5l4.5 4.5L19 7"/>');
  var ERASE = icon("cev-note-erase", "web.note.erase", '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>');

  // Seconds to read a text at an adult's usual silent speed (rough figures): words for the languages
  // written with spaces, characters for Chinese and Japanese.
  var WPM = { fr: 200, en: 230, de: 180, es: 215, it: 190, pt: 180, nl: 200, pl: 165, ru: 185, ko: 200 };
  function readSeconds(text) {
    if (/[\u3040-\u30ff]/.test(text)) { return text.replace(/\s/g, "").length / 350 * 60; }
    if (/[\u4e00-\u9fff]/.test(text)) { return text.replace(/\s/g, "").length / 250 * 60; }
    var words = text.split(/\s+/).filter(function (w) { return /[\p{L}\p{N}]/u.test(w); }).length;
    return words / (WPM[CEV.lang ? CEV.lang() : "fr"] || 200) * 60;
  }
  // erase: at once when short, after "Oui" when long
  function askErase(text, go, no) {
    if (readSeconds(text) <= 7) { go(); return; }
    CEV.confirm(CEV.t("web.note.erase_ask"), go, no);
  }

  function show(msg, text) {
    var box = msg.querySelector(":scope > .cev-note");
    if (!text) { if (box) { box.remove(); } return; }
    box = frame(msg);
    box.innerHTML = HEAD + '<div class="content-text plain-text cev-note-text"></div>';
    box.querySelector(".cev-note-text").textContent = text;
    box.classList.toggle("editable", served);
    box.classList.remove("writing");
    grip(box, msg);
    CEV.apply(box);
  }

  function edit(msg) {
    if (finish) { finish(); }  // one note written at a time: the other one is saved
    var id = msg.getAttribute("data-uuid");
    var box = frame(msg);
    var old = ((notes()[conv] || {})[id] || {}).text || "";
    box.classList.remove("editable");
    box.innerHTML = '<div class="cev-note-head">' + LABEL + '<span class="cev-note-tools">' + TOOLS + (old ? ERASE : "") +
      '</span></div><textarea class="cev-note-edit" rows="3"></textarea>';
    CEV.apply(box);
    box.classList.add("writing");
    grip(box, msg);
    var area = box.querySelector("textarea");
    area.value = old;
    area.placeholder = CEV.t("web.note.placeholder");
    var fit = function () { area.style.height = "auto"; area.style.height = Math.max(48, area.scrollHeight) + "px"; };
    fit();
    area.focus();
    area.setSelectionRange(old.length, old.length);
    var done = false;
    var close = function () { done = true; if (writing === msg) { writing = finish = null; } };
    var cancel = function () { close(); show(msg, old); };
    var send = function (text) {
      close();
      box.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      A.post({ action: "note", conversation: conv, message: id, text: text }).then(function () {
        show(msg, text);  // out of writing, before the others are painted again
        paint();
      }, function (err) {
        box.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
        A.failed(err);
      });
    };
    var save = function () {
      if (done) { return; }
      var text = area.value.trim();
      if (text === old.trim()) { cancel(); return; }
      send(text);
    };
    // undo / redo: the steps of the typing, a step closed by a pause of 0.6 s
    var hist = [old], at = 0, last = 0;
    var tools = function () {
      box.querySelector(".cev-note-undo").disabled = at === 0;
      box.querySelector(".cev-note-redo").disabled = at === hist.length - 1;
    };
    var go = function (k) {
      if (k < 0 || k >= hist.length) { return; }
      var before = area.value, after = hist[k], i = 0;
      while (i < before.length && i < after.length && before[i] === after[i]) { i++; }
      at = k;
      area.value = after;
      var j = 0;  // the caret at the end of what changed
      while (j < before.length - i && j < after.length - i && before[before.length - 1 - j] === after[after.length - 1 - j]) { j++; }
      area.setSelectionRange(after.length - j, after.length - j);
      fit();
      tools();
    };
    area.addEventListener("input", function () {
      var now = Date.now();
      if (at === hist.length - 1 && at > 0 && now - last < 600) { hist[at] = area.value; }
      else { hist = hist.slice(0, at + 1); hist.push(area.value); at = hist.length - 1; }
      last = now;
      fit();
      tools();
    });
    tools();
    writing = msg;
    finish = save;
    box.querySelectorAll(".cev-note-tool").forEach(function (b) {
      b.addEventListener("mousedown", function (e) { e.preventDefault(); });  // the text keeps the focus
      b.title = CEV.t(b.getAttribute("data-i18n-attr").slice(6));
    });
    box.querySelector(".cev-note-undo").addEventListener("click", function () { last = 0; go(at - 1); });
    box.querySelector(".cev-note-redo").addEventListener("click", function () { last = 0; go(at + 1); });
    box.querySelector(".cev-note-save").addEventListener("click", save);
    var erase = box.querySelector(".cev-note-erase");
    if (erase) { erase.addEventListener("click", function () { askErase(old, function () { send(""); }, function () { area.focus(); }); }); }
    area.addEventListener("keydown", function (e) {
      var k = e.key.toLowerCase();
      if (e.key === "Escape") { e.preventDefault(); cancel(); }
      else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); }
      else if ((e.ctrlKey || e.metaKey) && (k === "y" || (k === "z" && e.shiftKey))) { e.preventDefault(); last = 0; go(at + 1); }
      else if ((e.ctrlKey || e.metaKey) && k === "z") { e.preventDefault(); last = 0; go(at - 1); }
    });
    // a click elsewhere saves; not when the window itself loses the focus (another program)
    area.addEventListener("blur", function () {
      setTimeout(function () {
        if (done || !document.hasFocus() || box.contains(document.activeElement)) { return; }
        if (document.querySelector("dialog[open], .cev-confirm:not([hidden])")) { return; }
        save();
      }, 0);
    });
  }

  // The frame "Notes (n)" at the top of the page, in the order of the conversation
  var list = document.getElementById("note-list"), listItems = list && list.querySelector(".note-items");
  function paintList() {
    if (!list) { return; }
    var mine = notes()[conv] || {};
    var msgs = Array.prototype.filter.call(root.querySelectorAll(".message[data-uuid]"), function (m) {
      return mine[m.getAttribute("data-uuid")];
    });
    list.classList.toggle("has-notes", msgs.length > 0);
    var label = list.querySelector(".fav-label [data-i18n]");
    label.setAttribute("data-i18n-args", JSON.stringify({ n: msgs.length }));
    listItems.innerHTML = msgs.length ? msgs.map(function (m) {
      var id = m.getAttribute("data-uuid"), time = m.querySelector(".message-time time");
      var text = mine[id].text.replace(/\s+/g, " ");
      return '<li class="fav-item" data-message="' + esc(id) + '"><a href="#msg=' + esc(id) + '">' +
        '<b data-i18n="web.who.' + side(m) + '"></b> ' +
        (time ? '<time data-fmt="datetime" datetime="' + esc(time.getAttribute("datetime")) + '"></time> ' : "") +
        '<span class="fav-excerpt">' + esc(text.length > 160 ? text.slice(0, 159) + "…" : text) + "</span></a>" +
        (served ? '<button type="button" class="fav-remove" data-i18n-attr="title:web.note.erase">' + CROSS + "</button>" : "") +
        "</li>";
    }).join("") : '<li class="fav-none note-none" data-i18n="web.note.none"></li>';
    CEV.apply(list);
  }
  if (listItems) {
    listItems.addEventListener("click", function (e) {
      var b = e.target.closest(".fav-remove");
      if (!b) { return; }
      e.preventDefault();
      var mid = b.closest("li").getAttribute("data-message");
      askErase(((notes()[conv] || {})[mid] || {}).text || "", function () {
        b.disabled = true;
        A.post({ action: "note", conversation: conv, message: mid, text: "" })
          .then(function () { paint(); }, function (err) { b.disabled = false; A.failed(err); });
      });
    });
  }

  function paint() {
    var mine = notes()[conv] || {};
    Array.prototype.forEach.call(root.querySelectorAll(".message[data-uuid]"), function (msg) {
      if (!msg.classList.contains("message-human") && !msg.classList.contains("message-assistant")) { return; }
      var id = msg.getAttribute("data-uuid");
      var time = msg.querySelector(".message-time");
      var b = time && time.querySelector(".note-btn");
      var has = Boolean(mine[id]);
      if (time && !b && (served || has)) {
        b = document.createElement("button");
        b.type = "button";
        b.className = "note-btn";
        b.innerHTML = NOTE;
        b.addEventListener("mousedown", function (e) { if (writing) { e.preventDefault(); } });  // its click saves, not the blur
        var star = time.querySelector(".fav-star");  // order: star, note, T (plan.js)
        time.insertBefore(b, star ? star.nextSibling : null);
      }
      if (b) {
        b.classList.toggle("has-note", has);
        b.classList.toggle("readonly", !served);
        var key = !served ? "web.note.readonly" : has ? "web.note.edit" : "web.note.add";
        b.setAttribute("data-i18n-attr", "title:" + key);
        b.title = CEV.t(key);
      }
      var box = msg.querySelector(":scope > .cev-note");
      if (!(box && box.querySelector("textarea"))) { show(msg, has ? mine[id].text : ""); }
    });
    paintList();
  }

  root.addEventListener("click", function (e) {
    var b = e.target.closest(".note-btn");
    var box = !b && e.target.closest(".cev-note.editable");
    if (!served || (!b && !box) || (box && e.target.closest("textarea, button"))) { return; }
    if (box && window.getSelection && String(window.getSelection())) { return; }  // selecting the text of a note
    var msg = (b || box).closest(".message[data-uuid]");
    if (msg && b && writing === msg) { finish(); return; }  // its icon while it is written: "Enregistrer"
    if (msg) { edit(msg); }
  });
  paint();
  A.ready(function (s) { served = s; paint(); });
})();
