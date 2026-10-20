"""A one-rule player: always play next to a free node, if there is one.

The rule comes from the end of the game. When two free nodes are left, whoever
moves takes one and the other becomes the black hole — so a node with a free
neighbour is a node that *can* end up next to the hole. On the very last move the
rule is exactly right: if the two remaining nodes are adjacent, playing either one
scores the biggest batch of tiles of the game.

Earlier on it is only a rule of thumb: it keeps options open, but it never asks
which free neighbour will actually be the one left.

Among the nodes that satisfy the rule it picks at random, from a seeded private
RNG, so repeated games differ but stay reproducible.
"""

from __future__ import annotations

import random

from ..game import Move, State, adjacency, legal_moves
from ..player import Player


class FreeNeighbourBot(Player):
    """Plays a random free node that has a free neighbour (any free node if none has)."""

    def __init__(self, seed: int | None = None) -> None:
        """Create the bot.

        Args:
            seed: seed for the private RNG that picks among the candidates.
        """
        self._rng = random.Random(seed)

    @classmethod
    def create(cls, seed: int) -> FreeNeighbourBot:
        """Build an instance seeded for one game."""
        return cls(seed=seed)

    def choose_move(self, state: State) -> Move:
        """Return a random free node with at least one free neighbour.

        Falls back to any free node when no free node has a free neighbour.

        Raises:
            ValueError: if ``state`` is a finished game.
        """
        moves = legal_moves(state)
        if not moves:
            raise ValueError("no legal move on a finished game")
        adj = adjacency(state)
        owner = state["owner"]
        candidates = [v for v in moves if any(owner[w] is None for w in adj[v])]
        return self._rng.choice(candidates or moves)
