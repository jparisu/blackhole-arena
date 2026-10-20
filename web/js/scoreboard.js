// BlackHole Arena — the Scoreboard screen
//
// Renders results/leaderboard.json: standings, the player filter, the radar
// chart, per-match details and totals.
//
// Loaded as a plain script (not an ES module): the whole app shares one global
// namespace by design, and plain scripts keep working without a bundler.
"use strict";

/* ---------------- scoreboard ---------------- */
const MEDALS = { 1: "🥇", 2: "🥈", 3: "🥉" };
const fmtMs = (v) => (v == null ? "—" : `${Number(v).toFixed(v < 10 ? 3 : 1)} ms`);
const MODE_LABEL = { simple: "Simple", league: "League", championship: "Championship" };
const MODE_BLURB = {
  simple: "Every pair plays one match; players are ranked by points — the sum of " +
    "what they scored in every game.",
  league: "Every pair plays one match; players are ranked by Elo, computed as if " +
    "each game were won by whoever scored more.",
  championship: "A group phase (round-robin by points, top two advance) then a " +
    "knockout bracket where more points over the match advances.",
};

async function loadScoreboard() {
  const meta = $("sb-meta");
  const layout = $("sb-layout");
  const empty = $("sb-empty");
  try {
    const resp = await fetch("leaderboard.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error("not found");
    const data = await resp.json();
    empty.classList.add("hidden");
    layout.classList.remove("hidden");
    renderScoreboard(data);
  } catch {
    layout.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent =
      "No leaderboard yet. Run the tournament (`blackhole-tournament`) or the tournament workflow to generate results/leaderboard.json.";
    meta.textContent = "";
  }
}

/* The scoreboard's current view state. `selected` holds roster names ("random_0"). */
const SB = { data: null, useElo: false, mode: "simple", selected: new Set() };

/* How many copies of each kind ran. The count is per kind — the reference bots
   are entered twice, submissions once — so print a range when it is not uniform
   rather than a single number that would be wrong for most of the roster. */
function rosterShape(data, cfg) {
  const counts = Object.values(cfg.player_copies || {});
  const entrants = (data.standings || []).length;
  if (!counts.length) return `${cfg.player_repetition ?? "?"} per kind`;
  const lo = Math.min(...counts);
  const hi = Math.max(...counts);
  const per = lo === hi ? `${lo} per kind` : `${lo}-${hi} per kind`;
  return `${entrants} entrants, ${per}`;
}

function renderScoreboard(data) {
  const cfg = data.config || {};
  const mode = cfg.tournament || "simple";
  const useElo = !!cfg.elo;

  // The leaderboard carries its own player directory, so the scoreboard does not
  // depend on the live registry still matching the run that produced it.
  for (const p of data.players || []) META.set(p.name, p);

  SB.data = data;
  SB.mode = mode;
  SB.useElo = useElo;
  SB.selected = new Set((data.standings || []).map((r) => r.player));

  $("sb-title").textContent = `${MODE_LABEL[mode] || "Tournament"} results`;
  $("sb-meta").textContent =
    `Generated ${data.generated_at} · ${MODE_LABEL[mode] || mode} · ` +
    `${rosterShape(data, cfg)} · ${cfg.repetitions ?? "?"} reps/graph · ` +
    `graphs of ${(cfg.graphs || []).map((g) => g.nodes).join(", ") || "?"} nodes · ` +
    `budget ${cfg.game_budget_ms != null ? cfg.game_budget_ms + " ms/game" : "none"}`;

  buildPlayerFilter();
  renderStructure(data, mode);   // tournament-wide: never filtered
  renderTotals(data.totals || {});
  renderFiltered();
}

/* Everything that reacts to the player filter. */
function renderFiltered() {
  const data = SB.data || {};
  const keep = (name) => SB.selected.has(name);
  const standings = (data.standings || []).filter((r) => keep(r.player));
  const stats = (data.player_stats || []).filter((s) => keep(s.player));
  // A match is shown only when BOTH sides are selected: half a pairing tells you
  // nothing, and it would make the score column unreadable.
  const matches = (data.matches || []).filter((m) => keep(m.player_a) && keep(m.player_b));

  const total = (data.standings || []).length;
  $("sb-filter-count").textContent = `${SB.selected.size}/${total}`;
  $("sb-filter-hint").textContent =
    SB.selected.size === total
      ? "showing every player"
      : `showing ${SB.selected.size} of ${total} players`;

  renderStandings(standings, SB.useElo);
  renderRadar(stats);
  renderMatches(matches);
  renderPlayerStats(stats);
}

/* ---------------- player filter ---------------- */
function buildPlayerFilter() {
  const list = $("sb-filter-list");
  list.innerHTML = "";
  for (const row of SB.data.standings || []) {
    const name = row.player;
    const label = el("label", "sb-filter-item");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.value = name;
    cb.onchange = () => {
      if (cb.checked) SB.selected.add(name);
      else SB.selected.delete(name);
      renderFiltered();
    };
    label.appendChild(cb);
    const tag = el("span", "sb-filter-name");
    tag.innerHTML = playerHtml(name);
    label.appendChild(tag);
    list.appendChild(label);
  }
  const setAll = (on) => {
    SB.selected = on ? new Set((SB.data.standings || []).map((r) => r.player)) : new Set();
    for (const cb of list.querySelectorAll("input[type=checkbox]")) cb.checked = on;
    renderFiltered();
  };
  $("sb-filter-all").onclick = guard("Select all", (e) => { e.preventDefault(); setAll(true); });
  $("sb-filter-none").onclick = guard("Deselect all", (e) => { e.preventDefault(); setAll(false); });
}

/* ---------------- radar chart ---------------- */
/* Four axes, hand-drawn as SVG: no chart library is available offline, and a
   square needs no more than trigonometry. Two of them read the game as it is
   (not zero-sum: points), two read it as if it were zero-sum (whoever scored
   more won the game: Elo and win rate). */
const RADAR_AXES = [
  // Total points: the sum of every score — the non-zero-sum measure.
  { key: "points", label: "Points", higherIsBetter: true },
  // Elo, computed as if each game were won, drawn or lost.
  { key: "elo", label: "Elo", higherIsBetter: true },
  // Faster thinking should read as "better", i.e. further from the centre — so
  // this axis is inverted. Without that, the slowest bot would look strongest.
  { key: "avg_move_ms", label: "Avg move", higherIsBetter: false },
  // Share of games in which the player outscored its opponent.
  { key: "win_rate", label: "Win rate", higherIsBetter: true },
];

function renderRadar(stats) {
  const box = $("sb-radar");
  box.innerHTML = "";
  const axes = RADAR_AXES;
  const radarValue = (s, a) => Number(s[a.key]) || 0;
  $("sb-radar-sub").textContent = `${stats.length} shown · ${axes.map((a) => a.label).join(" · ")}`;

  if (!stats.length) {
    box.appendChild(el("p", "muted", "No players selected."));
    return;
  }

  // Normalise each axis across the *shown* players, so the chart always uses its
  // full area. A flat axis (everyone equal) sits at mid-radius.
  const ranges = axes.map((a) => {
    const vals = stats.map((s) => radarValue(s, a));
    return { min: Math.min(...vals), max: Math.max(...vals) };
  });
  const norm = (value, i) => {
    const { min, max } = ranges[i];
    if (max === min) return 0.55;
    const t = (value - min) / (max - min);
    // Floor at 0.12 so the weakest player is still a visible shape, not a dot.
    return 0.12 + 0.88 * (axes[i].higherIsBetter ? t : 1 - t);
  };

  const SIZE = 320, C = SIZE / 2, R = C - 46;
  const angle = (i) => (Math.PI * 2 * i) / axes.length - Math.PI / 2;
  const pt = (i, r) => [C + Math.cos(angle(i)) * R * r, C + Math.sin(angle(i)) * R * r];

  const parts = [];
  // Grid rings + spokes.
  for (const ring of [0.25, 0.5, 0.75, 1]) {
    const pts = axes.map((_, i) => pt(i, ring).map((n) => n.toFixed(1)).join(",")).join(" ");
    parts.push(`<polygon class="radar-grid" points="${pts}"/>`);
  }
  axes.forEach((a, i) => {
    const [x, y] = pt(i, 1);
    parts.push(`<line class="radar-spoke" x1="${C}" y1="${C}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`);
    const [lx, ly] = pt(i, 1.2);
    const anchor = Math.abs(lx - C) < 6 ? "middle" : lx > C ? "start" : "end";
    parts.push(
      `<text class="radar-axis" x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" ` +
      `text-anchor="${anchor}">${esc(a.label)}</text>`
    );
  });
  // One polygon per player.
  stats.forEach((s, idx) => {
    const hue = Math.round((360 * idx) / Math.max(1, stats.length));
    const pts = axes
      .map((a, i) => pt(i, norm(radarValue(s, a), i)).map((n) => n.toFixed(1)).join(","))
      .join(" ");
    parts.push(
      `<polygon class="radar-shape" points="${pts}" ` +
      `style="stroke:hsl(${hue} 75% 60%);fill:hsl(${hue} 75% 60% / 0.13)"/>`
    );
  });

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${SIZE} ${SIZE}`);
  svg.setAttribute("class", "radar");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Comparison of ${stats.length} players`);
  svg.innerHTML = parts.join("");
  const wrap = el("div", "radar-wrap");
  wrap.appendChild(svg);

  const legend = el("div", "radar-legend");
  stats.forEach((s, idx) => {
    const hue = Math.round((360 * idx) / Math.max(1, stats.length));
    const item = el("span", "radar-legend-item");
    item.innerHTML =
      `<span class="radar-swatch" style="background:hsl(${hue} 75% 60%)"></span>` + playerHtml(s.player);
    legend.appendChild(item);
  });
  wrap.appendChild(legend);
  box.appendChild(wrap);
  box.appendChild(el("p", "muted small",
    "Each axis is scaled across the players shown. Points measure the real, " +
    "non-zero-sum score; Elo and win rate treat each game as won by whoever scored " +
    "more. Avg move is inverted: faster thinking reaches further out."));
}

/* Right-wing classification column. */
function renderStandings(standings, useElo) {
  $("sb-class-title").textContent = useElo ? "Classification · Elo" : "Classification · points";
  const ol = $("sb-standings");
  ol.innerHTML = "";
  for (const row of standings) {
    const li = el("li", `sb-rank rank-${row.rank}`);
    const score = useElo ? Math.round(row.elo) : `${row.points} pts`;
    li.innerHTML =
      `<span class="sb-rank-no">${MEDALS[row.rank] || row.rank}</span>` +
      `<span class="sb-rank-name">${playerHtml(row.player)}</span>` +
      `<span class="sb-rank-score">${esc(score)}</span>` +
      `<span class="sb-rank-wl">${useElo ? `${row.points} pts` : `elo ${Math.round(row.elo ?? 0)}`}` +
      ` · W-D-L ${row.wins}–${row.draws}–${row.losses}` +
      `${row.forfeits ? ` · ${row.forfeits} ff` : ""}</span>`;
    ol.appendChild(li);
  }
}

/* Tournament structure block (mode-dependent). */
function renderStructure(data, mode) {
  $("sb-structure-sub").textContent = MODE_LABEL[mode] || mode;
  const box = $("sb-structure");
  box.innerHTML = "";
  box.appendChild(el("p", "muted", MODE_BLURB[mode] || ""));

  const struct = data.structure || {};
  if (mode !== "championship") {
    const t = data.totals || {};
    box.appendChild(el("p", null,
      `${t.players ?? "?"} players · ${t.matches ?? "?"} matches · ${t.games ?? "?"} games.`));
    return;
  }

  // Group phase
  const groupsWrap = el("div", "sb-groups");
  for (const g of struct.groups || []) {
    const card = el("div", "sb-group");
    card.appendChild(el("h4", null, g.name));
    const table = el("table", "sb-mini");
    table.innerHTML =
      "<thead><tr><th>#</th><th>Player</th><th>Pts</th><th>W</th><th>D</th><th>L</th></tr></thead>";
    const tb = el("tbody");
    for (const r of g.table) {
      const advanced = (g.advance || []).includes(r.player);
      const tr = el("tr", advanced ? "advances" : null);
      tr.innerHTML =
        `<td>${r.rank}</td><td>${playerHtml(r.player)}${advanced ? " ⬆" : ""}</td>` +
        `<td>${r.points}</td><td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td>`;
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    card.appendChild(table);
    groupsWrap.appendChild(card);
  }
  box.appendChild(el("h4", "sb-phase-title", "Group phase"));
  box.appendChild(groupsWrap);

  // Knockout bracket
  const bracket = struct.bracket || {};
  box.appendChild(el("h4", "sb-phase-title", "Knockout bracket"));
  const brWrap = el("div", "sb-bracket");
  for (const round of bracket.rounds || []) {
    const col = el("div", "sb-round");
    col.appendChild(el("div", "sb-round-name", round.name));
    for (const tie of round.ties) {
      const card = el("div", "sb-tie");
      card.appendChild(tieSide(tie.a, tie.a_points, tie.winner === tie.a, tie.b == null));
      card.appendChild(tieSide(tie.b, tie.b_points, tie.winner === tie.b, false));
      col.appendChild(card);
    }
    brWrap.appendChild(col);
  }
  box.appendChild(brWrap);
  if (bracket.champion) {
    const champ = el("div", "sb-champion");
    champ.innerHTML = `🏆 Champion: ${playerHtml(bracket.champion)}`;
    box.appendChild(champ);
  }
}

function tieSide(name, points, isWinner, isBye) {
  const row = el("div", `sb-tie-side${isWinner ? " won" : ""}`);
  if (name == null) {
    row.appendChild(el("span", "sb-tie-name muted", "— bye —"));
    return row;
  }
  const tieName = el("span", "sb-tie-name");
  tieName.innerHTML = playerHtml(name);
  row.appendChild(tieName);
  if (!isBye) row.appendChild(el("span", "sb-tie-score", `${points} pts`));
  return row;
}

/* Match summary — one expandable entry per match, mirroring Player stats. */
function renderMatches(matches) {
  $("sb-matches-sub").textContent = `${matches.length} matches`;
  const box = $("sb-matches");
  box.innerHTML = "";
  if (!matches.length) {
    box.appendChild(el("p", "muted", "No matches between the selected players."));
    return;
  }
  for (const m of matches) {
    const d = el("details", "sb-match");
    const summary = el("summary");
    const decided = m.winner
      ? `<span class="sb-match-win">${playerHtml(m.winner)}</span>`
      : `<span class="muted">tie</span>`;
    summary.innerHTML =
      `<span class="sb-match-pair">${playerHtml(m.player_a)}` +
      `<span class="muted"> vs </span>${playerHtml(m.player_b)}</span>` +
      `<span class="sb-match-score">${m.a_points}–${m.b_points} pts</span>` +
      `<span class="sb-match-meta">${decided}` +
      `${m.forfeits ? ` · <span class="warn">${m.forfeits} ff</span>` : ""}</span>`;
    d.appendChild(summary);

    const body = el("div", "sb-match-body");
    const tiles = el("div", "sb-tiles");
    tiles.appendChild(statTile("Phase", m.phase || "—"));
    tiles.appendChild(statTile("Games", String(m.games)));
    tiles.appendChild(statTile("Points", `${m.a_points}–${m.b_points}`));
    tiles.appendChild(statTile("Games won", `${m.a_wins}–${m.b_wins} · ${m.draws} drawn`));
    tiles.appendChild(statTile("Forfeits", String(m.forfeits ?? 0)));
    body.appendChild(tiles);

    // Per-side timing, which the flat table had no room for.
    const table = el("table", "sb-mini");
    table.innerHTML =
      "<thead><tr><th>Player</th><th>Points</th><th>Wins</th><th>Avg move</th>" +
      "<th>Std</th><th>Max move</th></tr></thead>";
    const tb = el("tbody");
    for (const side of ["a", "b"]) {
      const name = m[`player_${side}`];
      const tr = el("tr", m.winner === name ? "advances" : null);
      tr.innerHTML =
        `<td>${playerHtml(name)}</td>` +
        `<td class="num">${m[`${side}_points`]}</td>` +
        `<td class="num">${m[`${side}_wins`]}</td>` +
        `<td class="num">${fmtMs(m[`${side}_avg_move_ms`])}</td>` +
        `<td class="num">${fmtMs(m[`${side}_std_move_ms`])}</td>` +
        `<td class="num">${fmtMs(m[`${side}_max_move_ms`])}</td>`;
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    body.appendChild(el("h5", "sb-h2h", "Per player"));
    body.appendChild(table);
    d.appendChild(body);
    box.appendChild(d);
  }
}

/* Player stats — per-player card with head-to-head breakdown. */
function renderPlayerStats(stats) {
  $("sb-players-sub").textContent = `${stats.length} players`;
  const box = $("sb-playerstats");
  box.innerHTML = "";
  for (const s of stats) {
    const d = el("details", "sb-player");
    const summary = el("summary");
    summary.innerHTML =
      `<span class="sb-player-name">${playerHtml(s.player)}</span>` +
      `<span class="sb-player-quick">${s.points} pts · ${s.wins}–${s.draws}–${s.losses}` +
      `${s.elo != null ? ` · elo ${Math.round(s.elo)}` : ""}</span>`;
    d.appendChild(summary);

    const body = el("div", "sb-player-body");
    const tiles = el("div", "sb-tiles");
    tiles.appendChild(statTile("Points", String(s.points)));
    tiles.appendChild(statTile("Avg points / game", Number(s.avg_points).toFixed(2)));
    tiles.appendChild(statTile("Points against", String(s.points_against)));
    tiles.appendChild(statTile("Won / Drawn / Lost", `${s.wins} / ${s.draws} / ${s.losses}`));
    tiles.appendChild(statTile("Win rate", `${(s.win_rate * 100).toFixed(0)}%`));
    tiles.appendChild(statTile("Forfeits", String(s.forfeits)));
    tiles.appendChild(statTile("Avg move", fmtMs(s.avg_move_ms)));
    tiles.appendChild(statTile("Std move", fmtMs(s.std_move_ms)));
    tiles.appendChild(statTile("Max move", fmtMs(s.max_move_ms)));
    tiles.appendChild(statTile("Moves made", String(s.moves_made)));
    if (s.elo != null) tiles.appendChild(statTile("Elo", String(Math.round(s.elo))));
    body.appendChild(tiles);

    // Head-to-head follows the same filter, so a hidden player never appears here.
    const opponents = (s.opponents || []).filter((o) => SB.selected.has(o.opponent));
    if (opponents.length) {
      const oppTable = el("table", "sb-mini");
      oppTable.innerHTML =
        "<thead><tr><th>Opponent</th><th>Pts</th><th>Against</th>" +
        "<th>W</th><th>D</th><th>L</th></tr></thead>";
      const tb = el("tbody");
      for (const o of opponents) {
        const tr = el("tr");
        tr.innerHTML =
          `<td>${playerHtml(o.opponent)}</td><td>${o.points}</td><td>${o.points_against}</td>` +
          `<td>${o.wins}</td><td>${o.draws}</td><td>${o.losses}</td>`;
        tb.appendChild(tr);
      }
      oppTable.appendChild(tb);
      body.appendChild(el("h5", "sb-h2h", "Head-to-head"));
      body.appendChild(oppTable);
    }
    d.appendChild(body);
    box.appendChild(d);
  }
}

/* Total stats — overview tiles. */
function renderTotals(t) {
  $("sb-totals-sub").textContent = `${t.games ?? "?"} games`;
  const box = $("sb-totals");
  box.innerHTML = "";
  const tiles = el("div", "sb-tiles");
  tiles.appendChild(statTile("Players", String(t.players ?? "—")));
  tiles.appendChild(statTile("Matches", String(t.matches ?? "—")));
  tiles.appendChild(statTile("Games", String(t.games ?? "—")));
  tiles.appendChild(statTile("Total points", String(t.total_points ?? "—")));
  tiles.appendChild(statTile("Avg points / game", String(t.avg_game_points ?? "—")));
  tiles.appendChild(statTile("Total moves", String(t.total_moves ?? "—")));
  tiles.appendChild(statTile("Avg game length", `${t.avg_game_moves ?? "—"} moves`));
  tiles.appendChild(statTile("Longest game", `${t.longest_game_moves ?? "—"} moves`));
  tiles.appendChild(statTile("Forfeits", String(t.forfeits ?? "—")));
  tiles.appendChild(statTile("Total think time",
    t.total_move_time_ms != null ? `${(t.total_move_time_ms / 1000).toFixed(2)} s` : "—"));
  box.appendChild(tiles);
}

function statTile(label, value) {
  const tile = el("div", "sb-tile");
  tile.appendChild(el("div", "sb-tile-value", value));
  tile.appendChild(el("div", "sb-tile-label", label));
  return tile;
}


/* ---------------- wiring ---------------- */
function setupScoreboard() {
  // A <details> dropdown stays open until toggled, which feels broken. Bound
  // once here rather than on every filter rebuild.
  document.addEventListener("click", (e) => {
    const box = $("sb-filter");
    if (box && box.open && !box.contains(e.target)) box.open = false;
  });
}
