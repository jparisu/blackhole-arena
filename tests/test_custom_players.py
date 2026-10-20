"""Contract tests for the submitted players in ``players/custom/``.

Discovery is **automatic**: this module loads ``players/custom/players.yaml`` and
parametrizes every check over whatever it admits, so a new submission is covered
the moment its manifest line lands — there is nothing here to edit per player.

These tests deliberately live **outside** the main suite. ``tests.yml`` skips this
file and a separate workflow runs it alone, so one broken submission fails its own
check instead of turning every other pull request red. Nothing else in ``tests/``
loads the submitted manifest strictly, for the same reason.

What a submitted player must survive here:

* the manifest loads it and its identity accessors return something usable;
* :meth:`~blackholearena.player.Player.create` accepts a seed;
* :meth:`~blackholearena.player.Player.choose_move` returns a legal move and never
  mutates the board, on every graph, played out to the end;
* a full game against the reference ``random`` player, from both sides, ends
  ``normal`` — no crash, no hang, no illegal move.
"""

from __future__ import annotations

import copy

import pytest

from blackholearena import game, graphs
from blackholearena.manifest import CUSTOM, CUSTOM_MANIFEST, load_players
from blackholearena.player import Player
from blackholearena.registry import Registry
from blackholearena.tournament import Budgets, PlayerSpec, play_match

#: Graphs the contract checks sweep. Small, awkward ones first — a bot that breaks
#: does so on a 3-node path, a graph with an isolated node or a dense one far more
#: often than on a friendly one.
BOARDS = [
    game.new_game(3, [[0, 1], [1, 2]]),
    game.new_game(3, []),
    game.new_game(5, [[0, 1], [1, 2]]),
    graphs.classic(),
    graphs.wheel(7),
    graphs.grid(3, 3),
    graphs.wheel(11),
    graphs.random_graph(13, 0.5, seed=0),
]

#: Graphs used for the games against ``random``. A subset: each one is played from
#: both sides with every seed, so the game count grows quickly.
GAME_BOARDS = [graphs.classic(), graphs.wheel(7), graphs.grid(3, 3), graphs.wheel(11)]

#: Seeds handed to :meth:`~blackholearena.player.Player.create`. More than one, because a
#: seeded bot may configure itself differently per seed.
SEEDS = (0, 1, 2)

#: Deliberately far more generous than the tournament's own budget: the claim
#: under test is "does not crash or hang", not "is fast enough". Speed is judged by
#: the tournament, on its runners, with its own budget.
BUDGETS = Budgets(game_ms=10_000, build_ms=5_000)


def _load_submitted() -> tuple[Registry | None, Exception | None]:
    """Load the submitted manifest, returning either the registry or the failure.

    A failure is returned rather than raised so that it surfaces as one readable
    test failure instead of a collection error naming no player at all.
    """
    try:
        registry = load_players(
            {CUSTOM: CUSTOM_MANIFEST}, registry=Registry(), strict=True
        )
    except Exception as exc:  # noqa: BLE001 - reported by test_the_manifest_loads
        return None, exc
    return registry, None


_REGISTRY, _LOAD_ERROR = _load_submitted()

#: Names discovered in the manifest. Empty when the manifest is empty (no
#: submissions yet) or failed to load; the parametrized tests then have nothing to
#: run and ``test_the_manifest_loads`` reports why.
CUSTOM_NAMES = sorted(_REGISTRY.names()) if _REGISTRY is not None else []


def _kind(name: str) -> type[Player]:
    """Return the submitted class registered under ``name``."""
    assert _REGISTRY is not None
    return type(_REGISTRY.get(name))


def test_the_manifest_loads():
    """Every admitted submission must import, construct and declare an identity."""
    assert _LOAD_ERROR is None, f"players/custom/players.yaml did not load: {_LOAD_ERROR}"


@pytest.mark.parametrize("name", CUSTOM_NAMES)
def test_declares_a_usable_identity(name):
    cls = _kind(name)
    assert cls.get_name() == name
    authors = cls.get_authors()
    assert isinstance(authors, list) and authors and all(a.strip() for a in authors)
    assert cls.get_description().strip(), f"{name} declares no description"
    icon = cls.get_icon()
    assert isinstance(icon, str) and icon.strip(), f"{name} declares no icon"


@pytest.mark.parametrize("name", CUSTOM_NAMES)
def test_create_accepts_a_seed(name):
    cls = _kind(name)
    for seed in SEEDS:
        player = cls.create(seed=seed)
        assert isinstance(player, cls)
        assert player.name == name


@pytest.mark.parametrize("name", CUSTOM_NAMES)
def test_returns_legal_moves_and_never_mutates_the_board(name):
    """Play every graph out to the end, with the bot moving for both sides.

    Moving for both sides is what makes one pass cover every turn of the game —
    first and second player, one tile up to ``N`` — rather than only its opening.
    A game always ends after ``2N`` moves, so no move cap is needed.
    """
    cls = _kind(name)
    for seed in SEEDS:
        player = cls.create(seed=seed)
        for start in BOARDS:
            state = copy.deepcopy(start)
            while not game.is_terminal(state):
                before = copy.deepcopy(state)
                move = player.choose_move(state)
                assert state == before, f"{name} mutated the board it was given"
                assert game.is_legal(state, move), (
                    f"{name} returned the illegal move {move!r}; free nodes were "
                    f"{game.free_nodes(before)}"
                )
                state = game.apply_move(state, move)


@pytest.mark.parametrize("name", CUSTOM_NAMES)
def test_plays_full_games_against_random_without_failing(name):
    """Full games through the tournament runner, which forfeits on any misbehavior.

    Each game runs in a forked child with a hard deadline, so a bot that hangs is
    killed and reported instead of stalling the run. Losing is fine — ``random``
    is allowed to win; forfeiting is not.
    """
    # Imported here, not at module scope: `players` is a namespace package that
    # only conftest.py puts on sys.path, and the import sorter files it as a
    # third-party package if it sits beside `pytest`.
    from players.builtin.random import Random

    cls = _kind(name)
    failures = []
    for board in GAME_BOARDS:
        for seed in SEEDS:
            for goes_first in (True, False):
                mine = PlayerSpec(cls=cls, seed=seed, name=name)
                theirs = PlayerSpec(cls=Random, seed=seed + 100, name="random")
                first, second = (mine, theirs) if goes_first else (theirs, mine)
                result = play_match(first, second, board, BUDGETS)
                if result.result != "normal":
                    failures.append(
                        f"nodes={game.num_nodes(board)} seed={seed} first={first.name}: "
                        f"{result.result} — {result.detail}"
                    )
    assert not failures, f"{name} failed {len(failures)} game(s):\n" + "\n".join(failures)
