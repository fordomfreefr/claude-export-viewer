/* Index: the tabs "Vue d'ensemble", "Gestion des données", "Filtres" (14/11) and the overview (a line, the tiles
 * and a chart of the conversations active each week; a click on a week sets the period filter to it).
 * Everything is computed from the list of the page. */
(function () {
  "use strict";
  var list = document.getElementById("conversation-list");
  if (!list) { return; }
  var DAY = 864e5, WEEKS = 52;

  // --- Tabs (14/11): "Vue d'ensemble", "Gestion des données", "Filtres", one open at a time; a click on the open
  // one closes it; ← → (Home, End) go from one to the next. At the opening: the overview, or the data when there
  // is no conversation yet (that tab comes with the local server: admin.js calls CEV.indexTab).
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".index-tab"));
  function panelOf(tab) { return document.getElementById(tab.getAttribute("aria-controls")); }
  function openTab(tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on || (!tab && t === shownTabs()[0]) ? 0 : -1;
      var p = panelOf(t);
      if (p) { p.hidden = !on; }
    });
  }
  function shownTabs() { return tabs.filter(function (t) { return !t.hidden; }); }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { openTab(t.getAttribute("aria-selected") === "true" ? null : t); });
    t.addEventListener("keydown", function (e) {
      var shown = shownTabs(), i = shown.indexOf(t), to = null;
      if (e.key === "ArrowRight") { to = shown[(i + 1) % shown.length]; }
      else if (e.key === "ArrowLeft") { to = shown[(i - 1 + shown.length) % shown.length]; }
      else if (e.key === "Home") { to = shown[0]; }
      else if (e.key === "End") { to = shown[shown.length - 1]; }
      if (!to) { return; }
      e.preventDefault();
      openTab(to);
      to.focus();
    });
  });
  window.CEV.indexTab = function (name, open) {  // the tab shown (the data one comes with the server), opened if asked
    var tab = document.getElementById("tab-" + name);
    if (!tab) { return; }
    tab.hidden = false;
    if (open) { openTab(tab); } else if (!tabs.some(function (t) { return t.getAttribute("aria-selected") === "true"; })) { openTab(null); }
  };
  // at the opening: the overview, or the data when there is no conversation yet (15/11: that tab is always shown;
  // without the server it says so); admin.js may have asked for the data before this script ran
  openTab(window.CEV.dataTabLater ? document.getElementById("tab-data")
    : document.getElementById("tab-overview") || document.getElementById("tab-data"));

  // --- Overview -------------------------------------------------------------------------
  var sumEl = document.getElementById("dash-sum");
  if (!sumEl) { return; }
  var items = Array.prototype.slice.call(list.querySelectorAll(".conversation-item"));
  function nf(n) { try { return new Intl.NumberFormat(CEV.lang()).format(n); } catch (e) { return String(n); } }
  function tok(n) { return CEV.t("web.tokens.short", { n: { $tok: n } }); }
  function monday(d) {
    var x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() - (x.getDay() + 6) % 7);
    return x;
  }
  function iso(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  var convs = items.map(function (item) {
    var c = Date.parse(item.dataset.date || item.dataset.activity), l = Date.parse(item.dataset.activity || item.dataset.date);
    return { c: c, l: l, n: +item.dataset.messages || 0, tok: +item.dataset.tokens || 0, deleted: item.dataset.deleted === "1" };
  });
  // The 52 weeks shown end ``back`` weeks before this one; < and > move them by 26 weeks,
  // from the week of the oldest conversation to this week.
  var STEP = 26, back = 0;
  var oldest = Math.min.apply(null, convs.map(function (c) { return isNaN(c.c) ? Infinity : c.c; }).concat([Date.now()]));
  function weeksEnding(back) {
    var start = monday(new Date());
    start.setDate(start.getDate() - 7 * (WEEKS - 1 + back));
    var out = [];
    for (var w = 0; w < WEEKS; w++) {
      var s = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 7 * w);
      var e = new Date(s.getFullYear(), s.getMonth(), s.getDate() + 7);
      out.push({ s: s, e: e, n: convs.filter(function (c) { return !isNaN(c.c) && c.c < e.getTime() && c.l >= s.getTime(); }).length });
    }
    return out;
  }
  var current = weeksEnding(0), weeks = current;
  var prev = document.getElementById("dash-prev"), next = document.getElementById("dash-next");
  function move(step) {
    var before = {};  // height of each bar shown, by week
    Array.prototype.forEach.call(document.querySelectorAll("#dash-bars .dash-bar"), function (b) {
      before[b.getAttribute("data-key")] = b.style.height;
    });
    var labels = Array.prototype.map.call(document.querySelectorAll("#dash-axis > span"), function (x) { return x.textContent; });
    back = Math.max(0, back + step);
    weeks = weeksEnding(back);
    document.querySelectorAll(".dash-bar.sel").forEach(function (s) { s.classList.remove("sel"); });
    render();
    slide(step, before, labels);
  }
  prev.addEventListener("click", function () { if (!prev.disabled) { move(STEP); } });
  next.addEventListener("click", function () { if (!next.disabled) { move(-STEP); } });

  function render() {
    var msgs = convs.reduce(function (a, c) { return a + c.n; }, 0);
    var tokens = convs.reduce(function (a, c) { return a + c.tok; }, 0);
    var deleted = convs.filter(function (c) { return c.deleted; }).length;
    var box = document.getElementById("dash-tiles");
    var size = Number(box.getAttribute("data-size")) || 0, saved = Number(box.getAttribute("data-backup")) || 0;
    var days = saved ? Math.floor((Date.now() - saved * 1000) / DAY) : -1;
    // AF-f4 (15/11): a backup is advised when there is none, when it is over 30 days old, or older than the latest
    // import; the tile then in brick, a click on it opens the tab of the data at the button "Sauvegarder"
    var imported = Number(box.getAttribute("data-import")) || 0;
    var due = !convs.length ? "" : !saved ? "web.dash.save_due_never" : days > 30 ? "web.dash.save_due_old"
      : imported && saved < imported ? "web.dash.save_due_import" : "";

    sumEl.innerHTML = "";
    var parts = [CEV.t("web.index.count", { n: convs.length }), CEV.t("web.messages", { n: msgs }), tok(tokens)];
    parts.forEach(function (p, i) {
      if (i) { sumEl.appendChild(document.createTextNode(" · ")); }
      var b = document.createElement("span");
      b.textContent = p;
      if (i === parts.length - 1) { b.className = "dash-tok"; }
      sumEl.appendChild(b);
    });
    var rough = document.createElement("i");
    rough.textContent = " " + CEV.t("web.dash.rough");
    sumEl.appendChild(rough);
    document.getElementById("dash-week").textContent =
      CEV.t("web.dash.this_week", { count: CEV.t("web.index.count", { n: current[WEEKS - 1].n }) });
    var max = Math.max.apply(null, weeks.map(function (x) { return x.n; }).concat([1]));
    prev.disabled = weeks[0].s.getTime() <= oldest;  // nothing older
    next.disabled = back === 0;  // this week is shown

    var tiles = [
      [nf(convs.length), CEV.t("web.dash.t_convs", { n: convs.length }), deleted ? CEV.t("web.dash.t_deleted", { n: deleted }) : ""],
      [nf(msgs), CEV.t("web.dash.t_msgs", { n: msgs }), convs.length ? CEV.t("web.dash.t_avg", { n: Math.round(msgs / convs.length) }) : ""],
      [CEV.t("web.dash.tok_value", { n: { $tok: tokens } }), CEV.t("web.dash.t_tokens"), ""],
      [CEV.t("web.size_mb", { size: { $num: size / 1048576 } }), CEV.t("web.dash.t_size"),
        days < 0 ? CEV.t("web.dash.t_never") : days === 0 ? CEV.t("web.dash.t_saved_today") : CEV.t("web.dash.t_saved", { n: days })]
    ];  // 14/11: no tile of the topics (not a figure of the conversations imported)
    var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    document.getElementById("dash-tiles").innerHTML = tiles.map(function (t, i) {
      var late = due && i === tiles.length - 1;
      return '<div class="dash-tile' + (late ? ' due" role="button" tabindex="0" id="dash-save-due" title="' + esc(CEV.t(due)) : "") +
        '"><div class="v">' + esc(t[0]) + '</div><div class="l">' + esc(t[1]) +
        '</div><div class="s">' + esc(late ? CEV.t(due) : t[2]) + "</div></div>";
    }).join("");
    var saveBtn = document.getElementById("admin-backup");
    if (saveBtn) {  // the reminder in the tab of the data too
      saveBtn.classList.toggle("due", Boolean(due));
      saveBtn.title = due ? CEV.t(due) : CEV.t("web.backup_title");
    }
    var tile = document.getElementById("dash-save-due");
    if (tile) {
      var go = function () { if (CEV.indexTab) { CEV.indexTab("data", true); } if (saveBtn) { saveBtn.focus(); } };
      tile.addEventListener("click", go);
      tile.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    }
    var bars = document.getElementById("dash-bars");
    bars.innerHTML = "";
    weeks.forEach(function (x, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "dash-bar";
      b.style.height = Math.max(2, Math.round(100 * x.n / max)) + "%";
      b.title = CEV.t("web.dash.bar_title", { from: { $date: x.s.toISOString() },
        to: { $date: new Date(x.e.getTime() - DAY / 2).toISOString() }, n: x.n });
      b.setAttribute("data-week", String(i));
      b.setAttribute("data-key", iso(x.s));
      bars.appendChild(b);
    });
    var axis = document.getElementById("dash-axis");
    axis.innerHTML = [0, 13, 26, 39, 51].map(function (i) {
      var label;
      try { label = weeks[i].s.toLocaleDateString(CEV.lang(), { month: "short", year: "numeric" }); } catch (e) { label = iso(weeks[i].s); }
      return "<span>" + esc(label) + "</span>";
    }).join("");
  }

  // < and >: the bars slide by 26 weeks instead of being drawn again at once. The weeks that
  // leave are drawn beside the new ones and go out of the frame; the weeks still shown go from
  // their former height to the new one (the scale follows the highest week of the 52).
  var SLIDE = 400;
  function slide(step, before, labels) {
    var bars = document.getElementById("dash-bars");
    if (!bars.animate || (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches)) { return; }
    var dir = step > 0 ? 1 : -1, shown = {};  // older weeks come in from the left
    Array.prototype.forEach.call(bars.querySelectorAll(".dash-bar"), function (b) {
      var key = b.getAttribute("data-key");
      shown[key] = true;
      if (before[key]) { b.animate([{ height: before[key] }, { height: b.style.height }], { duration: SLIDE, easing: "ease-in-out" }); }
    });
    var ghost = document.createElement("div");
    ghost.className = "dash-ghost";
    ghost.style[dir > 0 ? "left" : "right"] = "calc(100% + 3px)";
    Object.keys(before).sort().forEach(function (key) {
      if (shown[key]) { return; }
      var g = document.createElement("i");
      g.style.height = before[key];
      ghost.appendChild(g);
    });
    bars.appendChild(ghost);
    var a = bars.animate([{ transform: "translateX(" + (-dir * 50) + "%)" }, { transform: "translateX(0)" }],
      { duration: SLIDE, easing: "ease-in-out" });
    a.onfinish = a.oncancel = function () { ghost.remove(); };
    // the dates under the bars follow them: the former ones that leave are drawn beside the new
    // ones (half a frame further), those still in the frame are the new ones at the same place
    var axis = document.getElementById("dash-axis"), old = document.createElement("div");
    old.className = "dash-axis-ghost";
    old.style.left = (dir * 50) + "%";
    labels.forEach(function (text, i) {
      var sp = document.createElement("span");
      sp.textContent = text;
      if (dir > 0 ? i <= 2 : i >= 2) { sp.style.visibility = "hidden"; }
      old.appendChild(sp);
    });
    axis.appendChild(old);
    var b = axis.animate([{ transform: "translateX(" + (-dir * 50) + "%)" }, { transform: "translateX(0)" }],
      { duration: SLIDE, easing: "ease-in-out" });
    b.onfinish = b.oncancel = function () { old.remove(); };
  }

  document.getElementById("dash-bars").addEventListener("click", function (e) {
    var b = e.target.closest(".dash-bar");
    if (!b) { return; }
    var x = weeks[+b.getAttribute("data-week")];
    var period = document.getElementById("filter-period");
    period.value = "custom";
    document.getElementById("period-from").value = iso(x.s);
    document.getElementById("period-to").value = iso(new Date(x.e.getTime() - DAY / 2));
    period.dispatchEvent(new Event("change"));
    Array.prototype.forEach.call(document.querySelectorAll(".dash-bar.sel"), function (s) { s.classList.remove("sel"); });
    b.classList.add("sel");
    list.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  document.addEventListener("cev-language", render);
  document.addEventListener("cev-site-size", function (e) {  // admin.js: measured by the server (after a cleaning…)
    document.getElementById("dash-tiles").setAttribute("data-size", String(e.detail));
    render();
  });
  document.addEventListener("cev-backup", function () {  // admin.js: a backup was just written
    document.getElementById("dash-tiles").setAttribute("data-backup", String(Date.now() / 1000));
    render();
  });
  render();
})();
