"""Tests for the ready-made graphs in :mod:`blackholearena.graphs`."""

from __future__ import annotations

import pytest

from blackholearena import game, graphs


def _connected(state) -> bool:
    adj = game.adjacency(state)
    seen = {0}
    frontier = [0]
    while frontier:
        for w in adj[frontier.pop()]:
            if w not in seen:
                seen.add(w)
                frontier.append(w)
    return len(seen) == game.num_nodes(state)


def test_classic_is_the_rules_example():
    state = graphs.classic()
    assert game.num_nodes(state) == 5
    assert len(state["edges"]) == 7


def test_wheel_has_a_hub_touching_every_node():
    state = graphs.wheel(7)
    assert game.neighbors(state, 0) == [1, 2, 3, 4, 5, 6]
    # Every rim node touches the hub and its two rim neighbours.
    assert all(len(game.neighbors(state, v)) == 3 for v in range(1, 7))


def test_grid_degrees():
    adj = game.adjacency(graphs.grid(3, 3))
    assert sorted(len(a) for a in adj) == [2, 2, 2, 2, 3, 3, 3, 3, 4]


@pytest.mark.parametrize("build", [lambda: graphs.wheel(4), lambda: graphs.grid(2, 2)])
def test_graphs_that_cannot_be_played_are_rejected(build):
    with pytest.raises(ValueError):
        build()


def test_random_graph_is_connected_and_reproducible():
    a = graphs.random_graph(11, 0.2, seed=5)
    b = graphs.random_graph(11, 0.2, seed=5)
    assert a == b
    assert _connected(a)
    assert graphs.random_graph(11, 0.2, seed=6) != a


def test_random_graph_rejects_a_bad_density():
    with pytest.raises(ValueError):
        graphs.random_graph(5, 1.5, seed=0)


@pytest.mark.parametrize("name", list(graphs.PRESETS))
def test_every_preset_is_a_fresh_playable_game(name):
    state = graphs.PRESETS[name]
    assert game.free_nodes(state) == list(range(game.num_nodes(state)))
    assert _connected(state)
