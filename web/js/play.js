// BlackHole Arena — the Play screen
//
// One free-form game: human or AI in either seat, any graph, X-ray, move log,
// timeline scrubbing and shareable replay links.
//
// Loaded as a plain script (not an ES module): the whole app shares one global
// namespace by design, and plain scripts keep working without a bundler.
"use strict";

const HUMAN = "Human";
/* The preset a fresh page starts on: the example from the rules. */
const DEFAULT_PRESET = "classic";
/* Probability of each extra edge in a random graph (on top of a spanning tree). */
const RANDOM_DENSITY = 0.3;

/* name -> {name, label, state}, filled from the engine at boot. */
const PRESETS = new Map();

const G = {
  start: null,       // the starting state (every node free)
  seats: [HUMAN, HUMAN], // seat 0 (first) and seat 1 (second)
  history: [],       // states; history[0] is the start
  analyses: [],      // window.BH.analysis() of each state in `history`
  moves: [],         // {seat, move, tiles, elapsed, info} for each transition
  cursor: 0,         // which history index is shown
  gameOver: false,
  thinking: false,
  aiTimer: null,
  showXray: false,
  showWhy: true,
  delay: 600,
};

/* ---------------- setup / seats ---------------- */
/* Preferred default opponent, best first — the first one present is used. */
const DEFAULT_OPPONENTS = ["aggressive-max", "easy", "random"];

function populateSeatSelects() {
  const players = window.BH.players();
  for (const p of players) META.set(p.name, p);
  const names = players.map((p) => p.name);
  const preferred = DEFAULT_OPPONENTS.find((n) => names.includes(n)) || names[0];
  for (const i of [0, 1]) {
    const sel = $(`seat-${i}`);
    sel.innerHTML = "";
    for (const opt of [HUMAN, ...names]) {
      // <option> renders text only — no markup, no SVG — so the icon has to be a
      // glyph and the copy index a Unicode subscript.
      const o = el("option", null, opt === HUMAN ? `${HUMAN_ICON} ${HUMAN}` : playerText(opt));
      o.value = opt;
      const meta = META.get(opt);
      if (meta) o.title = `${meta.description}\nBy: ${meta.authors.join(", ")}`;
      sel.appendChild(o);
    }
    // Default: seat 0 Human, seat 1 a bot, so a first game needs no setup.
    sel.value = i === 1 && preferred ? preferred : HUMAN;
    G.seats[i] = sel.value;
    sel.onchange = () => {
      G.seats[i] = sel.value;
      // Swapping a seat mid-game takes effect on the next turn.
      if (!G.gameOver && isLive()) maybeScheduleAI();
      render();
    };
  }
}

/* Fill the graph picker from the engine's presets, plus "random" and "custom". */
function populatePresets() {
  const sel = $("cfg-preset");
  sel.innerHTML = "";
  PRESETS.clear();
  for (const p of window.BH.presets()) {
    PRESETS.set(p.name, p);
    const o = el("option", null, p.label);
    o.value = p.name;
    sel.appendChild(o);
  }
  for (const [value, label] of [["random", "Random graph"], ["custom", "Custom (edit the edges)"]]) {
    const o = el("option", null, label);
    o.value = value;
    sel.appendChild(o);
  }
  sel.value = DEFAULT_PRESET;
  showGraphInputs(PRESETS.get(DEFAULT_PRESET).state);
}

function showGraphInputs(state) {
  $("cfg-nodes").value = state.owner.length;
  $("cfg-edges").value = formatEdges(state.edges);
}

function drawRandomGraph() {
  const nodes = parseInt($("cfg-nodes").value);
  const problem = nodesProblem(nodes);
  if (problem) { toast(problem); return; }
  const seed = Math.floor(Math.random() * 1e9);
  showGraphInputs(window.BH.randomGraph(nodes, RANDOM_DENSITY, seed));
  $("cfg-preset").value = "random";
}

function onPresetChange() {
  const choice = $("cfg-preset").value;
  if (choice === "random") drawRandomGraph();
  else if (PRESETS.has(choice)) showGraphInputs(PRESETS.get(choice).state);
}

/* Build the starting state from the setup inputs. Returns null (after a toast)
   if the engine rejects it. */
function readConfig() {
  return buildGame(parseInt($("cfg-nodes").value), parseEdges($("cfg-edges").value));
}

/* ---------------- game lifecycle ---------------- */
function newGame(startState, replayMoves) {
  const start = startState || readConfig();
  if (!start) return;
  clearTimeout(G.aiTimer);
  G.start = start;
  showGraphInputs(start);
  G.history = [start];
  G.analyses = [window.BH.analysis(start)];
  G.moves = [];
  G.cursor = 0;
  G.gameOver = false;
  G.thinking = false;
  $("why").innerHTML = "";

  if (replayMoves && replayMoves.length) {
    for (const mv of replayMoves) {
      if (G.gameOver) break;
      if (!commitMove(mv, null)) break;
    }
    G.cursor = G.history.length - 1;
  }
  render();
  maybeScheduleAI();
}

const current = () => G.history[G.history.length - 1];
const shown = () => G.history[G.cursor];
const isLive = () => G.cursor === G.history.length - 1;
const seatToMove = () => G.analyses[G.analyses.length - 1].to_move;

function commitMove(move, meta) {
  const before = current();
  if (!window.BH.legalMoves(before).includes(move)) {
    toast(`Illegal move ${JSON.stringify(move)} — ignored.`);
    return false;
  }
  const seat = seatToMove();
  const tiles = G.analyses[G.analyses.length - 1].tiles_to_place;
  const after = window.BH.applyMove(before, move);
  const an = window.BH.analysis(after);
  G.history.push(after);
  G.analyses.push(an);
  G.moves.push({ seat, move, tiles, elapsed: meta?.elapsed_ms ?? null, info: meta?.info ?? null });
  G.cursor = G.history.length - 1;
  logMove(G.moves[G.moves.length - 1]);
  if (an.terminal) G.gameOver = true;
  return true;
}

function humanMove(node) {
  if (G.gameOver || !isLive() || G.thinking) return;
  if (G.seats[seatToMove()] !== HUMAN) return;
  if (commitMove(node, null)) {
    render();
    maybeScheduleAI();
  }
}

function maybeScheduleAI() {
  clearTimeout(G.aiTimer);
  if (G.gameOver || !isLive() || G.thinking) return;
  const name = G.seats[seatToMove()];
  if (name === HUMAN) return;
  G.aiTimer = setTimeout(() => runAITurn(name), Math.max(0, G.delay));
}

function runAITurn(name) {
  if (G.gameOver || !isLive()) return;
  if (G.seats[seatToMove()] !== name) return; // seat was swapped
  G.thinking = true;
  render();
  try {
    const res = window.BH.askMove(name, current());
    G.thinking = false;
    if (!commitMove(res.move, res)) {
      toast(`${name} returned an illegal move — stopping.`);
      G.gameOver = true;
    }
  } catch (err) {
    G.thinking = false;
    G.gameOver = true;
    toast(`${name} crashed: ${pyMessage(err)}`);
  }
  render();
  maybeScheduleAI();
}

/* ---------------- rendering ---------------- */
function render() {
  renderStatus();
  renderScorebar();
  renderBoard();
  renderXray();
  renderTimeline();
  updateButtons();
}

function seatLabel(i) {
  return `Seat ${i + 1} (${G.seats[i]})`;
}

const pts = (n) => `${n} point${n === 1 ? "" : "s"}`;

function renderStatus() {
  const st = $("status");
  const an = G.analyses[G.cursor];
  if (!isLive()) {
    st.innerHTML = `⏳ Viewing move ${G.cursor} / ${G.moves.length}. ` +
      `<em>Return to the latest move to keep playing.</em>`;
    return;
  }
  if (an.terminal) {
    const [a, b] = an.scores;
    const lead = a === b ? "Both seats score the same."
      : `${esc(seatLabel(a > b ? 0 : 1))} scored more.`;
    st.innerHTML = `🕳 Node <strong>${an.black_hole}</strong> is the black hole. ` +
      `Seat 1 scores <strong>${pts(a)}</strong>, Seat 2 scores <strong>${pts(b)}</strong>. ${lead}`;
    return;
  }
  if (G.gameOver) {
    st.textContent = "The game was stopped.";
    return;
  }
  const seat = an.to_move;
  const who = G.seats[seat];
  const chip = seat === 0 ? "chip-a" : "chip-b";
  const tiles = `${an.tiles_to_place} tile${an.tiles_to_place === 1 ? "" : "s"}`;
  if (who === HUMAN) {
    st.innerHTML = `<span class="chip ${chip}">${esc(seatLabel(seat))}</span> your turn — ` +
      `click a free node to place <strong>${tiles}</strong> on it.`;
  } else {
    st.innerHTML = `<span class="chip ${chip}">${esc(seatLabel(seat))}</span> ${esc(who)} ` +
      `places ${tiles} — ${G.thinking ? "thinking…" : "up next…"}`;
  }
}

/* One card per seat: tiles placed so far, and the score once the game is over. */
function renderScorebar() {
  const box = $("scorebar");
  box.innerHTML = "";
  const state = shown();
  const an = G.analyses[G.cursor];
  for (const seat of [0, 1]) {
    const placed = state.owner.reduce((n, o, v) => n + (o === seat ? state.tiles[v] : 0), 0);
    const card = el("div", `score-card s${seat}`);
    if (!an.terminal && an.to_move === seat) card.classList.add("active");
    card.appendChild(el("div", "score-name", seatLabel(seat)));
    card.appendChild(el("div", "score-tiles", `tiles placed ${placed} / ${an.tiles_per_player}`));
    card.appendChild(el("div", "score-points", an.terminal ? pts(an.scores[seat]) : "—"));
    box.appendChild(card);
  }
}

function renderBoard() {
  const state = shown();
  const an = G.analyses[G.cursor];
  const interactive =
    isLive() && !G.gameOver && !G.thinking && G.seats[an.to_move] === HUMAN;
  const last = G.cursor > 0 ? G.moves[G.cursor - 1].move : -1;
  paintBoard($("board"), state, {
    onPick: interactive ? humanMove : null,
    analysis: an,
    xray: G.showXray,
    highlight: last,
  });
}

function renderXray() {
  const box = $("xray");
  if (!G.showXray) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const an = G.analyses[G.cursor];
  if (an.terminal) {
    box.innerHTML = `<strong>X-ray:</strong> the game is over — node ${an.black_hole} is the black hole.`;
    return;
  }
  // The best hole for each seat, if the game ended right now. Only tiles already
  // placed count: the moves still to come can change everything.
  const entries = Object.entries(an.hole_payoffs).map(([v, s]) => [Number(v), s]);
  const best = (seat) => entries.reduce((b, e) => (e[1][seat] > b[1][seat] ? e : b), entries[0]);
  const [b0, b1] = [best(0), best(1)];
  box.innerHTML =
    `<strong>X-ray:</strong> under each free node, <span class="xs0">Seat 1</span> · ` +
    `<span class="xs1">Seat 2</span> scores if that node became the black hole now. ` +
    `Best hole for Seat 1: node ${b0[0]} (${pts(b0[1][0])}); ` +
    `for Seat 2: node ${b1[0]} (${pts(b1[1][1])}). ` +
    `<em>Only tiles already placed count — the bigger moves are still to come.</em>`;
}

function logMove(m) {
  if (!G.showWhy) return;
  const cls = m.seat === 0 ? "a" : "b";
  const entry = el("div", `why-entry ${cls}`);
  const head = el("div", "head");
  head.appendChild(el("span", null, `${seatLabel(m.seat)} · node ${m.move} +${m.tiles}`));
  head.appendChild(el("span", "time", m.elapsed != null ? `${m.elapsed.toFixed(1)} ms` : "human"));
  entry.appendChild(head);
  // Optional: a bot may explain itself through `last_info`.
  if (m.info && m.info.note) {
    entry.appendChild(el("div", "note", m.info.note));
    const bits = [];
    if (m.info.depth != null) bits.push(`depth ${m.info.depth}`);
    if (m.info.score != null) bits.push(`score ${Number(m.info.score).toFixed(2)}`);
    if (m.info.nodes != null) bits.push(`${m.info.nodes} nodes`);
    if (bits.length) entry.appendChild(el("div", "note", bits.join(" · ")));
  }
  const body = $("why");
  body.insertBefore(entry, body.firstChild);
}

/* ---------------- timeline ---------------- */
function renderTimeline() {
  const slider = $("tl-slider");
  slider.max = G.history.length - 1;
  slider.value = G.cursor;
  $("tl-label").textContent = `move ${G.cursor} / ${G.history.length - 1}`;
}

function gotoCursor(idx) {
  G.cursor = Math.max(0, Math.min(G.history.length - 1, idx));
  clearTimeout(G.aiTimer);
  render();
  if (isLive()) maybeScheduleAI(); // returning to live resumes AI play
}

function setupTimeline() {
  $("tl-first").onclick = () => gotoCursor(0);
  $("tl-prev").onclick = () => gotoCursor(G.cursor - 1);
  $("tl-next").onclick = () => gotoCursor(G.cursor + 1);
  $("tl-last").onclick = () => gotoCursor(G.history.length - 1);
  $("tl-slider").oninput = (e) => gotoCursor(parseInt(e.target.value));
}

/* ---------------- buttons ---------------- */
function updateButtons() {
  const an = G.analyses[G.analyses.length - 1];
  const aiTurn = isLive() && !G.gameOver && G.seats[an.to_move] !== HUMAN;
  $("btn-play-ai").disabled = !aiTurn;
}

/* ---------------- share / replay ---------------- */
function shareLink() {
  const payload = {
    n: G.start.owner.length,
    e: G.start.edges,
    seats: G.seats,
    m: G.moves.map((x) => x.move),
  };
  const hash = "#g=" + btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
  const url = location.origin + location.pathname + hash;
  navigator.clipboard?.writeText(url).then(
    () => toast("Replay link copied to clipboard!"),
    () => toast("Copy failed — link is in the address bar."),
  );
  history.replaceState(null, "", hash);
}

function loadFromHash() {
  if (!location.hash.startsWith("#g=")) return false;
  try {
    const payload = JSON.parse(decodeURIComponent(escape(atob(location.hash.slice(3)))));
    for (const i of [0, 1]) {
      if (payload.seats?.[i]) {
        $(`seat-${i}`).value = payload.seats[i];
        G.seats[i] = payload.seats[i];
      }
    }
    const start = buildGame(payload.n, payload.e);
    if (!start) return false;
    $("cfg-preset").value = "custom";
    newGame(start, payload.m || []);
    showScreen("game");
    toast("Loaded a shared replay.");
    return true;
  } catch (err) {
    toast("Could not read the shared link.");
    return false;
  }
}


/* ---------------- wiring ---------------- */
function setupPlay() {
  setupTimeline();
  $("btn-new").onclick = guard("New game", () => newGame());
  $("btn-share").onclick = guard("Share", shareLink);
  $("btn-random-graph").onclick = guard("Random graph", drawRandomGraph);
  $("cfg-preset").onchange = guard("Graph", onPresetChange);
  // Editing the graph by hand makes it a custom one.
  $("cfg-edges").oninput = () => { $("cfg-preset").value = "custom"; };
  $("cfg-nodes").onchange = () => { $("cfg-preset").value = "custom"; };
  $("btn-play-ai").onclick = guard("Step", () => {
    clearTimeout(G.aiTimer);
    const name = G.seats[seatToMove()];
    if (name !== HUMAN) runAITurn(name);
  });
  $("cfg-delay").onchange = (e) => { G.delay = parseInt(e.target.value) || 0; };
  $("toggle-xray").onchange = guard("X-ray", (e) => { G.showXray = e.target.checked; render(); });
  $("toggle-why").onchange = (e) => { G.showWhy = e.target.checked; };
}
