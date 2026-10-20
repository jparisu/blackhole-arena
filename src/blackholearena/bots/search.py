"""A generic depth-limited game-tree search, parametrized by what a player wants.

BlackHole is **not zero-sum**, so "the best move" depends on two modelling
choices that plain minimax hides:

1. **What the bot values** at the end of a game, given both final scores
   ``(mine, theirs)`` — its :meth:`SearchBot.utility`.
2. **How the opponent behaves** — :attr:`SearchBot.cooperative`. An
   *adversarial* opponent picks whatever is worst for the bot's utility; a
   *cooperative* one picks whatever is best for it.

The subclasses in this package are nothing but those two choices:

* :class:`~blackholearena.bots.aggressive.MaxOwnBot` — maximize ``mine``;
  the opponent minimizes it.
* :class:`~blackholearena.bots.aggressive.MinRivalBot` — maximize ``-theirs``;
  the opponent minimizes that, i.e. maximizes its own score.
* :class:`~blackholearena.bots.cooperative.CooperativeBot` — maximize
  ``mine + theirs``; the opponent plays along.

How deep it searches
--------------------
From a position with ``F`` free nodes there are ``F`` moves, then ``F - 1``, and
so on, so a full tree of depth ``d`` holds ``F + F(F-1) + ... + F!/(F-d)!``
nodes. Before each move the bot picks the **largest uniform depth whose full
tree fits in** :attr:`SearchBot.max_nodes` (see :func:`search_depth`), capped at
the end of the game. Every branch is searched to that same depth: early in the
game the tree is wide and the search shallow; near the end it reaches the final
positions and plays exactly. Pruning only ever makes the real count smaller.

At the depth limit, positions are scored by :func:`expected_scores`, a
heuristic estimate of both final scores, fed through the same utility.

Pruning and memoization
-----------------------
**Alpha-beta** applies to all three bots, because each one reduces to "one side
maximizes a number, the other maximizes or minimizes the same number". The
search window starts at the utility's true bounds
(:meth:`SearchBot.utility_bounds`), so a branch that already reaches the best
possible value stops the search at once — the only cut available to the
cooperative bot, whose nodes all maximize.

**A transposition table** remembers positions whose subtree was searched **all
the way to the end of the game** — and only those. Such a value is the true game
value (or, after an alpha-beta cutoff, a true bound on it), so it can be reused
safely. A value that rests on heuristic leaves is *not* stored: it depends on how
deep that particular search happened to go, and reusing it would make the answer
depend on what the bot searched before. Entries are likewise only *used* by a
search that would itself reach the end from there, so every tree keeps one
uniform depth, and a bot that remembers plays exactly like a fresh one.

Each entry holds the value, whether it is exact or a lower/upper bound, and the
best move, which is tried first next time (better ordering, more cutoffs). A
subtlety of this game: a node's tile count *is* the turn it was played on, so a
position records its own history and **no position can be reached twice within
one search**. The table pays off *across turns* instead: two plies later, the new
root's endgame was very likely solved already.
"""

from __future__ import annotations

import random
from abc import abstractmethod
from typing import Any, ClassVar

from ..game import (
    Move,
    State,
    adjacency,
    apply_move,
    free_nodes,
    is_terminal,
    legal_moves,
    scores,
    tiles_per_player,
    to_move,
)
from ..player import Player

#: Default node budget per move. Measured: a whole 13-node game takes the
#: cooperative bot (the one that prunes least) about 0.4 s on a laptop, which
#: leaves room for a slower CI runner, or Pyodide, inside the tournament's
#: 2-second-per-game clock.
DEFAULT_MAX_NODES = 30_000
#: Entries kept in the transposition table before it is cleared.
_MAX_TABLE_ENTRIES = 200_000

# Kinds of transposition-table entry.
_EXACT, _LOWER, _UPPER = 0, 1, 2

_INF = float("inf")


def search_depth(free: int, max_nodes: int) -> int:
    """Return the deepest uniform depth whose full tree fits in ``max_nodes``.

    From ``free`` free nodes the game has ``free - 1`` moves left, and ply ``k``
    offers ``free - k`` moves, so depth ``d`` costs
    ``free + free(free-1) + ... + free!/(free-d)!`` nodes.

    Returns:
        A depth between 1 and ``free - 1`` (0 if the game is already over). At
        least 1, so a bot always looks at its own moves even on a tiny budget.
    """
    remaining = max(free - 1, 0)
    if remaining == 0:
        return 0
    depth, level, total = 0, 1, 0
    while depth < remaining:
        level *= free - depth  # nodes at ply `depth + 1`
        if total + level > max_nodes:
            break
        total += level
        depth += 1
    return max(depth, 1)


def expected_scores(state: State, adj: list[list[int]]) -> tuple[float, float]:
    """Estimate both final scores, ``(first, second)``, of an unfinished game.

    Two parts, assuming nothing about how anybody will play:

    * **Tiles already placed.** The black hole will be one of the free nodes;
      taking each one as equally likely, a tile counts in proportion to how many
      free neighbours its node has.
    * **Tiles still to come.** Each future tile lands on a free node and the hole
      is another free node; it scores when the two are adjacent, which for a
      random pair happens with the density of the free part of the graph.

    The estimate never exceeds :func:`~blackholearena.game.tiles_per_player`, so
    it stays inside the same bounds as a real score.

    Args:
        state: a position with at least two free nodes.
        adj: ``adjacency(state)``, passed in so a search computes it once.
    """
    owner, tiles = state["owner"], state["tiles"]
    free = free_nodes(state)
    count = len(free)
    placed = [0.0, 0.0]
    for f in free:
        for v in adj[f]:
            who = owner[v]
            if who is not None:
                placed[who] += tiles[v]
    is_free = [o is None for o in owner]
    free_edges = sum(1 for a, b in state["edges"] if is_free[a] and is_free[b])
    pair_adjacent = 2 * free_edges / (count * (count - 1)) if count > 1 else 0.0
    best = tiles_per_player(state)
    used = [0, 0]
    for who, t in zip(owner, tiles, strict=True):
        if who is not None:
            used[who] += t
    return (
        placed[0] / count + (best - used[0]) * pair_adjacent,
        placed[1] / count + (best - used[1]) * pair_adjacent,
    )


class SearchBot(Player):
    """Depth-limited alpha-beta search over a configurable utility.

    Subclass it and implement :meth:`utility` and :meth:`utility_bounds`; set
    :attr:`cooperative` if the opponent should be assumed to help. Like every
    class in this package it stays abstract until a subclass declares its
    identity, so it cannot be entered in a tournament by accident.
    """

    #: ``True``: the opponent maximizes this bot's utility too.
    #: ``False``: the opponent minimizes it.
    cooperative: ClassVar[bool] = False

    def __init__(self, max_nodes: int = DEFAULT_MAX_NODES, seed: int | None = None) -> None:
        """Create the searcher.

        Args:
            max_nodes: node budget per move; decides the search depth (see
                :func:`search_depth`). Must be at least 1.
            seed: seed for the private RNG used only to break ties between
                equally-valued moves.

        Raises:
            ValueError: if ``max_nodes`` is less than 1.
        """
        if max_nodes < 1:
            raise ValueError(f"max_nodes must be >= 1, got {max_nodes}")
        self.max_nodes = max_nodes
        self._rng = random.Random(seed)
        #: position -> (value, kind, best move), for subtrees solved to the end.
        self._table: dict[tuple[Any, ...], tuple[float, int, Move]] = {}
        self._graph: tuple[int, tuple[tuple[int, ...], ...]] | None = None
        self._adj: list[list[int]] = []
        self._nodes = 0
        #: Populated after each search, for the web move log. An optional extra,
        #: not part of the Player contract; ``Any`` because it goes to JSON.
        self.last_info: dict[str, Any] = {}

    @classmethod
    def create(cls, seed: int) -> SearchBot:
        """Build an instance for one game, with the default budget and ``seed``."""
        return cls(seed=seed)

    # ------------------------------------------------------------------ #
    # What the bot wants                                                 #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def utility(self, mine: float, theirs: float) -> float:
        """Return how much this bot likes a final (or estimated) score pair."""

    @abstractmethod
    def utility_bounds(self, best: int) -> tuple[float, float]:
        """Return the lowest and highest possible :meth:`utility`.

        Args:
            best: the most a player can score on this graph,
                :func:`~blackholearena.game.tiles_per_player`.
        """

    # ------------------------------------------------------------------ #
    # Search                                                             #
    # ------------------------------------------------------------------ #

    def choose_move(self, state: State) -> Move:
        """Return the best move found, breaking ties randomly.

        Each root move is searched with the **full** window, so every root value
        is exact and the set of equally-best moves is right.
        """
        self._prepare(state)
        self._nodes = 0
        me = to_move(state)
        moves = legal_moves(state)
        depth = search_depth(len(moves), self.max_nodes)
        low, high = self.utility_bounds(tiles_per_player(state))

        best_value = -_INF
        best_moves: list[Move] = []
        for move in moves:
            value = self._search(apply_move(state, move), depth - 1, low, high, me)
            if value > best_value:
                best_value, best_moves = value, [move]
            elif value == best_value:
                best_moves.append(move)

        chosen = self._rng.choice(best_moves)
        remaining = len(moves) - 1
        if depth >= remaining:
            note = f"Searched to the end of the game ({remaining} plies): the value is exact."
        else:
            note = (
                f"Searched {depth} of the {remaining} plies left; deeper positions "
                "were estimated with the expected-score heuristic."
            )
        self.last_info = {
            "player": self.name,
            "depth": depth,
            "score": best_value,
            "nodes": self._nodes,
            "chosen": chosen,
            "note": note,
        }
        return chosen

    def _prepare(self, state: State) -> None:
        """Cache the adjacency, and forget the table if the graph changed."""
        graph = (len(state["owner"]), tuple(tuple(e) for e in state["edges"]))
        if graph != self._graph or len(self._table) > _MAX_TABLE_ENTRIES:
            self._graph = graph
            self._adj = adjacency(state)
            self._table.clear()

    def _value(self, pair: tuple[float, float], me: int) -> float:
        """Apply the utility to a ``(first, second)`` score pair from ``me``'s side."""
        return self.utility(pair[me], pair[1 - me])

    def _search(self, state: State, depth: int, alpha: float, beta: float, me: int) -> float:
        """Return the value of ``state`` for ``me``, searched ``depth`` more plies.

        Args:
            state: the position to value.
            depth: plies left before falling back to the heuristic.
            alpha: the value the maximizing side can already guarantee.
            beta: the value the minimizing side can already hold it to.
            me: the player whose utility is being searched.
        """
        self._nodes += 1
        if is_terminal(state):
            return self._value(scores(state), me)

        moves = legal_moves(state)
        # Only a search that reaches the end of the game from here may read or
        # write the table: its values are true game values, not heuristic ones.
        complete = depth >= len(moves) - 1
        if not complete and depth <= 0:
            return self._value(expected_scores(state, self._adj), me)

        key = (me, tuple(state["owner"]), tuple(state["tiles"]))
        hint: Move | None = None
        entry = self._table.get(key) if complete else None
        if entry is not None:
            stored, kind, hint = entry
            if kind == _EXACT:
                return stored
            if kind == _LOWER:
                alpha = max(alpha, stored)
            else:
                beta = min(beta, stored)
            if alpha >= beta:
                return stored

        if hint is not None:
            # The best move last time is the likeliest to cause a cutoff.
            moves.remove(hint)
            moves.insert(0, hint)

        maximizing = self.cooperative or to_move(state) == me
        alpha0, beta0 = alpha, beta
        value = -_INF if maximizing else _INF
        best = moves[0]
        for move in moves:
            child = self._search(apply_move(state, move), depth - 1, alpha, beta, me)
            if maximizing and child > value:
                value, best = child, move
                alpha = max(alpha, value)
            elif not maximizing and child < value:
                value, best = child, move
                beta = min(beta, value)
            if alpha >= beta:
                break  # alpha-beta cutoff

        if complete:
            kind = _UPPER if value <= alpha0 else _LOWER if value >= beta0 else _EXACT
            self._table[key] = (value, kind, best)
        return value
