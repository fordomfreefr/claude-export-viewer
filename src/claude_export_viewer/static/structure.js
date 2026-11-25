/* Structure view of a conversation (AE-c1, maquettes « Structure » and « ordre logique » of 03-07/11): the shape
 * of the thread as a drawing, and under it the numbered list of the questions. Shown by the switch "Lecture ·
 * Plan · Structure" (plan.js calls CEV.structure.show()); read from the messages of the page.
 * - The followed thread is one continuous line from left to right; each other version (an edited question,
 *   a retried answer, a part deleted on claude.ai) leaves it as a dotted line, in a lane below. The column
 *   is the rank in the thread: the versions of one question (or one answer) are in the same column, one
 *   under the other. The branches leaving one branch are placed from the one leaving furthest right (the
 *   nearest lane) to the one leaving furthest left, each followed by its own branches: the lines do not
 *   cross (checked on the usual cases, not proved for every tree).
 * - Questions: blue circles, filled on a thread, empty in another version (a long number: a pill); answers
 *   of Claude: small empty grey circles.
 * - Numbers, those of the actual order whatever the order shown: the questions of the followed thread 1, 2,
 *   3…; a branch leaving after question k of its thread (0 before the first) is k.1, k.2… in the order of
 *   time; its questions add a level (k.b.1…), except a branch starting with a question (edited question):
 *   that question takes the number of the branch.
 * - "Ordre : réel · logique". The logical order applies the moves of the user (annotations "moves", through
 *   the local server), a question always moving with all that follows it on its thread:
 *   . dropped on a question: under it (another version of it): the lowest lane, a thick curved line from the
 *     answer it then follows, drawn as a thread (thick, filled questions); listed right under that question;
 *   . dropped on an answer: after it, in its lane; what followed that answer becomes another version of the
 *     question moved (the lowest lane, thick curved line);
 *   . ✂ on the line coming to a question (shown when the mouse is on it): cut there, the part stays alone
 *     (the lowest lane, no line before it): another subject.
 *   The question moved is ringed; "↺" on its line puts it back. A logical link (annotations "relations"),
 *   in both orders: Shift + drag from a point to another; a green curve with its arrows; a click on it:
 *   → ← ↔, then removed. Every thick curved line and every link has a handle in its middle (shown when the
 *   mouse is on it): drag it to bend the line, double click: the automatic curve. "↶ Annuler" takes back the
 *   last change (10 at most, kept between visits); "Réinitialisation" (after Oui / Non) removes every move
 *   and link of the conversation.
 * - The list: one line per question (its title in bold, else the start of its text), per other answer of
 *   Claude, per answer holding a link; shifted by level. Moves and links are written at the end of the lines.
 * - The mouse over a point or a line: its date, and the point and its line light up together. A click: the
 *   question and all its answers under the list (its other answers folded in their frames); a double click:
 *   from that question to the end of its branch, in the order shown. These are the messages of the page
 *   themselves, so that everything of the reading view works on them. */
(function () {
  "use strict";
  var root = document.querySelector(".messages[data-conversation]");
  var bar = document.getElementById("plan-bar");
  if (!root || !bar) { return; }
  var conv = root.getAttribute("data-conversation");
  var NS = "http://www.w3.org/2000/svg";
  var STEP = 40, DY = 34, TOP = 20;
  var A = window.CEV && CEV.annot, served = false;
  var panel = null, pic = null, last = null;

  function get(key, def) { try { var v = localStorage.getItem(key); return v === null ? def : v; } catch (e) { return def; } }
  function put(key, v) { try { localStorage.setItem(key, v); } catch (e) { /* no storage */ } }
  var order = get("cev-struct-order", "real") === "logic" ? "logic" : "real";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }
  function svg(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) { e.textContent = text; }
    return e;
  }
  function message(uuid) { return root.querySelector('.message[data-uuid="' + CSS.escape(uuid) + '"]'); }
  function date(uuid) {
    var m = message(uuid), t = m && m.querySelector(":scope > .message-time time");
    return t ? t.textContent.trim() : "";
  }
  function data() { return (A ? A.data() : window.CEV_ANNOTATIONS) || {}; }
  function titles() { return (data().titles || {})[conv] || {}; }
  function moves() { return (data().moves || {})[conv] || {}; }
  function relations() { return (data().relations || {})[conv] || []; }
  function undos() { return (data().structure_history || {})[conv] || 0; }
  function post(body) { return A.post(body).catch(A.failed); }

  // --- The tree of the page: messages and frames of the other versions, in the order of the page ----------
  function tree(box) {
    var out = [];
    Array.prototype.forEach.call(box.children, function (x) {
      if (x.matches("details.removed-part")) {
        var inner = x.querySelector(":scope > .removed-messages");
        out.push({ branch: inner ? tree(inner) : [] });
      } else if (x.matches(".message-human[data-uuid], .message-assistant[data-uuid]")) {
        var t = x.querySelector(".content-text");
        out.push({ q: x.classList.contains("message-human"), uuid: x.getAttribute("data-uuid"),
                   text: t ? t.textContent.replace(/\s+/g, " ").trim() : "" });
      }
    });
    return out;
  }
  function find(items, uuid) {  // {list, index} of a message
    for (var i = 0; i < items.length; i++) {
      if (items[i].uuid === uuid) { return { list: items, index: i }; }
      if (items[i].branch) { var f = find(items[i].branch, uuid); if (f) { return f; } }
    }
    return null;
  }
  function holds(items, uuid) { return Boolean(find(items, uuid)); }
  function prune(items) {  // a frame emptied by a move goes
    for (var i = items.length - 1; i >= 0; i--) {
      if (items[i].branch) { prune(items[i].branch); if (!items[i].branch.length) { items.splice(i, 1); } }
    }
  }
  // the logical order: each move, in the order they were made; one onto what follows itself is left out.
  // applied: {question: its move}
  function logical(items, ms, applied) {
    Object.keys(ms).forEach(function (q) {
      var m = ms[q], from = find(items, q);
      if (!from || (m.how !== "cut" && !find(items, m.to))) { return; }
      var part = from.list.slice(from.index);
      if (m.to && holds(part, m.to)) { return; }
      from.list.splice(from.index);
      if (applied) { applied[q] = m; }
      var frame = { branch: part, moved: q, kind: m.how === "under" ? "moved" : m.how, bend: m.bend };
      if (m.how === "cut") { from.list.push(frame); return; }  // in its place, without its line
      var to = find(items, m.to);
      if (m.how === "under") {
        // under the first question of a cut part (11/11): another version of a question without line, so cut too
        var host = owner(items, to.list);
        if (host && host.kind === "cut" && to.list.slice(0, to.index).every(function (x) { return x.branch; })) { frame.kind = "cut"; }
        to.list.splice(to.index, 0, frame);
        return;
      }
      // after an answer: what followed it becomes another version of the question moved
      var rest = to.list.splice(to.index + 1);
      if (rest.some(function (x) { return !x.branch; })) {
        to.list.push({ branch: rest, moved: q, kind: "pushed", bend: m.bend });
      } else {
        Array.prototype.push.apply(to.list, rest);
      }
      Array.prototype.push.apply(to.list, part);
    });
    prune(items);
    return items;
  }
  function owner(items, list) {  // the frame whose branch is that list
    for (var i = 0; i < items.length; i++) {
      if (!items[i].branch) { continue; }
      if (items[i].branch === list) { return items[i]; }
      var o = owner(items[i].branch, list);
      if (o) { return o; }
    }
    return null;
  }
  function under(items, q, target) {  // is target in what follows q on its thread (a move there: refused)
    var f = find(items, q);
    return Boolean(f && holds(f.list.slice(f.index), target));
  }

  // --- Layout: rows (one per message), columns, lanes ---------------------------------------------------------
  function layout(items, labels, applied) {
    var rows = [], branches = [{ parent: null }];
    (function go(list, br, prev, prefix, head, kind) {
      var lastQ = prefix + "0", c = 0, at = {}, lead = Boolean(kind);
      list.forEach(function (e) {
        if (e.branch) {
          at[lastQ] = (at[lastQ] || 0) + 1;
          var label = lastQ + "." + at[lastQ];
          var headQ = Boolean(e.branch.length && !e.branch[0].branch && e.branch[0].q);
          branches.push({ parent: br, kind: e.kind || null, moved: e.moved || null, bend: e.bend });
          var nb = branches.length - 1, start = rows.length;
          go(e.branch, nb, prev, label + ".", headQ ? label : null, e.kind);  // the followed thread goes on from prev
          if (rows[start]) {
            rows[start].fork = rows[start].prev;
            if (!headQ) { rows[start].branchNum = label; }
          }
          return;
        }
        var r = { q: e.q, uuid: e.uuid, text: e.text, br: br, prev: prev, moved: applied ? applied[e.uuid] : null, lead: lead };
        lead = false;
        if (e.q) {
          if (head) { r.num = head; head = null; } else { c += 1; r.num = prefix + c; }
          lastQ = r.num;
        }
        rows.push(r);
        prev = rows.length - 1;
      });
    })(items, 0, null, "", null);
    if (labels) {  // the numbers of the actual order
      rows.forEach(function (r) { var l = labels[r.uuid] || {}; r.num = l.num; r.branchNum = l.branchNum; });
    }
    rows.forEach(function (r) { r.col = r.prev === null ? 0 : rows[r.prev].col + 1; });
    var span = {}, kids = {}, b;
    branches.forEach(function (x, i) { kids[i] = []; });
    for (b = 1; b < branches.length; b++) {
      kids[branches[b].parent].push(b);
      var cols = rows.filter(function (r) { return r.br === b; }).map(function (r) { return r.col; });
      span[b] = cols.length ? [Math.min.apply(null, cols) - 1, Math.max.apply(null, cols)] : [0, 0];
    }
    var lanes = { 0: 0 }, used = {};
    var place = function (parent) {
      kids[parent].filter(function (k) { return !branches[k].kind; })
        .sort(function (x, y) { return span[y][0] - span[x][0] || x - y; }).forEach(function (k) {
          var lo = span[k][0], hi = span[k][1], lane = lanes[parent] + 1;
          var busy = function (l) { return (used[l] || []).some(function (s) { return !(hi < s[0] || lo > s[1]); }); };
          while (busy(lane)) { lane++; }
          (used[lane] = used[lane] || []).push([lo, hi]);
          lanes[k] = lane;
          place(k);
        });
    };
    var lowest = function () { return Math.max.apply(null, Object.keys(used).map(Number).concat([0])); };
    place(0);
    for (b = 1; b < branches.length; b++) {  // a part moved, pushed aside or cut: always the lowest lane
      if (!branches[b].kind) { continue; }
      lanes[b] = lowest() + 1;
      (used[lanes[b]] = used[lanes[b]] || []).push(span[b]);
      place(b);
    }
    var depth = { 0: 0 };
    for (b = 1; b < branches.length; b++) { depth[b] = branches[b].kind === "cut" ? 0 : depth[branches[b].parent] + 1; }
    rows.forEach(function (r) { r.solid = r.br === 0 || Boolean(branches[r.br].kind); });
    return { rows: rows, lanes: lanes, depth: depth, branches: branches };
  }
  function shape() {  // the layout of the order shown
    var real = layout(tree(root));
    if (order !== "logic") { return real; }
    var labels = {}, applied = {};
    real.rows.forEach(function (r) { labels[r.uuid] = { num: r.num, branchNum: r.branchNum }; });
    return layout(logical(tree(root), moves(), applied), labels, applied);
  }
  function label(L, i) {  // the number of a row; an answer: "R" and the number of its question
    var r = L.rows[i];
    if (r.q) { return r.num || ""; }
    if (r.branchNum) { return r.branchNum; }
    for (var p = r.prev; p !== null; p = L.rows[p].prev) {
      if (L.rows[p].q) { return CEV.t("web.struct.answer", { n: L.rows[p].num }); }
    }
    return CEV.t("web.struct.answer", { n: "" });
  }

  // --- Curves with a handle: a quadratic curve through the handle H, at "bend" from the middle of the chord,
  // on its normal (-dy, dx) -----------------------------------------------------------------------------------
  function frame(p1, p2) {
    var dx = p2[0] - p1[0], dy = p2[1] - p1[1], len = Math.sqrt(dx * dx + dy * dy) || 1;
    return { m: [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2], n: [-dy / len, dx / len], len: len };
  }
  function curve(p1, p2, bend, r1, r2) {  // {d, h}: the path (from the edges of the points) and the handle
    var f = frame(p1, p2), h = [f.m[0] + f.n[0] * bend, f.m[1] + f.n[1] * bend];
    var c = [2 * h[0] - f.m[0], 2 * h[1] - f.m[1]];
    var edge = function (p, r) {
      var dx = c[0] - p[0], dy = c[1] - p[1], n = Math.sqrt(dx * dx + dy * dy) || 1;
      return [p[0] + dx / n * r, p[1] + dy / n * r];
    };
    var a = edge(p1, r1), b = edge(p2, r2);
    return { d: "M" + a[0] + "," + a[1] + " Q" + c[0] + "," + c[1] + " " + b[0] + "," + b[1], h: h };
  }
  function defaultBend(p1, p2, link) {
    var f = frame(p1, p2);
    if (link) { return (f.n[0] >= 0 ? 1 : -1) * (24 + f.len * 0.12); }  // a link: bent to the right
    return (f.n[1] >= 0 ? 1 : -1) * f.len * 0.18;  // a thick line: bent downwards, away from its column
  }
  function bendable(s, kind, key, p1, p2, bend, r1, r2, cls, markers) {
    var g = svg("g", { "class": "st-curve", "data-kind": kind, "data-key": key });
    var b = typeof bend === "number" ? bend : defaultBend(p1, p2, kind === "rel");
    var c = curve(p1, p2, b, r1, r2);
    var line = svg("path", { "class": cls, d: c.d });
    if (markers) { Object.keys(markers).forEach(function (k) { line.setAttribute(k, markers[k]); }); }
    g.appendChild(line);
    var hit = svg("path", { "class": "st-curve-hit" + (kind === "rel" ? " st-rel-hit" : ""), d: c.d });
    if (kind === "rel") { hit.setAttribute("data-rel", key); hit.appendChild(svg("title", {}, CEV.t("web.struct.link_title"))); }
    g.appendChild(hit);
    if (served) {
      var handle = svg("circle", { "class": "st-handle", cx: c.h[0], cy: c.h[1], r: 5 });
      handle.appendChild(svg("title", {}, CEV.t("web.struct.bend_title")));
      g.appendChild(handle);
    }
    g._geo = { p1: p1, p2: p2, r1: r1, r2: r2 };
    s.appendChild(g);
  }

  // --- The drawing ------------------------------------------------------------------------------------------
  function draw(L) {
    var rows = L.rows, lanes = L.lanes, index = {};
    rows.forEach(function (r, i) { index[r.uuid] = i; });
    var x = function (i) { return 30 + rows[i].col * STEP; };
    var y = function (i) { return TOP + lanes[rows[i].br] * DY; };
    var rad = function (i) { return rows[i].q ? 10 : 6; };
    var maxCol = 0, maxLane = 0;
    rows.forEach(function (r) { maxCol = Math.max(maxCol, r.col); maxLane = Math.max(maxLane, lanes[r.br]); });
    var s = svg("svg", { "class": "st-svg", width: 130 + maxCol * STEP, height: TOP + maxLane * DY + 34 });
    s.appendChild(svg("title", {}, CEV.t("web.struct.help")));
    var defs = svg("defs", {}), mk = svg("marker", { id: "st-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7,
      markerHeight: 7, orient: "auto-start-reverse" });
    mk.appendChild(svg("path", { "class": "st-arrow", d: "M0,0 L10,5 L0,10 z" }));
    defs.appendChild(mk);
    s.appendChild(defs);
    var mains = rows.map(function (r, i) { return r.br === 0 ? i : -1; }).filter(function (i) { return i >= 0; });
    if (mains.length) { s.appendChild(svg("line", { "class": "st-main", x1: 12, y1: TOP, x2: x(mains[mains.length - 1]), y2: TOP })); }
    // ✂: on the line coming to a question (logical order), cut there
    if (served && order === "logic") {
      rows.forEach(function (r, i) {
        var kind = L.branches[r.br].kind;
        if (!r.q || r.prev === null || r.moved && r.moved.how === "cut" || kind === "cut" && (r.fork !== undefined || r.lead)) { return; }
        var p = r.prev, x1 = x(p), y1 = y(p), x2 = x(i), y2 = y(i);
        var g = svg("g", { "class": "st-cut", "data-cut": r.uuid });
        g.appendChild(svg("line", { "class": "st-cut-hit", x1: x1, y1: y1, x2: x2, y2: y2 }));
        var t = svg("text", { "class": "st-scissors", x: x1 + (x2 - x1) * 0.4, y: y1 + (y2 - y1) * 0.4 - 6 }, "✂");
        t.appendChild(svg("title", {}, CEV.t("web.struct.cut_title")));
        g.appendChild(t);
        s.appendChild(g);
      });
    }
    rows.forEach(function (r, i) {
      if (r.br === 0) { return; }
      var p = r.prev, x1 = p === null ? 12 : x(p), y1 = p === null ? TOP : y(p), x2 = x(i), y2 = y(i);
      var kind = L.branches[r.br].kind;
      if (kind) {  // a part moved, pushed aside or cut: thick; its line from the answer before (none when cut)
        if (r.fork === undefined && !r.lead) { s.appendChild(svg("line", { "class": "st-main", x1: x1, y1: y1, x2: x2, y2: y2 })); }
        else if (kind !== "cut" && p !== null) {
          bendable(s, "move", L.branches[r.br].moved, [x1, y1], [x2, y2], L.branches[r.br].bend, rad(p), rad(i), "st-main st-join");
        }
        return;
      }
      s.appendChild(r.fork !== undefined
        ? svg("path", { "class": "st-alt", d: "M" + x1 + "," + y1 + " C" + (x1 + 22) + "," + y1 + " " + (x2 - 22) + "," + y2 + " " + x2 + "," + y2 })
        : svg("line", { "class": "st-alt", x1: x1, y1: y1, x2: x2, y2: y2 }));
    });
    // the logical links
    relations().forEach(function (rel, k) {
      var a = index[rel.a], b = index[rel.b];
      if (a === undefined || b === undefined) { return; }
      var markers = {};
      if (rel.dir !== "back") { markers["marker-end"] = "url(#st-arrow)"; }
      if (rel.dir !== "to") { markers["marker-start"] = "url(#st-arrow)"; }
      bendable(s, "rel", String(k), [x(a), y(a)], [x(b), y(b)], rel.bend, rad(a), rad(b), "st-rel", markers);
    });
    rows.forEach(function (r, i) {
      var solid = r.solid, cx = x(i), cy = y(i);
      if (r.moved) { s.appendChild(svg("circle", { "class": "st-moved", cx: cx, cy: cy, r: 12 })); }
      if (r.q) {
        var num = r.num || "", node;
        if (solid && num.length > 2) {  // a long number on a thread: a pill
          var w = 6.2 * num.length + 8;
          node = svg("rect", { "class": "st-q", x: cx - w / 2, y: cy - 8, width: w, height: 16, rx: 8, "data-uuid": r.uuid });
        } else {
          node = svg("circle", { "class": solid ? "st-q" : "st-q st-off", cx: cx, cy: cy, r: solid ? 8 : 6.5, "data-uuid": r.uuid });
        }
        node.appendChild(svg("title", {}, date(r.uuid)));
        s.appendChild(node);
        s.appendChild(svg("text", { "class": solid ? "st-n" : "st-n st-off", x: cx, y: solid ? cy + 3.5 : cy + 19 }, num));
      } else {
        s.appendChild(svg("circle", { "class": "st-a", cx: cx, cy: cy, r: 4, "data-uuid": r.uuid }))
          .appendChild(svg("title", {}, date(r.uuid)));
        if (r.branchNum) { s.appendChild(svg("text", { "class": "st-n st-a-n", x: cx, y: cy + 16 }, r.branchNum)); }
      }
    });
    return s;
  }

  // --- The list ---------------------------------------------------------------------------------------------
  function list(L) {
    var t = titles(), box = el("div", "st-list"), rows = L.rows, heads = {}, rels = relations(), index = {};
    rows.forEach(function (r, i) { index[r.uuid] = i; if (r.br && heads[r.br] === undefined) { heads[r.br] = i; } });
    var linked = function (uuid) { return rels.some(function (x) { return x.a === uuid || x.b === uuid; }); };
    // 18/11: the lines in the order and with the indents of the drawing (the user's example) — from each
    // bubble, what follows it in the drawing (rows[].prev); several questions after one answer (versions, a
    // part moved after it): one step to the right each, in the order of the drawing (top first); a question
    // alone after an answer: the same step; the other answers of a question: one step to the right, before
    // what follows its answer. The starts of the thread (versions of the first question) in the order asked;
    // a part cut into a subject apart: a start too.
    var kids = { root: [] }, seq = [], level = {};
    rows.forEach(function (r, i) {
      var cut = heads[r.br] === i && L.branches[r.br].kind === "cut";
      var p = r.prev === null || cut ? "root" : r.prev;
      (kids[p] = kids[p] || []).push(i);
    });
    var byLane = function (a, b) { return (L.lanes[rows[a].br] || 0) - (L.lanes[rows[b].br] || 0) || a - b; };
    var visit = function (i, lvl) {
      seq.push(i);
      level[i] = lvl;
      var r = rows[i], next = (kids[i] || []).slice().sort(byLane);
      if (r.q) {
        var main = next.filter(function (k) { return !rows[k].q && rows[k].br === r.br; })[0];
        next.forEach(function (k) { if (k !== main) { visit(k, lvl + 1); } });
        if (main !== undefined) { visit(main, lvl); }
        return;
      }
      next.forEach(function (k) { visit(k, next.length > 1 ? lvl + 1 : lvl); });
    };
    kids.root.sort(function (a, b) { return a - b; }).forEach(function (i) { visit(i, 0); });
    seq.forEach(function (i) {
      var r = rows[i];
      if (!r.q && !r.branchNum && !linked(r.uuid)) { return; }
      var main = r.solid;
      var line = el("div", "st-row" + (main ? "" : " st-off"));
      line.setAttribute("data-uuid", r.uuid);
      line.title = date(r.uuid);
      line.style.paddingLeft = (level[i] * 22) + "px";
      line.appendChild(el("span", "st-num" + (main && r.q ? "" : " st-off") + (r.q ? "" : " st-ans"), label(L, i)));
      if (r.q) {
        var title = (t[r.uuid] || {}).text;
        line.appendChild(el(title ? "b" : "span", "st-text", title || r.text));
      } else {
        var other = el("i", "st-text", CEV.t("web.struct.other_answer"));
        other.setAttribute("data-i18n", "web.struct.other_answer");
        line.appendChild(other);
      }
      if (r.moved) {
        var to = index[r.moved.to];
        var tag = r.moved.how === "cut" ? CEV.t("web.struct.cut") : to === undefined ? "" :
          CEV.t(r.moved.how === "after" ? "web.struct.after" : "web.struct.moved", { n: label(L, to) });
        if (tag) { line.appendChild(el("span", "st-tag", tag)); }
        if (served) {
          var undo = el("button", "st-undo", "↺");
          undo.type = "button";
          undo.title = CEV.t("web.struct.undo");
          line.appendChild(undo);
        }
      }
      rels.forEach(function (x) {
        if (x.a !== r.uuid && x.b !== r.uuid) { return; }
        var j = index[x.a === r.uuid ? x.b : x.a];
        if (j === undefined) { return; }
        var way = x.dir === "both" ? "↔" : (x.dir === "to") === (x.a === r.uuid) ? "→" : "←";
        line.appendChild(el("span", "st-lk", way + " " + label(L, j)));
      });
      box.appendChild(line);
    });
    return box;
  }

  // --- What the click shows under the list ------------------------------------------------------------------
  var chosen = null;
  function mark(uuid, cls, on) {
    if (!panel || !uuid) { return; }
    panel.querySelectorAll('[data-uuid="' + CSS.escape(uuid) + '"]').forEach(function (x) { x.classList.toggle(cls, on); });
  }
  // the message before / after x on its thread, over the frames of the other versions (and out of the frame
  // x opens); frames: those met on the way
  function before(x) {
    for (var y = x.previousElementSibling; y; y = y.previousElementSibling) {
      if (y.classList.contains("message")) { return y; }
    }
    var box = x.parentElement, f = box && box.classList.contains("removed-messages") ? box.parentElement : null;
    return f ? before(f) : null;
  }
  function after(x, frames) {
    for (var y = x.nextElementSibling; y; y = y.nextElementSibling) {
      if (y.matches("details.removed-part")) { frames.push(y); } else if (y.classList.contains("message")) { return y; }
    }
    return null;
  }
  function isAnswer(x) { return Boolean(x && x.classList.contains("message-assistant")); }
  function display(msgs, frames, uuid) {  // these messages under the list, the frames folded
    root.querySelectorAll(".st-shown, .st-path, .st-alt").forEach(function (x) { x.classList.remove("st-shown", "st-path", "st-alt"); });
    mark(chosen, "st-sel", false);
    chosen = uuid;
    mark(chosen, "st-sel", true);
    msgs.forEach(function (x) {
      x.classList.add("st-shown");
      for (var d = x.closest("details.removed-part"); d; d = d.parentElement.closest("details.removed-part")) {
        d.classList.add("st-path");
        d.open = true;
      }
    });
    frames.forEach(function (f) {
      if (f.classList.contains("st-path")) { return; }
      f.classList.add("st-alt");
      f.open = false;
    });
    document.documentElement.classList.add("st-has");
    var top = msgs[0] && msgs[0].getBoundingClientRect();
    if (top && (top.top > window.innerHeight - 80 || top.bottom < 0)) { msgs[0].scrollIntoView({ block: "start", behavior: "smooth" }); }
  }
  function choose(uuid) {  // a click: the question and all its answers (an interrupted one and its sequel)
    var m = message(uuid);
    if (!m) { return; }
    var q = m, first = null, frames = [];
    if (isAnswer(m)) {
      q = before(m);
      while (isAnswer(q)) { q = before(q); }
      if (q && !q.classList.contains("message-human")) { q = null; }
      first = m;
      if (q) {  // from the first answer: the followed one, or the first one of the other version m is in
        var a = after(q, frames), alt = frames.find(function (f) { return f.contains(m); });
        first = alt ? alt.querySelector(":scope > .removed-messages > .message") : a;
      }
    } else {
      first = after(m, frames);
      if (!isAnswer(first)) { first = null; frames = []; }
    }
    var msgs = q ? [q] : [];
    for (var x = first; isAnswer(x); ) {
      msgs.push(x);
      var g = [], n = after(x, g);
      if (!isAnswer(n)) { break; }
      Array.prototype.push.apply(frames, g);
      x = n;
    }
    display(msgs, frames, uuid);
  }
  function stretch(uuid) {  // a double click: from that question to the end of its branch, in the order shown
    var L = last, i = L ? L.rows.findIndex(function (r) { return r.uuid === uuid; }) : -1;
    if (i < 0) { return; }
    while (!L.rows[i].q && L.rows[i].prev !== null && L.rows[L.rows[i].prev].br === L.rows[i].br) { i = L.rows[i].prev; }
    var msgs = L.rows.filter(function (x, j) { return j >= i && x.br === L.rows[i].br; })
      .map(function (x) { return message(x.uuid); }).filter(Boolean);
    var frames = [];
    msgs.forEach(function (x, k) {
      var f = [], n = after(x, f);
      if (n && n === msgs[k + 1]) { Array.prototype.push.apply(frames, f); }
    });
    display(msgs, frames, uuid);
  }

  // --- Drag: a question onto a question or an answer (logical order); Shift: a logical link; a handle -------
  var drag = null, dragged = false;
  function point(e) {  // the mouse in the coordinates of the drawing
    var r = pic.querySelector(".st-svg").getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }
  function start(e) {
    if (!served || e.button !== 0) { return; }
    var h = e.target.closest && e.target.closest(".st-handle");
    if (h) {
      var g = h.parentNode;
      drag = { handle: g, sx: e.clientX, sy: e.clientY, bend: null };
      e.preventDefault();
      return;
    }
    var c = e.target.closest && e.target.closest(".st-svg [data-uuid]");
    if (!c) { return; }
    var box = c.getBBox();
    drag = { uuid: c.getAttribute("data-uuid"), q: c.classList.contains("st-q"), link: e.shiftKey,
             x: box.x + box.width / 2, y: box.y + box.height / 2, sx: e.clientX, sy: e.clientY, line: null };
  }
  function move(e) {
    if (!drag) { return; }
    if (drag.handle) {  // bend the line: the handle follows the mouse on the normal of the chord
      var geo = drag.handle._geo, f = frame(geo.p1, geo.p2), p = point(e);
      drag.bend = Math.round((p[0] - f.m[0]) * f.n[0] + (p[1] - f.m[1]) * f.n[1]);
      var c = curve(geo.p1, geo.p2, drag.bend, geo.r1, geo.r2);
      drag.handle.querySelectorAll("path").forEach(function (x) { x.setAttribute("d", c.d); });
      var hd = drag.handle.querySelector(".st-handle");
      hd.setAttribute("cx", c.h[0]);
      hd.setAttribute("cy", c.h[1]);
      return;
    }
    if (!drag.line) {
      if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) < 6) { return; }
      if (!drag.link && (order !== "logic" || !drag.q)) { drag = null; return; }  // a move: a question, logical order
      drag.line = svg("line", { "class": drag.link ? "st-ghost st-ghost-link" : "st-ghost", x1: drag.x, y1: drag.y });
      pic.querySelector(".st-svg").appendChild(drag.line);
    }
    var q = point(e);
    drag.line.setAttribute("x2", q[0]);
    drag.line.setAttribute("y2", q[1]);
  }
  function bendBody(g, bend) {
    var kind = g.getAttribute("data-kind"), key = g.getAttribute("data-key");
    if (kind === "move") { return { action: "bend", conversation: conv, message: key, bend: bend }; }
    var rel = relations()[+key];
    return { action: "bend", conversation: conv, a: rel.a, b: rel.b, bend: bend };
  }
  function end(e) {
    if (!drag) { return; }
    var d = drag;
    drag = null;
    if (d.handle) {
      if (d.bend !== null) { dragged = true; setTimeout(function () { dragged = false; }, 0); post(bendBody(d.handle, d.bend)); }
      return;
    }
    if (!d.line) { return; }
    d.line.remove();
    dragged = true;
    setTimeout(function () { dragged = false; }, 0);
    var hit = document.elementFromPoint(e.clientX, e.clientY);
    var c = hit && hit.closest && hit.closest(".st-svg [data-uuid]");
    var to = c && c.getAttribute("data-uuid");
    if (!to || to === d.uuid) { return; }
    if (d.link) {
      var old = relations().some(function (x) { return (x.a === d.uuid && x.b === to) || (x.a === to && x.b === d.uuid); });
      if (!old) { post({ action: "relation", conversation: conv, a: d.uuid, b: to, dir: "to" }); }
      return;
    }
    if (under(logical(tree(root), moves()), d.uuid, to)) { return; }
    post({ action: "move", conversation: conv, message: d.uuid, target: to, how: c.classList.contains("st-q") ? "under" : "after" });
  }

  // --- The panel ----------------------------------------------------------------------------------------------
  function head() {  // "Ordre : réel · logique", "↶ Annuler", "Réinitialisation"
    var h = el("div", "st-bar");
    var chip = el("button", "plan-chip st-order");
    chip.type = "button";
    chip.title = CEV.t("web.struct.order_title");
    chip.appendChild(document.createTextNode(CEV.t("web.struct.order") + " "));
    ["real", "logic"].forEach(function (v, k) {
      if (k) { chip.appendChild(document.createTextNode(" · ")); }
      var o = el("span", "plan-opt" + (order === v ? " on" : ""), CEV.t("web.struct." + v));
      o.setAttribute("data-v", v);
      chip.appendChild(o);
    });
    h.appendChild(chip);
    if (served && undos()) {
      var undo = el("button", "st-reset st-back", "↶ " + CEV.t("web.struct.back"));
      undo.type = "button";
      undo.title = CEV.t("web.struct.back_title", { n: undos() });
      h.appendChild(undo);
    }
    if (served && (Object.keys(moves()).length || relations().length)) {
      var reset = el("button", "st-reset", CEV.t("web.struct.reset"));
      reset.type = "button";
      h.appendChild(reset);
    }
    return h;
  }
  // 21/11: the controls of the structure at the end of the line "Vue · Lignes · Voix", always there (only seen in
  // the structure view: switching views lights them up or off, nothing moves)
  function paintBar() {
    var line = document.getElementById("plan-bar");
    if (!line) { return; }
    var old = line.querySelector(":scope > .st-bar");
    if (old) { old.remove(); }
    line.appendChild(head());
  }
  function helpBox() {  // P9 (11/11): how to reorganise, folded at the top of the panel, on the left
    var help = el("details", "st-help");
    help.appendChild(el("summary", "", CEV.t("web.struct.help_title")));
    help.appendChild(el("p", "", CEV.t("web.struct.help")));
    return help;
  }
  function show() {
    if (!panel) {
      panel = el("div", "st-panel");
      root.parentNode.insertBefore(panel, root);
      document.addEventListener("cev-annotations", function () { if (panel.childNodes.length) { render(); } });
      var over = function (e, on) {
        var x = e.target.closest && e.target.closest("[data-uuid]");
        if (x && panel.contains(x)) { mark(x.getAttribute("data-uuid"), "st-hi", on); }
      };
      panel.addEventListener("mouseover", function (e) { over(e, true); });
      panel.addEventListener("mouseout", function (e) { over(e, false); });
      panel.addEventListener("pointerdown", start);
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", end);
      var barClick = function (e) {  // the controls of the line "Vue · Lignes" (21/11) and of the panel
        var o = e.target.closest(".st-order");
        if (o) {
          var v = e.target.closest(".plan-opt");
          order = v ? v.getAttribute("data-v") : order === "logic" ? "real" : "logic";
          put("cev-struct-order", order);
          render();
          badges();  // the relations on the bubbles follow the order chosen
          return true;
        }
        if (e.target.closest(".st-back")) { post({ action: "undo_structure", conversation: conv }); return true; }
        if (e.target.closest(".st-reset")) {
          CEV.confirm(CEV.t("web.struct.reset_ask"), function () { post({ action: "reset_structure", conversation: conv }); });
          return true;
        }
        return false;
      };
      var planBar = document.getElementById("plan-bar");
      if (planBar) { planBar.addEventListener("click", barClick); }
      panel.addEventListener("click", function (e) {
        if (dragged) { return; }
        if (barClick(e)) { return; }
        var u = e.target.closest(".st-undo");
        if (u) {
          post({ action: "move", conversation: conv, message: u.closest("[data-uuid]").getAttribute("data-uuid"), target: null });
          return;
        }
        var cut = e.target.closest(".st-scissors");
        if (cut) {
          post({ action: "move", conversation: conv, message: cut.parentNode.getAttribute("data-cut"), target: null, how: "cut" });
          return;
        }
        var h = e.target.closest(".st-rel-hit");
        if (h) {
          if (!served) { return; }
          var rel = relations()[+h.getAttribute("data-rel")];
          var next = { to: "back", back: "both", both: null }[rel.dir];
          post({ action: "relation", conversation: conv, a: rel.a, b: rel.b, dir: next });
          return;
        }
        var x = e.target.closest("[data-uuid]");
        if (x && panel.contains(x)) { choose(x.getAttribute("data-uuid")); }
      });
      panel.addEventListener("dblclick", function (e) {
        var hd = e.target.closest(".st-handle");
        if (hd) { post(bendBody(hd.parentNode, null)); return; }  // the automatic curve again
        var x = e.target.closest("[data-uuid]");
        if (x && panel.contains(x)) { stretch(x.getAttribute("data-uuid")); }
      });
    }
    render();
  }
  function render() {
    last = shape();
    panel.textContent = "";
    paintBar();
    if (served) { panel.appendChild(helpBox()); }
    pic = el("div", "st-pic");
    pic.appendChild(draw(last));
    panel.appendChild(pic);
    panel.appendChild(list(last));
    panel.appendChild(el("hr", "st-sep"));
    mark(chosen, "st-sel", true);
  }
  if (A) { A.ready(function (s) { served = s; if (panel && panel.childNodes.length) { render(); } }); }

  // --- 18/11 (AE-c1): the structure on the bubbles of the reading ----------------------------------------
  // On the line of a bubble, before its name, its direct relations in the drawing (the order chosen in the
  // structure view, real or logical): "[the question before] ← [itself] → [its other answers] [the questions
  // after]", each pill drawn as its point (a question of the followed thread: blue, full; another version: blue,
  // circled; an answer: grey, circled); a pill other than itself: a click goes to that bubble (brick when the mouse
  // is over it). An answer followed: its number only; another answer: "[its question] ← [itself] → [questions
  // after]". A part cut: "✂" in place of the one before. Then its logical links, green (→ 4, ← R3, ↔ 5).
  // "Masquer les numéros" hides them, their place kept (fold.js).
  function pillClass(r) { return "st-pill" + (r.solid && r.q ? "" : " st-off") + (r.q ? "" : " st-ans"); }
  function badges() {
    var L = shape(), rows = L.rows, index = {}, kids = {}, rels = relations();
    rows.forEach(function (r, i) {
      index[r.uuid] = i;
      if (r.prev !== null) { (kids[r.prev] = kids[r.prev] || []).push(i); }
    });
    var byLane = function (a, b) { return (L.lanes[rows[a].br] || 0) - (L.lanes[rows[b].br] || 0) || a - b; };
    var mainAnswer = function (q) {  // the answer of a question on its own line
      return (kids[q] || []).filter(function (k) { return !rows[k].q && rows[k].br === rows[q].br; })[0];
    };
    var questionsAfter = function (a) {  // the questions after an answer (through the answers going on after it)
      var out = [];
      (kids[a] || []).slice().sort(byLane).forEach(function (k) {
        if (rows[k].q) { out.push(k); } else { out = out.concat(questionsAfter(k)); }
      });
      return out;
    };
    var questionOf = function (i) {  // the question an answer belongs to, or the one a question follows
      for (var p = rows[i].prev; p !== null; p = rows[p].prev) { if (rows[p].q) { return p; } }
      return null;
    };
    var cutHead = function (i) {
      var br = rows[i].br;
      return L.branches[br].kind === "cut" && rows.findIndex(function (x) { return x.br === br; }) === i;
    };
    root.querySelectorAll(".st-badge").forEach(function (x) { x.remove(); });
    rows.forEach(function (r, i) {
      var m = message(r.uuid), headLine = m && m.querySelector(":scope > .message-time"), n = label(L, i);
      if (!headLine || !n) { return; }
      var b = el("span", "st-badge");
      var pill = function (j) {
        var x = el("button", pillClass(rows[j]), label(L, j));
        x.type = "button";
        x.setAttribute("data-go", rows[j].uuid);
        x.title = CEV.t("web.struct.go_title");
        return x;
      };
      var arrow = function (t) { b.appendChild(el("span", "st-arrow", t)); };
      var self = function () {  // itself: the same pill, not clickable
        var x = el("button", pillClass(r) + " st-self", n);
        x.type = "button";
        x.tabIndex = -1;
        return x;
      };
      var followed = !r.q && r.prev !== null && rows[r.prev].br === r.br;  // an answer on the line of its question
      if (followed) {
        b.appendChild(self());
      } else {
        var before = r.q ? questionOf(i) : r.prev;
        if (cutHead(i)) { b.appendChild(el("span", "st-cut", "✂")); arrow("←"); }
        else if (before !== null && before !== undefined) { b.appendChild(pill(before)); arrow("←"); }
        b.appendChild(self());
        var after = [];
        if (r.q) {
          var main = mainAnswer(i);
          after = (kids[i] || []).filter(function (k) { return k !== main && !rows[k].q; }).sort(byLane);
          after = after.concat(main === undefined ? [] : questionsAfter(main));
        } else {
          after = questionsAfter(i);
        }
        if (after.length) {
          arrow("→");
          var group = el("span", "st-after");
          after.forEach(function (j) { group.appendChild(pill(j)); });
          b.appendChild(group);
        }
      }
      rels.forEach(function (x) {
        if (x.a !== r.uuid && x.b !== r.uuid) { return; }
        var other = x.a === r.uuid ? x.b : x.a, j = index[other];
        if (j === undefined) { return; }
        var way = x.dir === "both" ? "↔" : (x.dir === "to") === (x.a === r.uuid) ? "→" : "←";
        var go = el("button", "st-badge-link", way + " " + label(L, j));
        go.type = "button";
        go.setAttribute("data-go", other);
        go.title = CEV.t("web.struct.go_title");
        b.appendChild(go);
      });
      headLine.insertBefore(b, headLine.firstChild);
    });
  }
  root.addEventListener("click", function (e) {
    var go = e.target.closest && e.target.closest(".st-badge [data-go]");
    if (!go) { return; }
    e.preventDefault();
    var m = message(go.getAttribute("data-go"));
    if (!m) { return; }
    if (document.documentElement.classList.contains("cev-structure")) {  // the structure view: shown as from the list
      choose(go.getAttribute("data-go"));
    } else {
      for (var d = m.parentElement; d && d !== root; d = d.parentElement) { if (d.tagName === "DETAILS") { d.open = true; } }
      m.scrollIntoView({ block: "center" });
    }
    m.classList.add("st-flash");  // its own frame brick, one second (20/11)
    setTimeout(function () { m.classList.remove("st-flash"); }, 1000);
  });
  badges();
  paintBar();
  if (A) { A.ready(paintBar); }
  document.addEventListener("cev-annotations", paintBar);
  document.addEventListener("cev-language", paintBar);
  document.addEventListener("cev-annotations", badges);
  document.addEventListener("cev-language", badges);

  window.CEV = window.CEV || {};
  CEV.structure = { show: show, layout: layout };
})();
