# API reference

Every public name in the `blackholearena` package, **generated from the source**
by [mkdocstrings](https://mkdocstrings.github.io/) every time this site is built.
Change a docstring and this page changes with it, so the reference and the code
can never contradict each other.

---

## The game

The rules, as pure functions over a `{"edges", "owner", "tiles"}` state.

::: blackholearena.game

---

## The graphs

Ready-made graphs to play on: the ones the tournament uses by default and the
ones the web page offers.

::: blackholearena.graphs

---

## The player contract

The one class an outsider implements.

::: blackholearena.player.Player

---

## The registry

How players are discovered and looked up by name.

::: blackholearena.registry.Registry

::: blackholearena.manifest.load_players

---

## The tournament

Running games, building the roster and scoring them.

::: blackholearena.tournament.run_tournament

::: blackholearena.tournament.copies_for

::: blackholearena.tournament.build_roster

::: blackholearena.tournament.play_match

---

## Elo rating

::: blackholearena.elo

---

## Reusable strategies

The pieces the reference players are built from: `RandomBot` (🎲 `random`),
`FreeNeighbourBot` (🌱 `easy`) and the `SearchBot` search with its three
utilities (⚔️ `aggressive-max`, 🗡️ `aggressive-min` and 🤝 `cooperative`).
How those three search is explained in [The tournament](tournament.md#how-the-search-players-play).

::: blackholearena.bots.random_bot.RandomBot

::: blackholearena.bots.neighbour_bot

::: blackholearena.bots.search

::: blackholearena.bots.aggressive

::: blackholearena.bots.cooperative
