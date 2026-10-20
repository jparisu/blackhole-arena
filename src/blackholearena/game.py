"""Parametrized BlackHole game engine.

**BlackHole** is a two-player, turn-based game played on an undirected graph of
``2N + 1`` nodes. Each player has ``N`` turns. On its ``n``-th turn a player
places ``n`` tiles on one free node, so over the game each player places
``M = N(N + 1) / 2`` tiles. After the ``2N`` turns exactly one node is still
free: that node is the **black hole**. Each player scores the tiles it placed on
the nodes **adjacent** to the black hole. **Each player tries to maximize its
own score** — this is *not* a zero-sum game, and both players may score well (or
badly) in the same game.

Design rules honored by this module:

* The game **state** is a plain, JSON-serializable mapping (see :class:`State`):
  the graph's edges, the owner of every node and the tiles on it. No custom
  objects ever cross the API boundary.
* A **move** is a plain ``int``: the index of the free node to place tiles on.
  How many tiles are placed is not part of the move — it is fixed by the turn.
* Every function is **pure**: it never mutates its arguments. In particular
  :func:`apply_move` returns a brand-new state. This matters because minimax
  explores many hypothetical futures, and shared mutable state is a classic
  source of subtle bugs.

Whose turn it is, and how many tiles that turn places, are both *derived* from
the board (see :func:`to_move` and :func:`tiles_to_place`), so a state can never
disagree with itself. Timing and forfeits live in the tournament (see
:mod:`blackholearena.tournament`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict


class State(TypedDict):
    """A BlackHole position.

    Nodes are numbered ``0 .. len(owner) - 1``.

    Attributes:
        edges: the undirected edges of the graph, as ``[a, b]`` pairs. Treat as
            read-only: :func:`apply_move` shares it between states.
        owner: ``owner[v]`` is ``0`` (the first player), ``1`` (the second
            player), or ``None`` if node ``v`` is still free.
        tiles: ``tiles[v]`` is the number of tiles on node ``v`` (``0`` if free).
    """

    edges: list[list[int]]
    owner: list[int | None]
    tiles: list[int]


Move = int

#: The player that moves first.
FIRST = 0
#: The player that moves second.
SECOND = 1
#: Fewest nodes a playable graph may have: ``N = 1``, one turn each.
MIN_NODES = 3


# --------------------------------------------------------------------------- #
# Building a game                                                              #
# --------------------------------------------------------------------------- #

def validate_graph(nodes: int, edges: Sequence[Sequence[int]]) -> list[list[int]]:
    """Return ``edges`` as clean ``[a, b]`` pairs, or explain why they are unusable.

    Args:
        nodes: number of nodes. Must be odd and at least :data:`MIN_NODES`, so
            that exactly one node is left free after both players' turns.
        edges: undirected edges as pairs of node indices.

    Returns:
        A fresh list of ``[a, b]`` pairs, each with ``a < b``.

    Raises:
        ValueError: if ``nodes`` is not an odd integer ``>= 3``, or an edge is not
            a pair of distinct in-range node indices, or an edge is repeated.
    """
    if isinstance(nodes, bool) or not isinstance(nodes, int):
        raise ValueError(f"the number of nodes must be an integer, got {nodes!r}")
    if nodes < MIN_NODES or nodes % 2 == 0:
        raise ValueError(
            f"the number of nodes must be odd and at least {MIN_NODES} (2N + 1), got {nodes}"
        )
    cleaned: list[list[int]] = []
    seen: set[tuple[int, int]] = set()
    for edge in edges:
        pair = list(edge)
        if len(pair) != 2:
            raise ValueError(f"an edge must be a pair of nodes, got {edge!r}")
        a, b = pair
        for v in (a, b):
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"edge {edge!r} has a non-integer node: {v!r}")
            if not 0 <= v < nodes:
                raise ValueError(f"edge {edge!r} names node {v}, outside 0..{nodes - 1}")
        if a == b:
            raise ValueError(f"edge {edge!r} joins a node to itself")
        key = (min(a, b), max(a, b))
        if key in seen:
            raise ValueError(f"edge {edge!r} is repeated")
        seen.add(key)
        cleaned.append([key[0], key[1]])
    return cleaned


def new_game(nodes: int, edges: Sequence[Sequence[int]]) -> State:
    """Return the starting state for a graph: every node free.

    Args:
        nodes: number of nodes, ``2N + 1``.
        edges: undirected edges as pairs of node indices.

    Raises:
        ValueError: if the graph is unusable (see :func:`validate_graph`).
    """
    return {
        "edges": validate_graph(nodes, edges),
        "owner": [None] * nodes,
        "tiles": [0] * nodes,
    }


# --------------------------------------------------------------------------- #
# Reading a state                                                              #
# --------------------------------------------------------------------------- #

def num_nodes(state: State) -> int:
    """Return the number of nodes in the graph, ``2N + 1``."""
    return len(state["owner"])


def turns_per_player(state: State) -> int:
    """Return ``N``: how many turns each player gets."""
    return (num_nodes(state) - 1) // 2


def tiles_per_player(state: State) -> int:
    """Return ``M = N(N + 1) / 2``: how many tiles each player places in a game.

    It is also the most a player can ever score.
    """
    n = turns_per_player(state)
    return n * (n + 1) // 2


def moves_played(state: State) -> int:
    """Return how many moves have been made so far (occupied nodes)."""
    return sum(1 for o in state["owner"] if o is not None)


def to_move(state: State) -> int:
    """Return the player to move: :data:`FIRST` (``0``) or :data:`SECOND` (``1``).

    Players alternate, starting with :data:`FIRST`. On a terminal state this is
    the player who *would* move next, which is meaningless but harmless.
    """
    return moves_played(state) % 2


def tiles_to_place(state: State) -> int:
    """Return how many tiles the current move places: ``n`` on a player's ``n``-th turn."""
    return moves_played(state) // 2 + 1


def free_nodes(state: State) -> list[int]:
    """Return the indices of the free nodes, in ascending order."""
    return [v for v, o in enumerate(state["owner"]) if o is None]


def adjacency(state: State) -> list[list[int]]:
    """Return ``adj`` where ``adj[v]`` lists the neighbours of ``v``, ascending.

    Search-heavy players should compute this once per move rather than calling
    :func:`neighbors` in a loop: it is a single pass over the edges.
    """
    adj: list[list[int]] = [[] for _ in range(num_nodes(state))]
    for a, b in state["edges"]:
        adj[a].append(b)
        adj[b].append(a)
    for row in adj:
        row.sort()
    return adj


def neighbors(state: State, node: int) -> list[int]:
    """Return the neighbours of ``node``, in ascending order."""
    return adjacency(state)[node]


# --------------------------------------------------------------------------- #
# Moves                                                                        #
# --------------------------------------------------------------------------- #

def is_terminal(state: State) -> bool:
    """Return ``True`` if the game is over: at most one free node remains."""
    return num_nodes(state) - moves_played(state) <= 1


def legal_moves(state: State) -> list[Move]:
    """Return every legal move from ``state``: the free nodes.

    Returns:
        The free nodes in ascending order. Empty if the game is already over —
        the last free node is the black hole, and nobody may play on it.
    """
    if is_terminal(state):
        return []
    return free_nodes(state)


def is_legal(state: State, move: object) -> bool:
    """Return ``True`` if ``move`` is legal from ``state``.

    This is the single source of truth for "what is a legal move", used by the
    tournament to forfeit players that return illegal moves.

    ``move`` is deliberately typed ``object`` rather than :data:`Move`: its whole
    job is to judge what an *untrusted* player handed back, which may be any
    object at all. ``bool`` is rejected even though it is an ``int`` subclass:
    ``True`` is not a node.
    """
    if isinstance(move, bool) or not isinstance(move, int):
        return False
    if is_terminal(state):
        return False
    return 0 <= move < num_nodes(state) and state["owner"][move] is None


def apply_move(state: State, move: Move) -> State:
    """Return a **new** state with ``move`` applied.

    The player to move places :func:`tiles_to_place` tiles on node ``move``.
    Does **not** mutate ``state``.

    Raises:
        ValueError: if ``move`` is not legal from ``state``.
    """
    if not is_legal(state, move):
        raise ValueError(f"Illegal move {move!r} for state {state!r}")
    owner = list(state["owner"])
    tiles = list(state["tiles"])
    owner[move] = to_move(state)
    tiles[move] = tiles_to_place(state)
    # The graph never changes, so it is shared rather than copied.
    return {"edges": state["edges"], "owner": owner, "tiles": tiles}


# --------------------------------------------------------------------------- #
# Scoring                                                                      #
# --------------------------------------------------------------------------- #

def black_hole(state: State) -> int:
    """Return the black hole: the one node left free at the end of the game.

    Raises:
        ValueError: if the game is not over yet.
    """
    if not is_terminal(state):
        raise ValueError("the game is not over, so there is no black hole yet")
    return free_nodes(state)[0]


def scores_if_hole(state: State, hole: int) -> tuple[int, int]:
    """Return ``(first, second)`` scores as if ``hole`` were the black hole now.

    Only tiles already on the board count. On a terminal state with ``hole`` set
    to :func:`black_hole` this is the final score; mid-game it answers "what if
    the game ended here, with this node as the hole?" — which is what the web
    X-ray mode shows and what a heuristic can build on.

    Raises:
        ValueError: if ``hole`` is not a node of the graph.
    """
    if not 0 <= hole < num_nodes(state):
        raise ValueError(f"node {hole} is not in the graph")
    result = [0, 0]
    for a, b in state["edges"]:
        if a == hole:
            other = b
        elif b == hole:
            other = a
        else:
            continue
        who = state["owner"][other]
        if who is not None:
            result[who] += state["tiles"][other]
    return (result[0], result[1])


def scores(state: State) -> tuple[int, int]:
    """Return the final ``(first, second)`` scores of a finished game.

    Each player scores the tiles it placed on the nodes adjacent to the black
    hole.

    Raises:
        ValueError: if the game is not over yet.
    """
    return scores_if_hole(state, black_hole(state))
