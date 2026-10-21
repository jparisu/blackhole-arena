// BlackHole Arena — shared helpers used by every screen
//
// DOM helpers, navigation, player identity, and the graph renderer. Nothing
// here knows about a specific screen.
//
// Loaded as a plain script (not an ES module): the whole app shares one global
// namespace by design, and plain scripts keep working without a bundler.
"use strict";

/* ---------------- element helpers ---------------- */
const $ = (id) => document.getElementById(id);
const el = (tag, cls, txt) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
};

/* Defined up here because playerHtml() below needs it, and a `const` arrow is
   unusable until its own line has been evaluated. */
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* A Python exception reaches JS as a PythonError whose message is the whole
   traceback. The last line ("ValueError: ...") is the part a person can act on. */
function pyMessage(err) {
  const text = String(err && err.message ? err.message : err).trim();
  const lines = text.split("\n").filter((l) => l.trim());
  return lines.length ? lines[lines.length - 1] : text;
}

/* ---------------- navigation & theme ---------------- */
function showScreen(name) {
  for (const s of document.querySelectorAll(".screen")) s.classList.add("hidden");
  $(`screen-${name}`).classList.remove("hidden");
  if (name === "scoreboard") loadScoreboard();
}

function setupNav() {
  for (const btn of document.querySelectorAll("[data-nav]")) {
    btn.addEventListener("click", () => showScreen(btn.dataset.nav));
  }
  $("theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    try { localStorage.setItem("bh-theme", next); } catch {}
  });
  try {
    const saved = localStorage.getItem("bh-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch {}
}

/* ---------------- player identity ---------------- */
/* name -> {icon, authors, description}, keyed by KIND ("random"), not roster
   entry ("random_0"). Populated from the live registry on the Play screen and
   from the leaderboard's `players` block on the Scoreboard, which may not be the
   same set: a player can be removed from the repo after a tournament ran. */
const META = new Map();

const SUB_DIGITS = "₀₁₂₃₄₅₆₇₈₉";
/* Silhouette for a human seat; every bot supplies its own icon. */
const HUMAN_ICON = "👤";
/* Fallback when the leaderboard predates icons, or a kind is unknown. */
const BOT_ICON = "🤖";

/* Split a roster name into its kind and copy index: "random_0" -> ["random", "0"]. */
function splitPlayer(name) {
  const m = /^(.*)_(\d+)$/.exec(String(name));
  return m ? [m[1], m[2]] : [String(name), null];
}

function playerIcon(name) {
  const [kind] = splitPlayer(name);
  return META.get(kind)?.icon || BOT_ICON;
}

/* Plain-text label — for <option>, tooltips and anywhere markup is not allowed.
   Uses Unicode subscript digits, since <sub> cannot render inside <option>. */
function playerText(name) {
  const [kind, idx] = splitPlayer(name);
  const sub = idx == null ? "" : [...idx].map((d) => SUB_DIGITS[+d]).join("");
  return `${playerIcon(name)} ${kind}${sub}`;
}

/* HTML label — real <sub> markup, for everywhere else. */
function playerHtml(name) {
  const [kind, idx] = splitPlayer(name);
  return (
    `<span class="p-icon">${esc(playerIcon(name))}</span>` +
    `<span class="p-name">${esc(kind)}` +
    (idx == null ? "" : `<sub>${esc(idx)}</sub>`) +
    `</span>`
  );
}

/* ---------------- graphs ---------------- */

/* Hard ceiling for a *playable* graph. 13 nodes is six turns each, 21 tiles per
   player — already a long game by hand, and the layout stays readable. The
   engine accepts more; the page does not offer it. */
const MAX_NODES = 13;
const MIN_NODES = 3;

/* Parse "0-1, 1-2, 2-0" into [[0, 1], [1, 2], [2, 0]]. Returns null if any part
   is not "number-number"; the engine judges whether the edges make sense. */
function parseEdges(text) {
  const edges = [];
  for (const part of String(text).split(",")) {
    const p = part.trim();
    if (!p) continue;
    const m = /^(\d+)\s*-\s*(\d+)$/.exec(p);
    if (!m) return null;
    edges.push([parseInt(m[1]), parseInt(m[2])]);
  }
  return edges;
}

const formatEdges = (edges) => edges.map(([a, b]) => `${a}-${b}`).join(", ");

/* Return why a node count is unplayable on this page, or null if it is fine.
   Everything else (odd count, edge ranges, repeats) is checked by Python. */
function nodesProblem(nodes) {
  if (!Number.isInteger(nodes)) return "The number of nodes must be a whole number.";
  if (nodes < MIN_NODES || nodes > MAX_NODES) {
    return `The number of nodes must be between ${MIN_NODES} and ${MAX_NODES}.`;
  }
  if (nodes % 2 === 0) return "The number of nodes must be odd (2N + 1).";
  return null;
}

/* Build a starting state through the engine, or toast why it cannot be built. */
function buildGame(nodes, edges) {
  const problem = nodesProblem(nodes);
  if (problem) { toast(problem); return null; }
  if (!edges) { toast('Write the edges as "a-b" pairs separated by commas, e.g. 0-1, 1-2.'); return null; }
  try {
    return window.BH.newGame(nodes, edges);
  } catch (err) {
    toast(pyMessage(err));
    return null;
  }
}

/* ---------------- graph layout ---------------- */
const BOARD_W = 440;
const BOARD_H = 330;
const BOARD_MARGIN = 42;
const NODE_R = 21;
const LAYOUT_ITERATIONS = 300;
const LAYOUT_CACHE = new Map();

/* Node positions for a graph, in board coordinates.
   Two deterministic candidates, and the one whose edges cross less wins (the
   spring layout on a tie, as it reads better):

     * a Fruchterman–Reingold spring layout started from a circle;
     * the nodes on an ellipse in index order. Random graphs are built so that
       this draws them with no crossing at all (see graphs.random_graph), so a
       random graph is always crossing-free.

   No randomness, so the same graph always looks the same — on the Play screen,
   in a replay, and after a reload. Cached per graph, so scrubbing a timeline
   never re-runs it. */
function graphLayout(state) {
  const n = state.owner.length;
  const key = `${n}|${JSON.stringify(state.edges)}`;
  if (LAYOUT_CACHE.has(key)) return LAYOUT_CACHE.get(key);

  const spring = fitToBoard(springLayout(state));
  const springCrossings = countCrossings(spring, state.edges);
  let out = spring;
  if (springCrossings > 0) {
    const ring = fitToBoard(ringLayout(n));
    if (countCrossings(ring, state.edges) < springCrossings) out = ring;
  }
  LAYOUT_CACHE.set(key, out);
  return out;
}

/* Spring layout in abstract coordinates (roughly a 2x2 square). */
function springLayout(state) {
  const n = state.owner.length;
  const pos = Array.from({ length: n }, (_, i) => {
    const a = (2 * Math.PI * i) / n - Math.PI / 2;
    return [Math.cos(a), Math.sin(a)];
  });
  const k = Math.sqrt(4 / n); // ideal distance for n nodes in a 2x2 square
  let temp = 0.25;
  for (let it = 0; it < LAYOUT_ITERATIONS; it++) {
    const disp = pos.map(() => [0, 0]);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = pos[i][0] - pos[j][0];
        const dy = pos[i][1] - pos[j][1];
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = (k * k) / d; // repulsion between every pair
        disp[i][0] += (dx / d) * f; disp[i][1] += (dy / d) * f;
        disp[j][0] -= (dx / d) * f; disp[j][1] -= (dy / d) * f;
      }
    }
    for (const [a, b] of state.edges) {
      const dx = pos[a][0] - pos[b][0];
      const dy = pos[a][1] - pos[b][1];
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = (d * d) / k; // attraction along every edge
      disp[a][0] -= (dx / d) * f; disp[a][1] -= (dy / d) * f;
      disp[b][0] += (dx / d) * f; disp[b][1] += (dy / d) * f;
    }
    for (let i = 0; i < n; i++) {
      const len = Math.max(Math.hypot(disp[i][0], disp[i][1]), 1e-9);
      const step = Math.min(len, temp);
      pos[i][0] += (disp[i][0] / len) * step;
      pos[i][1] += (disp[i][1] / len) * step;
    }
    temp *= 0.985;
  }
  return pos;
}

/* Nodes 0..n-1 on an ellipse with the board's proportions, in index order, at
   equal arc length — equal angles would crowd the ends of the long axis. Every
   point is a corner of a convex polygon, so two edges cross only when their
   endpoints interleave around it. */
const RING_SAMPLES = 720;

function ringLayout(n) {
  const rx = (BOARD_W - 2 * BOARD_MARGIN) / 2;
  const ry = (BOARD_H - 2 * BOARD_MARGIN) / 2;
  const at = (t) => [rx * Math.cos(t), ry * Math.sin(t)];
  const start = -Math.PI / 2;
  // Cumulative arc length at each sample along the ellipse.
  const lengths = [0];
  let prev = at(start);
  for (let s = 1; s <= RING_SAMPLES; s++) {
    const p = at(start + (2 * Math.PI * s) / RING_SAMPLES);
    lengths.push(lengths[s - 1] + Math.hypot(p[0] - prev[0], p[1] - prev[1]));
    prev = p;
  }
  const total = lengths[RING_SAMPLES];
  const pos = [];
  let s = 0;
  for (let i = 0; i < n; i++) {
    const target = (total * i) / n;
    while (lengths[s + 1] < target) s++;
    pos.push(at(start + (2 * Math.PI * s) / RING_SAMPLES));
  }
  return pos;
}

/* Number of pairs of edges that cross. Edges sharing a node never count. */
function countCrossings(pos, edges) {
  const side = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  let count = 0;
  for (let i = 0; i < edges.length; i++) {
    const [a, b] = edges[i];
    for (let j = i + 1; j < edges.length; j++) {
      const [c, d] = edges[j];
      if (a === c || a === d || b === c || b === d) continue;
      if (side(pos[a], pos[b], pos[c]) * side(pos[a], pos[b], pos[d]) < 0 &&
          side(pos[c], pos[d], pos[a]) * side(pos[c], pos[d], pos[b]) < 0) count++;
    }
  }
  return count;
}

/* Scale abstract positions onto the board, keeping the aspect ratio, then make
   sure every node can be clicked. */
function fitToBoard(pos) {
  const xs = pos.map((p) => p[0]);
  const ys = pos.map((p) => p[1]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = Math.min(
    (BOARD_W - 2 * BOARD_MARGIN) / Math.max(maxX - minX, 1e-9),
    (BOARD_H - 2 * BOARD_MARGIN) / Math.max(maxY - minY, 1e-9),
  );
  const offX = (BOARD_W - (maxX - minX) * scale) / 2;
  const offY = (BOARD_H - (maxY - minY) * scale) / 2;
  const out = pos.map(([x, y]) => [offX + (x - minX) * scale, offY + (y - minY) * scale]);
  separateNodes(out);
  return out;
}

/* Push apart any two nodes closer than MIN_SEPARATION, keeping them on the
   board. The spring layout balances forces, not pixels: on a dense graph two
   nodes can settle on top of each other, and then one cannot be clicked. */
const MIN_SEPARATION = 2 * NODE_R + 18;
const SEPARATION_PASSES = 60;

function separateNodes(pos) {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  for (let pass = 0; pass < SEPARATION_PASSES; pass++) {
    let moved = false;
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        let dx = pos[j][0] - pos[i][0];
        let dy = pos[j][1] - pos[i][1];
        let d = Math.hypot(dx, dy);
        if (d >= MIN_SEPARATION) continue;
        if (d < 1e-6) { dx = 1; dy = 0; d = 1; } // identical points: split sideways
        const push = (MIN_SEPARATION - d) / 2;
        pos[i][0] -= (dx / d) * push; pos[i][1] -= (dy / d) * push;
        pos[j][0] += (dx / d) * push; pos[j][1] += (dy / d) * push;
        moved = true;
      }
    }
    for (const p of pos) {
      p[0] = clamp(p[0], NODE_R + 4, BOARD_W - NODE_R - 4);
      p[1] = clamp(p[1], NODE_R + 18, BOARD_H - NODE_R - 18);
    }
    if (!moved) break;
  }
}

/* ---------------- the board ---------------- */
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, text = null) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text != null) e.textContent = text;
  return e;
}

/* Draw a graph position into any container.
   Shared by the Play and Tournament screens, so both render the identical board
   — same markup, same hover preview, same click semantics.

   Options:
     onPick(node)  called when a human clicks a free node; null = read-only.
     analysis      the result of window.BH.analysis(state), or null. When the game
                   is over it marks the black hole and its prize neighbours.
     xray          show, on every free node, what each player would score if
                   that node became the black hole now (needs `analysis`).
     highlight     a node to ring, e.g. the move just played (-1 = none). */
function paintBoard(container, state, { onPick = null, analysis = null, xray = false, highlight = -1 } = {}) {
  container.innerHTML = "";
  const interactive = typeof onPick === "function";
  container.classList.toggle("locked", !interactive);

  const pos = graphLayout(state);
  const hole = analysis && analysis.terminal ? analysis.black_hole : -1;
  const prize = new Set();
  if (hole >= 0) {
    for (const [a, b] of state.edges) {
      if (a === hole) prize.add(b);
      if (b === hole) prize.add(a);
    }
  }

  const svg = svgEl("svg", {
    viewBox: `0 0 ${BOARD_W} ${BOARD_H}`,
    class: "bh-graph",
    role: "img",
    "aria-label": `Graph with ${state.owner.length} nodes`,
  });

  for (const [a, b] of state.edges) {
    const hot = hole >= 0 && (a === hole || b === hole);
    svg.appendChild(svgEl("line", {
      class: `bh-edge${hot ? " hot" : ""}`,
      x1: pos[a][0].toFixed(1), y1: pos[a][1].toFixed(1),
      x2: pos[b][0].toFixed(1), y2: pos[b][1].toFixed(1),
    }));
  }

  state.owner.forEach((owner, v) => {
    const [x, y] = pos[v];
    const classes = ["bh-node"];
    if (v === hole) classes.push("hole");
    else if (owner === null) classes.push("free");
    else classes.push(`p${owner}`);
    if (prize.has(v)) classes.push("prize");
    if (v === highlight) classes.push("last");
    const free = owner === null && v !== hole;
    if (interactive && free) classes.push("selectable");

    const g = svgEl("g", { class: classes.join(" "), transform: `translate(${x.toFixed(1)},${y.toFixed(1)})` });
    g.appendChild(svgEl("circle", { class: "bh-disc", r: NODE_R }));
    g.appendChild(svgEl("text", { class: "bh-label", y: -NODE_R - 7 }, String(v)));

    let tip = `node ${v}`;
    if (v === hole) {
      g.appendChild(svgEl("text", { class: "bh-center", y: 1 }, "✦"));
      tip += " — the black hole";
    } else if (owner !== null) {
      g.appendChild(svgEl("text", { class: "bh-center", y: 1 }, String(state.tiles[v])));
      tip += ` — ${state.tiles[v]} tile(s) of player ${owner + 1}`;
    } else if (interactive && analysis) {
      // Whose turn and how many tiles come from the engine, never from JS.
      g.appendChild(svgEl("text", {
        class: `bh-center bh-preview p${analysis.to_move}`, y: 1,
      }, `+${analysis.tiles_to_place}`));
    }
    if (prize.has(v) && owner !== null) tip += " — next to the black hole: it scores";

    if (xray && free && analysis && analysis.hole_payoffs[String(v)]) {
      const [s0, s1] = analysis.hole_payoffs[String(v)];
      const t = svgEl("text", { class: "bh-xray", y: NODE_R + 15 });
      t.appendChild(svgEl("tspan", { class: "p0" }, String(s0)));
      t.appendChild(svgEl("tspan", { class: "sep" }, " · "));
      t.appendChild(svgEl("tspan", { class: "p1" }, String(s1)));
      g.appendChild(t);
      tip += ` — if it becomes the black hole: ${s0} · ${s1}`;
    }
    g.appendChild(svgEl("title", {}, tip));

    if (interactive && free) g.addEventListener("click", () => onPick(v));
    svg.appendChild(g);
  });

  container.appendChild(svg);
}
