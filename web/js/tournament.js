// BlackHole Arena — the Tournament screen
//
// A user-configured single-elimination bracket. Scheduling and drawing only —
// every move comes from Python via window.BH.
//
// Loaded as a plain script (not an ES module): the whole app shares one global
// namespace by design, and plain scripts keep working without a bundler.
"use strict";

const HUMAN_KIND = "__human__";
/* Mirrors blackholearena.tournament._seed_for_game: fold the tournament seed and the
   slot index together so every entrant is seeded distinctly, yet a given
   (seed, bracket) always reproduces the same tournament. */
const SEED_STRIDE = 1000003;
/* Pause between automatic bot-vs-bot matches, so the bracket visibly advances. */
const AUTO_MATCH_MS = 550;
/* Nodes of the random graph a bracket can be played on. */
const T_RANDOM_NODES = 9;

const T = {
  size: 8,
  seed: 1,
  graph: null,    // the starting state every match is played on
  graphLabel: "",
  slots: [],      // {id, kind, label, icon}
  rounds: [],     // [[{a, b, winner, scores, moves, result, detail, done}]]
  view: null,     // {r, m} match being replayed
  live: null,     // {r, m} human match in progress
  game: null,     // {history, analyses, moves, cursor, over, scores}
  timer: null,
};

const ROUND_NAME = { 1: "Final", 2: "Semifinals", 4: "Quarterfinals", 8: "Round of 16" };

/* ---------------- setup ---------------- */

function tKinds() {
  return (window.BH?.players?.() || []).map((p) => p.name);
}

/* Render a slot with its icon, and its copy index as a subscript when the same
   kind or name entered the bracket more than once. */
function tSlotHtml(slot) {
  if (!slot) return `<span class="muted">—</span>`;
  const display = slot.display || (slot.kind === HUMAN_KIND ? slot.label : slot.kind);
  if (slot.kind !== HUMAN_KIND) return playerHtml(display);
  const [base, idx] = splitPlayer(display);
  return (
    `<span class="p-icon">${HUMAN_ICON}</span>` +
    `<span class="p-name">${esc(base)}${idx == null ? "" : `<sub>${esc(idx)}</sub>`}</span>`
  );
}

/* Offer the same preset graphs as the Play screen, plus one drawn from the seed. */
function tBuildGraphPicker() {
  const sel = $("t-graph");
  const previous = sel.value;
  sel.innerHTML = "";
  for (const p of PRESETS.values()) {
    const o = el("option", null, p.label);
    o.value = p.name;
    sel.appendChild(o);
  }
  const o = el("option", null, `Random — ${T_RANDOM_NODES} nodes, from the seed`);
  o.value = "random";
  sel.appendChild(o);
  sel.value = previous && (PRESETS.has(previous) || previous === "random") ? previous : DEFAULT_PRESET;
}

function tBuildSetup() {
  tBuildGraphPicker();
  const kinds = tKinds();
  const size = parseInt($("t-size").value) || 8;
  const box = $("t-slots");
  const previous = T.slots;
  box.innerHTML = "";
  T.slots = [];

  for (let i = 0; i < size; i++) {
    const prev = previous[i];
    const slot = {
      id: `slot${i}`,
      kind: prev?.kind ?? (kinds[i % Math.max(1, kinds.length)] || HUMAN_KIND),
      label: prev?.label ?? `Player ${i + 1}`,
    };
    T.slots.push(slot);

    const row = el("div", "tslot");
    row.appendChild(el("span", "tslot-no", `${i + 1}`));

    const sel = el("select", "tslot-kind");
    for (const opt of [HUMAN_KIND, ...kinds]) {
      const o = el("option", null, opt === HUMAN_KIND ? `${HUMAN_ICON} Human` : playerText(opt));
      o.value = opt;
      sel.appendChild(o);
    }
    sel.value = slot.kind;

    const nameInput = el("input", "tslot-name");
    nameInput.type = "text";
    nameInput.value = slot.label;
    nameInput.placeholder = "Name";
    const syncName = () => {
      const human = sel.value === HUMAN_KIND;
      nameInput.classList.toggle("hidden", !human);
    };
    sel.onchange = () => { slot.kind = sel.value; syncName(); };
    nameInput.oninput = () => { slot.label = nameInput.value.trim() || `Player ${i + 1}`; };
    syncName();

    row.appendChild(sel);
    row.appendChild(nameInput);
    box.appendChild(row);
  }
}

function tRandomise() {
  const kinds = tKinds();
  if (!kinds.length) return;
  for (const [i, sel] of [...$("t-slots").querySelectorAll(".tslot-kind")].entries()) {
    const pick = kinds[Math.floor(Math.random() * kinds.length)];
    sel.value = pick;
    T.slots[i].kind = pick;
    sel.dispatchEvent(new Event("change"));
  }
}

/* ---------------- bracket construction ---------------- */

function tStart() {
  const seed = parseInt($("t-seed").value);
  if (!Number.isFinite(seed) || seed < 0) { toast("The seed must be a whole number, 0 or more."); return; }
  const choice = $("t-graph").value;
  if (choice === "random") {
    T.graph = window.BH.randomGraph(T_RANDOM_NODES, RANDOM_DENSITY, seed);
    T.graphLabel = `random ${T_RANDOM_NODES}-node graph (seed ${seed})`;
  } else {
    const preset = PRESETS.get(choice) || PRESETS.get(DEFAULT_PRESET);
    T.graph = preset.state;
    T.graphLabel = preset.label;
  }

  T.seed = seed;
  T.size = T.slots.length;

  // Make every display name unique, so the bracket stays readable when a kind
  // (or a human name) is entered more than once. A name used once is left alone;
  // duplicates get the same _0/_1 suffix the real tournament uses.
  const base = (slot) => (slot.kind === HUMAN_KIND ? slot.label : slot.kind);
  const totals = new Map();
  for (const slot of T.slots) totals.set(base(slot), (totals.get(base(slot)) || 0) + 1);
  const used = new Map();
  for (const slot of T.slots) {
    const b = base(slot);
    if (totals.get(b) === 1) { slot.display = b; continue; }
    const n = used.get(b) || 0;
    used.set(b, n + 1);
    slot.display = `${b}_${n}`;
  }

  // One independent, seeded instance per slot.
  window.BH.resetEntrants();
  T.slots.forEach((slot, i) => {
    if (slot.kind !== HUMAN_KIND) {
      window.BH.createEntrant(slot.id, slot.kind, T.seed * SEED_STRIDE + i);
    }
  });

  // Round 0 pairs adjacent slots, which is what the drawn tree shows.
  T.rounds = [];
  let entrants = T.slots.slice();
  while (entrants.length > 1) {
    const round = [];
    for (let i = 0; i < entrants.length; i += 2) {
      round.push({ a: entrants[i], b: entrants[i + 1], winner: null, scores: null,
                   moves: [], result: null, detail: "", done: false });
    }
    T.rounds.push(round);
    entrants = round.map(() => null);
  }

  T.view = null;
  T.live = null;
  T.game = null;
  $("t-setup").classList.add("hidden");
  $("t-reset").classList.remove("hidden");
  $("t-bracket-wrap").classList.remove("hidden");
  $("t-champion").classList.add("hidden");
  $("t-champion").innerHTML = "";
  tRenderBracket();
  tAdvance();
}

function tReset() {
  clearTimeout(T.timer);
  T.rounds = [];
  T.view = T.live = T.game = null;
  $("t-setup").classList.remove("hidden");
  $("t-reset").classList.add("hidden");
  $("t-bracket-wrap").classList.add("hidden");
  $("t-match").classList.add("hidden");
  $("t-champion").classList.add("hidden");
  $("t-champion").innerHTML = "";
  tBuildSetup();
}

/* ---------------- scheduling ---------------- */

/* The next match with both entrants known and no winner yet. */
function tNextMatch() {
  for (let r = 0; r < T.rounds.length; r++) {
    for (let m = 0; m < T.rounds[r].length; m++) {
      const match = T.rounds[r][m];
      if (!match.done && match.a && match.b) return { r, m };
    }
  }
  return null;
}

function tAdvance() {
  if (T.live) return;                       // waiting on a human
  const next = tNextMatch();
  if (!next) { tFinish(); return; }
  const match = T.rounds[next.r][next.m];
  const humans = [match.a, match.b].filter((s) => s.kind === HUMAN_KIND).length;

  if (humans === 0) {
    // Bot vs bot: Python plays the whole game in one call.
    const res = window.BH.playAuto(match.a.id, match.b.id, T.graph);
    tRecord(next, res.scores, res.moves, res.result, res.detail);
    tRenderBracket();
    T.timer = setTimeout(tAdvance, AUTO_MATCH_MS);
    return;
  }
  tOpenLiveMatch(next);
}

/* Record a finished match. More points advances; a tie goes to the upper
   entrant (`a`), mirroring the CI championship's "higher seed" rule. */
function tRecord({ r, m }, scores, moves, result, detail) {
  const match = T.rounds[r][m];
  match.moves = moves;
  match.scores = scores;
  match.result = result;
  match.detail = detail || "";
  match.winner = scores[1] > scores[0] ? match.b : match.a;
  match.done = true;
  // Promote the winner into the next round.
  const next = T.rounds[r + 1];
  if (next) {
    const slotIdx = Math.floor(m / 2);
    if (m % 2 === 0) next[slotIdx].a = match.winner;
    else next[slotIdx].b = match.winner;
  }
}

/* ---------------- a live match involving a human ---------------- */

function tOpenLiveMatch(at) {
  T.live = at;
  T.view = null;
  const match = T.rounds[at.r][at.m];
  T.game = { history: [T.graph], analyses: [window.BH.analysis(T.graph)], moves: [],
             cursor: 0, over: false, scores: null, result: "normal", detail: "" };
  $("t-match").classList.remove("hidden");
  $("t-close-view").classList.add("hidden");
  $("t-timeline").classList.add("hidden");
  $("t-match-title").innerHTML =
    `${tSlotHtml(match.a)} <span class="muted">vs</span> ${tSlotHtml(match.b)}`;
  $("t-match-sub").textContent = `${tRoundName(at.r)} · ${T.graphLabel}`;
  $("t-match").scrollIntoView({ behavior: "smooth", block: "nearest" });
  tRenderLive();
  tMaybeBotTurn();
}

function tCurrent() { return T.game.history[T.game.history.length - 1]; }
function tAnalysis() { return T.game.analyses[T.game.analyses.length - 1]; }

function tSeatSlot(seat) {
  const match = T.rounds[T.live.r][T.live.m];
  return seat === 0 ? match.a : match.b;
}

/* "Ada 3 · 2 random" — each side's points, in seat order. */
function tScoreLine(match, scores) {
  return `${tSlotHtml(match.a)} <strong>${scores[0]}</strong> · ` +
    `<strong>${scores[1]}</strong> ${tSlotHtml(match.b)}`;
}

function tRenderLive() {
  const g = T.game;
  const state = g.history[g.cursor];
  const an = g.analyses[g.cursor];
  const live = g.cursor === g.history.length - 1;
  const mySlot = g.over ? null : tSeatSlot(an.to_move);
  const interactive = live && !g.over && mySlot && mySlot.kind === HUMAN_KIND;

  paintBoard($("t-board"), state, {
    onPick: interactive ? tHumanMove : null,
    analysis: an,
    highlight: g.moves.length ? g.moves[g.moves.length - 1] : -1,
  });

  const status = $("t-status");
  const match = T.rounds[T.live.r][T.live.m];
  if (g.over) {
    const hole = an.terminal ? `🕳 Node ${an.black_hole} is the black hole. ` : "";
    status.innerHTML = `${hole}${tScoreLine(match, g.scores)}`;
  } else {
    const chip = an.to_move === 0 ? "chip-a" : "chip-b";
    const tiles = `${an.tiles_to_place} tile${an.tiles_to_place === 1 ? "" : "s"}`;
    status.innerHTML =
      `<span class="chip ${chip}">${an.to_move === 0 ? "first" : "second"}</span> ` +
      (mySlot.kind === HUMAN_KIND
        ? `${tSlotHtml(mySlot)} — your turn: click a free node to place ${tiles}.`
        : `${tSlotHtml(mySlot)} places ${tiles}…`);
  }
}

function tApply(move) {
  const g = T.game;
  const after = window.BH.applyMove(tCurrent(), move);
  const an = window.BH.analysis(after);
  g.history.push(after);
  g.analyses.push(an);
  g.cursor = g.history.length - 1;
  g.moves.push(move);
  if (an.terminal) {
    g.over = true;
    g.scores = an.scores;
  }
}

function tHumanMove(node) {
  const g = T.game;
  if (g.over || g.cursor !== g.history.length - 1) return;
  if (!window.BH.legalMoves(tCurrent()).includes(node)) { toast("Illegal move — ignored."); return; }
  tApply(node);
  tRenderLive();
  if (g.over) tFinishLiveMatch(); else tMaybeBotTurn();
}

function tMaybeBotTurn() {
  const g = T.game;
  if (g.over) return;
  const seat = tAnalysis().to_move;
  const slot = tSeatSlot(seat);
  if (slot.kind === HUMAN_KIND) return;
  T.timer = setTimeout(() => {
    try {
      const res = window.BH.entrantMove(slot.id, tCurrent());
      if (!window.BH.legalMoves(tCurrent()).includes(res.move)) {
        throw new Error(`illegal move ${JSON.stringify(res.move)}`);
      }
      tApply(res.move);
    } catch (err) {
      // A misbehaving bot forfeits rather than wedging the bracket: it scores 0
      // and the human the maximum, as in the real tournament.
      toast(`${slot.display} failed: ${pyMessage(err)}`);
      const best = tAnalysis().tiles_per_player;
      g.over = true;
      g.scores = seat === 0 ? [0, best] : [best, 0];
      g.result = "forfeit_error";
      g.detail = pyMessage(err);
    }
    tRenderLive();
    if (g.over) tFinishLiveMatch(); else tMaybeBotTurn();
  }, Math.max(150, G.delay));
}

function tFinishLiveMatch() {
  const at = T.live;
  tRecord(at, T.game.scores, T.game.moves, T.game.result, T.game.detail);
  T.live = null;
  tRenderBracket();
  T.timer = setTimeout(() => {
    $("t-match").classList.add("hidden");
    tAdvance();
  }, 1600);
}

/* ---------------- replaying a finished match ---------------- */

function tViewMatch(r, m) {
  const match = T.rounds[r][m];
  if (!match.done || T.live) return;
  T.view = { r, m };
  const states = [T.graph];
  for (const mv of match.moves) states.push(window.BH.applyMove(states[states.length - 1], mv));
  T.game = { history: states, analyses: states.map((st) => window.BH.analysis(st)),
             moves: match.moves, cursor: states.length - 1, over: true, scores: match.scores };

  $("t-match").classList.remove("hidden");
  $("t-close-view").classList.remove("hidden");
  $("t-timeline").classList.remove("hidden");
  $("t-match-title").innerHTML =
    `${tSlotHtml(match.a)} <span class="muted">vs</span> ${tSlotHtml(match.b)}`;
  const how = match.result && match.result !== "normal" ? ` · ${match.result}` : "";
  $("t-match-sub").textContent =
    `${tRoundName(r)} · ${match.moves.length} moves${how}${match.detail ? " · " + match.detail : ""}`;

  const slider = $("t-tl-slider");
  slider.min = 0;
  slider.max = states.length - 1;
  slider.value = states.length - 1;
  slider.oninput = () => { T.game.cursor = parseInt(slider.value); tRenderReplay(); };
  tRenderReplay();
  $("t-match").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function tRenderReplay() {
  const g = T.game;
  const match = T.rounds[T.view.r][T.view.m];
  const an = g.analyses[g.cursor];
  paintBoard($("t-board"), g.history[g.cursor], {
    onPick: null,
    analysis: an,
    highlight: g.cursor > 0 ? g.moves[g.cursor - 1] : -1,
  });
  $("t-tl-slider").value = g.cursor;
  $("t-tl-label").textContent = `move ${g.cursor} / ${g.history.length - 1}`;
  if (g.cursor === g.history.length - 1) {
    const hole = an.terminal ? `🕳 Node ${an.black_hole} is the black hole. ` : "";
    $("t-status").innerHTML =
      `${hole}${tScoreLine(match, match.scores)} — ${tSlotHtml(match.winner)} advances.`;
  } else {
    $("t-status").innerHTML =
      `Showing move ${g.cursor}. ${tSlotHtml(an.to_move === 0 ? match.a : match.b)} to play.`;
  }
}

function tCloseView() {
  T.view = null;
  $("t-match").classList.add("hidden");
  tRenderBracket();
}

/* ---------------- the tree ---------------- */

function tRoundName(r) {
  return ROUND_NAME[T.rounds[r].length] || `Round ${r + 1}`;
}

function tRenderBracket() {
  const wrap = $("t-bracket");
  wrap.innerHTML = "";
  const total = T.rounds.reduce((n, rd) => n + rd.length, 0);
  const done = T.rounds.reduce((n, rd) => n + rd.filter((x) => x.done).length, 0);
  $("t-progress").textContent = `${done} / ${total} matches played`;

  T.rounds.forEach((round, r) => {
    const col = el("div", "sb-round");
    col.appendChild(el("div", "sb-round-name", tRoundName(r)));
    round.forEach((match, m) => {
      const card = el("div", "sb-tie t-tie");
      const next = tNextMatch();
      if (next && next.r === r && next.m === m && !match.done) card.classList.add("t-next");
      if (T.view && T.view.r === r && T.view.m === m) card.classList.add("t-viewing");
      card.appendChild(tTieSide(match, match.a, 0));
      card.appendChild(tTieSide(match, match.b, 1));
      if (match.done) {
        card.classList.add("t-done");
        card.title = "Click to replay this match";
        card.onclick = () => tViewMatch(r, m);
      }
      col.appendChild(card);
    });
    wrap.appendChild(col);
  });
}

function tTieSide(match, slot, seat) {
  const won = match.done && match.winner === slot;
  const row = el("div", `sb-tie-side${won ? " won" : ""}`);
  const name = el("span", "sb-tie-name");
  name.innerHTML = slot ? tSlotHtml(slot) : `<span class="muted">—</span>`;
  row.appendChild(name);
  if (match.done) row.appendChild(el("span", "sb-tie-score", `${match.scores[seat]} pts`));
  return row;
}

/* ---------------- champion ---------------- */

function tFinish() {
  const final = T.rounds[T.rounds.length - 1][0];
  if (!final?.done) return;
  const champion = final.winner;
  const runnerUp = final.winner === final.a ? final.b : final.a;
  // No third-place match in a single-elimination bracket, so both losing
  // semi-finalists share the bronze. Stating that is better than inventing a rank.
  const semis = T.rounds.length >= 2
    ? T.rounds[T.rounds.length - 2].map((mt) => (mt.winner === mt.a ? mt.b : mt.a)).filter(Boolean)
    : [];

  const box = $("t-champion");
  box.classList.remove("hidden");
  box.innerHTML =
    `<div class="confetti" aria-hidden="true">${
      Array.from({ length: 28 }, (_, i) =>
        `<span style="--i:${i};--h:${(i * 37) % 360}">${["🎉", "🎊", "✨", "🏆"][i % 4]}</span>`
      ).join("")
    }</div>` +
    `<div class="tchampion-card">` +
    `<div class="tchampion-crown">🏆</div>` +
    `<h2>${tSlotHtml(champion)} wins the tournament!</h2>` +
    `<div class="podium">` +
    `<div class="podium-step silver"><div class="podium-medal">🥈</div>` +
    `<div class="podium-name">${tSlotHtml(runnerUp)}</div><div class="podium-block">2</div></div>` +
    `<div class="podium-step gold"><div class="podium-medal">🥇</div>` +
    `<div class="podium-name">${tSlotHtml(champion)}</div><div class="podium-block">1</div></div>` +
    `<div class="podium-step bronze"><div class="podium-medal">🥉</div>` +
    `<div class="podium-name">${semis.map(tSlotHtml).join('<span class="muted"> · </span>') || "—"}</div>` +
    `<div class="podium-block">3</div></div>` +
    `</div>` +
    `<p class="muted small">Seed ${T.seed} · ${esc(T.graphLabel)} · ` +
    `${T.rounds.reduce((n, rd) => n + rd.length, 0)} matches. Click any match above to replay it.</p>` +
    `</div>`;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------------- wiring ---------------- */

function setupTournament() {
  // The slot list is NOT built here: it needs the engine's player list, so
  // main() calls tBuildSetup() once boot finishes. Wiring must not depend on
  // anything that can fail, or a dead button is the result.
  $("t-size").onchange = guard("Bracket size", tBuildSetup);
  $("t-start").onclick = guard("Start tournament", tStart);
  $("t-reset").onclick = guard("New bracket", tReset);
  $("t-shuffle").onclick = guard("Randomise", tRandomise);
  $("t-close-view").onclick = guard("Back to bracket", tCloseView);
  const step = (d) => () => {
    if (!T.view) return;
    T.game.cursor = Math.max(0, Math.min(T.game.history.length - 1, T.game.cursor + d));
    tRenderReplay();
  };
  $("t-tl-prev").onclick = guard("Previous move", step(-1));
  $("t-tl-next").onclick = guard("Next move", step(1));
  $("t-tl-first").onclick = guard("First move", () => { if (T.view) { T.game.cursor = 0; tRenderReplay(); } });
  $("t-tl-last").onclick = guard("Last move", () => {
    if (T.view) { T.game.cursor = T.game.history.length - 1; tRenderReplay(); }
  });
}
