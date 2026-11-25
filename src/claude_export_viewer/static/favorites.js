/* Favorite messages (annotations.py): the star after the date of each message, the frame of a
 * favorite (thin line with a "neon" halo), the frame "Favoris (n)" of the page listing them
 * (under the export buttons, always shown) and their number on the index (line of information).
 * Read from annotations-data.js (window.CEV_ANNOTATIONS), so shown even on a page opened as a
 * file; changed only through the local server (the desktop icon): POST /__cev__/annotations.
 * A link "page.html#msg=<uuid>" shows that message (frames opened, hidden answer shown). */
(function () {
  "use strict";
  var data = window.CEV_ANNOTATIONS || {};
  function favorites() { return data.favorites || {}; }
  var token = null;
  var STAR = CEV.icon("star", 13, "fav-icon");
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  function post(body) {
    return fetch("/__cev__/annotations", {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.ok ? r.json() : r.text().then(function (text) { throw new Error(text); });
    });
  }

  function getToken(then) {
    if (!/^https?:$/.test(location.protocol)) { then(); return; }  // a file: read only
    fetch("/__cev__/token", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.token) { token = d.token; } then(); }, function () { then(); });
  }

  function setTitle(el, key) {
    el.setAttribute("data-i18n-attr", "title:" + key);
    el.title = CEV.t(key);
  }

  // --- Conversation page --------------------------------------------------------------
  var root = document.querySelector(".messages[data-conversation]");
  if (root) {
    var conv = root.getAttribute("data-conversation");
    var paint = function () {
      var mine = favorites()[conv] || {};
      Array.prototype.forEach.call(root.querySelectorAll(".message[data-uuid]"), function (m) {
        var on = Object.prototype.hasOwnProperty.call(mine, m.getAttribute("data-uuid"));
        m.classList.toggle("cev-fav", on);
        var star = m.querySelector(".message-time > .fav-star");
        if (!star) { return; }
        star.setAttribute("aria-pressed", on ? "true" : "false");
        star.classList.toggle("readonly", !token);
        setTitle(star, !token ? (on ? "web.fav.readonly_on" : "web.fav.readonly") : (on ? "web.fav.remove" : "web.fav.add"));
      });
      list();
    };

    // The frame "Favoris (n)" of the page: the favorites in the order of the conversation
    var box = document.getElementById("fav-list"), items = document.getElementById("fav-items");
    var list = function () {
      if (!box) { return; }
      var mine = favorites()[conv] || {};
      var ids = Object.keys(mine).sort(function (a, b) { return (mine[a].date || "").localeCompare(mine[b].date || ""); });
      if (document.body.classList.contains("cev-main-only")) {  // the other versions hidden (export.js)
        ids = ids.filter(function (id) {
          var el = root.querySelector('.message[data-uuid="' + id + '"]');
          return !el || !el.closest(".removed-part");
        });
      }
      box.classList.toggle("has-favs", ids.length > 0);
      var label = box.querySelector(".fav-label [data-i18n]");
      label.setAttribute("data-i18n-args", JSON.stringify({ n: ids.length }));
      items.innerHTML = ids.length ? ids.map(function (id) {
        var e = mine[id];
        return '<li class="fav-item" data-message="' + esc(id) + '"><a href="#msg=' + esc(id) + '">' +
          '<b data-i18n="web.who.' + (e.sender === "human" ? "human" : "assistant") + '"></b> ' +
          (e.date ? '<time data-fmt="datetime" datetime="' + esc(e.date) + '"></time> ' : "") +
          '<span class="fav-excerpt">' + esc(e.excerpt || "") + "</span></a>" +
          (token ? '<button type="button" class="fav-remove" data-i18n-attr="title:web.fav.remove">' +
            CEV.icon("cross", 12) + '</button>' : "") +
          "</li>";
      }).join("") : '<li class="fav-none" data-i18n="web.fav.none"></li>';
      CEV.apply(box);
    };
    document.addEventListener("cev-versions", function () { list(); });
    if (items) {
      items.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest(".fav-remove") : null;
        var a = e.target.closest ? e.target.closest(".fav-item a") : null;
        if (a && a.getAttribute("href") === location.hash) { goTo(); e.preventDefault(); return; }  // the same one again
        if (!b || !token) { return; }
        b.disabled = true;
        post({ action: "favorite", conversation: conv, message: b.closest(".fav-item").getAttribute("data-message"), on: false })
          .then(function (state) { data = state; paint(); }, function (err) { b.disabled = false; b.title = err.message; });
      });
    }
    root.addEventListener("click", function (e) {
      var star = e.target.closest ? e.target.closest(".fav-star") : null;
      if (!star || !token || star.disabled) { return; }
      var m = star.closest(".message[data-uuid]");
      star.disabled = true;
      post({ action: "favorite", conversation: conv, message: m.getAttribute("data-uuid"),
        on: !m.classList.contains("cev-fav") })
        .then(function (state) { data = state; paint(); },
          function (err) { star.title = err.message || CEV.t("web.fav.failed"); })
        .then(function () { star.disabled = false; });
    });
    paint();
    getToken(paint);

    // #msg=<uuid>: that message, shown and framed for a moment
    var goTo = function () {
      var id = (location.hash.match(/^#msg=([\w-]+)$/) || [])[1];
      if (!id) { return; }
      var all = root.querySelectorAll('.message[data-uuid="' + id + '"]');
      var m = all[0];
      if (!m) { return; }
      var top = m.closest(".messages > *");
      if (top && top.classList.contains("cev-folded")) {  // a hidden answer (fold.js)
        var q = top.previousElementSibling;
        while (q && !q.classList.contains("message-human")) { q = q.previousElementSibling; }
        var b = q && q.querySelector(".fold-one");
        if (b) { b.click(); }
      }
      for (var d = m.parentNode.closest("details"); d; d = d.parentNode.closest("details")) { d.open = true; }
      m.classList.add("cev-target");
      // the start of the message at the top of the window, under the search bar when it is shown
      var place = function () {
        var off = 8, bar = document.querySelector(".hit-bar");
        var r = bar ? bar.getBoundingClientRect() : null;  // fixed: no offsetParent, size 0 when hidden
        if (r && r.height > 0) { off = r.bottom + 8; }
        window.scrollTo(0, Math.max(0, m.getBoundingClientRect().top + window.scrollY - off));
      };
      setTimeout(place, 50);
      setTimeout(place, 600);  // after the formulas
      setTimeout(function () { m.classList.remove("cev-target"); }, 2500);
    };
    goTo();
    window.addEventListener("hashchange", goTo);
  }

  // --- Index: the number of favorites of each conversation, in its line of information ---
  if (!root) {
    var favs = favorites();
    Array.prototype.forEach.call(document.querySelectorAll(".conversation-item[data-uuid]"), function (item) {
      var n = Object.keys(favs[item.getAttribute("data-uuid")] || {}).length;
      var meta = item.querySelector(".conversation-meta");
      if (!n || !meta) { return; }
      var span = document.createElement("span");
      span.className = "fav-count";
      span.setAttribute("data-i18n-attr", "title:web.fav.count_title");
      span.setAttribute("data-i18n-args", JSON.stringify({ n: n }));
      span.title = CEV.t("web.fav.count_title", { n: n });
      span.innerHTML = " &middot; <span class=\"fav-star-n\">" + STAR + " " + n + "</span>";
      meta.appendChild(span);
    });
    // Served by the local server: a click on the star removes every favorite of the conversation,
    // after "Oui" in the confirmation box (the link of the line is not followed)
    getToken(function () {
      if (!token) { return; }
      Array.prototype.forEach.call(document.querySelectorAll(".fav-count"), function (span) {
        var star = span.querySelector(".fav-star-n");
        var item = span.closest(".conversation-item");
        star.classList.add("fav-clear");
        star.setAttribute("role", "button");
        star.tabIndex = 0;
        span.removeAttribute("data-i18n-attr");
        span.removeAttribute("title");
        setTitle(star, "web.fav.clear_title");
        function ask(e) {
          e.preventDefault();
          e.stopPropagation();
          var name = item.querySelector(".conversation-name").firstChild.textContent.trim();
          CEV.confirm(CEV.t("web.fav.clear_ask", { title: name }), function () {
            post({ action: "clear_favorites", conversation: item.getAttribute("data-uuid") }).then(function (state) {
              data = state;
              span.remove();
            }, function (err) { CEV.alert(CEV.t("web.fav.failed") + (err && err.message ? " : " + err.message : "")); });
          });
        }
        star.addEventListener("click", ask);
        star.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { ask(e); } });
      });
    });
  }

})();

// P3 (11/11): the frames of the head (Liens, Favoris, Notes, Titres) are tabs, one open at a time (also as a file)
(function () {
  "use strict";
  Array.prototype.forEach.call(document.querySelectorAll(".fav-tabs > .fav-list"), function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) { return; }
      Array.prototype.forEach.call(document.querySelectorAll(".fav-tabs > .fav-list[open]"), function (o) { if (o !== d) { o.open = false; } });
    });
  });
})();
