# BlackHole Arena 🕳️

[![Tests](https://github.com/jparisu/blackhole-arena/actions/workflows/tests.yml/badge.svg)](https://github.com/jparisu/blackhole-arena/actions/workflows/tests.yml)
[![Tournament](https://github.com/jparisu/blackhole-arena/actions/workflows/tournament.yml/badge.svg)](https://github.com/jparisu/blackhole-arena/actions/workflows/tournament.yml)
[![Docs](https://img.shields.io/readthedocs/blackhole-arena/latest)](https://blackhole-arena.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

### ▶️ &nbsp;[**Play it now**](https://jparisu.github.io/blackhole-arena) &nbsp;·&nbsp; 📚 &nbsp;[**Read the docs**](https://blackhole-arena.readthedocs.io/en/latest/en/) &nbsp;·&nbsp; 🚀 &nbsp;[**Submit your own AI**](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/submit-a-player/)

<sub>The documentation is published in English and Spanish — use the language switcher in its header.</sub>

---

A complete, self-contained project built entirely on GitHub, centered on the
graph game **BlackHole**:

- 🐍 a **Python library** — a parametrized game engine, ready-made graphs, a
  clean player API, a ladder of reference AIs, and a robust tournament runner;
- 🌐 a **static web page** — [**jparisu.github.io/blackhole-arena**](https://jparisu.github.io/blackhole-arena) —
  where you play BlackHole against a human or any AI, on the graph of your
  choice, running the *actual Python AI code in the browser* via **Pyodide**;
- 🏆 an **automatic tournament** (GitHub Actions) that pits the AIs against each
  other and publishes a [scoreboard](results/leaderboard.json) ranked by points;
- 📚 **documentation** — [**blackhole-arena.readthedocs.io**](https://blackhole-arena.readthedocs.io/en/latest/en/) —
  in English and Spanish: the rules, the player API, how an outsider [submits a
  new AI player by Pull
  Request](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/submit-a-player/),
  and the reference manual of the tournament, the scoreboard and the web app.

The elegance: the game rules and AIs are written **once, in Python**, and that
exact code runs both in the tournament (CI) and live in the browser
(Pyodide). One source of truth — the rules are **never** re-implemented in
JavaScript.

## The game

BlackHole is played by two players on a graph of `2N + 1` nodes. Each player
has `N` turns, and on its `n`-th turn it places `n` tiles on a free node. After
`2N` turns exactly one node is still free: that is the **black hole**. Each
player scores the tiles it placed on the nodes **adjacent** to the black hole.

Each player tries to maximize **its own** score: the game is **not zero-sum**,
so the tournament ranks players by the total points they score, not by games
won.

Full rules, with a worked example: see the
[docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/rules/).

## Install & play locally

```bash
git clone https://github.com/jparisu/blackhole-arena
cd blackhole-arena
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the tests
pytest

# Run the tournament and write results/leaderboard.json
blackhole-tournament --out results/leaderboard.json
```

Formats, scoring, time budgets and forfeits are covered in the
[tournament docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/advanced/tournament/).

Play a quick game in Python:

```python
from blackholearena import game, graphs
from blackholearena.manifest import load_players

reg = load_players()
Random = type(reg.get("random"))
players = [Random.create(seed=0), Random.create(seed=1)]

state = graphs.classic()
while not game.is_terminal(state):
    move = players[game.to_move(state)].choose_move(state)
    print(state["owner"], "->", move)
    state = game.apply_move(state, move)
print("black hole:", game.black_hole(state), "scores:", game.scores(state))
```

## Run the web app locally

The web page loads the shared Python via Pyodide. Assemble the site assets, then
serve the folder:

```bash
python scripts/build_web.py          # copies the package + players into web/py.zip
python -m http.server -d web 8000    # open http://localhost:8000
```

## The reference players

Registered in [`players/builtin/players.yaml`](players/builtin/players.yaml)
and competing in the tournament. Each is a thin wrapper naming a strategy from
[`blackholearena.bots`](src/blackholearena/bots/) — identity only.

| Name | Strategy | Measured (league, per game) |
|------|----------|-----------------------------|
| 🎲 `random` | places its tiles on a uniformly random free node | ≈2.6 points — the baseline |
| 🌱 `easy` | a random free node that has at least one free neighbour (any free node if none has) — on the last move, that scores the biggest batch of tiles whenever the two remaining nodes are adjacent | ≈2.8 points |
| ⚔️ `aggressive-max` | alpha-beta search maximizing **its own** score, assuming the opponent tries to minimize it | ≈3.7 points — the most points |
| 🗡️ `aggressive-min` | alpha-beta search minimizing **the opponent's** score, assuming the opponent maximizes it | ≈3.1 points — but the best Elo and win rate |
| 🤝 `cooperative` | search maximizing **both** players' total, assuming the opponent plays along | ≈2.4 points — last: selfish opponents exploit it |

The three searches share one engine
([`SearchBot`](src/blackholearena/bots/search.py)): a uniform depth chosen from a
node budget per move, an expected-score heuristic at the depth limit,
alpha-beta pruning, and a transposition table that only keeps subtrees solved to
the end of the game. Each takes well under half a second for a whole game. The
figures above are approximate, from one league run on the default graphs — see
the [tournament docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/advanced/tournament/#the-reference-ladder).
`random` is the baseline every other player has to beat — and the top of the
ladder is open to yours.

## Add your own AI (by Pull Request)

1. Copy [`players/builtin/random.py`](players/builtin/random.py) to
   `players/custom/<your_bot>.py`, or start from the minimal example in the
   [Player API docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/player-api/).
2. Subclass [`Player`](src/blackholearena/player.py), fill in `get_name` /
   `get_authors` / `get_description` / `get_icon`, and implement
   `choose_move(state) -> node` (the index of a free node).
3. Add one entry to
   [`players/custom/players.yaml`](players/custom/players.yaml) — just `file`
   and `class`.
4. Open a PR — CI runs the tests. A player that errors, times out, or reuses an
   existing name is not merged.

Full guide: [CONTRIBUTING.md](CONTRIBUTING.md) ·
[docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/submit-a-player/).

## Repository layout

```
src/blackholearena/       game engine, graphs, Player API, registry, manifest loader, tournament
src/blackholearena/bots/  reusable strategies the reference players are built from
players/builtin/          the reference ladder, and the manifest admitting it
players/custom/           submitted players, and the manifest admitting them
results/                  leaderboard.json, written by the tournament workflow
web/                      GitHub Pages site (Pyodide + thin JS UI)
docs/                     Read the Docs source (MkDocs + Material), in English and Spanish
tests/                    pytest suite
```

## License

[MIT](LICENSE).
