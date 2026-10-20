// Headless smoke test for the web app: boot it exactly as the browser does,
// then drive the Tournament screen the way a user does.
//
// This exists because two bugs shipped that no Python test could see, and that
// looked identical from the outside — "the button does nothing":
//
//   * a duplicate element id, so the board was painted into a text input;
//   * `main()` throwing before the wiring ran, leaving buttons with no handler.
//
// Both are caught below. Run with `node tests/js/boot_test.js`.
"use strict";

const path = require("path");
const fs = require("fs");
const { buildDocument } = require("./domstub.js");

const ROOT = path.resolve(__dirname, "..", "..");
const WEB = path.join(ROOT, "web");

let failures = 0;
function check(label, ok, detail = "") {
  if (ok) console.log(`  ok   ${label}`);
  else { failures++; console.log(`  FAIL ${label}${detail ? " — " + detail : ""}`); }
}

/* ---------- environment ---------- */
const document = buildDocument(WEB);
global.document = document;
global.localStorage = { getItem: () => null, setItem: () => {} };
global.Event = class { constructor(t) { this.type = t; } };
// Node ≥21 defines navigator as a getter-only global; only define it if absent.
if (!globalThis.navigator) global.navigator = {};
global.history = { replaceState: () => {} };
global.location = { hash: "", origin: "http://localhost", pathname: "/" };

let pending = [];
global.setTimeout = (fn) => { pending.push(fn); return 0; };
global.clearTimeout = () => {};
const drain = () => {
  let guard = 0;
  while (pending.length && guard++ < 500) { const fns = pending; pending = []; fns.forEach((f) => f()); }
};

// Screens are fetched at boot; serve them from disk.
global.fetch = async (url) => {
  const file = path.join(WEB, url.split("?")[0]);
  if (!fs.existsSync(file)) return { ok: false, status: 404 };
  return { ok: true, status: 200, text: async () => fs.readFileSync(file, "utf8") };
};

// The engine, standing in for Pyodide. Same payload shapes webglue produces.
const PLAYERS = [
  { name: "random", icon: "🎲", authors: ["jparisu"], description: "Random free node." },
  { name: "other", icon: "🧪", authors: ["tests"], description: "Lowest free node." },
];
// The 5-node example graph from the rules.
const CLASSIC = {
  edges: [[0, 1], [2, 3], [3, 4], [0, 2], [0, 3], [1, 3], [1, 4]],
  owner: [null, null, null, null, null],
  tiles: [0, 0, 0, 0, 0],
};
const played = (st) => st.owner.filter((o) => o !== null).length;
const free = (st) => st.owner.flatMap((o, v) => (o === null ? [v] : []));
const isTerminal = (st) => free(st).length <= 1;
const applyMove = (st, v) => {
  const owner = st.owner.slice();
  const tiles = st.tiles.slice();
  owner[v] = played(st) % 2;
  tiles[v] = Math.floor(played(st) / 2) + 1;
  return { edges: st.edges, owner, tiles };
};
const scoresIfHole = (st, hole) => {
  const s = [0, 0];
  for (const [a, b] of st.edges) {
    const other = a === hole ? b : b === hole ? a : -1;
    if (other >= 0 && st.owner[other] !== null) s[st.owner[other]] += st.tiles[other];
  }
  return s;
};
const analysis = (st) => {
  const n = (st.owner.length - 1) / 2;
  const term = isTerminal(st);
  return {
    to_move: played(st) % 2,
    tiles_to_place: Math.floor(played(st) / 2) + 1,
    tiles_per_player: (n * (n + 1)) / 2,
    turns_per_player: n,
    terminal: term,
    black_hole: term ? free(st)[0] : null,
    scores: term ? scoresIfHole(st, free(st)[0]) : null,
    hole_payoffs: Object.fromEntries(free(st).map((v) => [String(v), scoresIfHole(st, v)])),
  };
};
let entrantCalls = 0;
global.window = {
  _handlers: {},
  addEventListener(ev, fn) { (this._handlers[ev] ||= []).push(fn); },
  bootArena: async (onStatus) => { onStatus("Ready."); },
  BH: {
    players: () => PLAYERS,
    playerNames: () => PLAYERS.map((p) => p.name),
    presets: () => [{ name: "classic", label: "Classic", state: CLASSIC }],
    newGame: () => CLASSIC,
    randomGraph: () => CLASSIC,
    resetEntrants: () => "ok",
    createEntrant: () => "ok",
    entrantMove: (id, st) => {
      entrantCalls++;
      return { move: free(st)[0], elapsed_ms: 0.5, info: null };
    },
    // A deterministic game: always the lowest free node.
    playAuto: (a, b, st) => {
      const moves = [];
      let s = st;
      while (!isTerminal(s)) { moves.push(free(s)[0]); s = applyMove(s, free(s)[0]); }
      return { moves, scores: scoresIfHole(s, free(s)[0]), result: "normal",
               forfeit_seat: null, detail: "", elapsed_ms: [1, 1] };
    },
    applyMove,
    isTerminal,
    legalMoves: (st) => (isTerminal(st) ? [] : free(st)),
    analysis,
    askMove: (name, st) => ({ move: free(st)[0], elapsed_ms: 0.3, info: null }),
  },
};

/* ---------- load every screen script, in the order index.html does ----------
   Concatenated and evaluated once: separate <script> tags share one global
   scope, and evaluating each file separately here would not. */
const shell = fs.readFileSync(path.join(WEB, "index.html"), "utf8");
const scripts = [...shell.matchAll(/<script src="(js\/[^"]+)"><\/script>/g)].map((m) => m[1]);
if (scripts.length < 5) {
  console.log(`  FAIL index.html loads only ${scripts.length} screen scripts`);
  process.exit(1);
}
const app = {};
eval(
  scripts.map((rel) => fs.readFileSync(path.join(WEB, rel), "utf8")).join("\n;\n") +
  // `const` at the top of an eval is scoped to that eval, so hand out what the
  // assertions below need to poke at.
  "\n;Object.assign(app, { T, G, tHumanMove, newGame, humanMove });"
);

const $ = (id) => document.getElementById(id);
const nodesIn = (node, cls = "bh-node") => node.querySelectorAll(cls).length;

(async () => {
  console.log("boot");
  const dcl = window._handlers.DOMContentLoaded || [];
  check("index.html registers a DOMContentLoaded handler", dcl.length === 1);
  for (const fn of dcl) await fn();
  drain();

  check("no fatal banner", $("fatal").classList.contains("hidden"),
        $("fatal").innerHTML.replace(/<[^>]+>/g, " ").trim());
  check("boot overlay hidden", $("boot").classList.contains("hidden"));
  check("screens injected", $("screens").innerHTML.length > 500);
  check("no lookups for missing ids", document._missing.size === 0,
        [...document._missing].join(", "));

  console.log("\nwiring — every control a user can click must have a handler");
  for (const id of ["btn-new", "btn-random-graph", "btn-share", "btn-play-ai",
                    "t-start", "t-reset", "t-shuffle", "t-close-view",
                    "t-tl-first", "t-tl-prev", "t-tl-next", "t-tl-last"]) {
    check(`${id} is wired`, typeof $(id).onclick === "function");
  }

  console.log("\ntournament — all bots");
  check("slot list built", $("t-slots").children.length === 8);
  $("t-start").onclick();
  drain();
  check("bracket drawn", $("t-bracket").children.length === 3,
        `columns=${$("t-bracket").children.length}`);
  check("bracket visible", !$("t-bracket-wrap").classList.contains("hidden"));
  check("all matches played", /7 \/ 7/.test($("t-progress").textContent),
        $("t-progress").textContent);
  check("champion shown", !$("t-champion").classList.contains("hidden"));
  check("podium rendered", /podium-step/.test($("t-champion").innerHTML));

  console.log("\ntournament — replay a finished match");
  const firstTie = $("t-bracket").children[0].children[1]; // [0] is the round name
  check("finished match is clickable", typeof firstTie.onclick === "function");
  firstTie.onclick();
  check("match panel opens", !$("t-match").classList.contains("hidden"));
  check("timeline shown", !$("t-timeline").classList.contains("hidden"));
  $("t-tl-first").onclick();
  check("scrubbing to the start shows every node free", nodesIn($("t-board"), "free") === 5,
        `free=${nodesIn($("t-board"), "free")}`);
  $("t-tl-last").onclick();
  check("scrubbing to the end shows the black hole", nodesIn($("t-board"), "hole") === 1);
  check("replay status shows the points", /pts|<strong>\d/.test($("t-status").innerHTML),
        $("t-status").innerHTML);
  $("t-close-view").onclick();
  check("replay closes", $("t-match").classList.contains("hidden"));

  console.log("\ntournament — a human entrant gets somewhere to play");
  $("t-reset").onclick();
  $("t-size").value = "4";
  $("t-size").onchange();
  app.T.slots[0].kind = "__human__";
  app.T.slots[0].label = "Ada";
  [1, 2, 3].forEach((i) => { app.T.slots[i].kind = "random"; });
  $("t-start").onclick();
  drain();
  check("bracket paused for the human", app.T.live !== null);
  check("match panel visible", !$("t-match").classList.contains("hidden"));
  check("board has clickable nodes", nodesIn($("t-board"), "selectable") === 5,
        `selectable=${nodesIn($("t-board"), "selectable")}`);
  check("status names the human", /Ada/.test($("t-status").innerHTML));

  let n = 0;
  while (app.T.live && !app.T.game.over && n++ < 40) {
    const st = app.T.game.history[app.T.game.history.length - 1];
    app.tHumanMove(free(st)[0]);
    drain();
  }
  check("the bot replied", entrantCalls > 0, `entrantMove calls=${entrantCalls}`);
  check("human match recorded", app.T.rounds[0][0].done);
  drain();
  check("bracket ran to a champion", app.T.rounds.every((r) => r.every((m) => m.done)));
  check("champion panel shown", !$("t-champion").classList.contains("hidden"));

  console.log("\nplay screen still works after the split");
  app.newGame(CLASSIC);
  check("graph rendered", nodesIn($("board")) === 5, `nodes=${nodesIn($("board"))}`);
  check("edges rendered", nodesIn($("board"), "bh-edge") === 7);
  app.G.seats = ["Human", "Human"];
  app.newGame(CLASSIC);
  check("a human can click every free node", nodesIn($("board"), "selectable") === 5);
  // The worked example from the rules: A, B, D, C -> E is the black hole, 2 to 1.
  app.humanMove(0); app.humanMove(1); app.humanMove(3); app.humanMove(2);
  const last = app.G.analyses[app.G.analyses.length - 1];
  check("the game ends", app.G.gameOver === true);
  check("the rules example scores 2 to 1", last.scores[0] === 2 && last.scores[1] === 1,
        JSON.stringify(last.scores));
  check("the black hole is drawn", nodesIn($("board"), "hole") === 1);
  check("its neighbours are marked as scoring", nodesIn($("board"), "prize") === 2);
  check("status names the black hole", /black hole/.test($("status").innerHTML));
  $("toggle-xray").onchange({ target: { checked: true } });
  app.newGame(CLASSIC);
  check("x-ray labels every free node", nodesIn($("board"), "bh-xray") === 5);

  console.log(`\n${failures ? "FAILED: " + failures + " check(s)" : "all checks passed"}`);
  process.exit(failures ? 1 : 0);
})();
