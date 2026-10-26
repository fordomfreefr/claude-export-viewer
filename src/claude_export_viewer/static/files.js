/* Conversation pages, when they come from the local server (desktop icon):
 * - the icon of a document opens it with the program of the computer (otherwise the link
 *   simply shows the file in the browser);
 * - a file found automatically on the computer is accepted (Yes) or refused (No), and a
 *   "Yes" can be changed (Change): the server updates the page, which is then reloaded.
 *   Without the server, no buttons. */
(function () {
  "use strict";
  var token = null;
  if (location.protocol === "http:") {
    fetch("/__cev__/token", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.token) {
          token = data.token;
          document.documentElement.classList.add("cev-server");  // shows the Yes / No buttons
        }
      })
      .catch(function () {});
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
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

  function decide(button) {
    var box = button.closest(".userfile");
    var check = button.parentNode;
    var page = decodeURIComponent(location.pathname.split("/").pop()).replace(/\.html$/, "");
    check.classList.add("busy");
    post("/__cev__/file", { page: page, name: box.getAttribute("data-file"), action: button.getAttribute("data-action") })
      .then(function (r) {
        if (r.ok) { location.reload(); return; }
        return r.text().then(function (msg) { throw new Error(msg); });
      })
      .catch(function (err) {
        check.classList.remove("busy");
        var e = check.querySelector(".userfile-error") || check.appendChild(document.createElement("span"));
        e.className = "userfile-error";
        e.textContent = err && err.message ? err.message : CEV.t("web.admin.no_server");
      });
  }

  document.addEventListener("click", function (event) {
    if (!token || !event.target.closest) { return; }  // no server: the browser follows the link
    var link = event.target.closest("a.attachment-open");
    if (link) { event.preventDefault(); open(link); return; }
    var button = event.target.closest(".userfile-check button, .userfile-accepted button");
    if (button) { decide(button); }
  });
})();
