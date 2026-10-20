"""Tests for the pure game engine."""

from __future__ import annotations

import copy

import pytest

from blackholearena import game, graphs


def _play(state, moves):
    for move in moves:
        state = game.apply_move(state, move)
    return state


def test_new_game_starts_with_every_node_free():
    state = game.new_game(5, [[0, 1], [1, 2]])
    assert state == {"edges": [[0, 1], [1, 2]], "owner": [None] * 5, "tiles": [0] * 5}
    assert game.free_nodes(state) == [0, 1, 2, 3, 4]
    assert not game.is_terminal(state)


def test_edges_are_normalised_smaller_node_first():
    assert game.new_game(3, [[2, 0]])["edges"] == [[0, 2]]


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        (4, []),               # even: no single node would be left free
        (1, []),               # too small
        (5, [[0, 0]]),         # self-loop
        (5, [[0, 5]]),         # out of range
        (5, [[0, 1], [1, 0]]),  # repeated
        (5, [[0, 1, 2]]),      # not a pair
        (5, [[0, "1"]]),       # not an int
        (5, [[True, 1]]),      # bool is not a node
    ],
)
def test_unusable_graphs_are_rejected(nodes, edges):
    with pytest.raises(ValueError):
        game.new_game(nodes, edges)


def test_turns_and_tiles_follow_the_rules():
    # 2N + 1 = 9 nodes -> N = 4 turns each, M = 4 * 5 / 2 = 10 tiles each.
    state = graphs.grid(3, 3)
    assert game.turns_per_player(state) == 4
    assert game.tiles_per_player(state) == 10


def test_players_alternate_and_tiles_grow_each_turn():
    state = graphs.grid(3, 3)
    seen = []
    while not game.is_terminal(state):
        seen.append((game.to_move(state), game.tiles_to_place(state)))
        state = game.apply_move(state, game.legal_moves(state)[0])
    assert seen == [(0, 1), (1, 1), (0, 2), (1, 2), (0, 3), (1, 3), (0, 4), (1, 4)]
    # Each player placed exactly M tiles.
    for player in (0, 1):
        placed = sum(t for o, t in zip(state["owner"], state["tiles"], strict=True) if o == player)
        assert placed == game.tiles_per_player(state)


def test_legal_moves_are_the_free_nodes():
    state = _play(graphs.classic(), [0, 3])
    assert game.legal_moves(state) == [1, 2, 4]


def test_no_move_is_legal_once_the_game_is_over():
    state = _play(graphs.classic(), [0, 1, 3, 2])
    assert game.is_terminal(state)
    assert game.legal_moves(state) == []
    assert not game.is_legal(state, 4), "nobody may play on the black hole"


def test_is_legal_rejects_malformed_and_occupied_moves():
    state = _play(graphs.classic(), [0])
    assert game.is_legal(state, 1)
    assert not game.is_legal(state, 0)    # occupied
    assert not game.is_legal(state, 5)    # out of range
    assert not game.is_legal(state, -1)   # out of range
    assert not game.is_legal(state, "1")  # not an int
    assert not game.is_legal(state, 1.0)  # not an int
    assert not game.is_legal(state, True)  # bool is not a node
    assert not game.is_legal(state, (1,))


def test_apply_move_returns_new_state_and_does_not_mutate():
    state = graphs.classic()
    before = copy.deepcopy(state)
    new = game.apply_move(state, 2)
    assert state == before, "the original must be untouched"
    assert new is not state
    assert new["owner"][2] == 0 and new["tiles"][2] == 1


def test_apply_illegal_move_raises():
    with pytest.raises(ValueError):
        game.apply_move(_play(graphs.classic(), [0]), 0)


def test_the_rules_example_scores_two_to_one():
    """The worked example from the rules page, move for move.

    Nodes 0..4 are A..E. J1 plays A (1 tile), J2 plays B (1), J1 plays D (2),
    J2 plays C (2). E is left free: the black hole. Its neighbours are B and D.
    """
    state = _play(graphs.classic(), [0, 1, 3, 2])
    assert game.black_hole(state) == 4
    assert game.neighbors(state, 4) == [1, 3]
    assert game.scores(state) == (2, 1)


def test_scores_need_a_finished_game():
    with pytest.raises(ValueError):
        game.scores(graphs.classic())
    with pytest.raises(ValueError):
        game.black_hole(graphs.classic())


def test_scores_if_hole_counts_only_tiles_already_placed():
    state = _play(graphs.classic(), [0, 1])  # J1 on A, J2 on B
    # If C became the hole: C's neighbours are A and D -> J1 scores A's 1 tile.
    assert game.scores_if_hole(state, 2) == (1, 0)
    # If D became the hole: D touches A, B, C, E -> both score their 1 tile.
    assert game.scores_if_hole(state, 3) == (1, 1)
    with pytest.raises(ValueError):
        game.scores_if_hole(state, 9)


def test_adjacency_lists_every_neighbour_both_ways():
    adj = game.adjacency(graphs.classic())
    assert adj == [[1, 2, 3], [0, 3, 4], [0, 3], [0, 1, 2, 4], [1, 3]]


def test_full_game_always_ends_after_2n_moves():
    for state in (graphs.classic(), graphs.wheel(7), graphs.grid(3, 3), graphs.wheel(13)):
        n = game.turns_per_player(state)
        moves = 0
        while not game.is_terminal(state):
            state = game.apply_move(state, game.legal_moves(state)[-1])
            moves += 1
        assert moves == 2 * n
        assert len(game.free_nodes(state)) == 1
