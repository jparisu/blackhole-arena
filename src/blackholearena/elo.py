"""A tiny, self-contained Elo rating implementation.

Elo is used by the **league** tournament format (see :mod:`blackholearena.tournament`)
(and reported in every format) to rate players by *who* they outscored, not by
how many points they collected. Ratings are updated **one game at a time**, in play order,
so the result is order-dependent — the tournament always feeds games in a
deterministic order, keeping the ratings reproducible.

BlackHole is not zero-sum, but Elo is computed as if it were: a game is won by
whoever scored more, lost by whoever scored less, and drawn when both scored the
same. That complements the tournament points (which do measure the non-zero-sum
score) with a "who beats whom" rating.
"""

from __future__ import annotations

#: Rating every player starts from before any game is played.
DEFAULT_INITIAL_RATING = 1500.0
#: K-factor: the maximum a single game can move a rating. 32 is the classic
#: value used for casual/most club play — responsive without being volatile.
DEFAULT_K_FACTOR = 32.0
#: Rating gap (in points) at which the stronger player is expected to score ten
#: times as often as the weaker one. 400 is the standard Elo scale constant.
_RATING_SCALE = 400.0


def expected_score(rating: float, opponent_rating: float) -> float:
    """Return the expected score of a player against ``opponent_rating``.

    The value lies in ``(0.0, 1.0)`` and is interpreted as the probability of
    winning (plus half the probability of drawing).

    Args:
        rating: the player's current rating.
        opponent_rating: the opponent's current rating.

    Returns:
        The player's expected score against that opponent.
    """
    return 1.0 / (1.0 + 10.0 ** ((opponent_rating - rating) / _RATING_SCALE))


def updated_ratings(
    rating: float,
    opponent_rating: float,
    score: float,
    *,
    k_factor: float = DEFAULT_K_FACTOR,
) -> tuple[float, float]:
    """Return both ratings after one game, given the first player's ``score``.

    Args:
        rating: the first player's rating before the game.
        opponent_rating: the opponent's rating before the game.
        score: the first player's result — ``1.0`` win, ``0.0`` loss, ``0.5``
            draw (both players scored the same).
        k_factor: the maximum rating change per game.

    Returns:
        A ``(new_rating, new_opponent_rating)`` tuple. The two updates are
        symmetric and conserve total rating.
    """
    expected = expected_score(rating, opponent_rating)
    delta = k_factor * (score - expected)
    return (rating + delta, opponent_rating - delta)
