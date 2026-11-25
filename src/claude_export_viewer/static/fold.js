/* "Masquer :" (21/11) — what the screen hides, kept by the browser for every conversation (localStorage
 * cev-hide-*): the resources of the AI (checked at first: every folding line of claude.ai and the cut replies,
 * body.cev-show-resources when unchecked), the notes, the titles, the numbers of the structure (structure.js), the
 * other versions and the parts deleted on claude.ai (body.cev-main-only). The icon of a note or a title clicked
 * while they are hidden shows them again (what is written must be seen). */
(function () {
  "use strict";
  function get(k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v === "1"; } catch (e) { return d; } }
  function put(k, v) { try { localStorage.setItem(k, v ? "1" : "0"); } catch (e) { /* storage unavailable */ } }
  [["hide-resources", "cev-show-resources", null, true, true], ["hide-notes", "cev-hide-notes", ".note-btn", false],
   ["hide-titles", "cev-hide-titles", ".plan-add-title", false], ["hide-numbers", "cev-hide-numbers", null, false],
   ["hide-versions", "cev-main-only", null, false]].forEach(function (x) {
    var c = document.getElementById(x[0]);
    if (!c) { return; }
    var key = "cev-" + x[0], apply = function () { document.body.classList.toggle(x[1], x[4] ? !c.checked : c.checked); };
    c.checked = get(key, x[3]);  // not the state the browser may restore after "back"
    apply();
    c.addEventListener("change", function () {
      put(key, c.checked);
      apply();
      if (x[1] === "cev-main-only") { document.dispatchEvent(new Event("cev-versions")); }  // navigation, search, favorites
    });
    if (!x[2]) { return; }
    document.addEventListener("click", function (e) {
      if (c.checked && e.target.closest && e.target.closest(x[2])) { c.checked = false; put(key, false); apply(); }
    }, true);
  });
})();

/* Conversation pages: hide Claude's answers to keep only your own messages, one under the
 * other. The small arrow after the date of a message shows or hides the answer to that
 * message; the button of the header hides or shows them all. Kept while the tab is open
 * (a reload after "Yes / No" on a file found keeps the view). Printing shows everything. */
(function () {
  "use strict";
  var box = document.querySelector(".messages");
  var all = document.getElementById("fold-all");
  if (!box || !all) { return; }
  var groups = [];  // {q: your message, a: [the elements of the answer], button}
  Array.prototype.forEach.call(box.children, function (el) {
    if (el.classList.contains("message-human")) {
      groups.push({ q: el, a: [] });
    } else if (groups.length) {
      groups[groups.length - 1].a.push(el);
    }
  });
  groups = groups.filter(function (g) { return g.a.length; });
  if (!groups.length) { return; }
  var KEY = "cev-fold:" + location.pathname;

  function title(el, key) {
    el.setAttribute("data-i18n-attr", "title:" + key);  // follows a change of language
    el.title = CEV.t(key);
  }

  function set(g, folded) {
    g.folded = folded;
    g.a.forEach(function (el) { el.classList.toggle("cev-folded", folded); });
    g.q.classList.toggle("cev-answer-folded", folded);
    g.button.setAttribute("aria-expanded", folded ? "false" : "true");
    title(g.button, folded ? "web.fold.answer_show" : "web.fold.answer_hide");
  }

  function refresh() {
    var every = groups.every(function (g) { return g.folded; });
    all.setAttribute("aria-pressed", every ? "true" : "false");
    title(all, every ? "web.fold.all_show" : "web.fold.all_hide");
    try { sessionStorage.setItem(KEY, JSON.stringify(groups.map(function (g) { return g.folded ? 1 : 0; }))); } catch (e) { /* no storage */ }
  }

  groups.forEach(function (g) {
    var time = g.q.querySelector(".message-time");
    if (!time) {
      time = document.createElement("div");
      time.className = "message-time";
      g.q.insertBefore(time, g.q.firstChild);
    }
    var b = g.button = document.createElement("button");
    b.type = "button";
    b.className = "fold-one";
    b.innerHTML = CEV.icon("hide", 13, "fold-hide") + CEV.icon("show", 13, "fold-show");  // (22/11: as the button of all)
    b.addEventListener("click", function () { set(g, !g.folded); refresh(); });
    time.appendChild(b);
    set(g, false);
  });

  var saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (e) { saved = null; }
  if (Array.isArray(saved) && saved.length === groups.length) {
    groups.forEach(function (g, i) { set(g, Boolean(saved[i])); });
  }

  all.addEventListener("click", function () {
    var every = groups.every(function (g) { return g.folded; });
    var anchor = groups.filter(function (g) { return g.q.getBoundingClientRect().bottom > 0; })[0];
    groups.forEach(function (g) { set(g, !every); });
    refresh();
    if (anchor && anchor.q.getBoundingClientRect().top < 0) { anchor.q.scrollIntoView(); }  // stay on the same message
  });
  all.hidden = false;
  refresh();
})();
