/* Export buttons of a conversation page.
 *
 * .md   : built in the browser from the Markdown embedded in the page.
 * .pdf  : the browser's print window ("Save as PDF"), with formulas
 *   exactly as on screen; same content as the other exports (frames opened or
 *   hidden according to the checkbox, no thinking or tool calls).
 * Checkbox "Include the other versions…": unchecked, only the main thread is
 *   exported (all formats); the choice is remembered by the browser.
 * .odt / .docx : need Pandoc, run by the program:
 *   - page served by "--serve" (http://127.0.0.1:…): the file is requested from the server;
 *   - page opened as a file: the command to type is shown, with a "Copy" button.
 * Labels of the Markdown follow the language chosen in the index (CEV.resolve).
 */
(function () {
  "use strict";
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

  var versions = document.getElementById("export-versions");
  var STORE = "cev-export-versions";
  try {
    if (localStorage.getItem(STORE) === "0") { versions.checked = false; }
  } catch (e) { /* storage unavailable: keep the default (checked) */ }
  versions.addEventListener("change", function () {
    try { localStorage.setItem(STORE, versions.checked ? "1" : "0"); } catch (e) { /* ignore */ }
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

  document.getElementById("export-md").addEventListener("click", function () {
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
      document.body.classList.remove("print-export", "print-main-only");
      frames.forEach(function (d, i) { d.open = wasOpen[i]; });
      document.title = title;
      window.removeEventListener("afterprint", restore);
    }

    document.body.classList.add("print-export");
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

  Array.prototype.forEach.call(bar.querySelectorAll("button[data-format]"), function (button) {
    button.addEventListener("click", function () {
      var fmt = button.getAttribute("data-format");
      var key = bar.getAttribute("data-key");
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
      fetch("/export/" + encodeURIComponent(key) + "." + fmt + "?lang=" + CEV.lang() + (versions.checked ? "" : "&versions=0"))
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
