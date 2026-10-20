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


def random_graph(nodes: int, density: float = 0.4, seed: int | None = None) -> State:
    """A random connected graph: a random spanning tree plus extra random edges.

    The spanning tree guarantees every node has a neighbour, so no node is a
    dead loss for whoever plays on it.

    Args:
        nodes: number of nodes, odd and at least 3.
        density: probability of each *extra* edge, in ``[0, 1]``.
        seed: seed for a private RNG, so the same arguments give the same graph.

    Raises:
        ValueError: if ``nodes`` is unusable or ``density`` is outside ``[0, 1]``.
    """
    if not 0.0 <= density <= 1.0:
        raise ValueError(f"density must be in [0, 1], got {density}")
    rng = random.Random(seed)
    order = list(range(nodes))
    rng.shuffle(order)
    edges: set[tuple[int, int]] = set()
    for i in range(1, len(order)):
        a, b = order[i], order[rng.randrange(i)]
        edges.add((min(a, b), max(a, b)))
    for a in range(nodes):
        for b in range(a + 1, nodes):
            if (a, b) not in edges and rng.random() < density:
                edges.add((a, b))
    return new_game(nodes, [list(e) for e in sorted(edges)])


#: The named graphs offered by the web page, in display order.
PRESETS: dict[str, State] = {
    "classic": classic(),
    "wheel-7": wheel(7),
    "grid-3x3": grid(3, 3),
    "wheel-11": wheel(11),
}
