/* Topics of the conversations (index page): one topic at most per conversation.
 * Read from topics-data.js (window.CEV_TOPICS), so that filtering works on a page opened
 * as a file; changed only through the local server (page opened by the desktop icon),
 * which keeps them in the archive. */
(function () {
  "use strict";
  var state = normalize(window.CEV_TOPICS);
  var items = [];
  var token = null;
  var lastList = null;  // list of the topics when the cells were last drawn
  var filter = document.getElementById("filter-topic");
  var manageButton = document.getElementById("topics-manage");
  var manager = document.getElementById("topics-manager");

  function normalize(data) {
    data = data && typeof data === "object" ? data : {};
    return { topics: Array.isArray(data.topics) ? data.topics : [], assign: data.assign || {} };
  }

  function sorted() {
    return state.topics.slice().sort(function (a, b) { return a.localeCompare(b, CEV.lang(), { sensitivity: "base" }); });
  }

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) { e.textContent = text; }
    return e;
  }

  // An element whose text follows the language of the page (i18n.js rewrites data-i18n).
  function i18nEl(tag, key, args, attrs) {
    var e = el(tag, attrs, CEV.t(key, args || {}));
    e.setAttribute("data-i18n", key);
    if (args) { e.setAttribute("data-i18n-args", JSON.stringify(args)); }
    return e;
  }

  function send(body, onError) {
    return fetch("/__cev__/topics", {
      method: "POST",
      headers: { "X-CEV-Token": token, "X-CEV-Lang": CEV.lang(), "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) {
        if (r.ok) {
          return r.json().then(function (data) { state = normalize(data); refresh(); return true; });
        }
        return r.text().then(function (msg) { onError(msg); return false; });
      })
      .catch(function () { onError(CEV.t("web.admin.no_server")); return false; });
  }

  // --- the cell on the right of a conversation ---------------------------------
  function showError(cell, msg) {
    var e = el("div", { "class": "topic-error", role: "alert" }, msg);
    cell.appendChild(e);
    setTimeout(function () { if (e.parentNode) { e.parentNode.removeChild(e); } }, 5000);
  }

  function renderCell(item) {
    var cell = item.querySelector(".topic-cell");
    var topic = item.dataset.topic || "";
    cell.textContent = "";
    if (!token) {  // read only: the topic as a label
      if (topic) {
        var badge = el("span", { "class": "topic-badge", title: CEV.t("web.topics.read_only"),
          "data-i18n-attr": "title:web.topics.read_only" }, topic);
        cell.appendChild(badge);
      }
      return;
    }
    var select = el("select", { "class": "topic-select" + (topic ? "" : " empty"),
      "aria-label": CEV.t("web.topics.cell_title"), "data-i18n-attr": "aria-label:web.topics.cell_title" });
    select.appendChild(i18nEl("option", topic ? "web.topics.remove" : "web.topics.choose", null, { value: "" }));
    if (topic) { select.appendChild(el("option", { value: topic }, topic)); }
    select.value = topic;
    // The full list is built only when the menu is about to open: with a thousand
    // conversations, a thousand complete menus would make every change slow.
    function fill() {
      if (select.dataset.full) { return; }
      select.dataset.full = "1";
      while (select.options.length > 1) { select.remove(1); }
      sorted().forEach(function (name) { select.appendChild(el("option", { value: name }, name)); });
      select.appendChild(i18nEl("option", "web.topics.new", null, { "data-new": "1" }));  // "New topic…"
      select.value = topic;
    }
    ["focus", "mousedown", "pointerdown", "touchstart"].forEach(function (type) {
      select.addEventListener(type, fill, { passive: true });
    });
    select.addEventListener("change", function () {
      if (select.selectedOptions[0] && select.selectedOptions[0].hasAttribute("data-new")) {
        askName(item, cell);
        return;
      }
      send({ action: "assign", uuid: item.dataset.uuid, topic: select.value }, function (msg) {
        select.value = topic;
        showError(cell, msg);
      });
    });
    cell.appendChild(select);
  }

  function askName(item, cell) {
    cell.textContent = "";
    var form = el("form", { "class": "topic-new" });
    var input = el("input", { type: "text", maxlength: "40", autocomplete: "off", spellcheck: "false",
      placeholder: CEV.t("web.topics.new_placeholder") });
    var ok = i18nEl("button", "web.topics.ok", null, { type: "submit", "class": "admin-btn small" });
    form.appendChild(input);
    form.appendChild(ok);
    cell.appendChild(form);
    input.focus();
    var done = false;
    function cancel() { if (!done) { done = true; renderCell(item); } }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!input.value.trim()) { cancel(); return; }
      done = true;
      send({ action: "assign", uuid: item.dataset.uuid, topic: input.value }, function (msg) {
        renderCell(item);
        showError(cell, msg);
      });
    });
    input.addEventListener("keydown", function (event) { if (event.key === "Escape") { cancel(); } });
    form.addEventListener("focusout", function (event) {
      if (!form.contains(event.relatedTarget)) { setTimeout(cancel, 150); }
    });
  }

  // --- filter of the index ----------------------------------------------------------
  function renderFilter() {
    var current = filter.value;
    while (filter.options.length > 2) { filter.remove(2); }  // keep "every topic" and "without topic"
    sorted().forEach(function (name) { filter.appendChild(el("option", { value: name }, name)); });
    // (" " is "without topic": no topic name is blank)
    filter.value = current === "" || current === " " || state.topics.indexOf(current) >= 0 ? current : "";
    filter.hidden = state.topics.length === 0;
  }

  // --- managing the topics (rename, delete) -------------------------------------------
  function renderManager() {
    if (!manager || !token) { return; }
    var list = document.getElementById("topics-list");
    list.textContent = "";
    document.getElementById("topics-empty").hidden = state.topics.length > 0;
    var counts = {};
    Object.keys(state.assign).forEach(function (u) { counts[state.assign[u]] = (counts[state.assign[u]] || 0) + 1; });
    sorted().forEach(function (name) {
      var li = el("li", { "class": "topics-row" });
      var label = el("span", { "class": "topics-name" }, name);
      var count = i18nEl("span", "web.topics.count", { n: counts[name] || 0 }, { "class": "topics-count" });
      var rename = i18nEl("button", "web.topics.rename", null, { type: "button", "class": "admin-btn small" });
      var remove = i18nEl("button", "web.topics.delete", null, { type: "button", "class": "admin-btn small danger" });
      li.appendChild(label);
      li.appendChild(count);
      li.appendChild(rename);
      li.appendChild(remove);
      rename.addEventListener("click", function () { renameRow(li, name); });
      remove.addEventListener("click", function () { confirmDelete(li, name); });
      list.appendChild(li);
    });
  }

  function managerError(msg) {
    var e = document.getElementById("topics-error");
    e.textContent = msg;
    e.hidden = false;
  }

  function renameRow(li, name) {
    li.textContent = "";
    var form = el("form", { "class": "topic-new" });
    var input = el("input", { type: "text", maxlength: "40", autocomplete: "off", spellcheck: "false" });
    input.value = name;
    form.appendChild(input);
    form.appendChild(i18nEl("button", "web.topics.ok", null, { type: "submit", "class": "admin-btn small" }));
    var cancel = i18nEl("button", "web.topics.cancel", null, { type: "button", "class": "admin-btn small" });
    form.appendChild(cancel);
    li.appendChild(form);
    input.focus();
    input.select();
    cancel.addEventListener("click", renderManager);
    input.addEventListener("keydown", function (event) { if (event.key === "Escape") { renderManager(); } });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var value = input.value.trim();
      if (!value || value === name) { renderManager(); return; }
      var followFilter = filter.value === name;
      send({ action: "rename", topic: name, name: value }, managerError).then(function (ok) {
        if (ok && followFilter) {
          var target = state.topics.filter(function (n) { return n.toLowerCase() === value.toLowerCase(); })[0];
          if (target) { filter.value = target; filter.dispatchEvent(new Event("change")); }
        }
      });
    });
  }

  function confirmDelete(li, name) {
    li.textContent = "";
    li.appendChild(i18nEl("span", "web.topics.confirm_delete", { name: name }, { "class": "topics-confirm" }));
    var yes = i18nEl("button", "web.topics.delete", null, { type: "button", "class": "admin-btn small danger" });
    var no = i18nEl("button", "web.topics.cancel", null, { type: "button", "class": "admin-btn small" });
    li.appendChild(yes);
    li.appendChild(no);
    no.addEventListener("click", renderManager);
    yes.addEventListener("click", function () { send({ action: "delete", topic: name }, managerError); });
  }

  // --- everything ------------------------------------------------------------------------
  function refresh(all) {
    var list = state.topics.join("\n");
    var same = !all && list === lastList;
    lastList = list;
    items.forEach(function (item) {
      var topic = state.assign[item.dataset.uuid] || "";
      var cell = item.querySelector(".topic-cell");
      if (same && (item.dataset.topic || "") === topic && cell.firstChild && cell.firstChild.tagName === "SELECT") {
        return;  // unchanged (its menu is rebuilt when opened)
      }
      if (topic) { item.dataset.topic = topic; } else { delete item.dataset.topic; }
      renderCell(item);
    });
    renderFilter();
    renderManager();
    var err = document.getElementById("topics-error");
    if (err) { err.hidden = true; }
    document.dispatchEvent(new CustomEvent("cev-topics"));
  }

  window.CEVTopics = {
    init: function (list) {
      items = list;
      items.forEach(function (item) {
        var topic = state.assign[item.dataset.uuid];
        if (topic) { item.dataset.topic = topic; }
        renderCell(item);
      });
      renderFilter();
    }
  };

  // the local server answered (admin.js): topics can be changed
  document.addEventListener("cev-admin", function (event) {
    token = event.detail.token;
    if (manageButton) { manageButton.hidden = false; }
    refresh(true);
  });
  function showManager(on) {
    manager.hidden = !on;
    manageButton.setAttribute("aria-expanded", on ? "true" : "false");
    if (on) { renderManager(); }
  }
  if (manageButton) {
    // a second click closes it, like the cross
    manageButton.addEventListener("click", function () { showManager(manager.hidden); });
    document.getElementById("topics-close").addEventListener("click", function () { showManager(false); });
  }
  // the topics are sorted in the order of the language
  document.addEventListener("cev-language", function () { if (items.length) { refresh(true); } });
})();
