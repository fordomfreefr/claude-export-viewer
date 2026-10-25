/* Buttons "Haut de page", "Milieu", "Bas de page" (conversation pages and index),
 * shown on pages longer than about two screens. */
(function () {
  var nav = document.getElementById("page-nav");
  var buttons = {};
  Array.prototype.forEach.call(nav.querySelectorAll("button"), function (b) { buttons[b.getAttribute("data-go")] = b; });
  function maxScroll() { return document.documentElement.scrollHeight - window.innerHeight; }
  function update() {
    var max = maxScroll();
    nav.hidden = max < window.innerHeight;
    buttons.top.disabled = window.scrollY < 40;
    buttons.bottom.disabled = window.scrollY > max - 40;
  }
  nav.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) { return; }
    var go = b.getAttribute("data-go");
    var tries = 0, last = -1;
    (function aim() {
      // formulas are drawn when they come near the screen and change the page
      // height: aim again until the height stops changing
      var max = maxScroll();
      window.scrollTo(0, go === "top" ? 0 : go === "bottom" ? max : Math.round(max / 2));
      if (go !== "top" && max !== last && ++tries < 25) {
        last = max;
        setTimeout(aim, 80);
      }
    })();
  });
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  // the page height also changes without scrolling (index filters, formulas drawn)
  if ("ResizeObserver" in window) { new ResizeObserver(update).observe(document.body); }
  update();
  setTimeout(update, 500);  // after formulas and fonts
})();
