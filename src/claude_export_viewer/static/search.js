/* Index page: search in the content of the conversations (every term, from 3 letters or a
 * symbol; what a term looks for: query.js). The text comes from search/ (parts, see below), read at
 * each search. Under each title found: the number of passages; the link opens the page with
 * the words highlighted (?q=…, see msg.js). The index filters ask CEVContent.ok(item). */
(function () {
  "use strict";
  var box = document.getElementById("content-search");
  var status = document.getElementById("content-status");
  var items = Array.prototype.slice.call(document.querySelectorAll(".conversation-item"));
  var KEY = "cev-index-contenu";
  var hits = null, query = "", timer = null, run_id = 0, fuzzyN = 0;
  // "Tolérance ◂ n ▸" beside the box (approximate search, query.js); the words found besides: under it
  var fuzzyBox = CEVQuery.counter(function () { run(); });
  box.parentNode.insertBefore(fuzzyBox, box.nextSibling);
  var boxTitle = box.title, fuzzyTitle = fuzzyBox.title;
  // the words found besides: as tooltip of the box and of the counter (a line under the box made it higher)
  function sayAlso(words) {
    var text = words.length ? CEV.t("web.fuzzy.also", { words: words.slice(0, 30).join(", ") + (words.length > 30 ? "…" : "") }) : "";
    box.title = text ? text + "\n" + boxTitle : boxTitle;
    fuzzyBox.title = text ? text + "\n" + fuzzyTitle : fuzzyTitle;
    fuzzyBox.classList.toggle("found", !!text);
  }
  // The text is in parts (searchdata.py: search/index.js, then search/pNNN.js, about 100 conversations
  // each), read one after the other: the results show as they come, and the parts read are kept only up to
  // KEEP characters (beyond, read again at the next search), so that thousands of conversations never
  // load the browser at once.
  var KEEP = window.CEV_SEARCH_KEEP || 40e6, parts = null, kept = {}, keptSize = 0, queue = Promise.resolve();

  function say(key) {
    status.hidden = !key;
    if (key) { status.setAttribute("data-i18n", key); status.textContent = CEV.t(key); }
  }

  function script(src) {
    return new Promise(function (ok, ko) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = function () { s.remove(); ok(); };
      s.onerror = function () { s.remove(); ko(new Error(src)); };
      document.head.appendChild(s);
    });
  }

  function index() {
    if (parts) { return Promise.resolve(parts); }
    return script("search/index.js").then(function () {
      parts = ((window.CEV_SEARCH_INDEX || {}).parts) || [];
      return parts;
    });
  }

  function part(name) {  // one part read at a time (each one calls CEV_SEARCH_PART when read)
    var load = function () {
      if (kept[name]) { return kept[name]; }
      var got = null;
      window.CEV_SEARCH_PART = function (d) { got = d; };
      return script("search/" + name).then(function () {
        var d = got || {}, size = 0;
        Object.keys(d).forEach(function (k) { size += d[k].t.length; });
        if (keptSize + size <= KEEP) { kept[name] = d; keptSize += size; }
        return d;
      });
    };
    var p = queue.then(load, load);
    queue = p.catch(function () {});
    return p;
  }

  function publish() {
    items.forEach(function (item) {
      var a = item.querySelector("a");
      var base = a.getAttribute("href").split("?")[0];
      var badge = item.querySelector(".content-hits");
      var n = hits ? hits[item.dataset.key] : 0;
      a.setAttribute("href", hits && n ? base + "?q=" + encodeURIComponent(query) + (fuzzyN ? "&f=" + fuzzyN : "") : base);
      badge.hidden = !(hits && n);
      if (hits && n) {
        badge.setAttribute("data-i18n", "web.csearch.hits");
        badge.setAttribute("data-i18n-args", JSON.stringify({ n: n }));
        badge.textContent = CEV.t("web.csearch.hits", { n: n });
      }
    });
    document.dispatchEvent(new CustomEvent("cev-content"));
  }

  function run() {
    query = box.value.trim();
    try { sessionStorage.setItem(KEY, box.value); } catch (e) { /* no storage */ }
    var terms = CEVQuery.parse(query), me = ++run_id, alsoFound = [];
    fuzzyN = CEVQuery.level();
    sayAlso([]);
    if (!CEVQuery.enough(terms)) { hits = null; say(""); publish(); return; }
    // your notes (annotations-data.js) are searched with the text of their conversation
    var notes = (window.CEV_ANNOTATIONS || {}).notes || {}, noteText = {};
    items.forEach(function (item) {
      var mine = notes[item.dataset.uuid];
      if (mine) {
        noteText[item.dataset.key] = Object.keys(mine).map(function (m) { return CEVQuery.norm(mine[m].text || ""); }).join(" \n ");
      }
    });
    var found = {}, shown = 0;
    index().then(function (names) {
      var i = 0;
      var next = function () {
        if (me !== run_id) { return; }                 // another search started: this one stops
        if (i >= names.length) { hits = found; say(""); sayAlso(alsoFound); publish(); return; }
        return part(names[i++]).then(function (data) {
          if (me !== run_id) { return; }
          Object.keys(data).forEach(function (key) {
            var e = noteText[key] ? { t: data[key].t + " \n " + noteText[key], m: data[key].m } : data[key];
            var mine = terms;
            if (fuzzyN) {  // the words of each conversation, kept with its part
              if (!e.w) { e.w = CEVQuery.wordsOf(e.t); }
              var f = CEVQuery.fuzzy(terms, e.w, fuzzyN);
              mine = f.terms;
            }
            var n = CEVQuery.passages(e, mine);
            if (n) {
              found[key] = n;
              if (fuzzyN) { f.also.forEach(function (w) { if (alsoFound.indexOf(w) < 0 && e.t.indexOf(w) >= 0) { alsoFound.push(w); } }); }
            }
          });
          if (Date.now() - shown > 300) {                // the results so far, a few times a second
            shown = Date.now();
            hits = found;
            if (i < names.length) { say("web.csearch.searching"); }
            publish();
          }
          return next();
        });
      };
      return next();
    }).catch(function () { if (me === run_id) { say("web.csearch.unavailable"); } });
  }

  window.CEVContent = { ok: function (item) { return !hits || Boolean(hits[item.dataset.key]); } };
  box.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 250); });
  box.addEventListener("focus", function () { index().catch(function () {}); }, { once: true });  // ready before typing
  try { box.value = sessionStorage.getItem(KEY) || ""; } catch (e) { /* no storage */ }
  if (box.value.trim()) { setTimeout(run, 0); }
})();
