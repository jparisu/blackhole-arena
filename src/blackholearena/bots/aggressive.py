"""The two adversarial searches: one guards its own score, one attacks the rival's.

Both assume the opponent is out to get them; they differ in what they protect.

* :class:`MaxOwnBot` maximizes **its own** final score and assumes the opponent
  will try to hold that score down. Its value is the score it can *guarantee*.
* :class:`MinRivalBot` minimizes **the opponent's** final score and assumes the
  opponent will try to push its own score up. It never looks at its own points:
  denying the rival is all it cares about.

In a zero-sum game the two would play identically. In BlackHole they do not —
a move can be good for both players, or bad for both — which is exactly what
makes the comparison interesting.
"""

from __future__ import annotations

from .search import SearchBot


class MaxOwnBot(SearchBot):
    """Maximizes its own score; assumes the opponent minimizes it."""

    def utility(self, mine: float, theirs: float) -> float:
        """Only its own score matters."""
        return mine

    def utility_bounds(self, best: int) -> tuple[float, float]:
        """A score lies between 0 and the most a player can score."""
        return (0.0, float(best))


class MinRivalBot(SearchBot):
    """Minimizes the opponent's score; assumes the opponent maximizes it."""

    def utility(self, mine: float, theirs: float) -> float:
        """The lower the opponent's score, the better."""
        return -theirs

    def utility_bounds(self, best: int) -> tuple[float, float]:
        """Minus a score lies between minus the maximum and 0."""
        return (-float(best), 0.0)
