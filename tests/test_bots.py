"""Tests for the reusable strategies in :mod:`blackholearena.bots`.

The search bots are checked against a brute-force reference — plain minimax with
no pruning, no table and no heuristic — so a bug in alpha-beta or in the
transposition table shows up as a wrong value, not just as a weaker player.
"""

from __future__ import annotations

import math

import pytest

from blackholearena import game, graphs
from blackholearena.bots import (
    CooperativeBot,
    FreeNeighbourBot,
    MaxOwnBot,
    MinRivalBot,
    RandomBot,
    SearchBot,
    expected_scores,
    search_depth,
)


class _Meta:
    """Supplies the identity every concrete player must declare."""

    @classmethod
    def get_name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["tests"]

    @classmethod
    def get_description(cls) -> str:
        return f"Test subject {cls.__name__}."

    @classmethod
    def get_icon(cls) -> str:
        return "🧪"


class Rand(_Meta, RandomBot):
    pass


class Neighbour(_Meta, FreeNeighbourBot):
    pass


class MaxOwn(_Meta, MaxOwnBot):
    pass


class MinRival(_Meta, MinRivalBot):
    pass


class Coop(_Meta, CooperativeBot):
    pass


SEARCHERS = [MaxOwn, MinRival, Coop]


def _play(state, moves):
    for move in moves:
        state = game.apply_move(state, move)
    return state


def _brute_force(bot: SearchBot, state, me: int) -> float:
    """Exact value of ``state`` for ``me`` under ``bot``'s utility and opponent model."""
    if game.is_terminal(state):
        s = game.scores(state)
        return bot.utility(s[me], s[1 - me])
    values = [_brute_force(bot, game.apply_move(state, m), me) for m in game.legal_moves(state)]
    maximizing = bot.cooperative or game.to_move(state) == me
    return max(values) if maximizing else min(values)


# --------------------------------------------------------------------------- #
# Abstract until named                                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "cls", [RandomBot, FreeNeighbourBot, MaxOwnBot, MinRivalBot, CooperativeBot]
)
def test_library_bots_cannot_be_entered_without_an_identity(cls):
    with pytest.raises(TypeError):
        cls()


# --------------------------------------------------------------------------- #
# Random                                                                      #
# --------------------------------------------------------------------------- #

def test_random_only_returns_legal_moves():
    bot = Rand.create(seed=3)
    state = graphs.grid(3, 3)
    while not game.is_terminal(state):
        move = bot.choose_move(state)
        assert game.is_legal(state, move)
        state = game.apply_move(state, move)


def test_random_is_reproducible_for_a_seed():
    state = graphs.wheel(11)
    assert Rand.create(seed=9).choose_move(state) == Rand.create(seed=9).choose_move(state)


# --------------------------------------------------------------------------- #
# Free neighbour (easy)                                                       #
# --------------------------------------------------------------------------- #

def test_neighbour_bot_plays_next_to_a_free_node():
    state = game.new_game(5, [[0, 1], [1, 2]])  # nodes 3 and 4 have no neighbour
    for seed in range(20):
        assert Neighbour.create(seed=seed).choose_move(state) in {0, 1, 2}


def test_neighbour_bot_ignores_neighbours_that_are_taken():
    # Path 0-1-2-3-4, with 1 and 3 taken: 0, 2 and 4 are free but isolated from
    # each other, so the rule cannot be met and any free node will do.
    state = _play(game.new_game(5, [[0, 1], [1, 2], [2, 3], [3, 4]]), [1, 3])
    picks = {Neighbour.create(seed=s).choose_move(state) for s in range(30)}
    assert picks == {0, 2, 4}


def test_neighbour_bot_scores_its_last_move_when_it_can():
    """With the last two free nodes adjacent, the node it plays touches the hole."""
    state = _play(graphs.classic(), [0, 1, 2])
    assert game.free_nodes(state) == [3, 4]  # adjacent
    move = Neighbour.create(seed=0).choose_move(state)
    after = game.apply_move(state, move)
    assert move in game.neighbors(after, game.black_hole(after))


def test_neighbour_bot_varies_with_the_seed():
    state = graphs.wheel(11)
    assert len({Neighbour.create(seed=s).choose_move(state) for s in range(20)}) > 1


# --------------------------------------------------------------------------- #
# Search depth                                                                #
# --------------------------------------------------------------------------- #

def test_search_depth_is_the_deepest_full_tree_that_fits():
    # 9 free nodes: 9 + 72 + 504 + 3024 = 3609 nodes to depth 4; depth 5 needs 18729.
    assert search_depth(9, 3609) == 4
    assert search_depth(9, 3608) == 3
    assert search_depth(9, 18729) == 5


def test_search_depth_never_goes_past_the_end_of_the_game():
    assert search_depth(5, 10**9) == 4
    assert search_depth(1, 10**9) == 0


def test_search_depth_is_at_least_one():
    assert search_depth(13, 1) == 1


def test_search_goes_deeper_relative_to_what_is_left():
    """Shallow in the opening, to the very end in the endgame."""
    bot = MaxOwn(max_nodes=2_000, seed=0)
    state = graphs.wheel(11)
    seen = []
    while not game.is_terminal(state):
        left = len(game.legal_moves(state)) - 1
        state = game.apply_move(state, bot.choose_move(state))
        seen.append((bot.last_info["depth"], left))
    assert seen[0][0] < seen[0][1], "the opening cannot be searched to the end"
    assert seen[-1][0] == seen[-1][1], "the last move is searched to the end"


# --------------------------------------------------------------------------- #
# Heuristic                                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("moves", [[], [0], [0, 1], [4, 0, 2]])
def test_expected_scores_stay_within_the_possible_range(moves):
    state = _play(graphs.wheel(7), moves)
    best = game.tiles_per_player(state)
    for value in expected_scores(state, game.adjacency(state)):
        assert 0.0 <= value <= best


def test_expected_scores_count_tiles_next_to_free_nodes():
    # One move left on the classic graph after A, B, D: free nodes C and E.
    # C touches A (J1, 1 tile) and D (J1, 2); E touches B (J2, 1) and D (J1, 2).
    state = _play(graphs.classic(), [0, 1, 3])
    first, second = expected_scores(state, game.adjacency(state))
    # Placed: J1 = (3 + 2) / 2, J2 = 1 / 2. Still to come: J2's 2 tiles times the
    # chance that C and E are adjacent, which is 0.
    assert (first, second) == (2.5, 0.5)


# --------------------------------------------------------------------------- #
# Search correctness                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cls", SEARCHERS)
@pytest.mark.parametrize(
    "state",
    [graphs.classic(), graphs.wheel(7), _play(graphs.grid(3, 3), [4, 0])],
    ids=["classic", "wheel7", "grid-after-2"],
)
def test_full_depth_search_matches_brute_force(cls, state):
    """With the budget to see the end, alpha-beta + table must be exact."""
    bot = cls(max_nodes=10**7, seed=0)
    me = game.to_move(state)
    move = bot.choose_move(state)
    assert bot.last_info["depth"] == len(game.legal_moves(state)) - 1
    expected = max(
        _brute_force(bot, game.apply_move(state, m), me) for m in game.legal_moves(state)
    )
    assert bot.last_info["score"] == expected
    assert _brute_force(bot, game.apply_move(state, move), me) == expected


@pytest.mark.parametrize("cls", SEARCHERS)
def test_the_table_carried_across_turns_never_changes_a_value(cls):
    """A bot that remembers earlier searches must value positions like a fresh one."""
    reused = cls(max_nodes=3_000, seed=0)
    state = graphs.grid(3, 3)
    while not game.is_terminal(state):
        move = reused.choose_move(state)
        fresh = cls(max_nodes=3_000, seed=0)
        fresh.choose_move(state)
        assert reused.last_info["score"] == pytest.approx(fresh.last_info["score"])
        assert reused.last_info["depth"] == fresh.last_info["depth"]
        state = game.apply_move(state, move)


def test_a_search_that_cannot_see_the_end_remembers_nothing():
    """A value resting on heuristic leaves depends on depth, so it is never stored.

    With one uniform depth, a search reaches the end of the game everywhere or
    nowhere — so an opening search on a wide graph stores nothing at all.
    """
    bot = MaxOwn(max_nodes=2_000, seed=0)
    bot.choose_move(graphs.wheel(11))
    assert bot.last_info["depth"] < 10
    assert not bot._table


def test_a_search_that_sees_the_end_is_remembered_and_reused():
    reused = MaxOwn(max_nodes=30_000, seed=0)
    state = graphs.wheel(7)  # 6 plies left: the whole game fits the budget
    state = game.apply_move(state, reused.choose_move(state))
    assert reused._table, "a search solved to the end is stored"
    state = game.apply_move(state, game.legal_moves(state)[0])
    reused.choose_move(state)
    fresh = MaxOwn(max_nodes=30_000, seed=0)
    fresh.choose_move(state)
    assert reused.last_info["score"] == fresh.last_info["score"]
    assert reused.last_info["nodes"] < fresh.last_info["nodes"]


def test_pruning_visits_fewer_nodes_than_the_full_tree():
    bot = MaxOwn(max_nodes=10**7, seed=0)
    bot.choose_move(graphs.wheel(7))
    full_tree = sum(math.perm(7, k) for k in range(1, 7))
    assert bot.last_info["nodes"] < full_tree


@pytest.mark.parametrize("cls", SEARCHERS)
def test_search_bots_only_return_legal_moves(cls):
    bot = cls.create(seed=0)
    for start in (graphs.classic(), graphs.grid(3, 3), graphs.random_graph(13, 0.4, 2)):
        state = start
        while not game.is_terminal(state):
            move = bot.choose_move(state)
            assert game.is_legal(state, move)
            state = game.apply_move(state, move)


def test_the_three_utilities_disagree_where_they_should():
    """Last move on the classic graph after A, B, D: free C(2) and E(4); J2 moves.

    Playing C makes E the hole: E touches B (J2, 1) and D (J1, 2) -> (2, 1).
    Playing E makes C the hole: C touches A (J1, 1) and D (J1, 2) -> (3, 0).
    MaxOwn wants C (1 point instead of 0); MinRival wants C too (J1 gets 2, not
    3); for Cooperative the total is 3 either way.
    """
    state = _play(graphs.classic(), [0, 1, 3])
    assert MaxOwn.create(seed=0).choose_move(state) == 2
    assert MinRival.create(seed=0).choose_move(state) == 2
    picks = {Coop.create(seed=s).choose_move(state) for s in range(20)}
    assert picks == {2, 4}, "equally good to the cooperative bot, so both get picked"


def test_max_nodes_must_be_positive():
    with pytest.raises(ValueError):
        MaxOwn(max_nodes=0)


def test_last_info_is_populated_for_the_web_log():
    bot = Coop.create(seed=0)
    bot.choose_move(graphs.wheel(7))
    assert {"player", "depth", "score", "nodes", "chosen", "note"} <= set(bot.last_info)
