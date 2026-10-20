# Getting started

Four things you can do with the project locally, from least to most.

| I want to… | Command |
|---|---|
| 🔧 install it | `pip install -e ".[dev]"` |
| 🎮 play a game | from Python, [below](#play-a-game-in-python) |
| ✅ run the tests | `pytest` |
| 🏆 run a tournament | `blackhole-tournament` |

!!! tip "Just want to play?"
    Nothing to install: the
    [web page](https://jparisu.github.io/blackhole-arena) runs the same Python in your
    browser.

---

## Install the library

Requires Python 3.10+.

```bash
git clone https://github.com/jparisu/blackhole-arena
cd blackhole-arena
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Play a game in Python

```python
from blackholearena import game, graphs
from blackholearena.manifest import load_players

registry = load_players()          # reads both players.yaml manifests
Random = type(registry.get("random"))
players = [Random.create(seed=0), Random.create(seed=1)]

state = graphs.grid(3, 3)          # 9 nodes -> N = 4 turns per player
while not game.is_terminal(state):
    who = game.to_move(state)
    move = players[who].choose_move(state)
    print(f"player {who} places {game.tiles_to_place(state)} on node {move}")
    state = game.apply_move(state, move)
print("Black hole:", game.black_hole(state), "· scores:", game.scores(state))
```

The game pits two copies of `random` against each other, with different seeds.
Swap one of them for another player of the
[reference ladder](tournament.md#the-reference-ladder) — say,
`registry.get("aggressive-max")` — or for your own bot as soon as you have one.

---

## Run the tests

```bash
pytest
```

The suite checks the game rules and the scoring, that every reference player
returns legal moves and never mutates state, and that the tournament survives
hanging, crashing and cheating bots.

---

## Run the tournament locally

```bash
# Writes the ranking to results/leaderboard.json
blackhole-tournament --out results/leaderboard.json

# Faster, for testing your bot while you write it
blackhole-tournament --no-subprocess

# Custom graphs: NODES:A-B,C-D,... (repeat the flag)
blackhole-tournament --graph 5:0-1,1-2,2-3,3-4,4-0 --graph 3:0-1,1-2
```

See [The tournament](tournament.md) for the formats, the scoring, the timing
and the forfeits.

---

## Run the web app locally

The web page loads the shared Python via Pyodide. First assemble the bundle,
then serve the `web/` folder with any static server:

```bash
python scripts/build_web.py           # -> web/py.zip and web/leaderboard.json
python -m http.server -d web 8000     # open http://localhost:8000
```

!!! warning "Serve it, do not double-click it"
    Under `file://` the browser blocks `fetch()` and the page will not load.
    Always use a server, even the one-liner above.

!!! note "The first load needs internet"
    Pyodide is downloaded from a CDN the first time. Everything after that runs
    locally in your browser.

---

**Next:** [Player API](../upload-a-bot/player-api.md) — write your first AI in
twenty lines.
