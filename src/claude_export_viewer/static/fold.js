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
    b.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
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
