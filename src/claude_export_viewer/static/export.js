/* Export buttons of a conversation page.
 *
 * .md   : built in the browser from the Markdown embedded in the page.
 * .pdf  : the browser's print window ("Save as PDF"), with formulas
 *   exactly as on screen; same content as the other exports (frames opened or
 *   hidden according to the checkbox, no thinking or tool calls).
 * Checkbox "without the other versions…" (22/11): checked, only the main thread is
 *   exported (all formats); the choice is remembered by the browser.
 * .odt / .docx : need Pandoc, run by the program:
 *   - page served by "--serve" (http://127.0.0.1:…): the file is requested from the server;
 *   - page opened as a file: the command to type is shown, with a "Copy" button.
 * Labels of the Markdown follow the language chosen in the index (CEV.resolve).
 */
(function () {
  "use strict";
  // a part of a very long conversation (parts.js, 21/11): the export is that part's
  function partArg() { return window.CEV_PARTS ? "&part=" + window.CEV_PARTS.part : ""; }
  var bar = document.getElementById("export-bar");
  var data = document.getElementById("cev-markdown");
  var help = document.getElementById("export-help");
  if (!bar || !data) {
    return;
  }
  bar.hidden = false;
  var served = location.protocol === "http:" || location.protocol === "https:";
  if (served) {  // keep the local server alive while this page is open
    setInterval(function () { fetch("/__cev__/ping", { cache: "no-store" }).catch(function () {}); }, 60000);
  }

  // 22/11: "without the other versions and deletions", checked = the main thread only (the sense of "Masquer" on
  // the screen, fold.js); before, "Include…" checked. versions.checked keeps its meaning below: "with them".
  var mainOnly = document.getElementById("export-main");
  var versions = { get checked() { return !mainOnly.checked; } };
  var STORE = "cev-export-main", OLD = "cev-export-versions";
  try {
    var kept = localStorage.getItem(STORE);
    if (kept === null && localStorage.getItem(OLD) === "0") { kept = "1"; }   // the choice made with the old box
    mainOnly.checked = kept === "1";
  } catch (e) { /* storage unavailable: keep the default (unchecked) */ }
  mainOnly.addEventListener("change", function () {
    try { localStorage.setItem(STORE, mainOnly.checked ? "1" : "0"); } catch (e) { /* ignore */ }
    help.hidden = true;  // a command shown before no longer matches
  });

  function save(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function show(nodes) {
    help.innerHTML = "";
    nodes.forEach(function (n) { help.appendChild(n); });
    help.hidden = false;
  }

  function text(tag, content, cls) {
    var el = document.createElement(tag);
    el.textContent = content;
    if (cls) { el.className = cls; }
    return el;
  }

  function copyButton(value) {
    var b = text("button", CEV.t("web.copy"), "export-btn");
    b.type = "button";
    b.addEventListener("click", function () {
      var done = function () {
        b.textContent = CEV.t("web.copied");
        setTimeout(function () { b.textContent = CEV.t("web.copy"); }, 1600);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(value).then(done, function () { b.textContent = CEV.t("web.copy_failed"); });
      } else {
        var area = document.createElement("textarea");
        area.value = value;
        document.body.appendChild(area);
        area.select();
        try { document.execCommand("copy"); done(); } catch (e) { b.textContent = CEV.t("web.copy_failed"); }
        document.body.removeChild(area);
      }
    });
    return b;
  }

  // "2026-10-20 Title.md", or "2026-10-20 Title (main thread).md" (suffix in the chosen language)
  function filename(main) {
    var name = JSON.parse(data.textContent).filename || "conversation.md";
    return main ? name.replace(/\.md$/, "") + CEV.t("md.main_suffix") + ".md" : name;
  }

  // --- Box "ZIP" (only with the local server): the export in a dated ZIP, with the files it names,
  // written in a folder chosen in a window of the system (the index folder first, then the last
  // one chosen, remembered by the browser); .pdf is not concerned.
  var zipBox = document.getElementById("export-zip");
  var ZIP_FOLDER = "cev-zip-folder";
  if (served && zipBox) { zipBox.closest("label").hidden = false; }
  // Box "Annotations" (only with the local server): your notes and highlighted passages in the
  // export; the .md is then made by the server (the Markdown of the page has none)
  var annotBox = document.getElementById("export-annot");
  if (served && annotBox) { annotBox.closest("label").hidden = false; }
  [[zipBox, "cev-export-zip"], [annotBox, "cev-export-annot"]].forEach(function (x) {  // 21/11: kept by the browser
    if (!x[0]) { return; }
    try { x[0].checked = localStorage.getItem(x[1]) === "1"; } catch (e) { /* no storage */ }
    x[0].addEventListener("change", function () {
      try { localStorage.setItem(x[1], x[0].checked ? "1" : "0"); } catch (e) { /* no storage */ }
    });
  });
  function annotWanted() { return served && annotBox && annotBox.checked; }
  function zipWanted() { return served && zipBox && zipBox.checked; }
  function post(url, body) {
    return fetch("/__cev__/token", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        return fetch(url, { method: "POST", body: JSON.stringify(body),
          headers: { "X-CEV-Token": d.token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" } });
      })
      .then(function (r) { return r.ok ? r.json() : r.text().then(function (msg) { throw new Error(msg); }); });
  }
  function exportZip(fmt, button) {
    var last = "";
    try { last = localStorage.getItem(ZIP_FOLDER) || ""; } catch (e) { /* no storage */ }
    var label = button.textContent;
    button.textContent = "…";
    button.disabled = true;
    post("/__cev__/choose-folder", { start: last })
      .then(function (r) {
        return r.unavailable ? CEV.prompt(CEV.t("web.zip.type_folder"), r.start || "") : r.folder;
      })
      .then(function (folder) {
        if (!folder) { return null; }  // cancelled
        try { localStorage.setItem(ZIP_FOLDER, folder); } catch (e) { /* no storage */ }
        return post("/__cev__/export-zip", { key: bar.getAttribute("data-key"), format: fmt, versions: versions.checked,
          folder: folder, annotations: annotWanted(), part: window.CEV_PARTS ? window.CEV_PARTS.part : undefined });
      })
      .then(function (r) {
        if (!r) { return; }
        var nodes = [text("p", CEV.t("web.zip.saved", { path: r.path }))];
        if (r.warnings) { nodes.push(text("p", CEV.t("web.formulas_not_converted", { n: r.warnings }))); }
        show(nodes);
      })
      .catch(function (err) { show([text("p", err.message, "export-error")]); })
      .then(function () { button.textContent = label; button.disabled = false; });
  }

  document.getElementById("export-md").addEventListener("click", function () {
    if (zipWanted()) { exportZip("md", this); return; }
    if (annotWanted()) { fromServer("md", this); return; }
    var payload = JSON.parse(data.textContent);
    var main = !versions.checked && payload.markdown_main;  // absent when there is no other version
    var markdown = CEV.resolve(main ? payload.markdown_main : payload.markdown);  // labels in the chosen language
    save(new Blob([markdown], { type: "text/markdown;charset=utf-8" }), filename(main));
  });

  document.getElementById("export-pdf").addEventListener("click", function () {
    var payload = JSON.parse(data.textContent);
    var main = !versions.checked;
    var frames = Array.prototype.slice.call(document.querySelectorAll("details.removed-part"));
    var wasOpen = frames.map(function (d) { return d.open; });
    var title = document.title;
    var name = filename(main && payload.markdown_main);
    var restored = false;

    function restore() {
      if (restored) { return; }
      restored = true;
      document.body.classList.remove("print-export", "print-main-only", "print-no-annot");
      frames.forEach(function (d, i) { d.open = wasOpen[i]; });
      document.title = title;
      window.removeEventListener("afterprint", restore);
    }

    document.body.classList.add("print-export");
    document.body.classList.toggle("print-no-annot", !annotWanted());
    if (main) {
      document.body.classList.add("print-main-only");
    } else {
      frames.forEach(function (d) { d.open = true; });
    }
    document.title = name.replace(/\.md$/, "");  // suggested name of the PDF file
    help.hidden = true;
    window.addEventListener("afterprint", restore);
    window.print();
    setTimeout(restore, 1000);  // browsers where print() does not wait for the dialog
  });

  function filenameFrom(response, fallback) {
    var header = response.headers.get("Content-Disposition") || "";
    var m = /filename\*=UTF-8''([^;]+)/i.exec(header);
    return m ? decodeURIComponent(m[1]) : fallback;
  }

  // the .md with annotations: asked from the server like the other formats
  function fromServer(fmt, button) {
    var label = button.textContent;
    button.textContent = "…";
    button.disabled = true;
    fetch("/export/" + encodeURIComponent(bar.getAttribute("data-key")) + "." + fmt + "?lang=" + CEV.lang() +
      (versions.checked ? "" : "&versions=0") + "&annotations=1" + partArg())
      .then(function (response) {
        if (!response.ok) { return response.text().then(function (msg) { throw new Error(msg); }); }
        return response.blob().then(function (blob) { save(blob, filenameFrom(response, "conversation." + fmt)); help.hidden = true; });
      })
      .catch(function (err) { show([text("p", err.message, "export-error")]); })
      .then(function () { button.textContent = label; button.disabled = false; });
  }

  Array.prototype.forEach.call(bar.querySelectorAll("button[data-format]"), function (button) {
    button.addEventListener("click", function () {
      var fmt = button.getAttribute("data-format");
      var key = bar.getAttribute("data-key");
      if (zipWanted()) { exportZip(fmt, button); return; }
      if (!served) {
        var cmd = bar.getAttribute("data-cmd-" + fmt) + (versions.checked ? "" : " --fil-principal");
        var code = text("code", cmd, "export-cmd");
        show([
          text("p", CEV.t("web.cmd_intro", { format: fmt })),
          code,
          copyButton(cmd),
          text("p", CEV.t("web.cmd_note"), "export-note"),
        ]);
        return;
      }
      var label = button.textContent;
      button.textContent = "…";
      button.disabled = true;
      fetch("/export/" + encodeURIComponent(key) + "." + fmt + "?lang=" + CEV.lang() + (versions.checked ? "" : "&versions=0") +
        (annotWanted() ? "&annotations=1" : "") + partArg())
        .then(function (response) {
          if (!response.ok) {
            return response.text().then(function (msg) { throw new Error(msg); });
          }
          var missing = response.headers.get("X-Formulas-Not-Converted");
          return response.blob().then(function (blob) {
            save(blob, filenameFrom(response, "conversation." + fmt));
            if (missing) {
              show([text("p", CEV.t("web.formulas_not_converted", { n: Number(missing) }))]);
            } else {
              help.hidden = true;
            }
          });
        })
        .catch(function (err) {
          show([text("p", CEV.t("web.export_failed", { error: err.message }), "export-error")]);
        })
        .then(function () {
          button.textContent = label;
          button.disabled = false;
        });
    });
  });
})();

/* Export ONE message (PT-m1, 08/11): the icon after "Copier" of each bubble opens a box with the formats.
 * Through the local server every format is made by it (/export/<page>.<fmt>?msg=<uuid>, with the box
 * "Annotations"); opened as a file, only .md (the Markdown of the copy) and .pdf (the print window with
 * that message only) can be made, the others are greyed. */
(function () {
  "use strict";
  var bar = document.getElementById("export-bar");
  var data = document.getElementById("cev-markdown");
  if (!bar || !data) { return; }
  var served = location.protocol === "http:" || location.protocol === "https:";
  var key = bar.getAttribute("data-key");
  var FORMATS = ["md", "odt", "docx", "txt", "pdf"];

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  // " (message 2026-11-08 14h03)", as markdown_export.message_suffix
  function suffix(msg) {
    var time = msg.querySelector(".message-time time[datetime]");
    var d = time ? new Date(time.getAttribute("datetime")) : null;
    var when = d && !isNaN(d) ? d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " +
      pad(d.getHours()) + "h" + pad(d.getMinutes()) : "";
    return CEV.t("md.message_suffix", { when: when }).replace(/\s+([)）])/g, "$1");
  }
  function baseName() { return (JSON.parse(data.textContent).filename || "conversation.md").replace(/\.md$/, ""); }

  function save(blob, name) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function printOne(msg, name) {
    var frames = [];
    for (var el = msg.parentElement; el; el = el.parentElement) {
      if (el.matches && el.matches("details.removed-part") && !el.open) { el.open = true; frames.push(el); }
    }
    var title = document.title;
    var restored = false;
    function restore() {
      if (restored) { return; }
      restored = true;
      document.body.classList.remove("print-export", "print-one", "print-no-annot");
      msg.classList.remove("print-this");
      frames.forEach(function (d) { d.open = false; });
      document.title = title;
      window.removeEventListener("afterprint", restore);
    }
    document.body.classList.add("print-export", "print-one");
    msg.classList.add("print-this");
    document.title = name;
    window.addEventListener("afterprint", restore);
    window.print();
    setTimeout(restore, 1000);
  }

  function open(msg) {
    var box = document.createElement("dialog");
    box.className = "cev-confirm cev-export-one";
    box.innerHTML = '<div class="cev-confirm-in"><p class="cev-confirm-text"></p><div class="cev-export-formats"></div>' +
      '<label class="cev-export-annot" hidden><input type="checkbox"> <span></span></label>' +
      '<p class="cev-export-status" hidden></p><div class="cev-confirm-buttons"><button type="button" class="cev-confirm-no"></button></div></div>';
    var who = msg.querySelector(".message-who");
    var time = msg.querySelector(".message-time time");
    box.querySelector(".cev-confirm-text").textContent = CEV.t("web.export_one.head") +
      (who ? " " + who.textContent + (time ? ", " + time.textContent : "") : "");
    box.querySelector(".cev-confirm-no").textContent = CEV.t("web.close");
    var annotLabel = box.querySelector(".cev-export-annot");
    var annot = annotLabel.querySelector("input");
    annotLabel.querySelector("span").textContent = CEV.t("web.export_annotations");
    annotLabel.title = CEV.t("web.export_annotations_title");
    var main = document.getElementById("export-annot");
    annot.checked = !!(main && main.checked);
    if (served && key) { annotLabel.hidden = false; }
    var status = box.querySelector(".cev-export-status");
    function say(text, error) {
      status.hidden = !text;
      status.textContent = text || "";
      status.classList.toggle("export-error", !!error);
    }
    var name = baseName() + suffix(msg);
    var uuid = msg.getAttribute("data-uuid");
    FORMATS.forEach(function (fmt) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = "." + fmt;
      b.setAttribute("data-format", fmt);
      var possible = fmt === "pdf" || fmt === "md" || (served && key);
      if (!possible) { b.disabled = true; b.title = CEV.t("web.export_one.server"); }
      b.addEventListener("click", function () {
        if (fmt === "pdf") { close(); printOne(msg, name); return; }
        var copy = msg.querySelector(".copy-msg[data-md]");
        if (fmt === "md" && (!served || !key) && copy) {
          var h1 = document.querySelector("h1");
          var head = (h1 ? "# " + h1.textContent.trim() + "\n\n" : "") + "**" + (who ? who.textContent : "") + "**" +
            (time ? " — " + time.textContent : "") + "\n\n";
          save(new Blob([head + copy.getAttribute("data-md") + "\n"], { type: "text/markdown;charset=utf-8" }), name + ".md");
          close();
          return;
        }
        var label = b.textContent;
        b.textContent = "…";
        b.disabled = true;
        say("");
        fetch("/export/" + encodeURIComponent(key) + "." + fmt + "?lang=" + CEV.lang() + "&msg=" + encodeURIComponent(uuid) +
          (annot.checked ? "&annotations=1" : ""))
          .then(function (r) {
            if (!r.ok) { return r.text().then(function (m) { throw new Error(m); }); }
            return r.blob().then(function (blob) { save(blob, name + "." + fmt); close(); });
          })
          .catch(function (err) { say(CEV.t("web.export_failed", { error: err.message }), true); })
          .then(function () { b.textContent = label; b.disabled = false; });
      });
      box.querySelector(".cev-export-formats").appendChild(b);
    });
    var done = false;
    function close() {
      if (done) { return; }
      done = true;
      box.close();
      box.remove();
    }
    box.addEventListener("click", function (e) {
      if (e.target.closest(".cev-confirm-no") || e.target === box) { close(); }
    });
    box.addEventListener("cancel", function (e) { e.preventDefault(); close(); });
    document.body.appendChild(box);
    box.showModal();
    box.querySelector(".cev-export-formats button").focus();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest(".export-msg") : null;
    var msg = button && button.closest(".message");
    if (msg) { open(msg); }
  });
})();
