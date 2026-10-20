"""The cooperative search: assume both players want as many points as possible.

:class:`CooperativeBot` maximizes the **sum** of both final scores and assumes the
opponent plays along, choosing whatever is best for that same sum. Every node of
its tree is a maximizing node, so alpha-beta has nothing to cut except a branch
that already reaches the best possible total.

Against a like-minded opponent this finds the outcomes where everyone scores
well. Against a selfish one it can be exploited: it will happily set up points
the opponent takes.
"""

from __future__ import annotations

from typing import ClassVar

from .search import SearchBot


class CooperativeBot(SearchBot):
    """Maximizes both players' total score; assumes the opponent does too."""

    cooperative: ClassVar[bool] = True

    def utility(self, mine: float, theirs: float) -> float:
        """Every point counts, whoever scores it."""
        return mine + theirs

    def utility_bounds(self, best: int) -> tuple[float, float]:
        """The total lies between 0 and both players' maximum."""
        return (0.0, 2.0 * best)
