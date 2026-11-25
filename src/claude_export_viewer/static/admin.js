/* Index page, when opened through the local server (the desktop icon):
 * "Import a new manifest" button, with a live log (in the language chosen in the index);
 * the same import for files dropped on the page (end of this file).
 * Also keeps the server alive while the page is open. Does nothing on a page opened as a file. */
(function () {
  "use strict";
  function noServer() {  // 15/11: the tab of the data says why it is empty
    var note = document.getElementById("admin-noserver");
    if (note) { note.hidden = false; document.querySelector("#admin-bar .admin-bar").hidden = true; }
  }
  function dataTab(open) {  // (dashboard.js may come after the token: then it opens the tab itself)
    if (window.CEV.indexTab) { CEV.indexTab("data", open); } else if (open) { window.CEV.dataTabLater = true; }
  }
  if (location.protocol !== "http:") {
    noServer();
    // as a file: no server to receive dropped files; say so instead of letting the browser open them
    var fileVeil = null;
    var files = function (e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0; };
    window.addEventListener("dragenter", function (e) {
      if (!files(e)) { return; }
      e.preventDefault();
      if (!fileVeil) {
        fileVeil = document.createElement("div");
        fileVeil.className = "drop-veil refused";
        fileVeil.innerHTML = '<div class="drop-box"></div>';
        document.body.appendChild(fileVeil);
      }
      fileVeil.firstChild.textContent = CEV.t("web.drop.no_server");
      fileVeil.hidden = false;
      clearTimeout(fileVeil.timer);
      fileVeil.timer = setTimeout(function () { fileVeil.hidden = true; }, 2500);
    });
    window.addEventListener("dragover", function (e) { if (files(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "none"; } });
    window.addEventListener("drop", function (e) { if (files(e)) { e.preventDefault(); fileVeil.hidden = true; } });
    return;
  }
  var panel = document.getElementById("admin-panel");
  var log = document.getElementById("admin-log");
  var button = document.getElementById("admin-import");
  var token = null;
  var running = false;  // an import is in progress
  var reloadOnClose = false;  // a job changed the site: the index is reloaded when its frame is closed

  var opener = button;  // the button of the job shown in the log frame (import, backup, search)

  // The site changed (import, search…): closing the log reloads the index, the other frames open are opened
  // again after it (08/11: they all closed) — the button of each, as the user would click it.
  var REOPEN = { "topics-manager": "topics-manage", "clean-panel": "admin-clean", "annot-panel": "admin-annot" };
  function showPanel(on) {
    if (!on && reloadOnClose && !running) {
      var open = Object.keys(REOPEN).filter(function (id) { var el = document.getElementById(id); return el && !el.hidden; });
      try { sessionStorage.setItem("cev-reopen", JSON.stringify(open)); } catch (e) { /* no storage */ }
      location.reload();
      return;
    }
    panel.hidden = !on;
    opener.setAttribute("aria-expanded", on ? "true" : "false");
  }

  function finished() {
    running = false;
    opener.classList.remove("busy");
  }

  setInterval(function () { fetch("/__cev__/ping", { cache: "no-store" }).catch(function () {}); }, 60000);

  fetch("/__cev__/token", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (data && data.token) {
        token = data.token;
        loadDownloads();
        if (document.getElementById("welcome")) { offerRestore(); }
        document.dispatchEvent(new CustomEvent("cev-admin", { detail: { token: token } }));  // topics.js
        var again = [];
        try { again = JSON.parse(sessionStorage.getItem("cev-reopen") || "[]"); sessionStorage.removeItem("cev-reopen"); } catch (e) { /* none */ }
        if (again.length) { dataTab(true); }  // the frames opened again after a reload are in the tab of the data
        again.forEach(function (id) { var b = document.getElementById(REOPEN[id]); if (b) { b.click(); } });
      } else {
        noServer();
      }
    })
    .catch(noServer);

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
        var bar = document.getElementById("job-progress");  // the pages made again (15/11)
        if (bar) {
          bar.hidden = !state.progress || state.done;
          if (state.progress) {
            var n = state.progress[0], total = Math.max(state.progress[1], 1);
            document.getElementById("job-progress-label").textContent = CEV.t("web.build.title") + " " +
              CEV.t("web.build.count", { n: state.progress[0], total: state.progress[1] });
            document.getElementById("job-progress-bar").style.width = Math.min(100, Math.round(100 * n / total)) + "%";
          }
        }
        if (!state.done) {
          setTimeout(function () { poll(state.next); }, 800);
          return;
        }
        var extra = state.extra || {};
        if (extra.big_message) {  // (21/11) a message set aside, too big for the free memory: read it all the same?
          if (state.ok) { line(CEV.t("web.admin.done")); reloadOnClose = reloadOnClose || reloadAfter; }
          finished();
          var big = extra.big_message;
          CEV.choose(CEV.t("web.import.big_question", { size: big.size, need: big.need, free: big.free }),
            [CEV.t("web.import.big_read"), CEV.t("web.downloads.cancel")], function (k) {
              if (k !== 0) { return; }
              panel.hidden = true;
              startJob("/__cev__/import-date", "web.admin.searching", true, opener, { choice: "big" });
            });
          return;
        }
        if (!state.ok && extra.date_question) {  // (21/11) the export date beyond the clock: the user chooses the date
          finished();
          var q = extra.date_question, when = function (iso) {
            var d = iso ? new Date(iso) : null;
            return !d || isNaN(d) ? CEV.t("web.import.date_unknown") : d.toLocaleString(CEV.lang(), { dateStyle: "short", timeStyle: "short" });
          };
          var choices = q.newest ? ["export", "newest"] : ["export"];
          var labels = choices.map(function (c) { return CEV.t("web.import.date_use_" + c); }).concat([CEV.t("web.downloads.cancel")]);
          CEV.choose(CEV.t("web.import.date_question", { export: when(q.export), clock: when(q.clock), newest: when(q.newest) }),
            labels, function (k) {
              if (k === null || k >= choices.length) { line(CEV.t("web.import.date_cancelled")); return; }
              panel.hidden = true;
              startJob("/__cev__/import-date", "web.admin.searching", true, opener, { choice: choices[k] });
            });
          return;
        }
        if (!state.ok && opener.id === "uninstall-go" && extra.problems) {  // AE-m10: the archive checked first
          line(CEV.t("web.admin.failed"));
          finished();
          CEV.confirm(CEV.t("web.uninstall.ask_problems"), function () {
            panel.hidden = true;
            startJob("/__cev__/uninstall", "web.uninstall.running", false, opener,
              { copies: opener.dataset.copies ? opener.dataset.copies.split(",") : [], dest: opener.dataset.dest || "",
                ignore_problems: true });
          });
          return;
        }
        if (state.ok && opener.id === "admin-verify" && extra.repairable) {  // AE-m10: "Réparer", after Oui / Non
          var fix = document.createElement("button");
          fix.type = "button";
          fix.className = "admin-btn";
          fix.id = "verify-repair";
          fix.textContent = CEV.t("web.verify.repair");
          fix.addEventListener("click", function () {
            CEV.confirm(CEV.t("web.verify.repair_ask", { n: extra.repairable }), function () {
              panel.hidden = true;
              startJob("/__cev__/verify", "web.verify.repairing", true, document.getElementById("admin-verify"), { repair: true });
            });
          });
          var row = document.createElement("div");
          row.className = "clean-buttons";
          row.appendChild(fix);
          log.appendChild(row);
        }
        if (state.ok) {
          // never closed automatically: the user reads the log, then closes the frame (the cross)
          line(CEV.t(reloadAfter ? "web.admin.done" : "web.admin.finished"));
          reloadOnClose = reloadOnClose || reloadAfter;
          if (reloadAfter && document.getElementById("welcome")) { setTimeout(function () { location.reload(); }, 1500); }  // the first conversations
          if (opener.id === "admin-backup") { document.dispatchEvent(new CustomEvent("cev-backup")); }
          if (opener.id === "uninstall-go") {  // the server stops: what this browser keeps for the pages goes too
            try { localStorage.clear(); sessionStorage.clear(); } catch (e) { /* no storage */ }
            token = null;
            uninstalled(opener.dataset.dest || "");
          }
          finished();
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
  var dlForm = document.getElementById("dl-form");
  var dlInput = document.getElementById("dl-input");
  var dlError = document.getElementById("dl-error");
  var dlChange = document.getElementById("dl-change");
  var current = { downloads: "", system: "" };

  function showDownloads(data) {
    if (data.file_folders) { showFiles(data.file_folders); }
    current = data;
    dlPath.textContent = data.downloads || data.system;
    dlBox.hidden = false;
  }

  function siteSize(n) {  // the tile of the overview (dashboard.js): the size of the folder now
    if (typeof n === "number") { document.dispatchEvent(new CustomEvent("cev-site-size", { detail: n })); }
  }

  function loadDownloads() {
    fetch("/__cev__/settings", { headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang() }, cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { if (data) { showDownloads(data); siteSize(data.site_size); } })
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

  // --- Folders where the files of the conversations are looked for (userfiles) ---
  var filesBox = document.getElementById("admin-files");
  var filesPath = document.getElementById("files-path");
  var filesForm = document.getElementById("files-form");
  var filesInput = document.getElementById("files-input");
  var filesError = document.getElementById("files-error");
  var filesChange = document.getElementById("files-change");
  var fileFolders = [];

  function showFiles(folders) {
    fileFolders = folders;
    filesPath.textContent = folders.length ? folders.join(" ; ") : "-";
    filesBox.hidden = false;
  }

  function editingFiles(on) {
    filesForm.hidden = !on;
    filesChange.setAttribute("aria-expanded", on ? "true" : "false");
    filesError.hidden = true;
    if (on) {
      filesInput.value = fileFolders.join("\n");
      filesInput.focus();
    }
  }

  filesChange.addEventListener("click", function () { editingFiles(filesForm.hidden); });
  document.getElementById("files-cancel").addEventListener("click", function () { editingFiles(false); });
  filesForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var lines = filesInput.value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
    fetch("/__cev__/settings", {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify({ file_folders: lines.length ? lines : null })  // empty: the default folders
    })
      .then(function (r) {
        return r.ok ? r.json().then(function (data) { showFiles(data.file_folders); editingFiles(false); })
          : r.text().then(function (msg) { filesError.textContent = msg; filesError.hidden = false; });
      })
      .catch(function () { filesError.textContent = CEV.t("web.admin.no_server"); filesError.hidden = false; });
  });

  // The cross, or a second click on the button, closes the log. An import still running
  // goes on (the page reloads when it ends); clicking the button meanwhile shows the log again.
  document.getElementById("admin-close").addEventListener("click", function () { showPanel(false); });

  var reloadAfter = true;  // an import changes the site: reload the index at the end
  function startJob(path, first, reload, from, body) {  // body: sent as JSON (the uninstall)
    if (!token) { return; }
    if (!panel.hidden) { showPanel(false); return; }
    if (!running) { opener = from || button; }
    showPanel(true);
    if (running) { return; }
    running = true;
    reloadAfter = reload !== false;
    opener.classList.add("busy");
    log.innerHTML = "";
    line(CEV.t(first));
    fetch(path, { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined })
      .then(function (r) {
        if (r.status === 202) { poll(0); return; }
        return r.text().then(function (msg) { line(CEV.t("web.admin.refused", { message: msg })); finished(); });
      })
      .catch(function () { line(CEV.t("web.admin.no_server")); finished(); });
  }

  // The frame of the import (14/11): the latest manifest of the downloads when there is one (the former button),
  // else the window of the system to choose the manifest and / or the ZIPs, taken as if dropped
  var pick = document.getElementById("admin-files-pick");
  button.addEventListener("click", function () {
    if (running || !panel.hidden || !pick) { startJob("/__cev__/import", "web.admin.searching"); return; }
    fetch("/__cev__/has-manifest", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(),
      "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.ok ? r.json() : { found: true }; })
      .then(function (d) { if (d.found) { startJob("/__cev__/import", "web.admin.searching"); } else { pick.click(); } },
        function () { startJob("/__cev__/import", "web.admin.searching"); });
  });
  if (pick) {
    pick.addEventListener("change", function () {
      var files = Array.prototype.slice.call(pick.files || []);
      pick.value = "";
      if (files.length) { dropped(files); }
    });
  }
  document.getElementById("files-search").addEventListener("click", function () {
    startJob("/__cev__/files", "web.files.searching", true, this);
  });
  document.getElementById("admin-backup").addEventListener("click", function () {
    startJob("/__cev__/backup", "web.backup_running", false, this);
  });
  document.getElementById("admin-verify").addEventListener("click", function () {  // AE-m10
    startJob("/__cev__/verify", "web.verify.running", false, this, {});
  });
  document.getElementById("admin-export-all").addEventListener("click", function () {  // AE-m11
    startJob("/__cev__/export-all", "web.export_all_running", false, this);
  });

  // --- Uninstall (AF-m1, 14/11): the copies ticked, what will be removed, Oui/Non ---------
  var unBtn = document.getElementById("admin-uninstall");
  var unPanel = document.getElementById("uninstall-panel");
  var unBody = document.getElementById("uninstall-body");
  function showUninstall(on) {
    unPanel.hidden = !on;
    unBtn.setAttribute("aria-expanded", on ? "true" : "false");
    if (on) { loadUninstall(); } else { unBody.textContent = ""; }
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }
  function loadUninstall() {
    unBody.textContent = "";
    fetch("/__cev__/uninstall-plan", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(),
      "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.json(); })
      .then(function (plan) {
        var dest = plan.dest;
        var where = el("div", "uninstall-where");
        where.appendChild(el("span", "", CEV.t("web.uninstall.copies") + " "));
        var code = el("code", "", dest);
        where.appendChild(code);
        var change = el("button", "admin-btn small", CEV.t("web.downloads.change"));
        change.type = "button";
        change.addEventListener("click", function () {
          CEV.prompt(CEV.t("web.uninstall.dest_prompt"), dest).then(function (value) {
            if (value && value.trim()) { dest = value.trim(); code.textContent = dest; }
          });
        });
        where.appendChild(change);
        unBody.appendChild(where);
        var boxes = {};
        ["exports", "site", "markdown", "program"].forEach(function (w) {
          if (!plan.copies[w]) { return; }
          var label = el("label", "uninstall-copy");
          var box = document.createElement("input");
          box.type = "checkbox";
          box.checked = true;
          box.id = "uninstall-copy-" + w;
          boxes[w] = box;
          label.appendChild(box);
          label.appendChild(document.createTextNode(" " + CEV.t("web.uninstall.copy." + w, { size: size(plan.copies[w]) })));
          unBody.appendChild(label);
        });
        unBody.appendChild(el("div", "uninstall-removed-head", CEV.t("web.uninstall.removed")));
        var list = el("ul", "uninstall-list");
        plan.targets.forEach(function (x) {
          var li = el("li");
          li.appendChild(el("span", "", CEV.t("web.uninstall.key." + x.key) + " : "));
          li.appendChild(el("code", "", x.path));
          li.appendChild(el("span", "uninstall-size", " (" + size(x.size) + ")"));
          list.appendChild(li);
        });
        unBody.appendChild(list);
        unBody.appendChild(el("div", "uninstall-note", CEV.t("web.uninstall.browser")));
        var go = el("button", "admin-btn danger", CEV.t("web.uninstall.go"));
        go.type = "button";
        go.id = "uninstall-go";
        go.setAttribute("aria-controls", "admin-panel");
        go.addEventListener("click", function () {
          var copies = Object.keys(boxes).filter(function (w) { return boxes[w].checked; });
          CEV.confirm(CEV.t(copies.length ? "web.uninstall.ask" : "web.uninstall.ask_nocopy"), function () {
            go.dataset.dest = copies.length ? dest : "";
            go.dataset.copies = copies.join(",");
            showUninstall(false);
            startJob("/__cev__/uninstall", "web.uninstall.running", false, go, { copies: copies, dest: dest });
          });
        });
        var row = el("div", "clean-buttons");
        row.appendChild(go);
        unBody.appendChild(row);
      })
      .catch(function () { unBody.textContent = CEV.t("web.admin.no_server"); });
  }
  // 15/11: once uninstalled, only the top of the page stays (title, version, language), with the last word; the
  // log in "Détails"
  function uninstalled(dest) {
    var box = document.querySelector(".container");
    Array.prototype.forEach.call(box.children, function (c) { if (!c.classList.contains("site-header")) { c.style.display = "none"; } });
    var nav = document.getElementById("page-nav");
    if (nav) { nav.style.display = "none"; }
    var end = el("div", "uninstalled");
    end.appendChild(el("p", "", dest ? CEV.t("web.uninstall.final", { path: dest }) : CEV.t("web.uninstall.closed")));
    var more = el("details");
    more.appendChild(el("summary", "", CEV.t("web.uninstall.details")));
    more.appendChild(log);
    end.appendChild(more);
    box.appendChild(end);
  }

  // 15/11: an empty Library offers the backup found in the downloads (after an uninstall), put back in one click
  function offerRestore() {
    fetch("/__cev__/backup-found", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(),
      "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (b) {
        if (!b.path) { return; }
        var date = new Date(b.date).toLocaleDateString(CEV.lang());
        document.getElementById("restore-text").textContent = CEV.t("web.restore.found", { name: b.name, date: date, size: size(b.size), n: b.n });
        document.getElementById("restore-found").hidden = false;
        var go = document.getElementById("restore-go");
        go.addEventListener("click", function () {
          dataTab(true);
          startJob("/__cev__/restore", "web.restore.running", true, go, { path: b.path });
        });
      }).catch(function () {});
  }

  // --- "Récupération des annotations…" (AF-f5, 15/11): the states kept by CEV, one put back -----------------------
  var anBtn = document.getElementById("admin-annot");
  var anPanel = document.getElementById("annot-panel");
  var anBody = document.getElementById("annot-body");
  function annotCounts(c) { return CEV.t("web.annot_copies.counts", c); }
  function annotPost(body) {
    return fetch("/__cev__/annotations-copies", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(),
      "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) { return r.text().then(function (m) { throw new Error(m); }); } return r.json(); });
  }
  function showAnnot(on) {
    anPanel.hidden = !on;
    anBtn.setAttribute("aria-expanded", on ? "true" : "false");
    anBody.textContent = "";
    if (!on) { return; }
    annotPost({ action: "list" }).then(function (st) {
      anBody.appendChild(el("div", "", CEV.t("web.annot_copies.now", { counts: annotCounts(st.now) })));
      if (!st.copies.length) { anBody.appendChild(el("div", "uninstall-note", CEV.t("web.annot_copies.none"))); return; }
      var list = el("ul", "uninstall-list annot-list");
      st.copies.forEach(function (c) {
        var when = new Date(c.date).toLocaleString(CEV.lang(), { dateStyle: "short", timeStyle: "short" });
        var li = el("li");
        li.appendChild(el("strong", "", when + " "));
        li.appendChild(el("span", "uninstall-size", annotCounts(c.counts) + " "));
        var put = el("button", "admin-btn small", CEV.t("web.annot_copies.put"));
        put.type = "button";
        put.addEventListener("click", function () {
          CEV.confirm(CEV.t("web.annot_copies.ask", { date: when }), function () {
            annotPost({ action: "recover", name: c.name }).then(function () {
              try { sessionStorage.setItem("cev-reopen", JSON.stringify(["annot-panel"])); } catch (e) { /* no storage */ }
              location.reload();  // the pages read the annotations again
            }).catch(function (err) { anBody.appendChild(el("div", "dl-error", err.message)); });
          });
        });
        li.appendChild(put);
        list.appendChild(li);
      });
      anBody.appendChild(list);
    }).catch(function (err) { anBody.textContent = err.message; });
  }
  anBtn.addEventListener("click", function () { showAnnot(anPanel.hidden); });
  document.getElementById("annot-close").addEventListener("click", function () { showAnnot(false); });

  unBtn.addEventListener("click", function () { showUninstall(unPanel.hidden); });
  document.getElementById("uninstall-close").addEventListener("click", function () { showUninstall(false); });

  // --- Cleaning: copies of the site no link uses any more (userfiles.orphans) ---------
  var clean = document.getElementById("admin-clean");
  var cleanPanel = document.getElementById("clean-panel");
  var cleanBody = document.getElementById("clean-body");

  function size(bytes) {
    var kb = bytes / 1024;
    return kb < 1024 ? CEV.t("web.size_kb", { size: { $num: kb } }) : CEV.t("web.size_mb", { size: { $num: kb / 1024 } });
  }

  function showClean(on) {
    cleanPanel.hidden = !on;
    clean.setAttribute("aria-expanded", on ? "true" : "false");
    if (!on) { cleanBody.textContent = ""; }
  }

  function cleanMessage(text) {
    cleanBody.textContent = "";
    var p = document.createElement("div");
    p.textContent = text;
    cleanBody.appendChild(p);
  }

  document.getElementById("clean-close").addEventListener("click", function () { showClean(false); });

  // The sounds read aloud, kept out of the site in the cache folder (speech.cache_dir, 08/11): their size,
  // the largest size kept (CACHE_MIN_MB at least) and a button that removes them all (made again when read).
  function soundsPost(body) {
    return fetch("/__cev__/speech-cache", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(),
      "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) { return r.text().then(function (m) { throw new Error(m); }); } return r.json(); });
  }

  function soundsSection(st, note) {
    var old = document.getElementById("clean-sounds");
    var box = document.createElement("div");
    box.id = "clean-sounds";
    box.className = "clean-sounds";
    var head = document.createElement("div");
    head.textContent = CEV.t("web.clean.sounds", { n: st.count, size: size(st.size) });
    head.title = st.folder;  // (22/11) the folder (a technical path) on hover only
    box.appendChild(head);
    var row = document.createElement("div");
    row.className = "clean-buttons";
    var label = document.createElement("label");
    label.className = "clean-sounds-max";
    label.appendChild(document.createTextNode(CEV.t("web.clean.sounds_max") + " "));
    var input = document.createElement("input");
    input.type = "number";
    input.min = String(st.min_mb);
    input.step = "10";
    input.value = String(st.max_mb);
    input.addEventListener("change", function () {
      var mb = Math.max(st.min_mb, Math.round(Number(input.value) || st.min_mb));
      input.value = String(mb);
      soundsPost({ action: "size", mb: mb }).then(function (res) { soundsSection(res); })
        .catch(function (err) { head.textContent = err.message; });
    });
    label.appendChild(input);
    label.appendChild(document.createTextNode(" " + CEV.t("web.clean.sounds_unit")));
    row.appendChild(label);
    var del = document.createElement("button");
    del.type = "button";
    del.className = "admin-btn";
    del.id = "clean-sounds-delete";
    del.textContent = CEV.t("web.clean.sounds_delete");
    del.disabled = !st.count;
    del.addEventListener("click", function () {
      CEV.confirm(CEV.t("web.clean.sounds_ask", { n: st.count, size: size(st.size) }), function () {
        soundsPost({ action: "clear" }).then(function (res) {
          soundsSection(res, CEV.t("web.clean.sounds_done", { n: res.removed, size: size(res.size) }));
        }).catch(function (err) { head.textContent = err.message; });
      });
    });
    row.appendChild(del);
    box.appendChild(row);
    if (note) {
      var done = document.createElement("div");
      done.textContent = note;
      box.appendChild(done);
    }
    if (old) { old.replaceWith(box); } else { cleanBody.appendChild(box); }
  }

  function addSounds() {
    soundsPost({ action: "state" }).then(function (st) { if (!cleanPanel.hidden) { soundsSection(st); } addArtifacts(); })
      .catch(function () {});  // an older server: no sounds part
  }

  // AF-f1 (14/11): the versions of artifacts extracted when opened (extras/artifacts/), shown when there are some
  function artifactsPost(body) {
    return fetch("/__cev__/artifacts-cache", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(),
      "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) { return r.text().then(function (m) { throw new Error(m); }); } return r.json(); });
  }
  function artifactsSection(st, note) {
    var old = document.getElementById("clean-artifacts");
    if (!st.count && !note) { if (old) { old.remove(); } return; }
    var box = document.createElement("div");
    box.id = "clean-artifacts";
    box.className = "clean-sounds";
    var head = document.createElement("div");
    head.textContent = note || CEV.t("web.clean.artifacts", { n: st.count, size: size(st.size) });
    box.appendChild(head);
    if (st.count) {
      var row = document.createElement("div");
      row.className = "clean-buttons";
      var del = document.createElement("button");
      del.type = "button";
      del.className = "admin-btn";
      del.id = "clean-artifacts-delete";
      del.textContent = CEV.t("web.clean.artifacts_delete");
      del.addEventListener("click", function () {
        CEV.confirm(CEV.t("web.clean.artifacts_ask", { n: st.count, size: size(st.size) }), function () {
          artifactsPost({ action: "clear" }).then(function (res) {
            artifactsSection(res, CEV.t("web.clean.artifacts_done", { n: res.removed, size: size(res.freed) }));
          }).catch(function (err) { head.textContent = err.message; });
        });
      });
      row.appendChild(del);
      box.appendChild(row);
    }
    if (old) { old.replaceWith(box); } else { cleanBody.appendChild(box); }
  }
  function addArtifacts() {
    artifactsPost({ action: "state" }).then(function (st) { if (!cleanPanel.hidden) { artifactsSection(st); } })
      .catch(function () {});
  }

  clean.addEventListener("click", function () {
    if (!cleanPanel.hidden) { showClean(false); return; }
    showClean(true);
    cleanMessage(CEV.t("web.clean.looking"));
    fetch("/__cev__/orphans", { headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang() }, cache: "no-store" })
      .then(function (r) { if (!r.ok) { return r.text().then(function (m) { throw new Error(m); }); } return r.json(); })
      .then(function (data) {
        var n = data.files.length;
        if (!n) { cleanMessage(CEV.t("web.clean.none")); addSounds(); return; }
        cleanBody.textContent = "";
        var p = document.createElement("div");
        p.textContent = CEV.t("web.clean.found", { n: n, size: size(data.total), folder: data.folder });
        cleanBody.appendChild(p);
        var details = document.createElement("details");
        var summary = document.createElement("summary");
        summary.textContent = CEV.t("web.clean.list");
        details.appendChild(summary);
        var list = document.createElement("div");
        list.className = "clean-list";
        data.files.forEach(function (f) {
          var row = document.createElement("div");
          row.textContent = f[0] + " · " + size(f[1]);
          list.appendChild(row);
        });
        details.appendChild(list);
        cleanBody.appendChild(details);
        var del = document.createElement("button");
        del.type = "button";
        del.className = "admin-btn";
        del.id = "clean-delete";
        del.textContent = CEV.t("web.clean.delete", { n: n });
        var cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "admin-btn";
        cancel.textContent = CEV.t("web.downloads.cancel");
        cancel.addEventListener("click", function () { showClean(false); });
        del.addEventListener("click", function () {
          del.disabled = cancel.disabled = true;
          fetch("/__cev__/orphans", { method: "POST", headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang() } })
            .then(function (r) { if (!r.ok) { return r.text().then(function (m) { throw new Error(m); }); } return r.json(); })
            .then(function (res) { cleanMessage(CEV.t("web.clean.done", { n: res.removed, size: size(res.size) })); siteSize(res.site_size); addSounds(); })
            .catch(function (err) { cleanMessage(err && err.message ? err.message : CEV.t("web.admin.no_server")); });
        });
        var row = document.createElement("div");
        row.className = "clean-buttons";
        row.appendChild(del);
        row.appendChild(cancel);
        cleanBody.appendChild(row);
        addSounds();
      })
      .catch(function (err) { cleanMessage(err && err.message ? err.message : CEV.t("web.admin.no_server")); });
  });

  // --- Files dropped on the page (drop.py): manifest and/or export ZIPs ------------
  // A veil over the whole page while a file is dragged over it; each file is sent to the
  // local server in pieces of 4 MB, then the usual import runs (log, reload at the end).
  var CHUNK = 4 * 1024 * 1024;
  var veil = document.createElement("div");
  veil.className = "drop-veil";
  veil.hidden = true;
  veil.innerHTML = '<div class="drop-box"></div>';
  document.body.appendChild(veil);
  var depth = 0;
  function hasFiles(e) {
    return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0;
  }
  window.addEventListener("dragenter", function (e) {
    if (!hasFiles(e)) { return; }
    e.preventDefault();
    depth++;
    veil.firstChild.textContent = CEV.t(token ? "web.drop.veil" : "web.drop.no_server");
    veil.classList.toggle("refused", !token);
    veil.hidden = false;
  });
  window.addEventListener("dragover", function (e) {
    if (!hasFiles(e)) { return; }
    e.preventDefault();  // else the browser opens the file and leaves the index
    e.dataTransfer.dropEffect = token ? "copy" : "none";
  });
  window.addEventListener("dragleave", function (e) {
    if (!hasFiles(e)) { return; }
    depth = Math.max(0, depth - 1);
    if (!depth) { veil.hidden = true; }
  });
  window.addEventListener("drop", function (e) {
    if (!hasFiles(e)) { return; }
    e.preventDefault();
    depth = 0;
    veil.hidden = true;
    if (token) { dropped(Array.prototype.slice.call(e.dataTransfer.files)); }
  });

  function fail(message) {
    line(CEV.t("web.drop.failed", { message: message }));
    finished();
  }

  function send(file, offset, id, el, done) {
    var end = Math.min(offset + CHUNK, file.size), last = end >= file.size;
    var url = "/__cev__/upload?id=" + id + "&name=" + encodeURIComponent(file.name) + "&offset=" + offset +
      (last ? "&last=1&mtime=" + file.lastModified : "");
    fetch(url, {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/octet-stream" },
      body: file.slice(offset, end)
    }).then(function (r) {
      return r.ok ? r.json() : r.text().then(function (m) { throw new Error(m); });
    }).then(function () {
      if (last) {
        el.textContent = CEV.t("web.drop.sent", { name: file.name, size: (file.size / 1e6).toFixed(1) });
        done();
      } else {
        el.textContent = CEV.t("web.drop.sending", { name: file.name, percent: Math.round(100 * end / file.size) });
        send(file, end, id, el, done);
      }
    }).catch(function (err) { fail(err.message || ""); });
  }

  function dropped(files) {
    dataTab(true);  // its log is in the tab of the data
    if (!running) { opener = button; }  // a drop is an import
    showPanel(true);
    if (running) { line(CEV.t("web.drop.busy")); return; }
    running = true;
    reloadAfter = true;
    opener.classList.add("busy");
    log.innerHTML = "";
    var ok = files.filter(function (f) { return /\.(zip|json)$/i.test(f.name); });
    files.forEach(function (f) { if (ok.indexOf(f) < 0) { line(CEV.t("web.drop.refused", { name: f.name })); } });
    if (!ok.length) { line(CEV.t("web.drop.nothing")); finished(); return; }
    var id = "";
    while (id.length < 16) { id += Math.random().toString(36).slice(2); }
    id = id.slice(0, 16);
    var i = 0;
    (function next() {
      if (i >= ok.length) {
        fetch("/__cev__/import-dropped", {
          method: "POST",
          headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
          body: JSON.stringify({ id: id })
        }).then(function (r) {
          if (r.status === 202) { poll(0); return; }
          return r.text().then(function (m) { fail(m); });
        }).catch(function () { fail(CEV.t("web.admin.no_server")); });
        return;
      }
      var file = ok[i++];
      line(CEV.t("web.drop.sending", { name: file.name, percent: 0 }));
      send(file, 0, id, log.lastChild, next);
    })();
  }
})();
