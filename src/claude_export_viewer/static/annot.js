/* What links.js, notes.js and marks.js share: the annotations of the site (annotations-data.js,
 * window.CEV_ANNOTATIONS), changed only through the local server (POST /__cev__/annotations), and
 * a number with an icon in the line of information of a conversation on the index.
 *   CEV.annot.data()          the current state
 *   CEV.annot.ready(fn)       fn(served) once the server is known (served: changes possible)
 *   CEV.annot.post(body)      Promise of the new state; then the event "cev-annotations"
 *   CEV.annot.call(path, body) Promise of the answer (fetch) of another POST of the server (speak.js)
 *   CEV.annot.count(item, cls, svg, n, titleKey, clearKey, ask, body)  the icon on the index */
(function () {
  "use strict";
  var data = window.CEV_ANNOTATIONS || {};
  var token = null, known = false, waiting = [];

  function ready(fn) {
    if (known) { fn(!!token); return; }
    waiting.push(fn);
    if (waiting.length > 1) { return; }
    var done = function () { known = true; waiting.splice(0).forEach(function (f) { f(!!token); }); };
    if (!/^https?:$/.test(location.protocol)) { done(); return; }  // a file: read only
    fetch("/__cev__/token", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.token) { token = d.token; } done(); }, done);
  }

  function post(body) {
    return fetch("/__cev__/annotations", {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.ok ? r.json() : r.text().then(function (text) { throw new Error(text); });
    }).then(function (state) {
      data = state;
      window.CEV_ANNOTATIONS = state;
      document.dispatchEvent(new Event("cev-annotations"));
      return state;
    });
  }

  function call(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function failed(err) { CEV.alert(CEV.t("web.fav.failed") + (err && err.message ? " : " + err.message : "")); }

  // The icon and its number in the line of information of a conversation (index); served: a click
  // removes them all, after "Oui" in the confirmation box (the link of the line is not followed).
  function count(item, cls, svg, n, titleKey, clearKey, askKey, body) {
    var meta = item.querySelector(".conversation-meta");
    var old = meta && meta.querySelector("." + cls);
    if (old) { old.remove(); }
    if (!n || !meta) { return; }
    var span = document.createElement("span");
    span.className = cls + " annot-count";
    span.innerHTML = " &middot; <span class=\"annot-n\">" + svg + " " + n + "</span>";
    var inner = span.querySelector(".annot-n");
    meta.appendChild(span);
    ready(function (served) {
      served = served && !!clearKey;  // clearKey null: shown only (the notes)
      inner.setAttribute("data-i18n-attr", "title:" + (served ? clearKey : titleKey));
      inner.setAttribute("data-i18n-args", JSON.stringify({ n: n }));
      inner.title = CEV.t(served ? clearKey : titleKey, { n: n });
      if (!served) { return; }
      inner.classList.add("annot-clear");
      inner.setAttribute("role", "button");
      inner.tabIndex = 0;
      var ask = function (e) {
        e.preventDefault();
        e.stopPropagation();
        var name = item.querySelector(".conversation-name").firstChild.textContent.trim();
        CEV.confirm(CEV.t(askKey, { title: name }), function () { post(body).catch(failed); });
      };
      inner.addEventListener("click", ask);
      inner.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { ask(e); } });
    });
  }

  window.CEV.annot = { data: function () { return data; }, ready: ready, post: post, call: call, failed: failed, count: count };
})();
