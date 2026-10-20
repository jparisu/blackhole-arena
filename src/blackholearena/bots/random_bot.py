"""The simplest possible correct player: pick a legal move uniformly at random.

This is the baseline every other bot has to beat, and the clearest example of the
:class:`~blackholearena.player.Player` contract.
"""

from __future__ import annotations

import random

from ..game import Move, State, legal_moves
from ..player import Player


class RandomBot(Player):
    """Chooses uniformly among all legal moves."""

    def __init__(self, seed: int | None = None) -> None:
        """Create the bot.

        Args:
            seed: seed for the private RNG. A private RNG keeps the bot
                reproducible without touching global random state.
        """
        self._rng = random.Random(seed)

    @classmethod
    def create(cls, seed: int) -> RandomBot:
        """Build an instance seeded for one game."""
        return cls(seed=seed)

    def choose_move(self, state: State) -> Move:
        """Return a free node chosen uniformly at random."""
        return self._rng.choice(legal_moves(state))
