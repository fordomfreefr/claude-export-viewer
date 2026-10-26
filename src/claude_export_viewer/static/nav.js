/* Buttons on the right of the conversation pages and of the index, shown on pages longer
 * than about two screens: slow continuous scrolling (+ / - change its speed, Escape or a
 * second click stops it), "Haut de page", "Milieu" (also key 5 of the numeric keypad when
 * it is off), "Bas de page". Previous / next message: msg.js. */
(function () {
  var nav = document.getElementById("page-nav");
  var speedBox = document.getElementById("nav-speed");
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
    if (go === "scroll") { if (running) { stop(); } else { start(); } return; }
    if (go !== "top" && go !== "middle" && go !== "bottom") { return; }
    stop();
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

  // --- Slow continuous scrolling (speed kept in this browser) -------------------------
  var SPEEDS = [12, 20, 32, 48, 70, 100, 150];  // pixels per second
  var level = 2;
  try { var saved = parseInt(localStorage.getItem("cev-scroll-speed"), 10); if (saved >= 0 && saved < SPEEDS.length) { level = saved; } } catch (e) { /* no storage */ }
  var running = false, lastTime = 0, pos = 0, hideTimer = null;

  function showSpeed() {
    speedBox.textContent = CEV.t("web.nav.speed", { n: level + 1, max: SPEEDS.length });
    speedBox.hidden = false;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () { speedBox.hidden = true; }, 1500);
  }

  function frame(time) {
    if (!running) { return; }
    if (lastTime) {
      if (Math.abs(window.scrollY - pos) > 3) { pos = window.scrollY; }  // moved by hand meanwhile
      pos = Math.min(pos + SPEEDS[level] * (time - lastTime) / 1000, maxScroll());
      window.scrollTo(0, pos);
      if (pos >= maxScroll() - 1) { stop(); return; }
    }
    lastTime = time;
    requestAnimationFrame(frame);
  }

  function start() {
    running = true;
    lastTime = 0;
    pos = window.scrollY;
    buttons.scroll.setAttribute("aria-pressed", "true");
    buttons.scroll.setAttribute("data-i18n-attr", "title:web.nav.scroll_stop");
    buttons.scroll.title = CEV.t("web.nav.scroll_stop");
    showSpeed();
    requestAnimationFrame(frame);
  }

  function stop() {
    if (!running) { return; }
    running = false;
    buttons.scroll.setAttribute("aria-pressed", "false");
    buttons.scroll.setAttribute("data-i18n-attr", "title:web.nav.scroll");
    buttons.scroll.title = CEV.t("web.nav.scroll");
  }

  // 5 of the numeric keypad when it is off (7 and 1 are already Home and End): the middle.
  // Keypad on, the digit 5 is left alone.
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.altKey || e.metaKey || e.defaultPrevented) { return; }
    var t = e.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) { return; }
    if (e.key === "Clear" || (e.code === "Numpad5" && e.key !== "5")) {
      buttons.middle.click();
      e.preventDefault();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (!running || e.ctrlKey || e.altKey || e.metaKey) { return; }
    if (e.key === "+" || e.key === "=") { level = Math.min(level + 1, SPEEDS.length - 1); }
    else if (e.key === "-" || e.key === "_") { level = Math.max(level - 1, 0); }
    else if (e.key === "Escape") { stop(); e.preventDefault(); return; }
    else { return; }
    try { localStorage.setItem("cev-scroll-speed", String(level)); } catch (err) { /* no storage */ }
    showSpeed();
    e.preventDefault();
  });

  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  // the page height also changes without scrolling (index filters, formulas drawn)
  if ("ResizeObserver" in window) { new ResizeObserver(update).observe(document.body); }
  update();
  setTimeout(update, 500);  // after formulas and fonts
})();
