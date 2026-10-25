/* Renders the LaTeX formulas of a conversation page with KaTeX (offline).
 *
 * Elements: <span class="math math-inline">TeX</span>
 *           <span|div class="math math-display">TeX</span|div>
 *
 * - Lazy: a formula is rendered when it comes near the screen, so even a page
 *   with thousands of formulas opens instantly on a modest computer.
 * - Before printing (or "Save as PDF"), all remaining formulas are rendered.
 * - \newcommand / \def made in one formula stay available in the next ones.
 * - A formula KaTeX cannot render is left as its LaTeX source, with the reason
 *   in a tooltip, instead of breaking the page.
 * - Copying a selection copies the LaTeX source of the formulas (copy-tex).
 */
(function () {
  "use strict";
  if (!window.katex) {
    return;
  }
  var items = Array.prototype.slice.call(document.querySelectorAll(".math"));
  var macros = {};

  function renderOne(el) {
    if (el.getAttribute("data-rendered")) {
      return;
    }
    el.setAttribute("data-rendered", "1");
    var tex = el.textContent;
    var display = el.classList.contains("math-display");
    try {
      window.katex.render(tex, el, {
        displayMode: display,
        throwOnError: true,
        strict: "ignore",
        trust: false,
        macros: macros,
        globalGroup: true,
      });
    } catch (err) {
      el.classList.add("math-error");
      var reason = err && err.message ? err.message : String(err);
      el.title = window.CEV ? CEV.t("web.formula_error", { error: reason }) : reason;
      el.textContent = display ? "$$" + tex + "$$" : "$" + tex + "$";
    }
  }

  function renderAll() {
    items.forEach(renderOne);
  }

  // Definitions (\newcommand, \def...) must be known before the formulas that
  // use them, whatever the scrolling order: render those first.
  items.forEach(function (el) {
    if (/\\(newcommand|renewcommand|def|gdef|let)\b/.test(el.textContent)) {
      renderOne(el);
    }
  });

  window.addEventListener("beforeprint", renderAll);

  if (!("IntersectionObserver" in window)) {
    // Old browser: render everything in small batches.
    var i = 0;
    (function step() {
      var end = Math.min(i + 150, items.length);
      for (; i < end; i++) {
        renderOne(items[i]);
      }
      if (i < items.length) {
        setTimeout(step, 0);
      }
    })();
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          observer.unobserve(entry.target);
          renderOne(entry.target);
        }
      });
    },
    { rootMargin: "1200px 0px" }
  );
  items.forEach(function (el) {
    if (!el.getAttribute("data-rendered")) {
      observer.observe(el);
    }
  });
})();
