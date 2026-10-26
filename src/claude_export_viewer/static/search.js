/* Index page: search in the content of the conversations (every term, from 3 letters or a
 * symbol; what a term looks for: query.js). The text comes from search-data.js, loaded on the first
 * search. Under each title found: the number of passages; the link opens the page with
 * the words highlighted (?q=…, see msg.js). The index filters ask CEVContent.ok(item). */
(function () {
  "use strict";
  var box = document.getElementById("content-search");
  var status = document.getElementById("content-status");
  var items = Array.prototype.slice.call(document.querySelectorAll(".conversation-item"));
  var KEY = "cev-index-contenu";
  var data = null, loading = false, waiting = [], hits = null, query = "", timer = null;

  function say(key) {
    status.hidden = !key;
    if (key) { status.setAttribute("data-i18n", key); status.textContent = CEV.t(key); }
  }

  function load(then) {
    if (data) { then(); return; }
    waiting.push(then);
    if (loading) { return; }
    loading = true;
    say("web.csearch.loading");
    var s = document.createElement("script");
    s.src = "search-data.js";
    s.onload = function () {
      loading = false;
      data = window.CEV_SEARCH || {};
      say("");
      waiting.splice(0).forEach(function (f) { f(); });
    };
    s.onerror = function () { loading = false; waiting = []; say("web.csearch.unavailable"); };
    document.head.appendChild(s);
  }

  function publish() {
    items.forEach(function (item) {
      var a = item.querySelector("a");
      var base = a.getAttribute("href").split("?")[0];
      var badge = item.querySelector(".content-hits");
      var n = hits ? hits[item.dataset.key] : 0;
      a.setAttribute("href", hits && n ? base + "?q=" + encodeURIComponent(query) : base);
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
    var terms = CEVQuery.parse(query);
    if (!CEVQuery.enough(terms)) { hits = null; say(""); publish(); return; }
    load(function () {
      hits = {};
      Object.keys(data).forEach(function (key) {
        var n = CEVQuery.passages(data[key], terms);
        if (n) { hits[key] = n; }
      });
      publish();
    });
  }

  window.CEVContent = { ok: function (item) { return !hits || Boolean(hits[item.dataset.key]); } };
  box.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 250); });
  box.addEventListener("focus", function () { load(function () {}); }, { once: true });  // ready before typing
  try { box.value = sessionStorage.getItem(KEY) || ""; } catch (e) { /* no storage */ }
  if (box.value.trim()) { setTimeout(run, 0); }
})();
