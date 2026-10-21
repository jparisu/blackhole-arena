"""Ready-made graphs to play BlackHole on.

Every function here returns a **starting state** (see
:func:`blackholearena.game.new_game`): the graph with every node free. They are
what the tournament plays by default (see
:data:`~blackholearena.tournament.DEFAULT_STARTING_STATES`) and what the web page
offers as presets, so both always agree on what "the grid" is.
"""

from __future__ import annotations

import random

from .game import State, new_game


def classic() -> State:
    """The 5-node example graph from the rules (``N = 2``, ``M = 3``).

    Nodes ``0..4`` are ``A..E`` in the rules page.
    """
    return new_game(5, [[0, 1], [2, 3], [3, 4], [0, 2], [0, 3], [1, 3], [1, 4]])


def wheel(nodes: int = 7) -> State:
    """A hub (node ``0``) joined to every node of a ring ``1..nodes-1``.

    The hub touches everything, so whoever claims it — and when — shapes the
    whole game.

    Raises:
        ValueError: if ``nodes`` is not odd and at least 5.
    """
    if nodes < 5:
        raise ValueError(f"a wheel needs at least 5 nodes, got {nodes}")
    ring = list(range(1, nodes))
    edges = [[0, v] for v in ring]
    edges += [[ring[i], ring[(i + 1) % len(ring)]] for i in range(len(ring))]
    return new_game(nodes, edges)


def grid(rows: int = 3, cols: int = 3) -> State:
    """A ``rows x cols`` grid, each node joined to its horizontal and vertical neighbours.

    Node ``r * cols + c`` sits at row ``r``, column ``c``. Corners have two
    neighbours, edges three and inner nodes four.

    Raises:
        ValueError: if ``rows * cols`` is not odd and at least 3.
    """
    edges: list[list[int]] = []
    for r in range(rows):
        for c in range(cols):
            v = r * cols + c
            if c + 1 < cols:
                edges.append([v, v + 1])
            if r + 1 < rows:
                edges.append([v, v + cols])
    return new_game(rows * cols, edges)


def _chords_cross(e: tuple[int, int], f: tuple[int, int]) -> bool:
    """Return whether two edges cross when the nodes sit on a circle in index order.

    Edges ``(a, b)`` and ``(c, d)``, with ``a < b`` and ``c < d``, cross exactly
    when one endpoint of ``(c, d)`` lies strictly inside the arc ``a..b`` and the
    other strictly outside it. Edges sharing an endpoint never cross.
    """
    (a, b), (c, d) = e, f
    return a < c < b < d or c < a < d < b


def random_graph(nodes: int, density: float = 0.4, seed: int | None = None) -> State:
    """A random connected graph that can always be drawn without crossing edges.

    Every edge is a chord of the polygon whose corners are the nodes in index
    order, and no two chords cross — an *outerplanar* graph. Placing the nodes on
    a circle in index order therefore draws it with no crossings, which is what
    the web board falls back to.

    It is built as a random non-crossing spanning tree plus extra random
    non-crossing edges. The spanning tree guarantees every node has a neighbour,
    so no node is a dead loss for whoever plays on it. It always exists: a side of
    the polygon, ``(i, i + 1)``, crosses no chord, so two separate components can
    always be joined.

    Args:
        nodes: number of nodes, odd and at least 3.
        density: probability of each *extra* edge that would cross no edge
            already chosen, in ``[0, 1]``.
        seed: seed for a private RNG, so the same arguments give the same graph.

    Raises:
        ValueError: if ``nodes`` is unusable or ``density`` is outside ``[0, 1]``.
    """
    if not 0.0 <= density <= 1.0:
        raise ValueError(f"density must be in [0, 1], got {density}")
    rng = random.Random(seed)
    pairs = [(a, b) for a in range(nodes) for b in range(a + 1, nodes)]
    rng.shuffle(pairs)
    edges: list[tuple[int, int]] = []

    def crosses_any(pair: tuple[int, int]) -> bool:
        return any(_chords_cross(pair, e) for e in edges)

    # Random non-crossing spanning tree (Kruskal over shuffled pairs).
    component = list(range(nodes))

    def root(v: int) -> int:
        while component[v] != v:
            component[v] = component[component[v]]
            v = component[v]
        return v

    for a, b in pairs:
        ra, rb = root(a), root(b)
        if ra != rb and not crosses_any((a, b)):
            component[ra] = rb
            edges.append((a, b))

    # Extra edges, each kept with probability `density` if it crosses nothing.
    for pair in pairs:
        if pair not in edges and rng.random() < density and not crosses_any(pair):
            edges.append(pair)
    return new_game(nodes, [list(e) for e in sorted(edges)])


#: The named graphs offered by the web page, in display order.
PRESETS: dict[str, State] = {
    "classic": classic(),
    "wheel-7": wheel(7),
    "grid-3x3": grid(3, 3),
    "wheel-11": wheel(11),
}
