"""Tests for the browser bridge — including the Tournament page's entrants.

``web/webglue.py`` is shipped code: it is what the page calls into for every rule
query and every AI move. Its forfeit handling matters especially, because the
browser enforces no timeout and a page must never be taken down by one bad player.
"""

from __future__ import annotations

import json

import pytest
import webglue

from blackholearena import game, graphs
from blackholearena.player import Player

#: The reference players that ship with the repository. ``players.yaml`` is an
#: open admission list, so the page may legitimately offer more than these — a
#: test may check that they are *present*, never that they are all there is.
REFERENCE_PLAYERS = {"random", "easy", "aggressive-max", "aggressive-min", "cooperative"}

CLASSIC = json.dumps(graphs.classic())


@pytest.fixture(autouse=True)
def loaded():
    """Load the real manifest once per test and start from a clean entrant table."""
    webglue.init(".")
    webglue.reset_entrants()
    yield
    webglue.reset_entrants()


class Boom(Player):
    """Raises instead of moving."""

    @classmethod
    def get_name(cls):
        return "boom"

    @classmethod
    def get_authors(cls):
        return ["tests"]

    @classmethod
    def get_description(cls):
        return "Always raises."

    @classmethod
    def get_icon(cls):
        return "💥"

    def choose_move(self, state):
        raise RuntimeError("kaboom")


class Cheat(Boom):
    """Returns a move that is never legal."""

    @classmethod
    def get_name(cls):
        return "cheat"

    def choose_move(self, state):
        return 999


# --------------------------------------------------------------------------- #
# Rules, graphs and identity                                                  #
# --------------------------------------------------------------------------- #

def test_players_json_carries_identity():
    entries = json.loads(webglue.players_json())
    assert REFERENCE_PLAYERS <= {e["name"] for e in entries}
    for e in entries:
        assert e["icon"].strip() and e["authors"] and e["description"].strip()


def test_presets_come_from_the_engine():
    presets = json.loads(webglue.presets_json())
    assert [p["name"] for p in presets] == list(graphs.PRESETS)
    assert all(p["label"] and p["state"]["owner"] for p in presets)


def test_new_game_validates_through_the_engine():
    state = json.loads(webglue.new_game(5, "[[0, 1], [1, 2]]"))
    assert state == game.new_game(5, [[0, 1], [1, 2]])
    with pytest.raises(ValueError, match="odd"):
        webglue.new_game(4, "[]")


def test_random_graph_is_reproducible():
    assert webglue.random_graph(9, 0.3, 4) == webglue.random_graph(9, 0.3, 4)


def test_rules_come_from_the_engine():
    assert json.loads(webglue.legal_moves(CLASSIC)) == [0, 1, 2, 3, 4]
    after = json.loads(webglue.apply_move(CLASSIC, 3))
    assert after["owner"][3] == 0 and after["tiles"][3] == 1
    assert webglue.is_terminal(CLASSIC) is False


def test_analysis_mid_game_lists_what_each_hole_would_score():
    state = json.dumps(game.apply_move(game.apply_move(graphs.classic(), 0), 1))
    an = json.loads(webglue.analysis(state))
    assert an["to_move"] == 0 and an["tiles_to_place"] == 2
    assert an["tiles_per_player"] == 3 and an["turns_per_player"] == 2
    assert an["terminal"] is False and an["scores"] is None
    assert an["hole_payoffs"] == {"2": [1, 0], "3": [1, 1], "4": [0, 1]}


def test_analysis_of_a_finished_game_reports_the_black_hole():
    state = graphs.classic()
    for move in (0, 1, 3, 2):
        state = game.apply_move(state, move)
    an = json.loads(webglue.analysis(json.dumps(state)))
    assert an["terminal"] is True
    assert an["black_hole"] == 4
    assert an["scores"] == [2, 1]


def test_ask_move_refuses_a_finished_game():
    state = graphs.classic()
    for move in (0, 1, 3, 2):
        state = game.apply_move(state, move)
    with pytest.raises(ValueError, match="over"):
        webglue.ask_move("random", json.dumps(state))


def test_ask_move_returns_a_legal_node():
    res = json.loads(webglue.ask_move("random", CLASSIC))
    assert res["move"] in range(5)
    assert res["elapsed_ms"] >= 0


# --------------------------------------------------------------------------- #
# Tournament entrants                                                         #
# --------------------------------------------------------------------------- #

def test_the_same_kind_can_enter_twice_independently():
    webglue.create_entrant("a", "random", 1)
    webglue.create_entrant("b", "random", 2)
    assert webglue._ENTRANTS["a"] is not webglue._ENTRANTS["b"]


def test_an_unknown_entrant_says_what_to_do():
    with pytest.raises(KeyError, match="create_entrant"):
        webglue.entrant_move("nobody", CLASSIC)


def test_reset_entrants_clears_the_table():
    webglue.create_entrant("a", "random", 0)
    webglue.reset_entrants()
    assert not webglue._ENTRANTS


def test_play_auto_returns_a_complete_scored_game():
    webglue.create_entrant("a", "random", 0)
    webglue.create_entrant("b", "random", 1)
    res = json.loads(webglue.play_auto("a", "b", CLASSIC))
    assert res["result"] == "normal"
    assert res["forfeit_seat"] is None
    # Replaying the moves must finish the game with exactly the reported scores.
    state = graphs.classic()
    for move in res["moves"]:
        state = game.apply_move(state, move)
    assert game.is_terminal(state)
    assert res["scores"] == list(game.scores(state))


def test_play_auto_is_reproducible_for_a_seed():
    def run():
        webglue.reset_entrants()
        webglue.create_entrant("a", "random", 7)
        webglue.create_entrant("b", "random", 8)
        return json.loads(webglue.play_auto("a", "b", json.dumps(graphs.wheel(11))))["moves"]

    assert run() == run()


@pytest.mark.parametrize(
    ("cls", "expected"),
    [(Boom, "forfeit_error"), (Cheat, "forfeit_illegal")],
)
def test_a_misbehaving_entrant_forfeits_instead_of_breaking_the_page(cls, expected):
    webglue._ENTRANTS["bad"] = cls.create(seed=0)
    webglue.create_entrant("good", "random", 0)
    res = json.loads(webglue.play_auto("bad", "good", CLASSIC))
    assert res["result"] == expected
    assert res["forfeit_seat"] == 0
    assert res["scores"] == [0, game.tiles_per_player(graphs.classic())], "the opponent scores the maximum"
    assert res["detail"]
