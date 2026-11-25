// Builds src/claude_export_viewer/static/run-libs.js: the libraries of the "Lancer" button (run.js),
// as ES modules sharing one React, held as strings in window.CEV_RUN_LIBS (read by the parent page, then
// handed to the sandboxed frame, which makes blob: URLs and an import map of them).
//
//   node tools/build_run_libs.mjs <node_modules> <git clones> <lodash clone>
//
// <node_modules>: react, react-dom, scheduler, d3 (+ d3-*), clsx, tailwindcss, typescript, esbuild.
// <git clones>: recharts (v2.15.0), react-smooth (v4.0.4), recharts-scale, react-transition-group (v4.4.5),
// dom-helpers (v5.2.1), fast-equals (v5.0.1, for react-fast-compare), eventemitter3 (5.0.1), decimal.js-light (v2.5.1),
// prop-types (v15.8.1), lucide (0.469.0, folder icons/). <lodash clone>: lodash/lodash at 4.17.21.
// Licences: static/run-libs-LICENSES.txt.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const [NM, SRC, LODASH] = process.argv.slice(2).map((p) => path.resolve(p));
const require = createRequire(path.join(NM, "x.js"));
const esbuild = require("esbuild");
const OUT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../src/claude_export_viewer/static/run-libs.js");
const TMP = fs.mkdtempSync("/tmp/cev-run-");
const REACT_EXTERNAL = ["react", "react-dom", "react-dom/client", "react/jsx-runtime", "react/jsx-dev-runtime"];
const libs = {};

async function bundle(name, contents, opts = {}) {
  const r = await esbuild.build({
    stdin: { contents, resolveDir: TMP, loader: "js" },
    bundle: true, write: false, minify: true, format: "esm", platform: "browser", target: "es2020",
    nodePaths: [NM], define: { "process.env.NODE_ENV": '"production"' }, legalComments: "none",
    logLevel: "error", ...opts,
  });
  libs[name] = r.outputFiles[0].text;
}

// A CommonJS package as an ES module: its default export and each of its keys as a named export
function cjsWrapper(spec, keys) {
  const named = keys.filter((k) => /^[A-Za-z_$][\w$]*$/.test(k) && k !== "default");
  return `import M from ${JSON.stringify(spec)}; export default M; export const {${named.join(",")}} = M;`;
}

// --- React: one bundle holding react, react-dom, react-dom/client and the JSX runtime (one copy of React,
// which the hooks need), then one small module per name, re-exporting its part ---
const keys = (spec) => Object.keys(require(spec));
const parts = { react: "R", "react-dom": "D", "react-dom/client": "C", "react/jsx-runtime": "J" };
await bundle("cev-react-all", Object.entries(parts).map(([spec, v]) =>
  `import ${v} from ${JSON.stringify(require.resolve(spec))};`).join("") + `export { ${Object.values(parts).join(", ")} };`);
for (const [spec, v] of Object.entries(parts)) {
  const named = keys(spec).filter((k) => /^[A-Za-z_$][\w$]*$/.test(k) && k !== "default");
  libs[spec] = `import { ${v} } from "cev-react-all"; export default ${v}; export const {${named.join(",")}} = ${v};`;
}
libs["react/jsx-dev-runtime"] = libs["react/jsx-runtime"];

// --- lodash (the build of the repository) and lodash/<name> ---
const lodashFile = path.join(LODASH, "dist", "lodash.js");
await bundle("lodash", cjsWrapper(lodashFile, Object.keys(require(lodashFile))));

// --- d3 ---
await bundle("d3", `export * from "d3";`);

// --- recharts 2.15 from its sources, with its dependencies from their repositories ---
const shim = (file, code) => { const p = path.join(TMP, file); fs.writeFileSync(p, code); return p; };
const alias = {
  "react-smooth": path.join(SRC, "react-smooth/src/index.js"),
  "recharts-scale": path.join(SRC, "recharts-scale/src/index.js"),
  "react-transition-group": path.join(SRC, "react-transition-group/src/index.js"),
  "dom-helpers": path.join(SRC, "dom-helpers/src"),
  // react-smooth 4.0.4 compares its props with react-fast-compare: the deep equality of fast-equals
  "react-fast-compare": shim("react-fast-compare.js", `export { deepEqual as default } from ${JSON.stringify(path.join(SRC, "fast-equals/src/index.ts"))};`),
  "eventemitter3": path.join(SRC, "eventemitter3/index.js"),
  "decimal.js-light": path.join(SRC, "decimal.js-light/decimal.js"),
  "prop-types": path.join(SRC, "prop-types/index.js"),
  "victory-vendor/d3-scale": "d3-scale",
  "victory-vendor/d3-shape": "d3-shape",
  // React 19 elements: what recharts asks of react-is
  "react-is": shim("react-is.js", `import { Fragment, isValidElement } from "react";
    export const isFragment = (e) => isValidElement(e) && e.type === Fragment;
    export const isElement = isValidElement;`),
  "tiny-invariant": shim("tiny-invariant.js", `export default function invariant(c, m) {
    if (!c) throw new Error("Invariant failed" + (m ? ": " + (typeof m === "function" ? m() : m) : "")); }`),
};
const lodashPlugin = { name: "lodash", setup(b) {
  b.onResolve({ filter: /^lodash(\/.*)?$/ }, (a) => ({ path: a.path, namespace: "lodash" }));
  b.onLoad({ filter: /.*/, namespace: "lodash" }, (a) => a.path === "lodash"
    ? { contents: `export { default } from ${JSON.stringify(lodashFile)};`, resolveDir: TMP }
    : { contents: `import _ from ${JSON.stringify(lodashFile)}; export default _.${a.path.slice(7).replace(/\.js$/, "")};`,
        resolveDir: TMP });
} };
await bundle("recharts", `export * from ${JSON.stringify(path.join(SRC, "recharts/src/index.ts"))};`,
  { external: REACT_EXTERNAL, alias, plugins: [lodashPlugin], loader: { ".js": "jsx" }, jsx: "automatic" });

// --- lucide-react from the icons of lucide (SVG + JSON of aliases) ---
const icons = path.join(SRC, "lucide/icons");
const pascal = (s) => s.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join("");
const nodes = {}, names = [];
for (const f of fs.readdirSync(icons).filter((f) => f.endsWith(".svg")).sort()) {
  const id = f.slice(0, -4);
  const svg = fs.readFileSync(path.join(icons, f), "utf8");
  const inner = svg.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>[\s\S]*$/, "");
  nodes[id] = [...inner.matchAll(/<(\w+)([^>]*?)\/?>/g)].map(([, tag, attrs]) =>
    [tag, Object.fromEntries([...attrs.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, k, v]) => [k, v]))]);
  let aliases = [];
  try {
    aliases = (JSON.parse(fs.readFileSync(path.join(icons, id + ".json"), "utf8")).aliases || [])
      .map((a) => (typeof a === "string" ? a : a.name));
  } catch { /* no JSON */ }
  for (const n of [id, ...aliases]) names.push([pascal(n), id]);
}
const seen = new Set();
const exportsList = [];
for (const [p, id] of names) {
  for (const n of [p, p + "Icon", "Lucide" + p]) {
    if (!seen.has(n)) { seen.add(n); exportsList.push(`export const ${n} = I(${JSON.stringify(id)});`); }
  }
}
await bundle("lucide-react", `import { createElement, forwardRef } from "react";
const N = ${JSON.stringify(nodes)};
const kebab = (s) => s.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
export const Icon = forwardRef(({ color = "currentColor", size = 24, strokeWidth = 2, absoluteStrokeWidth,
    className = "", children, iconNode = [], ...rest }, ref) => createElement("svg", { ref,
  xmlns: "http://www.w3.org/2000/svg", width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: color, strokeWidth: absoluteStrokeWidth ? (Number(strokeWidth) * 24) / Number(size) : strokeWidth,
  strokeLinecap: "round", strokeLinejoin: "round", className: ["lucide", className].join(" ").trim(), ...rest },
  ...iconNode.map(([t, a], i) => createElement(t, { key: i, ...a })), ...(Array.isArray(children) ? children : [children])));
export const createLucideIcon = (name, iconNode) => {
  const C = forwardRef(({ className = "", ...p }, ref) => createElement(Icon, { ref, iconNode,
    className: ("lucide-" + kebab(name) + " " + className).trim(), ...p }));
  C.displayName = name;
  return C;
};
const cache = {};
const I = (id) => cache[id] || (cache[id] = createLucideIcon(id.split("-").map((w) => w[0].toUpperCase() + w.slice(1)).join(""), N[id]));
${exportsList.join("\n")}
export const icons = Object.fromEntries(Object.keys(N).map((id) => [id.split("-").map((w) => w[0].toUpperCase() + w.slice(1)).join(""), I(id)]));
`, { external: REACT_EXTERNAL });

// --- Tailwind (v4) in the browser: the classes found in the page, compiled again when new ones appear ---
const css = (f) => fs.readFileSync(path.join(NM, "tailwindcss", f), "utf8");
await bundle("cev-tailwind", `import { compile } from "tailwindcss";
const files = ${JSON.stringify({ "index.css": css("index.css"), "theme.css": css("theme.css"),
  "preflight.css": css("preflight.css"), "utilities.css": css("utilities.css") })};
export async function start(doc) {
  const load = async (id, base) => {
    const f = id === "tailwindcss" ? "index.css" : id.replace(/^(\\.\\/|tailwindcss\\/)/, "");
    return { path: f, base, content: files[f] || "" };
  };
  // the defaults of Tailwind 3, which the programs of Claude are written for (light grey borders, hand on buttons)
  const compiler = await compile('@import "tailwindcss"; @layer base { *, ::after, ::before, ::backdrop, ::file-selector-button'
    + ' { border-color: var(--color-gray-200, currentColor); } button:not(:disabled), [role="button"]:not(:disabled)'
    + ' { cursor: pointer; } }', { base: "/", loadStylesheet: load });
  const style = doc.createElement("style");
  doc.head.appendChild(style);
  const seen = new Set();
  const scan = () => {
    let added = false;
    for (const el of doc.querySelectorAll("[class]")) {
      for (const c of (el.getAttribute("class") || "").split(/\\s+/)) if (c && !seen.has(c)) { seen.add(c); added = true; }
    }
    if (added) style.textContent = compiler.build([...seen]);
  };
  scan();
  new MutationObserver(scan).observe(doc.documentElement, { subtree: true, childList: true, attributes: true,
    attributeFilter: ["class"] });
}`, { loader: { ".css": "text" } });

// --- TypeScript: turns .jsx / .tsx into ES modules (classic script, global ts) ---
const ts = await esbuild.build({ entryPoints: [path.join(NM, "typescript/lib/typescript.js")], bundle: true,
  write: false, minify: true, format: "iife", globalName: "ts", platform: "browser", target: "es2020",
  external: ["fs", "path", "os", "crypto", "perf_hooks", "inspector", "source-map-support", "buffer", "module", "worker_threads"],
  legalComments: "none", logLevel: "error" });
libs["typescript"] = ts.outputFiles[0].text;

const versions = Object.fromEntries(["react", "react-dom", "d3", "tailwindcss", "typescript"].map((p) => [p, JSON.parse(fs.readFileSync(path.join(NM, p, "package.json"), "utf8")).version]));
versions.recharts = "2.15.0"; versions["lucide-react"] = "0.469.0 (icônes de lucide)"; versions.lodash = "4.17.21";
fs.writeFileSync(OUT, `/* Built by tools/build_run_libs.mjs: ${JSON.stringify(versions)}. Licences: run-libs-LICENSES.txt */\n`
  + `window.CEV_RUN_LIBS = ${JSON.stringify(libs)};\nwindow.CEV_RUN_VERSIONS = ${JSON.stringify(versions)};\n`);
for (const [k, v] of Object.entries(libs)) console.log(k.padEnd(22), (v.length / 1024).toFixed(0).padStart(6), "Ko");
console.log("total", (fs.statSync(OUT).size / 1048576).toFixed(2), "Mo ->", OUT);
