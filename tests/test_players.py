"""Tests that the admitted players obey the contract."""

from __future__ import annotations

import copy

import pytest

from blackholearena import game, graphs
from blackholearena.manifest import BUILTIN, BUILTIN_MANIFEST, load_players
from blackholearena.registry import Registry
from blackholearena.tournament import UNLIMITED, build_roster, run_tournament

#: The reference players that ship with the repository.
#:
#: Every assertion below is scoped to these **on purpose**. The manifest is an
#: open admission list: any merged pull request adds a player to it. A test that
#: pinned the *exact* roster would therefore turn CI red on every single
#: submission — so the roster is only ever checked for what must be present,
#: never for what must be absent. A submitted bot proves itself in the
#: tournament, which is built to survive a bad one; it is not this suite's job.
LADDER = ["random", "easy", "aggressive-max", "aggressive-min", "cooperative"]

#: Graphs every player is swept over, played out to the end.
BOARDS = [graphs.classic(), graphs.wheel(7), graphs.grid(3, 3), graphs.random_graph(11, 0.3, 1)]


@pytest.fixture(scope="module")
def registry():
    # Only the built-in manifest. A submission is an outsider's code: loading it
    # strictly here would let one broken bot fail the whole suite, and so every
    # unrelated pull request. Submissions are checked by tests/test_custom_players.py.
    return load_players({BUILTIN: BUILTIN_MANIFEST}, registry=Registry(), strict=True)


def test_the_manifest_loads_without_error(registry):
    """Whatever ``players/builtin/players.yaml`` admits must load; the fixture is ``strict``."""
    assert registry.names(), "the manifest admitted no players at all"


def test_the_reference_players_are_admitted(registry):
    """The built-in players must always be there. Others may join them."""
    assert set(LADDER) <= set(registry.names())


@pytest.mark.parametrize("name", LADDER)
def test_every_player_declares_its_identity(registry, name):
    cls = type(registry.get(name))
    assert cls.get_name() == name
    authors = cls.get_authors()
    assert isinstance(authors, list) and authors and all(a.strip() for a in authors)
    assert cls.get_description().strip()
    icon = cls.get_icon()
    assert isinstance(icon, str) and icon.strip(), f"{name} declares no icon"


@pytest.mark.parametrize("name", LADDER)
def test_create_accepts_a_seed_and_returns_a_player(registry, name):
    cls = type(registry.get(name))
    player = cls.create(seed=7)
    assert isinstance(player, cls)
    assert player.name == name


@pytest.mark.parametrize("name", LADDER)
def test_players_return_legal_moves_and_do_not_mutate(registry, name):
    player = type(registry.get(name)).create(seed=0)
    for start in BOARDS:
        state = copy.deepcopy(start)
        while not game.is_terminal(state):
            before = copy.deepcopy(state)
            move = player.choose_move(state)
            assert state == before, f"{name} mutated the state"
            assert game.is_legal(state, move), f"{name} returned illegal move {move}"
            state = game.apply_move(state, move)


def test_random_varies_with_the_seed(registry):
    """Different seeds must give a different game, or repetitions are wasted."""
    cls = type(registry.get("random"))
    sequences = []
    for seed in (0, 1, 2, 3):
        player = cls.create(seed=seed)
        state, moves = graphs.wheel(11), []
        while not game.is_terminal(state):
            move = player.choose_move(state)
            moves.append(move)
            state = game.apply_move(state, move)
        sequences.append(tuple(moves))
    assert len(set(sequences)) > 1, "seeding had no effect on play"


def test_same_seed_reproduces_the_same_play(registry):
    cls = type(registry.get("random"))
    state = graphs.grid(3, 3)
    assert cls.create(seed=42).choose_move(state) == cls.create(seed=42).choose_move(state)


def test_the_search_players_outperform_random(registry):
    """What each search is for, measured: points for -max, wins for -min.

    A small league on the default graphs; the margins measured on a full run are
    wide (about 3.7 points a game for aggressive-max against 2.6 for random, and a
    70% win rate for aggressive-min against 25%), so loose bounds are not brittle.
    """
    lb = run_tournament(
        build_roster([registry.get(n) for n in ("random", "aggressive-max", "aggressive-min")], 1),
        repetitions=2, budgets=UNLIMITED, use_subprocess=False,
    )
    rows = {r["player"]: r for r in lb["standings"]}
    assert rows["aggressive-max_0"]["points"] > rows["random_0"]["points"]
    assert rows["aggressive-min_0"]["win_rate"] > rows["random_0"]["win_rate"]


def test_every_player_has_a_distinct_icon(registry):
    """Icons are how a player is recognised at a glance, so they must not collide."""
    icons = [type(registry.get(n)).get_icon() for n in LADDER]
    assert len(set(icons)) == len(icons), f"duplicate icons: {icons}"


def test_leaderboard_carries_a_player_directory(registry):
    """The scoreboard reads identity from the leaderboard, not the live registry."""
    lb = run_tournament(
        build_roster([registry.get(n) for n in LADDER], 2),
        starting_states=[graphs.classic()], repetitions=1,
        budgets=UNLIMITED, use_subprocess=False,
    )
    directory = {p["name"]: p for p in lb["players"]}
    assert set(directory) == set(LADDER), "one entry per kind, not per roster copy"
    for entry in directory.values():
        assert entry["icon"].strip()
        assert entry["authors"]
        assert entry["description"].strip()
    # Roster names carry an underscore suffix the web app renders as a subscript.
    assert all("_" in r["player"] for r in lb["standings"])
