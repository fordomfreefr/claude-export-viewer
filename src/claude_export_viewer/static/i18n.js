/* Language of the pages.
 *
 * Texts are written in the language of the build and marked with their key
 * (data-i18n="key", data-i18n-args='{…}', data-i18n-attr="title:key"); dates are
 * <time data-fmt="date|datetime|day">. This script rewrites them in the chosen
 * language: the one picked in the index menu (remembered by the browser), or
 * else the browser's language, or else English. The texts of every language
 * come from i18n-data.js (window.CEV_I18N), written next to this file.
 */
(function () {
  "use strict";
  var DATA = window.CEV_I18N || { languages: { en: "English" }, default: "en", build: "en", texts: { en: {} } };
  var STORE = "cev-lang";
  var current = null;

  function known(code) {
    if (!code) { return null; }
    var base = String(code).toLowerCase().split(/[-_]/)[0];
    return Object.prototype.hasOwnProperty.call(DATA.languages, base) ? base : null;
  }

  function initial() {
    try {
      var saved = known(localStorage.getItem(STORE));
      if (saved) { return saved; }
    } catch (e) { /* storage unavailable */ }
    var wanted = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language];
    for (var i = 0; i < wanted.length; i++) {
      var code = known(wanted[i]);
      if (code) { return code; }
    }
    return DATA.default;
  }

  function raw(lang, key) {
    var texts = DATA.texts[lang] || {};
    return Object.prototype.hasOwnProperty.call(texts, key) ? texts[key] : undefined;
  }

  function pick(value, lang, args) {
    if (value && typeof value === "object") {
      var n = Number(args && args.n) || 0;
      var cat = "other";
      try { cat = new Intl.PluralRules(lang).select(n); } catch (e) { /* old browser */ }
      return value[cat] !== undefined ? value[cat] : value.other;
    }
    return typeof value === "string" ? value : undefined;
  }

  function pad(x) { return (x < 10 ? "0" : "") + x; }

  // Same patterns as the program ("fmt.date": "%d/%m/%Y"…), so that pages and files agree.
  function strftime(pattern, d, utc) {
    var parts = utc
      ? { d: d.getUTCDate(), m: d.getUTCMonth() + 1, Y: d.getUTCFullYear(), H: d.getUTCHours(), M: d.getUTCMinutes() }
      : { d: d.getDate(), m: d.getMonth() + 1, Y: d.getFullYear(), H: d.getHours(), M: d.getMinutes() };
    return pattern.replace(/%([dmYHM])/g, function (_, k) { return k === "Y" ? String(parts.Y) : pad(parts[k]); });
  }

  function formatDate(iso, kind, lang) {
    lang = lang || current;
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return ""; }
    var datePattern = t("fmt.date", null, lang);
    if (kind === "day") {  // the date of an export, as written (no time zone shift)
      var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
      return m ? datePattern.replace("%Y", m[1]).replace("%m", m[2]).replace("%d", m[3]) : strftime(datePattern, d, true);
    }
    var date = strftime(datePattern, d, false);
    if (kind !== "datetime") { return date; }
    return t("fmt.datetime", { date: date, time: strftime("%H:%M", d, false) }, lang);
  }

  function formatNumber(x, lang) {
    try {
      return new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(x);
    } catch (e) {
      return x.toFixed(1);
    }
  }

  function show(value, lang) {
    if (value && typeof value === "object") {
      if (value.$datetime) { return formatDate(value.$datetime, "datetime", lang); }
      if (value.$date) { return formatDate(value.$date, "date", lang); }
      if (value.$day) { return formatDate(value.$day, "day", lang); }
      if (value.$num !== undefined) { return formatNumber(value.$num, lang); }
    }
    return value;
  }

  function t(key, args, lang) {
    lang = lang || current || DATA.default;
    var text = pick(raw(lang, key), lang, args);
    if (text === undefined && lang !== DATA.default) { text = pick(raw(DATA.default, key), DATA.default, args); }
    if (text === undefined) { return key; }
    return text.replace(/\{(\w+)\}/g, function (whole, name) {
      return args && Object.prototype.hasOwnProperty.call(args, name) ? String(show(args[name], lang)) : whole;
    });
  }

  function argsOf(el) {
    var a = el.getAttribute("data-i18n-args");
    if (!a) { return null; }
    try { return JSON.parse(a); } catch (e) { return null; }
  }

  function apply(root) {
    root = root || document;
    Array.prototype.forEach.call(root.querySelectorAll("[data-i18n]"), function (el) {
      el.textContent = t(el.getAttribute("data-i18n"), argsOf(el));
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-i18n-attr]"), function (el) {
      el.getAttribute("data-i18n-attr").split(";").forEach(function (pair) {
        var i = pair.indexOf(":");
        if (i > 0) { el.setAttribute(pair.slice(0, i), t(pair.slice(i + 1), argsOf(el))); }
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll("time[data-fmt]"), function (el) {
      var text = formatDate(el.getAttribute("datetime"), el.getAttribute("data-fmt"));
      if (text) { el.textContent = text; }
    });
  }

  // Markdown embedded in the pages holds markers ⟦cev:key:{args}⟧ for its labels.
  function resolve(markdown, lang) {
    return markdown.replace(/⟦cev:([\w.]+)(?::(.*?))?⟧/g, function (_, key, json) {
      var args = null;
      if (json) { try { args = JSON.parse(json); } catch (e) { args = null; } }
      return t(key, args, lang);
    });
  }

  function setLanguage(code, remember) {
    current = known(code) || DATA.default;
    if (remember) {
      try { localStorage.setItem(STORE, current); } catch (e) { /* storage unavailable */ }
    }
    document.documentElement.lang = current;
    apply(document);
    try { document.dispatchEvent(new CustomEvent("cev-language", { detail: current })); } catch (e) { /* old browser */ }
  }

  window.CEV = {
    t: function (key, args) { return t(key, args); },
    lang: function () { return current; },
    languages: DATA.languages,
    formatDate: formatDate,
    resolve: resolve,
    apply: apply,
    setLanguage: setLanguage
  };

  setLanguage(initial(), false);

  // Language menu (index page only)
  var select = document.getElementById("lang-select");
  if (select) {
    Object.keys(DATA.languages).forEach(function (code) {
      var option = document.createElement("option");
      option.value = code;
      option.textContent = DATA.languages[code];
      select.appendChild(option);
    });
    select.value = current;
    select.addEventListener("change", function () { setLanguage(select.value, true); });
  }
})();
