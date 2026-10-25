/* "Copy" buttons of the code frames (labels from i18n.js).
 *
 * Copies the exact code of the frame (not the colouring) to the clipboard.
 * Works from file:// pages: uses the Clipboard API when available, and falls
 * back to a hidden text area + execCommand("copy") otherwise.
 */
(function () {
  "use strict";
  // Buttons stay hidden if this script cannot run (see style.css).
  document.documentElement.classList.add("js-copy");

  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok ? Promise.resolve() : Promise.reject(new Error("copy failed"));
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        return fallbackCopy(text);
      });
    }
    return fallbackCopy(text);
  }

  function flash(button, label, cls) {
    button.textContent = label;
    button.classList.add(cls);
    clearTimeout(button._timer);
    button._timer = setTimeout(function () {
      button.textContent = CEV.t("web.copy");
      button.classList.remove(cls);
    }, 1600);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest(".copy-btn") : null;
    if (!button) {
      return;
    }
    var frame = button.closest(".code-block");
    var code = frame ? frame.querySelector("pre code") : null;
    if (!code) {
      return;
    }
    var text = code.textContent.replace(/\n$/, "");
    copyText(text).then(
      function () { flash(button, CEV.t("web.copied"), "copied"); },
      function () { flash(button, CEV.t("web.copy_failed"), "copy-failed"); }
    );
  });
})();
