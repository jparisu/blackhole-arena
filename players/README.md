# `players/` — the admitted players

Every BlackHole Arena player is a single `.py` file that subclasses
[`blackholearena.player.Player`](../src/blackholearena/player.py) and is admitted
through a manifest. There are two directories, each with its own manifest:

| Directory | Manifest | Holds |
|-----------|----------|-------|
| [`builtin/`](builtin/) | [`builtin/players.yaml`](builtin/players.yaml) | the reference ladder that ships with the project |
| [`custom/`](custom/) | [`custom/players.yaml`](custom/players.yaml) | every player submitted by pull request |

A submission goes in `custom/` and touches nothing else, so two submissions never
collide in the same manifest and none of them can change the reference ladder.

A player file declares **identity and configuration**. The strategies themselves
are reusable and live in [`src/blackholearena/bots/`](../src/blackholearena/bots/),
so `random.py` is a few lines of metadata on top of `RandomBot` rather than a
strategy implementation — and so is every other built-in player. You may do
either: import a strategy and configure or subclass it, or write your own
`choose_move` from scratch.

## The reference ladder (ships with the project)

| File | Class | Built on | Name | Strategy |
|------|-------|----------|------|----------|
| [`builtin/random.py`](builtin/random.py) | `Random` | `RandomBot` | 🎲 `random` | places its tiles on a uniformly random free node — the baseline |
| [`builtin/easy.py`](builtin/easy.py) | `Easy` | `FreeNeighbourBot` | 🌱 `easy` | a random free node that has at least one free neighbour (any free node if none has) |
| [`builtin/aggressive_max.py`](builtin/aggressive_max.py) | `AggressiveMax` | `MaxOwnBot` | ⚔️ `aggressive-max` | alpha-beta search maximizing its own score against an opponent that minimizes it |
| [`builtin/aggressive_min.py`](builtin/aggressive_min.py) | `AggressiveMin` | `MinRivalBot` | 🗡️ `aggressive-min` | alpha-beta search minimizing the opponent's score against an opponent that maximizes it |
| [`builtin/cooperative.py`](builtin/cooperative.py) | `Cooperative` | `CooperativeBot` | 🤝 `cooperative` | search maximizing both players' total, assuming the opponent plays along |

`random` is the baseline: a bot that does not clearly outscore it does not have
a strategy yet. The three searches are one engine,
[`SearchBot`](../src/blackholearena/bots/search.py), that differs only in its
utility and in how it models the opponent. On a measured league run (default
graphs, approximate per-game averages) `aggressive-max` scores the most points
(≈3.7), `aggressive-min` scores fewer (≈3.1) but has the best Elo and win rate,
`easy` (≈2.8) edges out `random` (≈2.6), and `cooperative` (≈2.4) comes last.
How the search works is explained in the
[tournament docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/advanced/tournament/#how-the-search-players-play).

## The submitted players

None yet — [`custom/players.yaml`](custom/players.yaml) is an empty list, waiting
for the first one.

## Add your own

Copy [`builtin/random.py`](builtin/random.py) into `custom/`, rename the class,
implement `choose_move` (return the index of a free node), add one entry to
[`custom/players.yaml`](custom/players.yaml), and open a Pull Request.

The step-by-step walkthrough, with the code to copy and the acceptance criteria,
is in the docs: **[Submit a player](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/submit-a-player/)**
(short version: [CONTRIBUTING.md](../CONTRIBUTING.md)).
