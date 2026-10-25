/* Index page, when opened through the local server (the desktop icon):
 * "Import a new manifest" button, with a live log (in the language chosen in the index).
 * Also keeps the server alive while the page is open. Does nothing on a page opened as a file. */
(function () {
  "use strict";
  if (location.protocol !== "http:") {
    return;
  }
  var bar = document.getElementById("admin-bar");
  var panel = document.getElementById("admin-panel");
  var log = document.getElementById("admin-log");
  var button = document.getElementById("admin-import");
  var token = null;
  var running = false;  // an import is in progress

  function showPanel(on) {
    panel.hidden = !on;
    button.setAttribute("aria-expanded", on ? "true" : "false");
  }

  function finished() {
    running = false;
    button.classList.remove("busy");
  }

  setInterval(function () { fetch("/__cev__/ping", { cache: "no-store" }).catch(function () {}); }, 60000);

  fetch("/__cev__/token", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (data && data.token) {
        token = data.token;
        bar.hidden = false;
        loadDownloads();
        document.dispatchEvent(new CustomEvent("cev-admin", { detail: { token: token } }));  // topics.js
      }
    })
    .catch(function () {});

  function line(text) {
    var p = document.createElement("div");
    if (!text) {
      p.className = "admin-gap";  // empty line: a visible gap
    }
    // links (claude.ai download links) become clickable
    var parts = text.split(/(https:\/\/claude\.ai\/\S+)/);
    parts.forEach(function (part, i) {
      if (i % 2) {
        var a = document.createElement("a");
        a.href = part;
        a.textContent = part;
        a.target = "_blank";
        a.rel = "noopener";
        p.appendChild(a);
      } else {
        p.appendChild(document.createTextNode(part));
      }
    });
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

  function poll(since) {
    fetch("/__cev__/job?since=" + since, { headers: { "X-CEV-Token": token }, cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (state) {
        state.lines.forEach(line);
        if (!state.done) {
          setTimeout(function () { poll(state.next); }, 800);
          return;
        }
        if (state.ok) {
          line(CEV.t("web.admin.done"));
          setTimeout(function () { location.reload(); }, 2000);
        } else {
          line(CEV.t("web.admin.failed"));
          finished();
        }
      })
      .catch(function () {
        line(CEV.t("web.admin.no_server_icon"));
        finished();
      });
  }

  // --- Downloads folder (where the manifest is looked for) ---------------------
  var dlBox = document.getElementById("admin-downloads");
  var dlPath = document.getElementById("dl-path");
  var dlSystem = document.getElementById("dl-system");
  var dlForm = document.getElementById("dl-form");
  var dlInput = document.getElementById("dl-input");
  var dlError = document.getElementById("dl-error");
  var dlChange = document.getElementById("dl-change");
  var current = { downloads: "", system: "" };

  function showDownloads(data) {
    current = data;
    dlPath.textContent = data.downloads || data.system;
    dlSystem.hidden = Boolean(data.downloads);  // "(folder of the system)"
    dlBox.hidden = false;
  }

  function loadDownloads() {
    fetch("/__cev__/settings", { headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang() }, cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { if (data) { showDownloads(data); } })
      .catch(function () {});
  }

  function editing(on) {
    dlForm.hidden = !on;
    dlChange.setAttribute("aria-expanded", on ? "true" : "false");
    dlError.hidden = true;
    if (on) {
      dlInput.value = current.downloads || current.system;
      dlInput.focus();
      dlInput.select();
    }
  }

  dlChange.addEventListener("click", function () { editing(dlForm.hidden); });  // a second click closes it
  document.getElementById("dl-cancel").addEventListener("click", function () { editing(false); });
  dlForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var value = dlInput.value.trim();
    if (value === current.system) { value = ""; }  // the folder of the system: nothing to remember
    fetch("/__cev__/settings", {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify({ downloads: value })
    })
      .then(function (r) {
        return r.ok ? r.json().then(function (data) {
          showDownloads({ downloads: data.downloads, system: current.system });
          editing(false);
        }) : r.text().then(function (msg) { dlError.textContent = msg; dlError.hidden = false; });
      })
      .catch(function () { dlError.textContent = CEV.t("web.admin.no_server"); dlError.hidden = false; });
  });

  // The cross, or a second click on the button, closes the log. An import still running
  // goes on (the page reloads when it ends); clicking the button meanwhile shows the log again.
  document.getElementById("admin-close").addEventListener("click", function () { showPanel(false); });

  button.addEventListener("click", function () {
    if (!token) { return; }
    if (!panel.hidden) { showPanel(false); return; }
    showPanel(true);
    if (running) { return; }
    running = true;
    button.classList.add("busy");
    log.innerHTML = "";
    line(CEV.t("web.admin.searching"));
    fetch("/__cev__/import", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang() } })
      .then(function (r) {
        if (r.status === 202) { poll(0); return; }
        return r.text().then(function (msg) { line(CEV.t("web.admin.refused", { message: msg })); finished(); });
      })
      .catch(function () { line(CEV.t("web.admin.no_server")); finished(); });
  });
})();
