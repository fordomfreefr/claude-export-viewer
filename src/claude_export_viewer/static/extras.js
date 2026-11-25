/* The pages of the other data of the export (extras.py, 11/11).
 * Memory: the version shown (select, newest first) and "Comparer avec la précédente" (the lines added / removed).
 * Artifacts: "Ouvrir" asks the local server to extract that version (POST /__cev__/artifact {id, version}) and
 * opens it in a new tab on the server of the artifacts (another port: another origin, no access to the site nor
 * to the Internet); opened as a file, it says that the local server is needed. */
(function () {
  "use strict";
  var t = function (k, a) { return window.CEV && CEV.t ? CEV.t(k, a) : k; };

  var select = document.getElementById("ex-version");
  var compare = document.getElementById("ex-compare");
  function showVersion() {
    var n = select.value;
    document.querySelectorAll(".ex-version").forEach(function (v) { v.hidden = v.getAttribute("data-version") !== n; });
    var first = n === "0";
    if (compare) {
      compare.disabled = first;
      compare.parentNode.title = first ? t("web.extras.first") : "";
    }
    var diff = compare && compare.checked && !first;
    document.querySelectorAll(".ex-version .ex-diff").forEach(function (d) { d.hidden = !diff; });
    document.querySelectorAll(".ex-version .ex-text").forEach(function (d) { d.hidden = diff; });
  }
  if (select) {
    select.addEventListener("change", showVersion);
    if (compare) { compare.addEventListener("change", showVersion); }
    showVersion();
  }

  var status = document.getElementById("ex-status");
  function say(text) { if (status) { status.hidden = !text; status.textContent = text || ""; } }
  var served = /^https?:$/.test(location.protocol);
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest(".ex-open") : null;
    if (!b) { return; }
    e.preventDefault();
    if (!served) { say(t("web.extras.need_server")); return; }
    var card = b.closest("[data-artifact]"), row = b.closest("[data-version]");
    // the tab opened now (a click), filled once the version is extracted (else the browser blocks it)
    var tab = window.open("about:blank", "_blank");
    say(t("web.extras.opening"));
    fetch("/__cev__/token", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      return fetch("/__cev__/artifact", { method: "POST", headers: { "X-CEV-Token": d.token, "Content-Type": "application/json",
        "X-CEV-Lang": CEV.lang ? CEV.lang() : "fr" },
        body: JSON.stringify({ id: card.getAttribute("data-artifact"), version: row.getAttribute("data-version") }) });
    }).then(function (r) {
      if (!r.ok) { return r.text().then(function (m) { throw new Error(m || r.status); }); }
      return r.json();
    }).then(function (res) {
      var url = "http://127.0.0.1:" + res.port + "/" + b.getAttribute("data-path").split("/").map(encodeURIComponent).join("/");
      if (tab) { tab.location.href = url; } else { window.open(url, "_blank"); }
      say("");
    }).catch(function (err) {
      if (tab) { tab.close(); }
      say(t("web.extras.open_failed", { error: err.message }));
    });
  });
})();
