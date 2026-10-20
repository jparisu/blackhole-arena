"""Reusable strategy implementations that the shipped players are built from.

These are **public API**: a submitted player is free to import one and configure
or subclass it, although writing a bot from scratch is the real exercise.

* :class:`~blackholearena.bots.random_bot.RandomBot` — a uniformly random free
  node; the baseline.
* :class:`~blackholearena.bots.neighbour_bot.FreeNeighbourBot` — a random free
  node that has a free neighbour.
* :class:`~blackholearena.bots.search.SearchBot` — depth-limited alpha-beta
  search with memoization, parametrized by a utility. Three utilities ship:
  :class:`~blackholearena.bots.aggressive.MaxOwnBot`,
  :class:`~blackholearena.bots.aggressive.MinRivalBot` and
  :class:`~blackholearena.bots.cooperative.CooperativeBot`.

The players in ``players/`` add only *identity* — a name, authors, a description
and an icon. See ``players/builtin/random.py`` for the shortest complete example.
"""

from __future__ import annotations

from .aggressive import MaxOwnBot, MinRivalBot
from .cooperative import CooperativeBot
from .neighbour_bot import FreeNeighbourBot
from .random_bot import RandomBot
from .search import SearchBot, expected_scores, search_depth

__all__ = [
    "CooperativeBot",
    "FreeNeighbourBot",
    "MaxOwnBot",
    "MinRivalBot",
    "RandomBot",
    "SearchBot",
    "expected_scores",
    "search_depth",
]
