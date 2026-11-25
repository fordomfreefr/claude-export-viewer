/* "Lancer": runs a .jsx / .tsx / .html file of Claude (or a React / HTML artifact) in a frame under it.
 *
 * The frame is sandboxed without allow-same-origin: no access to the site, its storage or the archive;
 * its Content-Security-Policy forbids the network, unless the user agrees to download what is missing.
 * For JSX, the libraries of the program (run-libs.js, built by tools/build_run_libs.mjs: React, ReactDOM,
 * Recharts, lucide-react, lodash, d3, Tailwind, TypeScript as the JSX translator) are handed to the frame,
 * which makes blob: URLs and an import map of them; shadcn components ("@/components/ui/…") get simple
 * stand-ins. Labels from i18n.js (CEV.t). */
(function () {
  "use strict";
  var t = function (k, a) { return window.CEV && CEV.t ? CEV.t(k, a) : k; };
  var libsLoading = null;

  function loadLibs() {
    if (window.CEV_RUN_LIBS) { return Promise.resolve(); }
    if (!libsLoading) {
      libsLoading = new Promise(function (ok, ko) {
        var s = document.createElement("script");
        s.src = "../run-libs.js";
        s.onload = function () { ok(); };
        s.onerror = function () { libsLoading = null; ko(new Error("run-libs.js")); };
        document.head.appendChild(s);
      });
    }
    return libsLoading;
  }

  // --- What the program needs --------------------------------------------------------------------
  var IMPORT = /(?:^|[;\s])import\s+(?!type\s)(?:[\w*{}\s,$]+?\s+from\s+)?["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)|require\(\s*["']([^"']+)["']\s*\)/g;

  function importsOf(code) {
    var out = [], m;
    IMPORT.lastIndex = 0;
    while ((m = IMPORT.exec(code))) {
      var s = m[1] || m[2] || m[3];
      if (out.indexOf(s) < 0) { out.push(s); }
    }
    return out;
  }

  // {download: [specifiers esm.sh can give], absent: [project files, never available]}
  function missingJsx(code) {
    var libs = window.CEV_RUN_LIBS || {}, res = { download: [], absent: [] };
    importsOf(code).forEach(function (s) {
      if (libs[s] || /^lodash\/[\w.]+$/.test(s) || /^@\/components\/ui\//.test(s)) { return; }
      if (/^(\.|\/|@\/)/.test(s)) { res.absent.push(s); } else { res.download.push(s); }
    });
    return res;
  }

  function missingHtml(code) {
    var res = { download: [], absent: [] }, re = /<(?:script|link|img|iframe)\b[^>]*?\s(?:src|href)\s*=\s*["']?(https?:\/\/[^"'\s>]+)/gi, m;
    while ((m = re.exec(code))) {
      var host = m[1].replace(/^https?:\/\/([^/]+).*$/, "$1");
      if (res.download.indexOf(host) < 0) { res.download.push(host); }
    }
    return res;
  }

  // --- The frame ---------------------------------------------------------------------------------------
  function csp(net) {
    var n = net ? " https:" : "";
    return "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' blob: data:" + n +
      "; style-src 'unsafe-inline' blob: data:" + n + "; img-src data: blob:" + n + "; font-src data: blob:" + n +
      "; media-src data: blob:" + n + "; connect-src" + (net ? " https:" : " 'none'") + "; form-action 'none'";
  }

  function htmlDoc(code, net) {
    var meta = '<meta http-equiv="Content-Security-Policy" content="' + csp(net) + '">';
    // first thing of the document, before any script of the page
    return /<head[^>]*>/i.test(code) ? code.replace(/<head[^>]*>/i, function (h) { return h + meta; })
      : meta + code;
  }

  function jsxDoc(net) {
    return "<!doctype html><html><head><meta charset=\"utf-8\">" +
      '<meta http-equiv="Content-Security-Policy" content="' + csp(net) + '">' +
      "<style>body{margin:0;font-family:system-ui,sans-serif}#cev-msg{padding:1rem;color:#666;font:14px system-ui}" +
      "#cev-msg.err{color:#b91c1c;white-space:pre-wrap;font:13px ui-monospace,monospace}</style></head>" +
      "<body><div id=\"cev-msg\"></div><div id=\"root\"></div><script>(" + runner.toString() + ")();<\/script></body></html>";
  }

  // --- Visuals of claude.ai (show_widget): its design tokens, light or dark, and the height of the content ---
  var RAMPS = { purple: ["#EEEDFE", "#AFA9EC", "#534AB7", "#3C3489", "#CECBF6", "#26215C"],
    teal: ["#E1F5EE", "#5DCAA5", "#0F6E56", "#085041", "#9FE1CB", "#04342C"],
    coral: ["#FAECE7", "#F0997B", "#993C1D", "#712B13", "#F5C4B3", "#4A1B0C"],
    pink: ["#FBEAF0", "#ED93B1", "#993556", "#72243E", "#F4C0D1", "#4B1528"],
    gray: ["#F1EFE8", "#B4B2A9", "#5F5E5A", "#444441", "#D3D1C7", "#2C2C2A"],
    blue: ["#E6F1FB", "#85B7EB", "#185FA5", "#0C447C", "#B5D4F4", "#042C53"],
    green: ["#EAF3DE", "#97C459", "#3B6D11", "#27500A", "#C0DD97", "#173404"],
    amber: ["#FAEEDA", "#EF9F27", "#854F0B", "#633806", "#FAC775", "#412402"],
    red: ["#FCEBEB", "#F09595", "#A32D2D", "#791F1F", "#F7C1C1", "#501313"] };  // 50 200 600 800 100 900

  function widgetCss(dark) {
    var v = dark ? {
      s0: "#1f1e1d", s1: "#2b2a28", s2: "#30302e", s3: "#3a3937", t1: "#faf9f5", t2: "#c2c0b6", t3: "#9c9a92",
      b1: "rgba(255,255,255,0.15)", b2: "rgba(255,255,255,0.3)", b3: "rgba(255,255,255,0.4)" } : {
      s0: "#f5f4ef", s1: "#F1EFE8", s2: "#ffffff", s3: "#ffffff", t1: "#141413", t2: "#5F5E5A", t3: "#888780",
      b1: "rgba(31,30,29,0.15)", b2: "rgba(31,30,29,0.3)", b3: "rgba(31,30,29,0.4)" };
    var role = function (name, r) {  // bg, text, border, fill
      var c = RAMPS[r];
      return "--bg-" + name + ":" + (dark ? c[3] : c[0]) + ";--text-" + name + ":" + (dark ? c[1] : c[2]) +
        ";--border-" + name + ":" + c[1] + ";--fill-" + name + ":" + c[2] + ";";
    };
    var css = ":root{color-scheme:" + (dark ? "dark" : "light") + ";--surface-0:" + v.s0 + ";--surface-1:" + v.s1 +
      ";--surface-2:" + v.s2 + ";--surface-3:" + v.s3 + ";--surface-panel:" + v.s2 + ";--surface-popover:" + v.s3 +
      ";--text-primary:" + v.t1 + ";--text-secondary:" + v.t2 + ";--text-muted:" + v.t3 + ";--text-disabled:" + v.t3 +
      ";--border:" + v.b1 + ";--border-strong:" + v.b2 + ";--border-stronger:" + v.b3 + ";" +
      role("accent", "blue") + role("danger", "red") + role("success", "green") + role("warning", "amber") + role("pro", "purple") +
      "--font-sans:system-ui,-apple-system,'Segoe UI',sans-serif;--font-voice:Georgia,'Times New Roman',serif;" +
      "--font-mono:ui-monospace,'DejaVu Sans Mono',monospace;--radius:8px;--pad-sm:.5rem;--pad-md:.75rem;--pad-lg:1rem;" +
      "--pad-xl:1.5rem;--gap-xs:.25rem;--gap-sm:.5rem;--gap-md:.75rem;--gap-lg:1rem;--gap-xl:1.5rem;--h-control:36px}" +
      "html,body{margin:0;background:transparent}body{padding:4px 2px;font:16px/1.7 var(--font-sans);color:var(--text-primary)}" +
      "h1{font-size:22px}h2{font-size:18px}h3{font-size:16px}h1,h2,h3{font-weight:500;color:var(--text-primary);margin:0 0 .5rem}" +
      ".sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}" +
      "button{font:inherit;font-size:14px;color:var(--text-primary);background:transparent;border:.5px solid var(--border-strong);" +
      "border-radius:var(--radius);padding:6px 14px;cursor:pointer}button:hover{background:var(--surface-1)}" +
      "button:active{transform:scale(.98)}input:not([type=range]):not([type=checkbox]):not([type=radio]),select,textarea{" +
      "font:inherit;font-size:14px;height:var(--h-control);box-sizing:border-box;padding:0 10px;color:var(--text-primary);" +
      "background:var(--surface-2);border:.5px solid var(--border-strong);border-radius:var(--radius)}textarea{height:auto;padding:8px 10px}" +
      "input[type=range]{accent-color:var(--fill-accent)}svg{max-width:100%;height:auto}" +
      "svg .t,svg .th{font:14px var(--font-sans);fill:var(--text-primary)}svg .th{font-weight:500}" +
      "svg .ts{font:12px var(--font-sans);fill:var(--text-secondary)}";
    Object.keys(RAMPS).forEach(function (k) {
      var c = RAMPS[k], sel = function (s) {
        return ".c-" + k + " " + s + ",.c-" + k + ">" + s + "," + s + ".c-" + k;
      };
      css += [sel("rect"), sel("circle"), sel("ellipse"), sel("polygon")].join(",") + "{fill:" + (dark ? c[3] : c[0]) +
        ";stroke:" + (dark ? c[1] : c[2]) + "}" + ".c-" + k + " .t,.c-" + k + " .th,.c-" + k + " text{fill:" +
        (dark ? c[4] : c[3]) + "}.c-" + k + " .ts{fill:" + (dark ? c[1] : c[2]) + "}";
    });
    return css;
  }

  // The style sheet of claude.ai, when learnt from a visual the user saved (widget_host.py): the page as
  // claude.ai makes it; else the tokens above, by guess.
  function widgetDoc(code, net, dark) {
    var host = window.CEV_WIDGET_CSS;
    var tools = "<script>window.sendPrompt=function(){};window.openLink=function(){};" +
      "new ResizeObserver(function(){parent.postMessage({cevHeight:document.documentElement.scrollHeight},'*')})" +
      ".observe(document.documentElement);<\/script>";
    var css = host ? host + "\nbody{padding:16px;background:var(--surface-1);margin:0}#vis-container{overflow:visible}"
      : widgetCss(dark);
    var body = host ? '<svg style="position:absolute;width:0;height:0" aria-hidden="true"><defs><marker id="arrow" ' +
      'viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" ' +
      'fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs></svg>' +
      '<div id="vis-container">' + code + "</div>" : code;
    return "<!doctype html><html data-mode=\"" + (dark ? "dark" : "light") + "\"><head><meta charset=\"utf-8\">" +
      '<meta http-equiv="Content-Security-Policy" content="' + csp(net) + '"><style>' + css + "</style>" +
      tools + "</head><body>" + body + "</body></html>";
  }

  // A visual saved from claude.ai, as it is, with the rules of the frame first and the height reported
  function savedDoc(page, net) {
    var head = '<meta http-equiv="Content-Security-Policy" content="' + csp(net) + '">' +
      "<script>new ResizeObserver(function(){parent.postMessage({cevHeight:document.documentElement.scrollHeight},'*')})" +
      ".observe(document.documentElement);<\/script>";
    return /<head[^>]*>/i.test(page) ? page.replace(/<head[^>]*>/i, function (h) { return h + head; }) : head + page;
  }

  function pageIsDark() {
    var th = document.documentElement.getAttribute("data-theme");
    return th === "dark" || (th !== "light" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
  }

  // Runs inside the frame (no access to anything outside it): receives the libraries and the code.
  function runner() {
    var msg = document.getElementById("cev-msg");
    function fail(e) {
      msg.className = "err";
      msg.textContent = (msg.dataset.prefix || "") + (e && (e.stack || e.message) || String(e));
      msg.style.display = "";
    }
    window.addEventListener("error", function (e) { fail(e.error || e.message); });
    window.addEventListener("unhandledrejection", function (e) { fail(e.reason); });
    window.addEventListener("message", function (ev) {
      var d = ev.source === parent && ev.data && ev.data.cevRun;
      if (!d) { return; }
      msg.textContent = d.loading;
      msg.dataset.prefix = d.errorPrefix;
      var blob = function (code) { return URL.createObjectURL(new Blob([code], { type: "text/javascript" })); };
      var map = {};
      Object.keys(d.libs).forEach(function (k) { if (k !== "typescript") { map[k] = blob(d.libs[k]); } });
      // the packages of esm.sh kept in the archive (esm_cache.py): each module by its address, the name to its entry
      Object.keys(d.esm || {}).forEach(function (spec) {
        var pkg = d.esm[spec];
        Object.keys(pkg.modules).forEach(function (u) { if (!map[u]) { map[u] = blob(pkg.modules[u]); } });
        map[spec] = map[pkg.entry];
      });
      var s = document.createElement("script");
      s.src = blob(d.libs.typescript);
      s.onerror = fail;
      s.onload = function () {
        try {
          var ts = window.ts;
          var out = ts.transpileModule(d.code, { fileName: "App.tsx", compilerOptions: {  // TSX: JSX + the types Claude may write
            jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText;
          var re = /(?:^|[;\s])import\s+(?:([\w*{}\s,$]+?)\s+from\s+)?["']([^"']+)["']/g, m;
          while ((m = re.exec(out))) {
            var spec = m[2];
            if (map[spec]) { continue; }
            if (/^lodash\/[\w.]+$/.test(spec)) {
              map[spec] = blob('import _ from "lodash"; export default _[' + JSON.stringify(spec.slice(7).replace(/\.js$/, "")) + "];");
            } else if (/^@\/components\/ui\//.test(spec)) {
              map[spec] = blob(d.stubs + (m[1] || "").replace(/^[^{]*\{|\}.*$/g, "").split(",").map(function (n) {
                n = n.trim().split(/\s+as\s+/)[0];
                return n ? "export const " + n + " = stub(" + JSON.stringify(n) + ");" : "";
              }).join("\n"));
            } else if (d.net && !/^(\.|\/|@\/)/.test(spec)) {
              map[spec] = "https://esm.sh/" + spec + "?external=react,react-dom";
            }
          }
          var im = document.createElement("script");
          im.type = "importmap";
          im.textContent = JSON.stringify({ imports: map });
          document.head.appendChild(im);
          import("cev-tailwind").then(function (tw) { return tw.start(document); }).then(function () {
            return import(blob(out));
          }).then(function (mod) {
            var App = mod.default || Object.keys(mod).map(function (k) { return mod[k]; })
              .filter(function (v) { return typeof v === "function"; })[0];
            return Promise.all([import("react"), import("react-dom/client")]).then(function (r) {
              msg.style.display = "none";
              if (App) { r[1].createRoot(document.getElementById("root")).render(r[0].createElement(App)); }
            });
          }).catch(fail);
        } catch (e) { fail(e); }
      };
      document.head.appendChild(s);
    });
  }

  // shadcn/ui stand-ins: the same elements with Tailwind classes; Tabs keep their state
  var STUBS = 'import { createElement as h, forwardRef, createContext, useContext, useState } from "react";\n' +
    "const cevC = { Card: ['div', 'rounded-lg border bg-white text-gray-900 shadow-sm'], CardHeader: ['div', 'flex flex-col space-y-1.5 p-6']," +
    " CardTitle: ['h3', 'text-2xl font-semibold leading-none tracking-tight'], CardDescription: ['p', 'text-sm text-gray-500']," +
    " CardContent: ['div', 'p-6 pt-0'], CardFooter: ['div', 'flex items-center p-6 pt-0']," +
    " Button: ['button', 'inline-flex items-center justify-center rounded-md text-sm font-medium px-4 py-2 bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-50']," +
    " Input: ['input', 'flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm']," +
    " Textarea: ['textarea', 'flex min-h-20 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm']," +
    " Label: ['label', 'text-sm font-medium'], Badge: ['span', 'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold']," +
    " Alert: ['div', 'relative w-full rounded-lg border p-4'], AlertTitle: ['h5', 'mb-1 font-medium leading-none tracking-tight']," +
    " AlertDescription: ['div', 'text-sm'], Separator: ['hr', 'my-2 border-gray-200'], TabsList: ['div', 'inline-flex h-10 items-center rounded-md bg-gray-100 p-1'] };\n" +
    "const cevT = createContext(null);\n" +
    "function cevTabs({ defaultValue, value, onValueChange, className = '', children, ...p }) {\n" +
    "  const [v, setV] = useState(defaultValue); const cur = value !== undefined ? value : v;\n" +
    "  return h(cevT.Provider, { value: { cur, set: (x) => { setV(x); onValueChange && onValueChange(x); } } }, h('div', { className, ...p }, children)); }\n" +
    "function cevTabsTrigger({ value, className = '', children, ...p }) { const c = useContext(cevT) || {};\n" +
    "  return h('button', { type: 'button', onClick: () => c.set && c.set(value), className: 'px-3 py-1.5 text-sm font-medium rounded-sm ' +" +
    " (c.cur === value ? 'bg-white shadow-sm ' : 'text-gray-500 ') + className, ...p }, children); }\n" +
    "function cevTabsContent({ value, className = '', children, ...p }) { const c = useContext(cevT) || {};\n" +
    "  return c.cur === value ? h('div', { className: 'mt-2 ' + className, ...p }, children) : null; }\n" +
    "function cevProgress({ value = 0, className = '', ...p }) { return h('div', { className: 'relative h-4 w-full overflow-hidden rounded-full bg-gray-200 ' + className, ...p }," +
    " h('div', { className: 'h-full bg-gray-900', style: { width: value + '%' } })); }\n" +
    "const cevS = { Tabs: cevTabs, TabsTrigger: cevTabsTrigger, TabsContent: cevTabsContent, Progress: cevProgress };\n" +
    "function stub(n) { if (cevS[n]) return cevS[n]; const [tag, base] = cevC[n] || ['div', ''];\n" +
    "  const X = forwardRef(({ className = '', asChild, variant, size, ...p }, ref) => h(tag, { ref, className: (base + ' ' + className).trim(), ...p }));\n" +
    "  X.displayName = n; return X; }\n";

  // --- One frame, one strip under its bar --------------------------------------------------------------
  // A runnable frame (.cev-runnable, renderer._runnable) holds its bar, its code (.cev-pane) and, once run,
  // its result (.cev-run): data-state says what the strip shows — "closed", "result", "code" (10 lines) or
  // "full" (the whole code); style.css shows / greys out from it. Lancer runs (again), Code shows 10 lines,
  // ↓ the whole code and back, a click on the bar outside its buttons folds / unfolds the strip.
  function setState(box, state) {
    if (state !== "closed") { box.setAttribute("data-last", state); }
    box.setAttribute("data-state", state);
    var full = box.querySelector(".full-btn"), key = state === "code" ? "web.run.full_more" : "web.run.full_less";
    if (full) { full.title = t(key); full.setAttribute("data-i18n-attr", "title:" + key); }  // what ↓ will show
  }

  function launch(box) {
    var code = box.querySelector(".cev-pane pre code");
    if (!code) { return; }
    var kind = box.getAttribute("data-run"), text = code.textContent;
    var name = ((box.querySelector(".artifact-title") || {}).textContent || box.getAttribute("data-file") || "")
      .replace(/^▶︎?\s*/, "").trim();
    var holder = box.querySelector(".cev-saved");  // the visual saved from claude.ai, associated: run as it is
    var saved = holder ? new TextDecoder().decode(Uint8Array.from(atob(holder.textContent.trim()), function (c) {
      return c.charCodeAt(0); })) : null;
    var run = function (net, page) {
      page = page === undefined ? (saved || text) : page;
      var old = box.querySelector(".cev-run");
      if (old) { old.remove(); }
      var panel = document.createElement("div");
      panel.className = "cev-run" + (kind === "widget" ? " cev-run-auto" : "");
      if (net) {
        var n = document.createElement("div");
        n.className = "cev-run-note cev-run-netnote";
        n.textContent = t("web.run.net_on");
        panel.appendChild(n);
      }
      var f = document.createElement("iframe");
      f.className = "cev-run-frame";
      f.setAttribute("sandbox", "allow-scripts allow-forms allow-modals");
      f.setAttribute("referrerpolicy", "no-referrer");
      f.title = name;
      if (kind === "widget") {
        f.srcdoc = saved ? savedDoc(page, net) : widgetDoc(page, net, pageIsDark());
        window.addEventListener("message", function (ev) {
          if (ev.source === f.contentWindow && ev.data && ev.data.cevHeight) {
            f.style.height = Math.min(Math.ceil(ev.data.cevHeight) + 2, 4000) + "px";
          }
        });
      } else if (kind === "html") {
        f.srcdoc = htmlDoc(page, net);
      } else {
        f.srcdoc = jsxDoc(net);
        f.addEventListener("load", function () {
          var esm = {};
          importsOf(text).forEach(function (sp) { if (window.CEV_ESM && window.CEV_ESM[sp]) { esm[sp] = window.CEV_ESM[sp]; } });
          f.contentWindow.postMessage({ cevRun: { libs: window.CEV_RUN_LIBS, code: text, tsx: kind === "tsx", esm: esm,
            net: net, stubs: STUBS, loading: t("web.run.loading"), errorPrefix: t("web.run.error") + "\n" } }, "*");
        }, { once: true });
      }
      panel.appendChild(f);
      box.appendChild(panel);
      setState(box, "result");
    };
    var page0;  // the page as it will run (libraries kept put inline)
    var ask = function (miss, page) {
      page0 = page;
      if (!miss.download.length && !miss.absent.length) { return run(false, page); }
      var text2 = miss.download.length ? t("web.run.ask", { list: miss.download.join(", ") }) : "";
      if (miss.absent.length) { text2 += (text2 ? "\n" : "") + t("web.run.absent", { list: miss.absent.join(", ") }); }
      CEV.confirm(text2, function () { run(miss.download.length > 0, page0); });  // "Non": nothing run
    };
    if (kind === "html" || kind === "widget") { return withLibraries(box, saved || text, run, ask); }
    loadLibs().then(loadEsm).then(function () { withPackages(box, text, ask); }, function () {
      var p = document.createElement("div");
      p.className = "cev-run cev-run-note cev-run-err";
      p.textContent = t("web.run.no_libs");
      var old = box.querySelector(".cev-run");
      if (old) { old.remove(); }
      box.appendChild(p);
      setState(box, "result");
    });
  }

  // --- Libraries of the Internet kept in the archive (cdn_cache.py, cdn-cache.js) -------------------------
  // The scripts and style sheets a page loads from https are put inline from window.CEV_CDN; one not kept
  // yet is downloaded once into the archive with the user's agreement (through the server), then used by
  // every page loading the same address. Without the server: the old way, the Internet for that run.
  var cdnLoading = null;

  function loadCdn(again) {
    if (window.CEV_CDN && !again) { return Promise.resolve(); }
    if (!cdnLoading || again) {
      cdnLoading = new Promise(function (ok) {
        var s = document.createElement("script");
        s.src = "../cdn-cache.js" + (again ? "?" + Date.now() : "");
        s.onload = s.onerror = function () { window.CEV_CDN = window.CEV_CDN || {}; ok(); };
        document.head.appendChild(s);
      });
    }
    return cdnLoading;
  }

  var LIB = /<script\b[^>]*?\ssrc\s*=\s*["']?(https:\/\/[^"'\s>]+)["']?[^>]*>\s*<\/script>|<link\b(?=[^>]*\bstylesheet\b)[^>]*?\shref\s*=\s*["']?(https:\/\/[^"'\s>]+)["']?[^>]*>/gi;

  function librariesOf(page) {
    var out = [], m;
    LIB.lastIndex = 0;
    while ((m = LIB.exec(page))) {
      var u = (m[1] || m[2]).replace(/&amp;/g, "&");
      if (out.indexOf(u) < 0) { out.push(u); }
    }
    return out;
  }

  function inlineLibraries(page) {
    return page.replace(LIB, function (all, js, css) {
      var u = (js || css).replace(/&amp;/g, "&"), kept = window.CEV_CDN[u];
      if (kept === undefined) { return all; }
      return js ? "<script>" + kept.replace(/<\/script/gi, "<\\/script") + "<\/script>"
        : "<style>" + kept.replace(/<\/style/gi, "<\\/style") + "</style>";
    });
  }

  function host(u) { return u.replace(/^https?:\/\/([^/]+).*$/, "$1"); }

  // A note in the strip of the frame (the reason a download failed…)
  function note(box, text) {
    var old = box.querySelector(".cev-run");
    if (old) { old.remove(); }
    var p = document.createElement("div");
    p.className = "cev-run cev-run-note cev-run-err";
    p.textContent = text;
    box.appendChild(p);
    box.setAttribute("data-state", "result");
  }

  function withLibraries(box, page, run, ask) {
    loadCdn().then(function () {
      var libs = librariesOf(page), missing = libs.filter(function (u) { return window.CEV_CDN[u] === undefined; });
      var rest = missingHtml(page.replace(LIB, "")).download;  // images, frames…: never kept
      var uniq = function (l) { return l.filter(function (h, i, a) { return a.indexOf(h) === i; }); };
      if (!missing.length && !rest.length) { return run(false, inlineLibraries(page)); }
      // no server, or keeping failed before on this page: the Internet for this run only, asked
      if (!missing.length || !/^https?:$/.test(location.protocol) || box.hasAttribute("data-keep-failed")) {
        return ask({ download: uniq(missing.map(host).concat(rest)), absent: [] }, inlineLibraries(page));
      }
      var hosts = uniq(missing.map(host));
      CEV.confirm(t("web.run.keep", { list: hosts.join(", ") }), function () {
        var failed = function (why) {  // said once, in the strip; the next click asks for this run only
          box.setAttribute("data-keep-failed", "");
          note(box, t("web.run.keep_failed", { why: why }));
        };
        fetch("/__cev__/token", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
          return fetch("/__cev__/cdn", { method: "POST", body: JSON.stringify({ urls: missing }),
            headers: { "X-CEV-Token": d.token, "X-CEV-Lang": CEV.lang ? CEV.lang() : "fr", "Content-Type": "application/json" } });
        }).then(function (r) {
          if (r.status === 404) { throw new Error(t("web.run.old_server")); }  // a server of an older program
          if (!r.ok) { return r.text().then(function (x) { throw new Error(r.status + " " + x); }); }
          return r.json();
        }).then(function (res) {
          return loadCdn(true).then(function () {
            var bad = res.errors || {}, urls = Object.keys(bad);
            if (urls.length) { return failed(urls.map(function (u) { return u + " — " + bad[u]; }).join("\n")); }
            if (rest.length) { return ask({ download: rest, absent: [] }, inlineLibraries(page)); }
            run(false, inlineLibraries(page));
          });
        }).catch(function (e) { failed(e && e.message || String(e)); });
      });
    });
  }

  // --- Packages of esm.sh kept in the archive (esm_cache.py, esm-cache.js; PT-m3, 08/11) ------------------------
  // A React program importing packages CEV does not bundle: with the server, the user is asked once to download
  // them into the archive; then the program runs without the Internet (also opened as a file). "Non": nothing
  // run; a download that failed is said, and the next click asks for the Internet for that run only.
  var esmLoading = null;
  function loadEsm(again) {
    if (window.CEV_ESM && !again) { return Promise.resolve(); }
    if (!esmLoading || again) {
      esmLoading = new Promise(function (ok) {
        var s = document.createElement("script");
        s.src = "../esm-cache.js" + (again ? "?" + Date.now() : "");
        s.onload = s.onerror = function () { window.CEV_ESM = window.CEV_ESM || {}; ok(); };
        document.head.appendChild(s);
      });
    }
    return esmLoading;
  }

  function withPackages(box, code, ask) {
    var miss = missingJsx(code), kept = window.CEV_ESM || {};
    var missing = miss.download.filter(function (sp) { return !kept[sp]; });
    if (!missing.length) { return ask({ download: [], absent: miss.absent }); }
    if (!/^https?:$/.test(location.protocol) || box.hasAttribute("data-keep-failed")) {
      return ask({ download: missing, absent: miss.absent });  // the Internet for this run only, asked
    }
    CEV.confirm(t("web.run.keep_esm", { list: missing.join(", ") }), function () {
      var failed = function (why) {
        box.setAttribute("data-keep-failed", "");
        note(box, t("web.run.keep_failed", { why: why }));
      };
      fetch("/__cev__/token", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
        return fetch("/__cev__/esm", { method: "POST", body: JSON.stringify({ specs: missing }),
          headers: { "X-CEV-Token": d.token, "X-CEV-Lang": CEV.lang ? CEV.lang() : "fr", "Content-Type": "application/json" } });
      }).then(function (r) {
        if (r.status === 404) { throw new Error(t("web.run.old_server")); }
        if (!r.ok) { return r.text().then(function (x) { throw new Error(r.status + " " + x); }); }
        return r.json();
      }).then(function (res) {
        return loadEsm(true).then(function () {
          var bad = res.errors || {}, names = Object.keys(bad);
          if (names.length) { return failed(names.map(function (n) { return n + " — " + bad[n]; }).join("\n")); }
          ask({ download: [], absent: miss.absent });
        });
      }).catch(function (e) { failed(e && e.message || String(e)); });
    });
  }

  // From outside (msg.js: a hit of the search in the code): show the whole code
  window.CEV = window.CEV || {};
  CEV.showCode = function (el) {
    var box = el.closest && el.closest(".cev-runnable");
    if (box) { setState(box, "full"); }
  };

  document.addEventListener("click", function (e) {
    var box = e.target.closest ? e.target.closest(".cev-runnable") : null;
    if (!box) { return; }
    var state = box.getAttribute("data-state");
    if (e.target.closest(".run-btn")) {
      e.preventDefault();
      launch(box);
    } else if (e.target.closest(".code-btn")) {
      if (state !== "code" && state !== "full") { setState(box, "code"); }
    } else if (e.target.closest(".full-btn")) {
      if (state !== "result") { setState(box, state === "code" ? "full" : "code"); }  // folded: the 10 lines
    } else if (e.target.closest(".cf-link")) {
      setState(box, "closed");  // its menu (files.js) is then the only strip; a choice reloads the page
    } else if (e.target.closest(".cev-bar") && !e.target.closest("a, button, input, select, textarea, .copy-btn")) {
      if (state !== "closed") { setState(box, "closed"); }  // the bar only folds; it never opens anything
    }
  });
})();
