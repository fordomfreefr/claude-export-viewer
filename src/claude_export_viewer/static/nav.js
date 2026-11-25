/* Buttons on the right of the conversation pages and of the index, shown on pages longer
 * than about two screens: slow continuous scrolling (+ / - change its speed, Escape or a
 * second click stops it), "Haut de page", "Milieu" (also key 5 of the numeric keypad when
 * it is off), "Bas de page". Previous / next message: msg.js.
 * Always shown, even on short pages: the theme (system -> light -> dark) and the background
 * music (wheel or + / - over the note: volume; wheel over the play button: speed). */
(function () {
  var nav = document.getElementById("page-nav");
  var speedBox = document.getElementById("nav-speed");
  var buttons = {};
  Array.prototype.forEach.call(nav.querySelectorAll("button"), function (b) { buttons[b.getAttribute("data-go")] = b; });
  function maxScroll() { return document.documentElement.scrollHeight - window.innerHeight; }
  function update() {
    var max = maxScroll();
    nav.hidden = false;
    nav.classList.toggle("short", max < window.innerHeight);
    buttons.top.disabled = window.scrollY < 40;
    buttons.bottom.disabled = window.scrollY > max - 40;
    buttons.scroll.disabled = !running && window.scrollY >= max - 2;  // at the end of the page: nothing to scroll
  }
  nav.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b || (nav.classList.contains("short") && !b.classList.contains("nav-keep"))) { return; }  // greyed (style.css)
    var go = b.getAttribute("data-go");
    if (go === "scroll") { if (running) { stop(); } else { start(); } return; }
    if (go === "theme") { setTheme(THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]); return; }
    if (go === "music") { if (music.on) { musicStop(); } else { musicStart(); } return; }
    if (go === "index") { location.href = b.getAttribute("data-href"); return; }
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
  // While a bubble is read aloud (speak.js, CEV.speak.target()), the scrolling follows the reading instead
  // of its speed; scrolling by hand (wheel, keys, touch, scroll bar) then stops it, the reading goes on.
  var SPEEDS = [6, 9, 12, 20, 32, 48, 70, 100, 150];  // pixels per second
  var level = 4;
  try {
    var saved = parseInt(localStorage.getItem("cev-scroll-level"), 10), old = parseInt(localStorage.getItem("cev-scroll-speed"), 10);
    if (isNaN(saved) && old >= 0) { saved = old + 2; }  // before the two slowest speeds
    if (saved >= 0 && saved < SPEEDS.length) { level = saved; }
  } catch (e) { /* no storage */ }
  var running = false, lastTime = 0, pos = 0, hideTimer = null, byHand = false;
  function following() { var t = window.CEV.speak && CEV.speak.target ? CEV.speak.target() : null; return t === null || isNaN(t) ? null : t; }
  window.CEV.scrolling = function () { return running; };

  // a small box (speed, volume) at the left of its button
  function beside(box, button) {
    box.hidden = false;
    var n = nav.getBoundingClientRect(), r = button.getBoundingClientRect();
    box.style.top = Math.round(r.top - n.top + (r.height - box.offsetHeight) / 2) + "px";
    box.style.right = Math.round(n.right - r.left + 6) + "px";
  }

  function showSpeed() {
    speedBox.textContent = CEV.t("web.nav.speed", { n: level + 1, max: SPEEDS.length });
    beside(speedBox, buttons.scroll);
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () { speedBox.hidden = true; }, 1500);
  }

  function frame(time) {
    if (!running) { return; }
    var goal = following();
    if (goal !== null && byHand) { stop(); return; }  // following the reading, scrolled by hand: stopped
    byHand = false;
    if (lastTime) {
      if (Math.abs(window.scrollY - pos) > 3) { pos = window.scrollY; }  // moved by hand meanwhile
      if (goal !== null) {  // the line read about a third down the screen, reached smoothly
        goal = Math.max(0, Math.min(goal, maxScroll()));
        pos += (goal - pos) * (1 - Math.exp(-(time - lastTime) / 450));
        window.scrollTo(0, pos);
      } else {
        pos = Math.min(pos + SPEEDS[level] * (time - lastTime) / 1000, maxScroll());
        window.scrollTo(0, pos);
        if (pos >= maxScroll() - 1) { stop(); return; }
      }
    }
    lastTime = time;
    requestAnimationFrame(frame);
  }

  // scrolled by hand (not by this script)
  function hand() { if (running) { byHand = true; } }
  window.addEventListener("wheel", function (e) { if (!e.target.closest || !e.target.closest("#page-nav")) { hand(); } }, { passive: true });
  window.addEventListener("touchmove", hand, { passive: true });
  document.addEventListener("keydown", function (e) {
    if (/^(ArrowUp|ArrowDown|PageUp|PageDown|Home|End| )$/.test(e.key) && !(e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))) { hand(); }
  });
  document.addEventListener("mousedown", function (e) { if (e.clientX >= document.documentElement.clientWidth) { hand(); } });  // scroll bar

  function start() {
    byHand = false;
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
    setTimeout(update, 0);  // greyed if stopped at the end of the page
    buttons.scroll.setAttribute("aria-pressed", "false");
    buttons.scroll.setAttribute("data-i18n-attr", "title:web.nav.scroll");
    buttons.scroll.title = CEV.t("web.nav.scroll");
  }

  // The one way to stop the slow scrolling, also for the other scripts (CEV.stopScroll). Any action
  // of the reader stops it: a click on a control (button, link, box, menu, folding line), typing in
  // a field, a choice in a list; controls added later need nothing more. Not stopped by its own
  // button (play/pause), the theme or the music.
  window.CEV.stopScroll = stop;
  var ACTIVE = "button, a, input, select, textarea, summary, label, [role=button], .cev-long > .code-header, .cev-long > .artifact-header";
  var KEEP = '#page-nav [data-go="scroll"], #page-nav [data-go="theme"], #page-nav [data-go="music"], #page-nav [data-go="speak"], .cev-speak';
  function onAction(e) {
    if (!running || !e.target.closest) { return; }
    var el = e.target.closest(ACTIVE);
    if (el && !el.closest(KEEP)) { stop(); }
  }
  ["click", "input", "change"].forEach(function (type) { document.addEventListener(type, onAction, true); });

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

  function changeSpeed(step) {
    level = Math.max(0, Math.min(SPEEDS.length - 1, level + step));
    try { localStorage.setItem("cev-scroll-level", String(level)); } catch (err) { /* no storage */ }
    showSpeed();
  }
  buttons.scroll.addEventListener("wheel", function (e) {
    e.preventDefault();
    if (e.deltaY) { changeSpeed(e.deltaY < 0 ? 1 : -1); }
  }, { passive: false });

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.altKey || e.metaKey) { return; }
    if (buttons.music.matches(":hover") && (e.key === "+" || e.key === "=" || e.key === "-" || e.key === "_")) {
      changeVolume(e.key === "+" || e.key === "=" ? 1 : -1);
      e.preventDefault();
      return;
    }
    if (!running) { return; }
    if (e.key === "+" || e.key === "=") { changeSpeed(1); }
    else if (e.key === "-" || e.key === "_") { changeSpeed(-1); }
    else if (e.key === "Escape") { stop(); e.preventDefault(); return; }
    else { return; }
    e.preventDefault();
  });

  // --- Theme: system (default), light, dark; kept in this browser ------------------
  // (the attribute is set before the page is drawn by a line in the page head, which also follows the system;
  // "system" puts the theme of the system in the attribute: the CSS knows only [data-theme="dark"], 14/11)
  var THEMES = ["system", "light", "dark"], theme = "system";
  try { var savedTheme = localStorage.getItem("cev-theme"); if (THEMES.indexOf(savedTheme) > 0) { theme = savedTheme; } } catch (e) { /* no storage */ }
  function setTheme(mode) {
    theme = mode;
    var sys = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", mode === "system" ? sys : mode);
    try { if (mode === "system") { localStorage.removeItem("cev-theme"); } else { localStorage.setItem("cev-theme", mode); } } catch (e) { /* no storage */ }
    buttons.theme.setAttribute("data-mode", mode);
    buttons.theme.setAttribute("data-i18n-attr", "title:web.theme." + mode);
    buttons.theme.title = CEV.t("web.theme." + mode);
  }
  setTheme(theme);

  // --- Background music: one soft note at a time, drawn at random from a pentatonic
  // scale (no clashing notes), random length and pause, a faint high note every 6 to 16 s.
  // Only oscillators, no audio file. Volume level kept in this browser.
  var VOLUMES = [0.03, 0.07, 0.15, 0.25, 0.4, 0.6, 0.85], vol = 2;  // 15 % by default
  try { var savedVol = parseInt(localStorage.getItem("cev-music-volume"), 10); if (savedVol >= 0 && savedVol < VOLUMES.length) { vol = savedVol; } } catch (e) { /* no storage */ }
  var SCALE = [196.00, 220.00, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25];  // G3 A3 C4 D4 E4 G4 A4 C5
  var HIGH = [523.25, 587.33, 659.25, 783.99, 880.00];  // C5 D5 E5 G5 A5
  var music = { on: false, ctx: null, master: null, reverb: null, timers: [], last: -1 };
  var volumeBox = document.getElementById("nav-volume"), volumeTimer = null;

  function impulse(ctx, seconds) {  // soft reverb: decaying noise
    var len = ctx.sampleRate * seconds, buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (var c = 0; c < 2; c++) {
      var d = buf.getChannelData(c);
      for (var i = 0; i < len; i++) { d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.5); }
    }
    return buf;
  }
  function note(freq, dur) {  // two slightly detuned oscillators, slow rise and fall
    var ctx = music.ctx, t = ctx.currentTime + 0.05, g = ctx.createGain(), f = ctx.createBiquadFilter();
    f.type = "lowpass"; f.frequency.value = 1100; f.Q.value = 0.3;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.06, t + dur * 0.35);
    g.gain.linearRampToValueAtTime(0, t + dur);
    [-5, 5].forEach(function (cents, k) {
      var o = ctx.createOscillator();
      o.type = k ? "triangle" : "sine";
      o.frequency.value = freq;
      o.detune.value = cents;
      o.connect(f); o.start(t); o.stop(t + dur + 0.1);
    });
    f.connect(g); g.connect(music.master); g.connect(music.reverb);
  }
  function sparkle() {  // now and then, a faint high note
    if (!music.on) { return; }
    var ctx = music.ctx, t = ctx.currentTime + 0.05, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "sine";
    o.frequency.value = HIGH[Math.floor(Math.random() * HIGH.length)];
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.02, t + 0.05);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 4);
    o.connect(g); g.connect(music.reverb); g.connect(music.master);
    o.start(t); o.stop(t + 4.2);
    music.timers.push(setTimeout(sparkle, 6000 + Math.random() * 10000));
  }
  function nextNote() {
    if (!music.on) { return; }
    var k, last = music.last;
    do {  // a near note most of the time, a jump now and then: a melody rather than a scatter
      k = Math.random() < 0.7 && last >= 0
        ? Math.max(0, Math.min(SCALE.length - 1, last + [-2, -1, 1, 2][Math.floor(Math.random() * 4)]))
        : Math.floor(Math.random() * SCALE.length);
    } while (k === last);
    music.last = k;
    var dur = 3 + Math.random() * 3, pause = 0.5 + Math.random() * 2.5;
    note(SCALE[k], dur);
    music.timers.push(setTimeout(nextNote, (dur + pause) * 1000));
  }
  function musicTitle() {
    var key = music.on ? "web.music.stop" : "web.music.play";
    buttons.music.setAttribute("aria-pressed", music.on ? "true" : "false");
    buttons.music.setAttribute("data-i18n-attr", "title:" + key);
    buttons.music.title = CEV.t(key);
  }
  function musicStart() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { return; }
    if (!music.ctx) {
      var ctx = music.ctx = new AC();
      music.master = ctx.createGain(); music.master.connect(ctx.destination);
      music.master.gain.value = 0;
      music.reverb = ctx.createConvolver(); music.reverb.buffer = impulse(ctx, 5);
      var wet = ctx.createGain(); wet.gain.value = 0.7;
      music.reverb.connect(wet); wet.connect(music.master);
    }
    var c = music.ctx, gain = music.master.gain;
    c.resume();
    gain.cancelScheduledValues(c.currentTime);
    gain.setValueAtTime(gain.value, c.currentTime);
    gain.linearRampToValueAtTime(VOLUMES[vol], c.currentTime + 3);
    music.on = true;
    music.timers.push(setTimeout(nextNote, 800), setTimeout(sparkle, 5000));
    musicTitle();
  }
  function musicStop() {
    music.on = false;
    music.timers.forEach(clearTimeout); music.timers = [];
    var c = music.ctx, gain = music.master.gain;
    gain.cancelScheduledValues(c.currentTime);
    gain.setValueAtTime(gain.value, c.currentTime);
    gain.linearRampToValueAtTime(0, c.currentTime + 2);
    musicTitle();
  }
  function changeVolume(step) {
    vol = Math.max(0, Math.min(VOLUMES.length - 1, vol + step));
    try { localStorage.setItem("cev-music-volume", String(vol)); } catch (err) { /* no storage */ }
    if (music.on) { music.master.gain.setTargetAtTime(VOLUMES[vol], music.ctx.currentTime, 0.2); }
    volumeBox.textContent = CEV.t("web.music.volume", { n: vol + 1, max: VOLUMES.length });
    beside(volumeBox, buttons.music);
    clearTimeout(volumeTimer);
    volumeTimer = setTimeout(function () { volumeBox.hidden = true; }, 1500);
  }
  buttons.music.addEventListener("wheel", function (e) {
    e.preventDefault();
    if (e.deltaY) { changeVolume(e.deltaY < 0 ? 1 : -1); }
  }, { passive: false });
  musicTitle();

  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  // the page height also changes without scrolling (index filters, formulas drawn)
  if ("ResizeObserver" in window) { new ResizeObserver(update).observe(document.body); }
  update();
  setTimeout(update, 500);  // after formulas and fonts

  // 15/11: "<" and ">" (after the title, in the buttons at the bottom right since 22/11): the page before / after in the history of the browser (its own buttons may
  // be hidden or far); greyed when there is none (the Navigation API; without it, ">" stays available)
  var histBack = document.getElementById("hist-back"), histFwd = document.getElementById("hist-forward");
  if (histBack && histFwd) {
    var paintHist = function () {
      var nav = window.navigation;
      histBack.disabled = nav && "canGoBack" in nav ? !nav.canGoBack : history.length < 2;
      histFwd.disabled = nav && "canGoForward" in nav ? !nav.canGoForward : false;
    };
    histBack.addEventListener("click", function () { history.back(); });
    histFwd.addEventListener("click", function () { history.forward(); });
    if (window.navigation && window.navigation.addEventListener) { window.navigation.addEventListener("currententrychange", paintHist); }
    window.addEventListener("pageshow", paintHist);
    paintHist();
  }
})();
