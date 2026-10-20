## 2026-10-20 — NIM Arena → BlackHole Arena

- **State shape.** `State` is a JSON-friendly TypedDict `{"edges", "owner", "tiles"}`.
  A move is a plain `int` (the free node). Whose turn it is and how many tiles
  it places are derived from the board (`to_move`, `tiles_to_place`), so a
  state can never contradict itself.
- **Scoring is by points.** Tournament points = sum of a player's scores over
  all its games. Wins/draws/losses ("who outscored whom") are kept, but only as
  information. Game scores are stored by seat `(first, second)`, not by name,
  so two same-named players in `play_match` cannot collide.
- **Forfeits.** The game never reaches a black hole, so the offender scores 0
  and the opponent scores `tiles_per_player` (the maximum possible). Mirrors
  NIM's "opponent wins" and never penalises the innocent side. One place to
  change if another rule is preferred: `tournament._forfeit` (+ webglue/JS).
- **League Elo.** Fed a fractional result: the first player's share of the
  game's points, `a / (a + b)`, 0.5 when both score 0.
- **Knockouts** (CI championship and the web bracket): more points advances;
  a tie goes to the higher seed / upper entrant.
- **Default tournament graphs:** classic (5 nodes, the rules example),
  wheel(7), grid(3x3). Web presets add wheel(11).
- **Players.** Per user request, only `random` ships; easy/medium/hard and the
  minimax/greedy strategies were removed to be rebuilt from scratch.
- **Web.** No hint button any more (NIM's came from the nim-sum; there is no
  closed form here). X-ray shows, per free node, what each player would score
  if it became the black hole now. Graph drawn as SVG with a deterministic
  spring layout plus a separation pass.

## 2026-10-20 — Built-in players: easy, aggressive-max/-min, cooperative

- **One search, three utilities** (`bots/search.py`). Utility over the final
  pair (mine, theirs): max → `mine` vs a minimizing opponent; min → `-theirs`
  vs a minimizing opponent (= the opponent maximizes its own score);
  cooperative → `mine + theirs`, both sides maximize.
- **Depth from a node budget**: largest d with F + F(F-1) + … ≤ 30 000,
  uniform for the whole tree, capped at the end of the game. Measured worst
  case: cooperative on 13 nodes ≈ 0.44 s per whole game (laptop).
- **Heuristic** `expected_scores`: placed tiles weighted by free neighbours
  (hole uniform over free nodes) + tiles still to come × density of the free
  subgraph. Stays within [0, M], so inside the utility bounds.
- **Memoization only for subtrees searched to the end** (user requirement):
  heuristic-backed values depend on depth, so they are never stored or read.
  With a uniform depth a search is complete everywhere or nowhere, so the
  table fills in the endgame; later turns become cache hits. Within one
  search positions never repeat (tile counts encode the turn).
- **Measured league** (3 graphs × 2 × 3 reps, 2 copies): points/game
  aggressive-max 3.7 > aggressive-min 3.1 > easy 2.8 > random 2.6 >
  cooperative 2.4; Elo/win rate led by aggressive-min (≈1790, 0.70).
