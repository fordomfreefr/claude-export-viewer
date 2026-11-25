/* Conversation pages, when they come from the local server (desktop icon):
 * - the icon of a document opens it with the program of the computer (otherwise the link
 *   simply shows the file in the browser);
 * - the button 🔗 of a link opens a menu to associate it with a file of the computer: one of the
 *   files found with its name (or a copy renamed by the browser), another file chosen in the
 *   browser, no file, or the automatic choice again. The server copies the file into the site and
 *   updates the page, which is then reloaded (see userfiles.py). Without the server, no button. */
(function () {
  "use strict";
  var token = null;
  if (location.protocol === "http:") {
    fetch("/__cev__/token", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.token) {
          token = data.token;
          document.documentElement.classList.add("cev-server");  // shows the buttons 🔗
        }
      })
      .catch(function () {});
  }

  function headers(type) {
    return { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": type };
  }

  function post(path, body) {
    return fetch(path, { method: "POST", headers: headers("application/json"), body: JSON.stringify(body) });
  }

  function page() {
    return decodeURIComponent(location.pathname.split("/").pop()).replace(/\.html$/, "");
  }

  function open(link) {
    post("/__cev__/open", { path: link.getAttribute("data-open") })
      .then(function (r) {
        link.classList.toggle("failed", !r.ok);
        link.title = CEV.t(r.ok ? "web.attachment.opened" : "web.attachment.open_failed");
        if (!r.ok) { window.open(link.href, "_blank"); }  // at least show it in the browser
      })
      .catch(function () { window.open(link.href, "_blank"); });
  }

  // --- menu of a link ---
  var menu = null;

  function close() {
    if (menu) {
      menu.box.querySelector(".cf-link").classList.remove("open");
      menu.el.remove();
      menu = null;
    }
  }

  function size(bytes) {
    var kb = bytes / 1024;
    return kb < 1024 ? CEV.t("web.size_kb", { size: { $num: kb } }) : CEV.t("web.size_mb", { size: { $num: kb / 1024 } });
  }

  function when(mtime) {
    var d = new Date(mtime * 1000);
    return d.toLocaleDateString(CEV.lang()) + " " + d.toLocaleTimeString(CEV.lang(), { hour: "2-digit", minute: "2-digit" });
  }

  function done(r) {
    if (r.ok) { location.reload(); return; }
    return r.text().then(function (msg) { throw new Error(msg); });
  }

  function failed(err) {
    if (!menu) { return; }
    menu.el.classList.remove("busy");
    var e = menu.el.querySelector(".cf-menu-error") || menu.el.appendChild(document.createElement("div"));
    e.className = "cf-menu-error";
    e.textContent = err && err.message ? err.message : CEV.t("web.admin.no_server");
  }

  function choose(body) {
    menu.el.classList.add("busy");
    post("/__cev__/link", Object.assign({ page: page(), link: menu.box.getAttribute("data-link") }, body))
      .then(done).catch(failed);
  }

  function upload(file) {
    menu.el.classList.add("busy");
    var q = "?page=" + encodeURIComponent(page()) + "&link=" + encodeURIComponent(menu.box.getAttribute("data-link")) +
      "&name=" + encodeURIComponent(file.name);
    fetch("/__cev__/link-file" + q, { method: "POST", headers: headers("application/octet-stream"), body: file })
      .then(done).catch(failed);
  }

  function item(cls, text) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = text;
    return b;
  }

  function show(box, button) {
    close();
    var cands = [];
    try { cands = JSON.parse(box.getAttribute("data-cands") || "[]"); } catch (e) { cands = []; }
    var el = document.createElement("div");
    el.className = "cf-menu";
    el.setAttribute("role", "menu");
    var head = document.createElement("div");
    head.className = "cf-menu-head";
    head.textContent = CEV.t("web.link.menu_head");
    el.appendChild(head);
    if (!cands.length) {
      var none = document.createElement("div");
      none.className = "cf-menu-empty";
      none.textContent = CEV.t("web.link.no_candidate");
      el.appendChild(none);
    }
    cands.forEach(function (c) {
      var row = document.createElement("button");
      row.type = "button";
      row.className = "cf-opt" + (c.current ? " cf-cur" : "");
      row.setAttribute("data-path", c.path);
      row.innerHTML = '<span class="cf-dot"></span><span class="cf-path"></span><span class="cf-meta"></span>';
      row.querySelector(".cf-path").textContent = c.shown;
      row.querySelector(".cf-meta").textContent = size(c.size) + " · " + when(c.mtime);
      if (c.current || c.others) {
        var tag = document.createElement("span");
        tag.className = "cf-tag";
        tag.textContent = c.current ? CEV.t("web.link.current") : CEV.t("web.link.used", { n: c.others });
        row.appendChild(tag);
      }
      el.appendChild(row);
    });
    var sep = document.createElement("div");
    sep.className = "cf-sep";
    el.appendChild(sep);
    var other = item("cf-act cf-other", CEV.t("web.link.other"));
    var input = document.createElement("input");
    input.type = "file";
    input.hidden = true;
    input.addEventListener("change", function () { if (input.files && input.files[0]) { upload(input.files[0]); } });
    el.appendChild(other);
    el.appendChild(input);
    el.appendChild(item("cf-act cf-none", CEV.t("web.link.nothing")));
    if (box.getAttribute("data-how") === "user") {
      el.appendChild(item("cf-act cf-auto", CEV.t("web.link.back_auto")));
    }
    box.querySelector(".userfile-bar").insertAdjacentElement("afterend", el);
    button.classList.add("open");
    menu = { box: box, el: el, input: input };
    var first = el.querySelector("button");
    if (first) { first.focus(); }
  }

  document.addEventListener("click", function (event) {
    if (!token || !event.target.closest) { return; }  // no server: the browser follows the link
    var link = event.target.closest("a.attachment-open");
    if (link) { event.preventDefault(); open(link); return; }
    var button = event.target.closest(".cf-link");
    if (button) {
      var box = button.closest(".userfile");
      if (menu && menu.box === box) { close(); } else { show(box, button); }
      return;
    }
    if (!menu) { return; }
    var opt = event.target.closest(".cf-menu button");
    if (!opt) {
      if (!event.target.closest(".cf-menu")) { close(); }
      return;
    }
    if (opt.classList.contains("cf-opt")) {
      if (!opt.classList.contains("cf-cur")) { choose({ action: "path", path: opt.getAttribute("data-path") }); }
      else { close(); }
    } else if (opt.classList.contains("cf-other")) {
      menu.input.click();
    } else if (opt.classList.contains("cf-none")) {
      choose({ action: "none" });
    } else if (opt.classList.contains("cf-auto")) {
      choose({ action: "auto" });
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && menu) { close(); }
  });
})();
