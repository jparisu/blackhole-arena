"""Tests for the tournament: scoring by points, and robustness (forfeits)."""

from __future__ import annotations

import time

import pytest

from blackholearena import game, graphs
from blackholearena.player import Player
from blackholearena.tournament import (
    BUILTIN_PLAYER_COPIES,
    CUSTOM_PLAYER_COPIES,
    UNLIMITED,
    Budgets,
    MatchResult,
    PlayerSpec,
    build_roster,
    copies_for,
    play_match,
    play_matchup,
    run_tournament,
    validate_starting_states,
)

#: A path of three nodes, 0 - 1 - 2: one turn each, one tile each.
PATH3 = game.new_game(3, [[0, 1], [1, 2]])
#: The 5-node example graph from the rules.
CLASSIC = graphs.classic()


class _Stub(Player):
    """Base for test players: derives the required identity from the class name.

    Keeps each stub below to just its ``choose_move``, which is the behaviour
    under test.
    """

    @classmethod
    def get_name(cls) -> str:
        return cls.__name__

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["tests"]

    @classmethod
    def get_description(cls) -> str:
        return f"Test stub {cls.__name__}."

    @classmethod
    def get_icon(cls) -> str:
        return "🧪"


class FirstFreeBot(_Stub):
    """Always plays the lowest free node (legal, simple)."""

    def choose_move(self, state):
        return game.legal_moves(state)[0]


class LastFreeBot(_Stub):
    """Always plays the highest free node (legal, simple, distinct from FirstFreeBot)."""

    def choose_move(self, state):
        return game.legal_moves(state)[-1]


class CrashBot(_Stub):
    def choose_move(self, state):
        raise RuntimeError("boom")


class CheatBot(_Stub):
    def choose_move(self, state):
        return 999  # illegal: no such node


class SlowBot(_Stub):
    def choose_move(self, state):
        while True:  # never returns -> must be killed by the subprocess timeout
            pass


# --------------------------------------------------------------------------- #
# Scoring                                                                      #
# --------------------------------------------------------------------------- #

def test_normal_game_is_scored_by_the_rules():
    # First plays 0, second plays 1, so node 2 is the hole: only node 1 touches it.
    result = play_match(FirstFreeBot(), FirstFreeBot(), PATH3, UNLIMITED)
    assert result.result == "normal"
    assert result.scores == (0, 1)
    assert result.winner == result.player_second


def test_a_draw_has_no_winner():
    # First plays 0, second plays 2, so node 1 is the hole and touches both.
    result = play_match(FirstFreeBot(), LastFreeBot(), PATH3, UNLIMITED)
    assert result.scores == (1, 1)
    assert result.winner == ""


def test_the_rules_example_through_the_runner():
    class Scripted(_Stub):
        """Plays A, B, D, C — the example from the rules."""

        def choose_move(self, state):
            return [0, 1, 3, 2][game.moves_played(state)]

    class Scripted2(Scripted):
        pass

    result = play_match(Scripted(), Scripted2(), CLASSIC, UNLIMITED)
    assert result.scores == (2, 1)
    assert result.score_of("Scripted") == 2 and result.score_of("Scripted2") == 1


def test_ranking_is_by_points_not_by_games_won():
    """A player that wins fewer games but scores more points must rank first."""
    from blackholearena.tournament import _new_stats, _rank_names, _tally_game

    stats = _new_stats(["Big", "Small"])
    for scores in ((3, 0), (0, 1), (0, 1)):
        _tally_game(stats, MatchResult("Big", "Small", CLASSIC, scores, "normal"))
    assert stats["Big"].wins == 1 and stats["Small"].wins == 2
    assert stats["Big"].points == 3 and stats["Small"].points == 2
    assert _rank_names(stats, use_elo=False) == ["Big", "Small"]


def test_both_players_can_score_in_the_same_game():
    """Not zero-sum: one player's points are not the other's losses."""
    from blackholearena.tournament import _new_stats, _tally_game

    stats = _new_stats(["A", "B"])
    _tally_game(stats, MatchResult("A", "B", CLASSIC, (2, 2), "normal"))
    assert stats["A"].points == 2 and stats["B"].points == 2
    assert stats["A"].draws == 1 and stats["B"].draws == 1


def test_elo_treats_each_game_as_won_drawn_or_lost():
    """Elo reads the game as zero-sum: the margin does not matter, only who won."""
    from blackholearena.tournament import _elo_result

    assert _elo_result(MatchResult("A", "B", CLASSIC, (3, 1), "normal")) == 1.0
    assert _elo_result(MatchResult("A", "B", CLASSIC, (1, 3), "normal")) == 0.0
    assert _elo_result(MatchResult("A", "B", CLASSIC, (2, 2), "normal")) == 0.5


# --------------------------------------------------------------------------- #
# Forfeits                                                                     #
# --------------------------------------------------------------------------- #

def test_exception_forfeits_and_opponent_scores_the_maximum():
    result = play_match(CrashBot(), FirstFreeBot(), CLASSIC, UNLIMITED)
    assert result.result == "forfeit_error"
    assert result.forfeiter == "CrashBot"
    assert result.scores == (0, game.tiles_per_player(CLASSIC))
    assert result.winner == "FirstFreeBot"


def test_a_forfeit_by_the_second_player_credits_the_first():
    result = play_match(FirstFreeBot(), CrashBot(), CLASSIC, UNLIMITED)
    assert result.scores == (game.tiles_per_player(CLASSIC), 0)


def test_illegal_move_forfeits():
    result = play_match(CheatBot(), FirstFreeBot(), CLASSIC, UNLIMITED)
    assert result.result == "forfeit_illegal"
    assert result.winner == "FirstFreeBot"


@pytest.mark.parametrize("bad", [True, 1.0, "1", (1,), None])
def test_moves_that_are_not_plain_ints_are_illegal(bad):
    class Odd(_Stub):
        def choose_move(self, state):
            return bad

    result = play_match(Odd(), FirstFreeBot(), CLASSIC, UNLIMITED)
    assert result.result == "forfeit_illegal"


def test_hung_bot_is_killed_and_forfeits():
    # Uses the process-based hard timeout; the infinite loop must be terminated.
    result = play_match(SlowBot(), FirstFreeBot(), CLASSIC, Budgets(game_ms=300, build_ms=300))
    assert result.result == "forfeit_timeout"
    assert result.winner == "FirstFreeBot"


def test_run_tournament_survives_a_bad_bot():
    players = [FirstFreeBot(), CrashBot(), CheatBot()]
    lb = run_tournament(
        players, starting_states=[CLASSIC], repetitions=1,
        budgets=UNLIMITED, use_subprocess=False,
    )
    # The run completes and produces standings for everyone despite bad bots.
    assert {r["player"] for r in lb["standings"]} == {
        "FirstFreeBot", "CrashBot", "CheatBot"
    }
    good = next(r for r in lb["standings"] if r["player"] == "FirstFreeBot")
    assert good["rank"] == 1
    # CrashBot forfeits every game it plays, except the one where CheatBot moves
    # first and forfeits before CrashBot is ever asked — which credits it the
    # maximum, 3 points on the 5-node graph.
    crash = next(r for r in lb["standings"] if r["player"] == "CrashBot")
    assert crash["forfeits"] == 3
    assert crash["points"] == game.tiles_per_player(CLASSIC)


# --------------------------------------------------------------------------- #
# Rosters                                                                      #
# --------------------------------------------------------------------------- #

def test_build_roster_duplicates_each_kind_with_seed_suffixes():
    # A deterministic bot ignores the seed but is still duplicated so it faces itself.
    # Every count below is passed explicitly: these tests are about build_roster's
    # behaviour, not about whatever BUILTIN/CUSTOM_PLAYER_COPIES happen to be.
    roster = build_roster([FirstFreeBot()], repetition=2)
    assert [p.name for p in roster] == ["FirstFreeBot_0", "FirstFreeBot_1"]


def test_build_roster_takes_a_per_kind_copy_count():
    """The count is per kind, and the caller decides it — see `copies_for`."""
    roster = build_roster(
        [FirstFreeBot(), LastFreeBot()], repetition=1, copies={"LastFreeBot": 3}
    )
    assert [p.name for p in roster] == [
        "FirstFreeBot_0", "LastFreeBot_0", "LastFreeBot_1", "LastFreeBot_2",
    ]


def test_build_roster_ignores_copies_for_kinds_not_entered():
    """A stale name in the mapping is harmless: only the given players are built."""
    roster = build_roster([FirstFreeBot()], repetition=1, copies={"NotEntered": 5})
    assert [p.name for p in roster] == ["FirstFreeBot_0"]


def test_build_roster_rejects_a_zero_copy_count():
    with pytest.raises(ValueError):
        build_roster([FirstFreeBot()], copies={"FirstFreeBot": 0})


def test_copies_follow_the_manifest_that_admitted_the_player():
    """Roster copies are a tournament decision, taken from a player's origin."""
    from blackholearena.manifest import BUILTIN, CUSTOM
    from blackholearena.registry import Registry

    reg = Registry()
    reg.register(FirstFreeBot(), origin=BUILTIN)
    reg.register(LastFreeBot(), origin=CUSTOM)
    assert copies_for(reg) == {
        "FirstFreeBot": BUILTIN_PLAYER_COPIES,
        "LastFreeBot": CUSTOM_PLAYER_COPIES,
    }


def test_build_roster_defaults_to_a_single_copy():
    """The default is a plain 1, independent of the policy constants."""
    assert [p.name for p in build_roster([FirstFreeBot()])] == ["FirstFreeBot_0"]


def test_build_roster_assigns_one_seed_per_copy():
    roster = build_roster([FirstFreeBot()], repetition=3)
    assert [s.seed for s in roster] == [0, 1, 2]
    assert all(s.cls is FirstFreeBot for s in roster)


def test_players_are_built_through_the_create_factory():
    """Construction must go through create(), and happen once per game."""
    built_with: list[int] = []

    class Recording(_Stub):
        @classmethod
        def create(cls, seed: int):
            built_with.append(seed)
            return cls()

        def choose_move(self, state):
            return game.legal_moves(state)[0]

    # In-process, so the recording list is visible to the test.
    play_match(Recording(), FirstFreeBot(), PATH3, UNLIMITED, use_subprocess=False)
    assert built_with == [0], "create() should be called exactly once per game"


def test_build_roster_seeds_random_bots_reproducibly():
    from players.builtin.random import Random

    a, b = build_roster([Random.create(seed=0)], repetition=2)
    assert (a.name, a.seed) == ("random_0", 0)
    assert (b.name, b.seed) == ("random_1", 1)
    # A copy built from its spec behaves exactly like a fresh instance with that seed.
    state = graphs.grid(3, 3)
    assert a.cls.create(seed=a.seed).choose_move(state) == (
        Random.create(seed=0).choose_move(state)
    )


def test_build_roster_rejects_zero_repetition():
    with pytest.raises(ValueError):
        build_roster([FirstFreeBot()], repetition=0)


def test_build_roster_lets_a_kind_play_itself():
    # Two seeded copies of the same kind are distinct opponents in the roster.
    roster = build_roster([FirstFreeBot()], repetition=2)
    lb = run_tournament(
        roster, starting_states=[CLASSIC], repetitions=1,
        budgets=UNLIMITED, use_subprocess=False,
    )
    assert {r["player"] for r in lb["standings"]} == {"FirstFreeBot_0", "FirstFreeBot_1"}
    # They played each other once from each side.
    assert all(r["games"] == 2 for r in lb["standings"])


# --------------------------------------------------------------------------- #
# The results payload                                                          #
# --------------------------------------------------------------------------- #

def test_leaderboard_schema_shape():
    lb = run_tournament(
        [FirstFreeBot(), CheatBot()],
        starting_states=[PATH3],
        repetitions=2,
        budgets=UNLIMITED,
        use_subprocess=False,
        now=lambda: __import__("datetime").datetime(2026, 3, 1, 12, 0, 0),
    )
    assert lb["generated_at"] == "2026-03-01T12:00:00Z"
    assert lb["config"]["graphs"] == [{"nodes": 3, "edges": [[0, 1], [1, 2]]}]
    assert lb["config"]["tournament"] == "simple"
    assert lb["config"]["repetitions"] == 2
    for block in ("standings", "matches", "player_stats", "totals", "structure"):
        assert block in lb
    match = lb["matches"][0]
    assert set(match) >= {
        "player_a", "player_b", "phase", "games", "a_points", "b_points",
        "a_wins", "b_wins", "draws", "winner",
    }
    # One graph, both first-mover orders, 2 reps -> 4 games in the single match.
    assert match["games"] == 4
    assert lb["totals"]["matches"] == 1 and lb["totals"]["players"] == 2
    row = lb["standings"][0]
    assert set(row) >= {"points", "avg_points", "points_against", "wins", "draws", "losses"}
    opp = lb["player_stats"][0]["opponents"][0]
    assert set(opp) >= {"opponent", "games", "points", "points_against", "wins", "draws", "losses"}


def test_points_add_up_across_the_payload():
    lb = run_tournament(
        [FirstFreeBot(), LastFreeBot()],
        starting_states=[CLASSIC, graphs.wheel(7)], repetitions=1,
        budgets=UNLIMITED, use_subprocess=False,
    )
    match = lb["matches"][0]
    by_name = {r["player"]: r for r in lb["standings"]}
    assert by_name[match["player_a"]]["points"] == match["a_points"]
    assert by_name[match["player_b"]]["points"] == match["b_points"]
    assert lb["totals"]["total_points"] == match["a_points"] + match["b_points"]


def test_timing_is_aggregated_and_never_per_move():
    """Timing ships as mean/std/max only — never a per-move array."""
    lb = run_tournament(
        [FirstFreeBot(), LastFreeBot()],
        starting_states=[CLASSIC], repetitions=2,
        budgets=UNLIMITED, use_subprocess=False,
    )
    match = lb["matches"][0]
    for key in ("a_avg_move_ms", "b_avg_move_ms", "a_std_move_ms",
                "b_std_move_ms", "a_max_move_ms", "b_max_move_ms"):
        assert key in match, key
    assert "moves" not in match
    for row in lb["standings"]:
        assert {"avg_move_ms", "std_move_ms", "max_move_ms"} <= set(row)
    for row in lb["player_stats"]:
        assert {"avg_move_ms", "std_move_ms", "max_move_ms"} <= set(row)
    # Nothing anywhere in the payload carries a per-move log.
    assert "state_before" not in repr(lb)


def test_league_mode_ranks_by_elo():
    lb = run_tournament(
        [FirstFreeBot(), CheatBot()],
        mode="league",
        starting_states=[CLASSIC],
        repetitions=1,
        budgets=UNLIMITED,
        use_subprocess=False,
    )
    assert lb["config"]["tournament"] == "league"
    assert lb["config"]["elo"] is True
    assert all("elo" in row for row in lb["standings"])
    # FirstFreeBot always outscores CheatBot (illegal move) -> higher Elo, rank 1.
    top = lb["standings"][0]
    assert top["player"] == "FirstFreeBot"
    assert top["elo"] > lb["standings"][1]["elo"]


def test_league_without_elo_falls_back_to_points():
    lb = run_tournament(
        [FirstFreeBot(), CheatBot()],
        mode="league",
        elo=False,
        starting_states=[CLASSIC],
        repetitions=1,
        budgets=UNLIMITED,
        use_subprocess=False,
    )
    assert lb["config"]["elo"] is False
    # Still rated and reported — it just does not decide the ranking.
    assert all("elo" in row for row in lb["standings"])
    points = [row["points"] for row in lb["standings"]]
    assert points == sorted(points, reverse=True)


def test_every_mode_reports_the_four_scoreboard_measures():
    """Points, Elo, win rate and average move time, whatever the format."""
    for mode in ("simple", "league", "championship"):
        lb = run_tournament(
            build_roster([FirstFreeBot(), LastFreeBot()], repetition=1), mode=mode,
            starting_states=[CLASSIC], repetitions=1, budgets=UNLIMITED,
            use_subprocess=False,
        )
        for block in ("standings", "player_stats"):
            for row in lb[block]:
                assert {"points", "elo", "win_rate", "avg_move_ms"} <= set(row), (mode, block)


def test_championship_builds_groups_and_bracket():
    # Four kinds x 2 copies = 8 players -> two groups of four, top two advance.
    roster = build_roster(
        [FirstFreeBot(), LastFreeBot(), CheatBot(), CrashBot()], repetition=2
    )
    lb = run_tournament(
        roster,
        mode="championship",
        starting_states=[CLASSIC],
        repetitions=1,
        budgets=UNLIMITED,
        use_subprocess=False,
    )
    structure = lb["structure"]
    assert structure["type"] == "championship"
    assert len(structure["groups"]) == 2
    assert all(len(g["advance"]) == 2 for g in structure["groups"])
    bracket = structure["bracket"]
    assert bracket["rounds"], "expected at least one knockout round"
    assert bracket["champion"] in {p.name for p in roster}
    tie = bracket["rounds"][0]["ties"][0]
    assert {"a_points", "b_points", "winner"} <= set(tie)


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        run_tournament([FirstFreeBot()], mode="bogus", use_subprocess=False)


# --------------------------------------------------------------------------- #
# Time budgets, hangs, and attribution                                         #
# --------------------------------------------------------------------------- #

class SlowBuildBot(_Stub):
    """Hangs while being constructed, not while playing."""

    def __init__(self):
        while True:
            pass

    def choose_move(self, state):
        return game.legal_moves(state)[0]


class BadBuildBot(_Stub):
    """Raises while being constructed."""

    def __init__(self):
        raise RuntimeError("bad build")

    def choose_move(self, state):
        return game.legal_moves(state)[0]


class GeneratorBot(_Stub):
    """Returns a single-use iterable instead of a node."""

    def choose_move(self, state):
        return (x for x in (0,))


class RenamerBot(_Stub):
    """Tries to rename itself mid-game."""

    def choose_move(self, state):
        self.name = "somethingElse"
        return game.legal_moves(state)[0]


class MutatorBot(_Stub):
    """Vandalises the board it is handed, then plays a legal move."""

    def choose_move(self, state):
        move = game.legal_moves(state)[0]
        state["edges"].clear()
        state["owner"][:] = [1] * len(state["owner"])
        return move


def test_a_hung_constructor_is_attributed_to_its_own_player():
    """The build phase must be killable, and blamed on the player being built."""
    # Passed as a spec and never instantiated here: constructing it would hang the
    # test process itself. That is exactly why the child does the building.
    result = play_match(
        PlayerSpec(SlowBuildBot, 0, "SlowBuildBot"), FirstFreeBot(), CLASSIC,
        Budgets(game_ms=200, build_ms=200),
    )
    assert result.result == "forfeit_build_timeout"
    assert result.winner == "FirstFreeBot"
    assert "SlowBuildBot" in result.detail


def test_a_raising_constructor_forfeits():
    result = play_match(
        PlayerSpec(BadBuildBot, 0, "BadBuildBot"), FirstFreeBot(), CLASSIC, UNLIMITED
    )
    assert result.result == "forfeit_build_error"
    assert result.winner == "FirstFreeBot"


def test_build_time_is_measured_and_reported():
    result = play_match(FirstFreeBot(), LastFreeBot(), CLASSIC, UNLIMITED)
    assert set(result.build_ms) == {"FirstFreeBot", "LastFreeBot"}
    assert all(v >= 0.0 for v in result.build_ms.values())


def test_a_generator_move_forfeits_instead_of_crashing_the_run():
    result = play_match(GeneratorBot(), FirstFreeBot(), CLASSIC, UNLIMITED)
    assert result.result == "forfeit_illegal"
    assert result.winner == "FirstFreeBot"
    # And it must not abort a whole run either.
    lb = run_tournament(
        [GeneratorBot(), FirstFreeBot()], starting_states=[CLASSIC], repetitions=1,
        budgets=UNLIMITED, use_subprocess=False,
    )
    assert lb["totals"]["games"] == 2


def test_a_player_renaming_itself_cannot_corrupt_the_standings():
    """Regression: names came from the player, so a rename raised KeyError."""
    lb = run_tournament(
        [RenamerBot(), FirstFreeBot()], starting_states=[CLASSIC], repetitions=1,
        budgets=UNLIMITED, use_subprocess=False,
    )
    assert {r["player"] for r in lb["standings"]} == {"RenamerBot", "FirstFreeBot"}


def test_a_player_mutating_its_board_cannot_corrupt_the_game():
    """Each move hands over a deep copy, edges included."""
    result = play_match(MutatorBot(), FirstFreeBot(), CLASSIC, UNLIMITED, use_subprocess=False)
    assert result.result == "normal"
    assert result.start_state == graphs.classic()
    assert len(result.moves) == 4


def test_game_budget_is_cumulative_across_moves_not_per_move():
    """A chess clock: many cheap moves must not each get the full budget."""

    class Dawdler(_Stub):
        def choose_move(self, state):
            time.sleep(0.05)
            return game.legal_moves(state)[0]

    # Each move is well inside 120 ms, but four of them (on 9 nodes) are not.
    result = play_match(
        Dawdler(), FirstFreeBot(), graphs.grid(3, 3), Budgets(game_ms=120, build_ms=2000),
        use_subprocess=False,
    )
    assert result.result == "forfeit_timeout"
    assert result.winner == "FirstFreeBot"
    assert "game budget" in result.detail


def test_spent_time_survives_a_kill():
    """The orchestrator must recover per-player time even when the child is killed."""
    result = play_match(
        SlowBot(), FirstFreeBot(), CLASSIC, Budgets(game_ms=200, build_ms=200)
    )
    assert result.result == "forfeit_timeout"
    assert set(result.spent_ms) == {"SlowBot", "FirstFreeBot"}
    assert set(result.build_ms) == {"SlowBot", "FirstFreeBot"}


def test_deadline_is_twice_the_budgets_plus_grace():
    b = Budgets(game_ms=1000, build_ms=500, grace_ms=250)
    assert b.deadline_ms == 2 * (1000 + 500) + 250
    assert UNLIMITED.deadline_ms is None


def test_player_state_survives_across_moves_in_one_game():
    """Fork-per-game, not per move: a counter must advance through the game."""

    class Counter(_Stub):
        def __init__(self):
            self.seen = 0

        def choose_move(self, state):
            self.seen += 1
            if self.seen > 1 and not self._ok:
                raise AssertionError("state was discarded between moves")
            self._ok = True
            return game.legal_moves(state)[0]

        _ok = False

    result = play_match(Counter(), Counter(), graphs.grid(3, 3), Budgets())
    assert result.result == "normal"


def test_repeated_games_differ_when_the_player_is_stochastic():
    """Repetitions must not be byte-identical."""
    from players.builtin.random import Random

    mu = play_matchup(
        PlayerSpec(Random, 0, "random_0"),
        PlayerSpec(Random, 1, "random_1"),
        [graphs.wheel(11)], repetitions=6, budgets=Budgets(),
    )
    signatures = {tuple(m.move for m in g.moves if m.move is not None) for g in mu.games}
    assert len(signatures) > 2, f"only {len(signatures)} distinct games out of {len(mu.games)}"


# --------------------------------------------------------------------------- #
# Input validation                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "states",
    [
        [],                                               # nothing to play
        [[3, 5, 7]],                                      # a NIM board, not a state
        [{"edges": [], "owner": [None] * 4, "tiles": [0] * 4}],  # even node count
        [{"edges": [[0, 9]], "owner": [None] * 3, "tiles": [0] * 3}],  # bad edge
        [game.apply_move(graphs.classic(), 0)],           # already started
    ],
)
def test_unplayable_starting_states_are_rejected(states):
    with pytest.raises(ValueError):
        validate_starting_states(states)


def test_valid_starting_states_are_returned_as_fresh_copies():
    original = graphs.classic()
    (cleaned,) = validate_starting_states([original])
    assert cleaned == original
    assert cleaned is not original and cleaned["edges"] is not original["edges"]


def test_empty_roster_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        run_tournament([], use_subprocess=False)


def test_duplicate_roster_names_are_rejected():
    """Two same-named entries would collapse into one standings row."""
    with pytest.raises(ValueError, match="unique"):
        run_tournament(
            [FirstFreeBot(), FirstFreeBot()], starting_states=[CLASSIC],
            repetitions=1, budgets=UNLIMITED, use_subprocess=False,
        )


def test_zero_repetitions_is_rejected():
    with pytest.raises(ValueError):
        run_tournament([FirstFreeBot(), LastFreeBot()], repetitions=0, use_subprocess=False)


@pytest.mark.parametrize(("group_size", "advance"), [(0, 2), (4, 0)])
def test_championship_rejects_degenerate_group_settings(group_size, advance):
    """group_size=0 used to raise ZeroDivisionError."""
    with pytest.raises(ValueError):
        run_tournament(
            build_roster([FirstFreeBot(), LastFreeBot()], repetition=1), mode="championship",
            starting_states=[CLASSIC], repetitions=1, budgets=UNLIMITED,
            use_subprocess=False, group_size=group_size, advance_per_group=advance,
        )


def test_a_whole_run_is_reproducible_despite_varying_games():
    """Games within a match differ, yet the run repeats byte-for-byte."""
    from players.builtin.random import Random

    def signatures():
        mu = play_matchup(
            PlayerSpec(Random, 0, "random_0"),
            PlayerSpec(Random, 1, "random_1"),
            [graphs.wheel(11)], repetitions=4, budgets=UNLIMITED, use_subprocess=False,
        )
        return [tuple(m.move for m in g.moves if m.move is not None) for g in mu.games]

    first, second = signatures(), signatures()
    assert first == second, "the same match must replay identically"
    assert len(set(first)) > 2, "but its games must not be identical to each other"


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def test_cli_graph_flag_parses_nodes_and_edges():
    from blackholearena.tournament import _parse_graph

    assert _parse_graph("5:0-1, 1-2,2-3") == game.new_game(5, [[0, 1], [1, 2], [2, 3]])
    with pytest.raises(ValueError):
        _parse_graph("5:0-1-2")
    with pytest.raises(ValueError):
        _parse_graph("4:0-1")  # even node count


def test_cli_writes_a_points_leaderboard(tmp_path):
    from blackholearena.tournament import main

    out = tmp_path / "lb.json"
    empty = tmp_path / "empty.yaml"
    empty.write_text("players: []\n")
    code = main([
        "--no-subprocess", "--repetitions", "1", "--custom-manifest", str(empty),
        "--graph", "5:0-1,1-2,2-3,3-4,4-0", "--out", str(out),
    ])
    assert code == 0
    data = __import__("json").loads(out.read_text())
    assert data["config"]["graphs"][0]["nodes"] == 5
    assert all("points" in row for row in data["standings"])
