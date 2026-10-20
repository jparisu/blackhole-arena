"""Tournament runner: formats, time budgets, forfeits, results.

**Robustness (not security) is the goal.** Even accepted, well-meaning bots can
hang, crash, or return an illegal move on some edge case. This runner survives all
of it and never aborts:

* a player that **exceeds a time budget** -> forfeits that game;
* a player that **raises an exception** -> forfeits that game;
* a player that **returns an illegal move** -> forfeits that game;
* a player that **hangs forever** -> is killed, and forfeits that game;
* a player that **fails or hangs while being built** -> forfeits that game.

In every case the reason is recorded in the results and the run continues.

## Scoring

BlackHole is **not zero-sum**: both players score in every game, and each one
tries to maximize its *own* score. So a player's tournament **points** are the
sum of the scores it obtained in its games — not a count of games "won".

Every player is also measured as if the game *were* zero-sum, where a game is
won by whoever scored more (a draw if both scored the same). Two figures come
from that view: the **win rate** and an [Elo rating][blackholearena.elo] (win 1,
draw 0.5, loss 0). Both are always reported, next to the points and the average
move time; they decide the ranking only in ``league`` mode.

A forfeit ends the game early, so there is no black hole to score. The offending
player scores ``0`` for that game and its opponent scores
[`tiles_per_player`][blackholearena.game.tiles_per_player] — the most a player
can ever score on that graph — so nobody is penalised for meeting a broken bot.

## Formats

Three tournament formats are supported (``--tournament``):

* ``simple`` — every pair plays one match; players are ranked by points.
* ``league`` — every pair plays one match; players are ranked by their Elo
  rating (see above) when enabled, else by points.
* ``championship`` — a group phase (round-robin in groups of four, ranked by
  points, top two advance) followed by a seeded single-elimination bracket, where
  the player with more points over the match advances.

A **match** between two players is played identically in every format: for each
starting graph, and for each player going first once, ``repetitions`` games are
played. So a match spans ``len(graphs) * 2 * repetitions`` games.

Every pair of *entrants* plays one match, and a player kind is entered more than
once so that it also meets its own strategy — see :func:`build_roster`. How many
copies each one gets is decided here, by :func:`copies_for`, from the manifest that
admitted it: :data:`BUILTIN_PLAYER_COPIES` for the reference ladder, :data:`CUSTOM_PLAYER_COPIES`
for a submission.

## Time budgets

Budgets are **per player, per game** — a chess clock, not a per-move limit. A bot
may spend most of its budget on one hard move; that is intended. Two independent
budgets, in [`Budgets`][blackholearena.tournament.Budgets]:

* ``build_ms`` covers [`create`][blackholearena.player.Player.create] for one player;
* ``game_ms`` covers all of that player's ``choose_move`` calls in one game.

Construction is budgeted separately so that an expensive precomputation cannot be
smuggled past the clock by doing it in ``__init__``.

## Why one process per game

A game runs in **one forked child process**, so a truly hung bot can be killed and
the tournament can move on. (Threads cannot be force-killed in Python, so they
cannot honour that guarantee.)

One fork per *game* rather than per *move* matters for correctness, not just speed:
a child's memory is discarded when it exits, so forking per move would throw away
everything a player learned — its RNG position, any cache, any memo table. Games
would be byte-identical repeats and memoization would be impossible.

The child owns the whole game, so the parent never holds a player instance — only a
[`PlayerSpec`][blackholearena.tournament.PlayerSpec]. That is also what makes a hanging
constructor survivable.

## Attributing a hang

The child adds a move's time to the clock only *after* ``choose_move`` returns, so a
bot that hangs never records its own time, and a queue's buffered writes can be lost
when the child is killed. The child therefore publishes its progress into **shared
memory** (:class:`multiprocessing.Array`), which is mapped into both processes and
stays readable by the parent after the child is killed. It records which phase it is
in and which player is executing *before* entering any player code, so the parent
can always name the culprit exactly rather than guessing.

If the platform cannot ``fork``, the runner falls back to running in-process with
soft budgets (over-budget games still forfeit, but a genuine infinite loop cannot be
interrupted). The web page runs neither path — it calls ``choose_move`` directly and
enforces no budget, by design.
"""

from __future__ import annotations

import argparse
import copy
import multiprocessing as mp
import queue as queue_mod
import statistics
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

from . import game
from .elo import DEFAULT_INITIAL_RATING, updated_ratings
from .game import Move, State
from .graphs import classic, grid, wheel
from .manifest import BUILTIN
from .player import Player

if TYPE_CHECKING:
    # Only the concrete contexts declare `Process`; BaseContext does not. This one
    # exists solely on POSIX, which is exactly where the fork path applies.
    from multiprocessing.context import ForkContext

    from .registry import Registry

#: Graphs every match is played on, unless the caller overrides them.
#:
#: Three deliberately different shapes and sizes: the 5-node example from the
#: rules (``N = 2``), a 7-node wheel whose hub touches every node (``N = 3``), and
#: a 3x3 grid where no node dominates (``N = 4``). The last one matters because a
#: depth-limited search cannot see the end of a 9-node game from its opening,
#: which keeps the top of the ranking discriminating. Every match plays
#: ``repetitions`` games on each graph, from each side.
DEFAULT_STARTING_STATES: list[State] = [classic(), wheel(7), grid(3, 3)]
#: Per-player, per-game thinking budget in milliseconds.
DEFAULT_GAME_BUDGET_MS = 2000
#: Per-player budget for :meth:`~blackholearena.player.Player.create`, in milliseconds.
DEFAULT_BUILD_BUDGET_MS = 2000
#: Slack added to the wall-clock deadline to cover fork, imports and teardown.
DEFAULT_GRACE_MS = 500
#: Per-player budget in seconds, used as the CLI default for both budgets.
DEFAULT_TIME_LIMIT_S = 2.0
#: Seeded copies entered for a player from ``players/builtin`` — the reference
#: ladder. Two, so that each rung also meets its own strategy: a round-robin never
#: pairs an instance with itself.
BUILTIN_PLAYER_COPIES = 2
#: Seeded copies entered for a player from ``players/custom`` — a submission.
#: One, because the work is quadratic in the number of entrants and this is the
#: side that grows with every merged pull request. Raise it only if the roster
#: stays small.
CUSTOM_PLAYER_COPIES = 1
#: Games played per (graph, first-mover) pairing within a single match.
#:
#: A match is ``graphs * 2 * repetitions`` games and every pair of entrants plays
#: one, so the cost of a tournament is this number times a quadratic. Three keeps
#: a full roster inside the CI job's timeout; raise it for a small roster, where
#: the extra resolution in the Elo ratings is cheap.
DEFAULT_REPETITIONS = 3
#: Players per group in the championship group phase.
DEFAULT_GROUP_SIZE = 4
#: Players that advance from each championship group to the knockout bracket.
DEFAULT_ADVANCE_PER_GROUP = 2
#: The tournament formats understood by :func:`run_tournament`.
TOURNAMENT_MODES = ("simple", "league", "championship")

#: One JSON object in the results payload.
#:
#: ``Any`` rather than ``object`` is deliberate, and rather than a ``TypedDict``
#: too. This is a JSON boundary: the payload is written to
#: ``results/leaderboard.json`` and consumed by a web page, its shape varies by
#: tournament mode, and some blocks (``structure``) differ entirely between modes.
#: Modelling that precisely needs ``NotRequired``, which is not in ``typing``
#: until 3.11 — so on the 3.10 floor it would mean adding ``typing_extensions``
#: as a runtime dependency of the package, to describe a dict that is validated
#: by tests against the schema documented in ``docs/tournament.md``. Not worth it.
#: Every *function* here is still fully annotated; only the payload's interior is
#: dynamic, which is the truth about JSON.
JsonDict = dict[str, Any]

#: Milliseconds per second, used to convert measured/allotted times.
_MS_PER_SECOND = 1000.0
#: Decimal places used when rounding reported times and rates.
_ROUND_DIGITS = 3
#: How long the parent waits to collect a finished child's result.
_COLLECT_GRACE_S = 5.0


# --------------------------------------------------------------------------- #
# Budgets and player specifications                                            #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Budgets:
    """The time a player is allowed, per game.

    Attributes:
        game_ms: total ``choose_move`` time allowed per player per game, in
            milliseconds. ``None`` disables the thinking budget.
        build_ms: time allowed to build one player, in milliseconds. ``None``
            disables the construction budget.
        grace_ms: slack added to the wall-clock deadline, covering fork, imports
            and process teardown. Without it a legitimately slow game gets killed.
    """

    game_ms: int | None = DEFAULT_GAME_BUDGET_MS
    build_ms: int | None = DEFAULT_BUILD_BUDGET_MS
    grace_ms: int = DEFAULT_GRACE_MS

    @property
    def deadline_ms(self) -> int | None:
        """Wall-clock limit for a whole game, or ``None`` if nothing is budgeted.

        Twice the per-player budgets, because *both* players may legitimately
        consume theirs in full, plus :attr:`grace_ms`.
        """
        if self.game_ms is None and self.build_ms is None:
            return None
        return 2 * ((self.game_ms or 0) + (self.build_ms or 0)) + self.grace_ms


#: Budgets that enforce nothing — used by tests and by ``--no-time-limit``.
UNLIMITED = Budgets(game_ms=None, build_ms=None)


@dataclass(frozen=True)
class PlayerSpec:
    """How to build one competitor, without building it.

    The parent orchestrates with specifications rather than instances: the child
    process is what calls :meth:`~blackholearena.player.Player.create`, so a constructor
    that hangs or raises is contained the same way a bad move is. It also means a
    player cannot rename itself out of the standings, and a configured player is
    never silently rebuilt with default arguments.

    Attributes:
        cls: the :class:`~blackholearena.player.Player` subclass to build.
        seed: seed handed to :meth:`~blackholearena.player.Player.create`.
        name: display name in the results (e.g. ``"hard#1"``).
    """

    cls: type[Player]
    seed: int
    name: str


#: Multiplier used to fold a roster seed and a game index into one game seed. A
#: prime well above any plausible game count, so distinct (roster seed, game index)
#: pairs never collide.
_SEED_STRIDE = 1_000_003


def _seed_for_game(spec: PlayerSpec, game_index: int) -> PlayerSpec:
    """Return ``spec`` re-seeded for game number ``game_index`` of a match.

    Forking per game lets a player's state survive its own game, but every game of
    a match would still be built with the *same* seed — so a stochastic player
    would replay one identical game ``repetitions`` times. Deriving the seed from
    the roster seed *and* the game index is what actually makes repeated games
    differ, while keeping the whole run reproducible: the same match in the same
    order always produces the same seeds.

    The display name is preserved, so the standings are unaffected.
    """
    return PlayerSpec(
        cls=spec.cls,
        seed=spec.seed * _SEED_STRIDE + game_index,
        name=spec.name,
    )


def _as_spec(entry: Player | PlayerSpec, seed: int = 0) -> PlayerSpec:
    """Coerce a player *or* an already-built spec into a :class:`PlayerSpec`.

    Accepting instances keeps ``run_tournament([MyBot(), Other()])`` working for
    tests and quick scripts; the instance is used only for its class and name.
    """
    if isinstance(entry, PlayerSpec):
        return entry
    return PlayerSpec(cls=type(entry), seed=seed, name=entry.name)


# --------------------------------------------------------------------------- #
# Shared progress, written by the child and readable after it is killed        #
# --------------------------------------------------------------------------- #

class _Buffer(Protocol):
    """A mutable, integer-indexed buffer of numbers.

    Satisfied by both a plain ``list`` (the in-process path) and a
    :class:`multiprocessing.Array` (the forked path). Neither is nominally a
    ``MutableSequence``, and ``Sequence`` would forbid the writes, so the shape is
    stated structurally instead.
    """

    def __getitem__(self, index: int) -> float: ...

    def __setitem__(self, index: int, value: float) -> None: ...


# Cumulative milliseconds, indexed by player position within the game.
_ACCT_MOVE = (0, 1)
_ACCT_BUILD = (2, 3)
_ACCT_SLOTS = 4

# Progress flags.
_ST_PHASE, _ST_ACTIVE, _ST_MOVES = 0, 1, 2
_ST_SLOTS = 3

_PHASE_BUILD, _PHASE_PLAY, _PHASE_DONE = 0, 1, 2


def _fork_context() -> ForkContext | None:
    """Return a ``fork`` context, or ``None`` where forking is unavailable.

    Only ``fork`` is used. Under ``spawn`` the child would have to unpickle the
    player class, which lives in a synthetic module created by the manifest loader
    and does not exist in a fresh interpreter — so every game would forfeit and the
    blame would land on the bot. Falling back to an in-process soft budget is
    honest; silently blaming players is not.
    """
    try:
        return mp.get_context("fork")
    except ValueError:  # pragma: no cover - non-fork platforms
        return None


# --------------------------------------------------------------------------- #
# Data structures                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class MoveRecord:
    """One move played in a game.

    Retained only so the runner can aggregate timing; it is never serialized.

    Attributes:
        player: name of the player that moved.
        state_before: board seen by the player before moving.
        move: the node played, or ``None`` if the player forfeited instead of
            moving.
        elapsed_ms: wall-clock time the player took, in milliseconds.
    """

    player: str
    state_before: State
    move: Move | None
    elapsed_ms: float


#: Every value :attr:`MatchResult.result` may take.
RESULTS = (
    "normal",
    "forfeit_timeout",
    "forfeit_illegal",
    "forfeit_error",
    "forfeit_build_timeout",
    "forfeit_build_error",
)


@dataclass
class MatchResult:
    """Outcome of a single game between two players.

    Attributes:
        player_first: name of the player that moved first.
        player_second: name of the player that moved second.
        start_state: graph the game started from.
        scores: ``(first, second)`` points scored in this game, in seat order —
            by seat rather than by name, so two same-named players cannot
            collide. On a forfeit the offender scores 0 and the opponent the
            maximum (see the module docstring).
        result: how the game ended; one of :data:`RESULTS`.
        forfeiter: name of the player that forfeited, or ``""`` for a normal game.
        moves: the moves played, in order.
        detail: human-readable explanation, populated on forfeits.
        spent_ms: total thinking time per player name. Recoverable even when a
            hang lost the per-move detail, which is why it is separate from
            ``moves``.
        build_ms: time spent building each player, by name.
    """

    player_first: str
    player_second: str
    start_state: State
    scores: tuple[int, int]
    result: str
    forfeiter: str = ""
    moves: list[MoveRecord] = field(default_factory=list)
    detail: str = ""
    spent_ms: dict[str, float] = field(default_factory=dict)
    build_ms: dict[str, float] = field(default_factory=dict)

    def score_of(self, name: str) -> int:
        """Return the points ``name`` scored in this game."""
        return self.scores[0] if name == self.player_first else self.scores[1]

    @property
    def winner(self) -> str:
        """Name of the player who scored more, or ``""`` if both scored the same.

        Informational only: the tournament ranks by points, not by games won.
        """
        first, second = self.scores
        if first > second:
            return self.player_first
        if second > first:
            return self.player_second
        return ""


@dataclass
class Matchup:
    """A whole match between two players: its many games plus quick aggregates.

    Attributes:
        player_a: name of the first player of the pairing.
        player_b: name of the second player of the pairing.
        games: every game played in the match, in play order.
        phase: label describing where the match sits in the tournament (e.g.
            ``"round-robin"``, ``"Group A"``, ``"Semifinals"``).
    """

    player_a: str
    player_b: str
    games: list[MatchResult]
    phase: str = "round-robin"

    @property
    def a_points(self) -> int:
        """Points scored by :attr:`player_a` over the whole match."""
        return sum(g.score_of(self.player_a) for g in self.games)

    @property
    def b_points(self) -> int:
        """Points scored by :attr:`player_b` over the whole match."""
        return sum(g.score_of(self.player_b) for g in self.games)

    @property
    def a_wins(self) -> int:
        """Games in which :attr:`player_a` outscored its opponent."""
        return sum(1 for g in self.games if g.winner == self.player_a)

    @property
    def b_wins(self) -> int:
        """Games in which :attr:`player_b` outscored its opponent."""
        return sum(1 for g in self.games if g.winner == self.player_b)

    @property
    def draws(self) -> int:
        """Games in which both players scored the same."""
        return sum(1 for g in self.games if g.winner == "")

    @property
    def forfeits(self) -> int:
        """Games that ended in a forfeit (by either player)."""
        return sum(1 for g in self.games if g.result != "normal")

    @property
    def winner(self) -> str:
        """Name of the player who scored more points, or ``""`` if the match is tied."""
        if self.a_points > self.b_points:
            return self.player_a
        if self.b_points > self.a_points:
            return self.player_b
        return ""

    def _move_times(self, name: str) -> list[float]:
        """Return every completed-move time (ms) played by ``name`` in the match."""
        return [
            rec.elapsed_ms
            for g in self.games
            for rec in g.moves
            if rec.player == name and rec.move is not None
        ]

    def to_dict(self) -> JsonDict:
        """Return a JSON-serializable, aggregated summary of the match.

        Timing is reported as **aggregates only** — mean, standard deviation and
        maximum per player. There is deliberately no per-move array: it would grow
        the leaderboard with every game played and answers nothing the aggregates
        do not.
        """
        a_times = self._move_times(self.player_a)
        b_times = self._move_times(self.player_b)
        return {
            "player_a": self.player_a,
            "player_b": self.player_b,
            "phase": self.phase,
            "games": len(self.games),
            "a_points": self.a_points,
            "b_points": self.b_points,
            "a_wins": self.a_wins,
            "b_wins": self.b_wins,
            "draws": self.draws,
            "winner": self.winner,
            "forfeits": self.forfeits,
            "a_avg_move_ms": round(_mean(a_times), _ROUND_DIGITS),
            "b_avg_move_ms": round(_mean(b_times), _ROUND_DIGITS),
            "a_std_move_ms": round(_stdev(a_times), _ROUND_DIGITS),
            "b_std_move_ms": round(_stdev(b_times), _ROUND_DIGITS),
            "a_max_move_ms": round(max(a_times, default=0.0), _ROUND_DIGITS),
            "b_max_move_ms": round(max(b_times, default=0.0), _ROUND_DIGITS),
        }


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean of ``values`` (0.0 for an empty list)."""
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    """Return the population standard deviation of ``values``.

    Population (not sample) deviation, because the list *is* the whole population
    of moves played — nothing is being estimated. Returns 0.0 for fewer than two
    values, where spread is undefined rather than infinite.
    """
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


# --------------------------------------------------------------------------- #
# Playing one game                                                             #
# --------------------------------------------------------------------------- #

def _normalize_move(raw: object) -> Move | None:
    """Coerce whatever a player returned into a plain ``int`` node, once.

    Doing this **exactly once**, before any validation, keeps every later check
    looking at the same value. Anything with ``__index__`` (a NumPy integer, for
    instance) is accepted as the integer it stands for; ``bool`` is rejected even
    though it is an ``int`` subclass, because ``True`` is not a node.

    Returns:
        The move, or ``None`` if it is not an integer.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return int(raw)
    index = getattr(type(raw), "__index__", None)
    if index is None:
        return None
    try:
        value = index(raw)
    except Exception:  # noqa: BLE001 - a broken __index__ is just an illegal move
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _forfeit(
    specs: Sequence[PlayerSpec],
    start_state: State,
    culprit: int,
    result: str,
    detail: str,
    moves: list[MoveRecord],
    acct: _Buffer,
) -> MatchResult:
    """Build the :class:`MatchResult` for a game forfeited by player ``culprit``.

    The culprit scores 0; its opponent scores the most anyone can score on this
    graph, so meeting a broken bot never costs the innocent side.
    """
    best = game.tiles_per_player(start_state)
    return MatchResult(
        player_first=specs[0].name,
        player_second=specs[1].name,
        start_state=copy.deepcopy(start_state),
        scores=(0, best) if culprit == 0 else (best, 0),
        result=result,
        forfeiter=specs[culprit].name,
        moves=moves,
        detail=detail,
        spent_ms={s.name: float(acct[_ACCT_MOVE[i]]) for i, s in enumerate(specs)},
        build_ms={s.name: float(acct[_ACCT_BUILD[i]]) for i, s in enumerate(specs)},
    )


def _play_game(
    acct: _Buffer,
    st: _Buffer,
    specs: Sequence[PlayerSpec],
    start_state: State,
    budgets: Budgets,
) -> MatchResult:
    """Build both players and play one game to completion.

    This is the single game loop: the forked child runs it, and so does the
    in-process fallback. ``acct`` and ``st`` are the shared-progress arrays — plain
    lists in-process, :class:`multiprocessing.Array` in a child — written *before*
    entering player code so the parent can attribute a hang.

    Never raises on player misbehaviour: anything a player does becomes a forfeit.
    """
    players: list[Player] = []
    st[_ST_PHASE] = _PHASE_BUILD

    for i, spec in enumerate(specs):
        st[_ST_ACTIVE] = i
        t0 = time.perf_counter()
        try:
            player = spec.cls.create(seed=spec.seed)
        except BaseException as exc:  # noqa: BLE001 - any failure becomes a forfeit
            acct[_ACCT_BUILD[i]] = (time.perf_counter() - t0) * _MS_PER_SECOND
            return _forfeit(
                specs, start_state, i, "forfeit_build_error",
                f"{spec.name} raised while being created: {exc!r}", [], acct,
            )
        elapsed = (time.perf_counter() - t0) * _MS_PER_SECOND
        acct[_ACCT_BUILD[i]] = elapsed
        if budgets.build_ms is not None and elapsed > budgets.build_ms:
            return _forfeit(
                specs, start_state, i, "forfeit_build_timeout",
                f"{spec.name} took {elapsed:.0f} ms to build, over {budgets.build_ms} ms",
                [], acct,
            )
        # The spec owns the display name; a player may not rename itself into (or
        # out of) the standings.
        player.name = spec.name
        players.append(player)

    st[_ST_PHASE] = _PHASE_PLAY
    state: State = copy.deepcopy(start_state)
    moves: list[MoveRecord] = []
    turn = 0

    while not game.is_terminal(state):
        st[_ST_ACTIVE] = turn
        name = specs[turn].name
        t0 = time.perf_counter()
        try:
            # A fresh deep copy every move: the player now lives for the whole
            # game, so mutating the board in place — or the edge list it shares
            # with every later state — would corrupt the game, not a throwaway.
            raw = players[turn].choose_move(copy.deepcopy(state))
        except BaseException as exc:  # noqa: BLE001 - any failure becomes a forfeit
            elapsed = (time.perf_counter() - t0) * _MS_PER_SECOND
            acct[_ACCT_MOVE[turn]] += elapsed
            moves.append(MoveRecord(name, state, None, elapsed))
            return _forfeit(
                specs, start_state, turn, "forfeit_error",
                f"{name} raised: {exc!r}", moves, acct,
            )

        elapsed = (time.perf_counter() - t0) * _MS_PER_SECOND
        acct[_ACCT_MOVE[turn]] += elapsed
        st[_ST_MOVES] += 1
        move = _normalize_move(raw)

        # The clock is checked first: it is the harder constraint, and it is the
        # one thing we measured rather than inspected.
        if budgets.game_ms is not None and acct[_ACCT_MOVE[turn]] > budgets.game_ms:
            moves.append(MoveRecord(name, state, None, elapsed))
            return _forfeit(
                specs, start_state, turn, "forfeit_timeout",
                f"{name} used {acct[_ACCT_MOVE[turn]]:.0f} ms of its "
                f"{budgets.game_ms} ms game budget",
                moves, acct,
            )

        if move is None or not game.is_legal(state, move):
            moves.append(MoveRecord(name, state, None, elapsed))
            return _forfeit(
                specs, start_state, turn, "forfeit_illegal",
                f"{name} returned illegal move {raw!r}; the free nodes were "
                f"{game.free_nodes(state)}",
                moves, acct,
            )

        # States are never mutated (apply_move builds a new one, and the player
        # only ever saw a copy), so the record can keep this one as is.
        moves.append(MoveRecord(name, state, move, elapsed))
        state = game.apply_move(state, move)
        turn = 1 - turn

    st[_ST_PHASE] = _PHASE_DONE
    return MatchResult(
        player_first=specs[0].name,
        player_second=specs[1].name,
        start_state=copy.deepcopy(start_state),
        scores=game.scores(state),
        result="normal",
        moves=moves,
        spent_ms={s.name: float(acct[_ACCT_MOVE[i]]) for i, s in enumerate(specs)},
        build_ms={s.name: float(acct[_ACCT_BUILD[i]]) for i, s in enumerate(specs)},
    )


def _game_worker(  # pragma: no cover - runs only in a child process
    result_queue: mp.Queue,
    acct: _Buffer,
    st: _Buffer,
    specs: Sequence[PlayerSpec],
    start_state: State,
    budgets: Budgets,
) -> None:
    """Child entry point: play one game and hand the result back."""
    try:
        result_queue.put(_play_game(acct, st, specs, start_state, budgets))
    except BaseException as exc:  # noqa: BLE001 - never die silently
        result_queue.put(("__crashed__", repr(exc)))


def _verdict_after_kill(
    specs: Sequence[PlayerSpec],
    start_state: State,
    acct: _Buffer,
    st: _Buffer,
    budgets: Budgets,
    detail_suffix: str = "",
) -> MatchResult:
    """Decide a game whose child had to be killed, from shared progress alone.

    The child records its phase and the active player *before* calling into player
    code, so the culprit is a fact rather than a guess:

    * still building -> the active player's constructor hung;
    * playing, and someone is over the game budget -> that player (the larger
      overage wins, for the rare case where both are over);
    * playing, nobody over budget -> the active player stopped responding
      mid-move. Its own time was never added to the clock, which is exactly why
      the fallback has to be the *active* player rather than the clocks.
    """
    phase = int(st[_ST_PHASE])
    raw_active = int(st[_ST_ACTIVE])
    active = raw_active if raw_active in (0, 1) else 0

    if phase == _PHASE_BUILD:
        return _forfeit(
            specs, start_state, active, "forfeit_build_timeout",
            f"{specs[active].name} did not finish being created{detail_suffix}",
            [], acct,
        )

    if budgets.game_ms is not None:
        over = [i for i in (0, 1) if acct[_ACCT_MOVE[i]] > budgets.game_ms]
        if over:
            culprit = max(over, key=lambda i: acct[_ACCT_MOVE[i]])
            return _forfeit(
                specs, start_state, culprit, "forfeit_timeout",
                f"{specs[culprit].name} used "
                f"{acct[_ACCT_MOVE[culprit]]:.0f} ms of its {budgets.game_ms} ms "
                f"game budget{detail_suffix}",
                [], acct,
            )

    return _forfeit(
        specs, start_state, active, "forfeit_timeout",
        f"{specs[active].name} stopped responding after {int(st[_ST_MOVES])} "
        f"move(s) in the game{detail_suffix}",
        [], acct,
    )


def play_match(
    first: Player | PlayerSpec,
    second: Player | PlayerSpec,
    start_state: State,
    budgets: Budgets | None = None,
    *,
    use_subprocess: bool = True,
) -> MatchResult:
    """Play one game; ``first`` moves first. Never raises on bot misbehavior.

    Both players score the tiles they placed next to the black hole. Exceeding a
    budget, raising, hanging, or returning an illegal move all make the offending
    player forfeit: it scores 0 and its opponent scores the maximum.

    Args:
        first: the player to move first (an instance or a :class:`PlayerSpec`).
        second: the other player.
        start_state: the graph to play on (every node free).
        budgets: time budgets; defaults to :class:`Budgets`. Pass
            :data:`UNLIMITED` to enforce nothing.
        use_subprocess: play the game in a forked child so a hung player can be
            killed. ``False`` runs in-process with soft budgets — faster, but an
            infinite loop cannot be interrupted.

    Returns:
        The completed :class:`MatchResult`.
    """
    specs = (_as_spec(first), _as_spec(second))
    budgets = Budgets() if budgets is None else budgets
    deadline_ms = budgets.deadline_ms
    ctx = _fork_context() if use_subprocess else None

    if ctx is None or deadline_ms is None:
        # Soft path: nothing to kill, or nothing to kill it with.
        return _play_game([0.0] * _ACCT_SLOTS, [0] * _ST_SLOTS, specs, start_state, budgets)

    acct = ctx.Array("d", [0.0] * _ACCT_SLOTS, lock=False)
    st = ctx.Array("i", [0] * _ST_SLOTS, lock=False)
    result_queue: mp.Queue = ctx.Queue()
    proc = ctx.Process(
        target=_game_worker,
        args=(result_queue, acct, st, specs, start_state, budgets),
        daemon=True,
    )
    proc.start()
    try:
        # Read *before* joining. A child cannot exit until its queued payload has
        # been drained, so joining first can deadlock on a large result.
        payload = result_queue.get(timeout=deadline_ms / _MS_PER_SECOND)
    except queue_mod.Empty:
        payload = None

    if payload is None:
        proc.terminate()
        proc.join()
        return _verdict_after_kill(specs, start_state, acct, st, budgets)

    proc.join(timeout=_COLLECT_GRACE_S)
    if proc.is_alive():  # pragma: no cover - defensive
        proc.terminate()
        proc.join()

    if isinstance(payload, tuple):  # pragma: no cover - the worker itself failed
        return _verdict_after_kill(
            specs, start_state, acct, st, budgets,
            detail_suffix=f" (runner error: {payload[1]})",
        )
    return payload


def play_matchup(
    a: Player | PlayerSpec,
    b: Player | PlayerSpec,
    starting_states: list[State],
    repetitions: int,
    budgets: Budgets | None = None,
    *,
    use_subprocess: bool = True,
    phase: str = "round-robin",
) -> Matchup:
    """Play a full match between ``a`` and ``b`` and return its :class:`Matchup`.

    The match plays, for every graph in ``starting_states`` and for each player
    going first once, ``repetitions`` games — so ``len(starting_states) * 2 *
    repetitions`` games in total. Alternating the first mover matters because
    moving first or second changes how many tiles each turn places, and when.

    Args:
        a: one player of the pairing.
        b: the other player of the pairing.
        starting_states: graphs to play on.
        repetitions: games per (graph, first-mover) combination.
        budgets: time budgets; defaults to :class:`Budgets`.
        use_subprocess: play each game in a forked child (hard kill available).
        phase: label recorded on the resulting :class:`Matchup`.

    Returns:
        The completed :class:`Matchup`.
    """
    spec_a, spec_b = _as_spec(a), _as_spec(b)
    games: list[MatchResult] = []
    # Counted across the whole match, so every game of it gets a distinct seed.
    game_index = 0
    for state in starting_states:
        for first, second in ((spec_a, spec_b), (spec_b, spec_a)):
            for _ in range(repetitions):
                games.append(
                    play_match(
                        _seed_for_game(first, game_index),
                        _seed_for_game(second, game_index),
                        state, budgets,
                        use_subprocess=use_subprocess,
                    )
                )
                game_index += 1
    return Matchup(spec_a.name, spec_b.name, games, phase)


# --------------------------------------------------------------------------- #
# Roster construction                                                          #
# --------------------------------------------------------------------------- #

def copies_for(registry: Registry) -> dict[str, int]:
    """Return ``player name -> roster copies`` for everything in ``registry``.

    How many copies a player is entered with is a **tournament** decision, not a
    property of the bot, so it is taken here and not declared by the player class.
    It follows the manifest that admitted the player: the reference ladder gets
    :data:`BUILTIN_PLAYER_COPIES`, a submission gets :data:`CUSTOM_PLAYER_COPIES`.

    Feed the result to :func:`build_roster`.
    """
    return {
        name: BUILTIN_PLAYER_COPIES if registry.origin(name) == BUILTIN else CUSTOM_PLAYER_COPIES
        for name in registry.names()
    }


def build_roster(
    players: Sequence[Player | PlayerSpec],
    repetition: int = 1,
    *,
    copies: Mapping[str, int] | None = None,
) -> list[PlayerSpec]:
    """Expand each player *kind* into seeded specifications, one per copy.

    A round-robin never lets a player face itself, so to make a *kind* of bot
    compete against its own kind we enter several independent copies of it, to be
    built through :meth:`~blackholearena.player.Player.create` with the seeds
    ``0, 1, ..., n - 1``. Every player accepts a seed, so no inspection of
    constructor signatures is needed; a deterministic bot ignores it but is still
    duplicated so its kind plays itself.

    Each copy is named ``"<name>_<seed>"`` so the copies stay distinct in the
    standings. The web app renders that suffix as a subscript.

    Args:
        players: one entry per kind (typically ``registry.all()``).
        copies: per-kind counts, normally from :func:`copies_for`. This is how a
            real run decides; pass it and ``repetition`` never applies.
        repetition: copies for a kind ``copies`` does not mention (``>= 1``).
            Deliberately a plain ``1`` and **not** one of the policy constants:
            a default that tracked :data:`CUSTOM_PLAYER_COPIES` would silently
            change what every other caller gets whenever that value is tuned.

    Returns:
        One specification per copy, in the order the kinds were given.

    Raises:
        ValueError: if ``repetition`` or any value in ``copies`` is less than 1.
    """
    if repetition < 1:
        raise ValueError(f"repetition must be >= 1, got {repetition}")
    for name, count in (copies or {}).items():
        if count < 1:
            raise ValueError(f"copies[{name!r}] must be >= 1, got {count}")
    roster: list[PlayerSpec] = []
    for entry in players:
        spec = _as_spec(entry)
        base_name = spec.cls.get_name()
        for seed in range((copies or {}).get(base_name, repetition)):
            roster.append(PlayerSpec(cls=spec.cls, seed=seed, name=f"{base_name}_{seed}"))
    return roster


def _copies_of(roster: Sequence[PlayerSpec], base_name: str) -> list[PlayerSpec]:
    """Return the roster entries that are copies of the kind called ``base_name``."""
    return [s for s in roster if s.cls.get_name() == base_name]


# --------------------------------------------------------------------------- #
# Per-player statistics                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class _HeadToHead:
    """One player's record against one opponent.

    Attributes:
        points: points scored against this opponent.
        points_against: points this opponent scored in the same games.
        wins: games in which the player outscored this opponent.
        draws: games in which both scored the same.
        losses: games in which this opponent scored more.
    """

    points: int = 0
    points_against: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0

    @property
    def games(self) -> int:
        """Games played against this opponent."""
        return self.wins + self.draws + self.losses


@dataclass
class _Stats:
    """Per-player running tallies used to build the standings and player stats.

    Attributes:
        points: total points scored over every game — the ranking criterion.
        points_against: total points the opponents scored in the same games.
        wins: games in which the player outscored its opponent (informational).
        draws: games in which both players scored the same (informational).
        losses: games in which the opponent scored more (informational).
        forfeits: games this player forfeited.
        move_ms: elapsed time of every completed move, in milliseconds.
        build_ms: time taken to build this player, once per game played.
        spent_ms: total thinking time, including games whose per-move detail was
            lost to a kill.
        opponents: head-to-head ``opponent name -> record`` breakdown.
        elo: current Elo rating, updated as if the game were zero-sum.
    """

    points: int = 0
    points_against: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    forfeits: int = 0
    move_ms: list[float] = field(default_factory=list)
    build_ms: list[float] = field(default_factory=list)
    spent_ms: float = 0.0
    opponents: dict[str, _HeadToHead] = field(default_factory=dict)
    elo: float = DEFAULT_INITIAL_RATING

    @property
    def games(self) -> int:
        """Total games played."""
        return self.wins + self.draws + self.losses

    @property
    def avg_points(self) -> float:
        """Mean points per game (0.0 if none played)."""
        return self.points / self.games if self.games else 0.0

    @property
    def avg_move_ms(self) -> float:
        """Mean time per completed move in milliseconds (0.0 if none)."""
        return _mean(self.move_ms)

    @property
    def std_move_ms(self) -> float:
        """Population standard deviation of completed move times, in ms."""
        return _stdev(self.move_ms)

    @property
    def max_move_ms(self) -> float:
        """Slowest single completed move in milliseconds (0.0 if none)."""
        return max(self.move_ms, default=0.0)

    @property
    def avg_build_ms(self) -> float:
        """Mean time to build this player, in milliseconds."""
        return _mean(self.build_ms)

    @property
    def std_build_ms(self) -> float:
        """Population standard deviation of build times, in ms."""
        return _stdev(self.build_ms)

    @property
    def max_build_ms(self) -> float:
        """Slowest single build, in milliseconds."""
        return max(self.build_ms, default=0.0)

    @property
    def win_rate(self) -> float:
        """Fraction of games in which it outscored the opponent (0.0 if none)."""
        return self.wins / self.games if self.games else 0.0


def _new_stats(names: list[str]) -> dict[str, _Stats]:
    """Return a fresh ``name -> _Stats`` map for every name in ``names``."""
    return {name: _Stats() for name in names}


def _tally_game(stats: dict[str, _Stats], result: MatchResult) -> None:
    """Fold one game ``result`` into the running ``stats`` (mutates ``stats``).

    A game whose child was killed contributes no per-move samples, because none
    were ever reported — but its total thinking and build times survive in shared
    memory, so they are still counted.
    """
    for rec in result.moves:
        if rec.move is not None and rec.player in stats:
            stats[rec.player].move_ms.append(rec.elapsed_ms)
    for name, value in result.build_ms.items():
        if name in stats:
            stats[name].build_ms.append(value)
    for name, value in result.spent_ms.items():
        if name in stats:
            stats[name].spent_ms += value
    names = (result.player_first, result.player_second)
    for seat, name in enumerate(names):
        rival = names[1 - seat]
        mine, theirs = result.scores[seat], result.scores[1 - seat]
        s = stats[name]
        h2h = s.opponents.setdefault(rival, _HeadToHead())
        s.points += mine
        s.points_against += theirs
        h2h.points += mine
        h2h.points_against += theirs
        if mine > theirs:
            s.wins += 1
            h2h.wins += 1
        elif mine < theirs:
            s.losses += 1
            h2h.losses += 1
        else:
            s.draws += 1
            h2h.draws += 1
    if result.forfeiter in stats:
        stats[result.forfeiter].forfeits += 1


def _elo_result(result: MatchResult) -> float:
    """Return the first player's Elo result, treating the game as zero-sum.

    Whoever scored more won: ``1.0`` for a win, ``0.0`` for a loss and ``0.5``
    for a draw. The margin is deliberately ignored — that is what the points are
    for; Elo answers "who beats whom".
    """
    a, b = result.scores
    return 1.0 if a > b else 0.0 if a < b else 0.5


def _apply_elo(stats: dict[str, _Stats], games: list[MatchResult]) -> None:
    """Update every player's Elo rating over ``games`` in play order."""
    for result in games:
        a, b = result.player_first, result.player_second
        stats[a].elo, stats[b].elo = updated_ratings(
            stats[a].elo, stats[b].elo, _elo_result(result)
        )


# --------------------------------------------------------------------------- #
# Result assembly (standings, player stats, totals)                            #
# --------------------------------------------------------------------------- #

def _rank_names(stats: dict[str, _Stats], *, use_elo: bool) -> list[str]:
    """Return the player names best-first under the active ranking rule.

    League with Elo ranks by rating; otherwise by total points. Both fall back to
    fewer forfeits, then the name. The name tie-break makes the order fully
    deterministic; average move time is deliberately *not* used, because a player
    that forfeits every move records no move times and would win that tie-break by
    having done nothing.
    """
    def key(name: str) -> tuple[float, int, str]:
        s = stats[name]
        primary = -s.elo if use_elo else float(-s.points)
        return (primary, s.forfeits, name)

    return sorted(stats, key=key)


def _standings(stats: dict[str, _Stats], *, use_elo: bool) -> list[JsonDict]:
    """Build the ranked, JSON-serializable classification (right-column data)."""
    standings: list[JsonDict] = []
    for rank, name in enumerate(_rank_names(stats, use_elo=use_elo), start=1):
        s = stats[name]
        row: JsonDict = {
            "rank": rank,
            "player": name,
            "points": s.points,
            "avg_points": round(s.avg_points, _ROUND_DIGITS),
            "points_against": s.points_against,
            "wins": s.wins,
            "draws": s.draws,
            "losses": s.losses,
            "forfeits": s.forfeits,
            "games": s.games,
            "win_rate": round(s.win_rate, _ROUND_DIGITS),
            "avg_move_ms": round(s.avg_move_ms, _ROUND_DIGITS),
            "std_move_ms": round(s.std_move_ms, _ROUND_DIGITS),
            "max_move_ms": round(s.max_move_ms, _ROUND_DIGITS),
            "elo": round(s.elo, _ROUND_DIGITS),
        }
        standings.append(row)
    return standings


def _player_stats(stats: dict[str, _Stats], *, use_elo: bool) -> list[JsonDict]:
    """Build the detailed per-player stats block (with head-to-head breakdown)."""
    rows: list[JsonDict] = []
    for name in _rank_names(stats, use_elo=use_elo):
        s = stats[name]
        opponents = [
            {
                "opponent": opp,
                "games": h.games,
                "points": h.points,
                "points_against": h.points_against,
                "wins": h.wins,
                "draws": h.draws,
                "losses": h.losses,
            }
            for opp, h in sorted(s.opponents.items())
        ]
        row: JsonDict = {
            "player": name,
            "points": s.points,
            "avg_points": round(s.avg_points, _ROUND_DIGITS),
            "points_against": s.points_against,
            "wins": s.wins,
            "draws": s.draws,
            "losses": s.losses,
            "forfeits": s.forfeits,
            "games": s.games,
            "win_rate": round(s.win_rate, _ROUND_DIGITS),
            "moves_made": len(s.move_ms),
            "avg_move_ms": round(s.avg_move_ms, _ROUND_DIGITS),
            "std_move_ms": round(s.std_move_ms, _ROUND_DIGITS),
            "max_move_ms": round(s.max_move_ms, _ROUND_DIGITS),
            "total_move_ms": round(s.spent_ms, _ROUND_DIGITS),
            "avg_build_ms": round(s.avg_build_ms, _ROUND_DIGITS),
            "std_build_ms": round(s.std_build_ms, _ROUND_DIGITS),
            "max_build_ms": round(s.max_build_ms, _ROUND_DIGITS),
            "opponents": opponents,
            "elo": round(s.elo, _ROUND_DIGITS),
        }
        rows.append(row)
    return rows


def _totals(
    all_games: list[MatchResult], num_matches: int, num_players: int
) -> JsonDict:
    """Build the overview totals block for the whole tournament."""
    total_moves = sum(len(g.moves) for g in all_games)
    total_time_ms = sum(sum(g.spent_ms.values()) for g in all_games)
    total_build_ms = sum(sum(g.build_ms.values()) for g in all_games)
    forfeits = sum(1 for g in all_games if g.result != "normal")
    longest = max((len(g.moves) for g in all_games), default=0)
    total_points = sum(sum(g.scores) for g in all_games)
    return {
        "players": num_players,
        "matches": num_matches,
        "games": len(all_games),
        "total_points": total_points,
        "avg_game_points": round(
            _mean([float(sum(g.scores)) for g in all_games]), _ROUND_DIGITS
        ),
        "total_moves": total_moves,
        "avg_game_moves": round(_mean([float(len(g.moves)) for g in all_games]), _ROUND_DIGITS),
        "longest_game_moves": longest,
        "forfeits": forfeits,
        "total_move_time_ms": round(total_time_ms, _ROUND_DIGITS),
        "total_build_time_ms": round(total_build_ms, _ROUND_DIGITS),
    }


# --------------------------------------------------------------------------- #
# Format: round-robin (used by "simple" and "league")                          #
# --------------------------------------------------------------------------- #

def _round_robin(
    roster: list[PlayerSpec],
    starting_states: list[State],
    repetitions: int,
    budgets: Budgets,
    *,
    use_subprocess: bool,
    phase: str = "round-robin",
) -> list[Matchup]:
    """Play every unordered pair once and return the matchups, in pair order."""
    matchups: list[Matchup] = []
    for i, a in enumerate(roster):
        for b in roster[i + 1:]:
            matchups.append(
                play_matchup(
                    a, b, starting_states, repetitions, budgets,
                    use_subprocess=use_subprocess, phase=phase,
                )
            )
    return matchups


# --------------------------------------------------------------------------- #
# Format: championship (group phase + single-elimination bracket)              #
# --------------------------------------------------------------------------- #

def _group_name(index: int) -> str:
    """Return a human-friendly group name (``"Group A"``, ``"Group B"``, ...)."""
    return f"Group {chr(ord('A') + index)}" if index < 26 else f"Group {index + 1}"


def _round_name(num_participants: int) -> str:
    """Return the conventional name of a knockout round of ``num_participants``."""
    known = {2: "Final", 4: "Semifinals", 8: "Quarterfinals", 16: "Round of 16"}
    return known.get(num_participants, f"Round of {num_participants}")


def _group_table(
    members: list[str], stats: dict[str, _Stats]
) -> list[JsonDict]:
    """Rank a group's members by points and return a JSON-serializable table."""
    ordered = sorted(
        members,
        key=lambda n: (-stats[n].points, stats[n].forfeits, n),
    )
    return [
        {
            "rank": rank,
            "player": name,
            "points": stats[name].points,
            "wins": stats[name].wins,
            "draws": stats[name].draws,
            "losses": stats[name].losses,
            "forfeits": stats[name].forfeits,
            "games": stats[name].games,
            "avg_move_ms": round(stats[name].avg_move_ms, _ROUND_DIGITS),
        }
        for rank, name in enumerate(ordered, start=1)
    ]


def _seed_bracket_pairs(seeds: list[str]) -> list[tuple[str, str | None]]:
    """Pair a seed-ordered (best-first) list into first-round ties with byes.

    The bracket is padded to the next power of two; the top seeds receive byes
    (``None`` opponents). Seed ``i`` is paired with seed ``size - 1 - i`` so the
    strongest meets the weakest, as in standard single-elimination seeding.

    Called afresh for every round. That looks like a bug — it re-seeds winners
    rather than pairing adjacent ones — but ``winners`` stays in bracket-position
    order, so the ``size - 1 - i`` pairing reproduces exactly the standard fixed
    bracket, byes included.
    """
    size = 1
    while size < len(seeds):
        size *= 2
    pairs: list[tuple[str, str | None]] = []
    for i in range(size // 2):
        high = seeds[i] if i < len(seeds) else None
        low_index = size - 1 - i
        low = seeds[low_index] if low_index < len(seeds) else None
        # `high` is always the better (or equal) seed; a missing `high` cannot
        # happen for the top half, so treat `low` as the bye opponent.
        if high is None:  # pragma: no cover - only if seeds is empty
            continue
        pairs.append((high, low))
    return pairs


def _run_championship(
    roster: list[PlayerSpec],
    starting_states: list[State],
    repetitions: int,
    budgets: Budgets,
    *,
    use_subprocess: bool,
    group_size: int,
    advance_per_group: int,
) -> tuple[list[Matchup], JsonDict]:
    """Run a group phase then a knockout bracket.

    Returns:
        ``(matchups, structure)`` where ``matchups`` is every match played (group
        and knockout) and ``structure`` is the JSON-serializable championship
        layout (groups, their tables and advancers, and the bracket rounds with
        the eventual champion) for the page to draw.

    Raises:
        ValueError: if ``group_size`` or ``advance_per_group`` is less than 1.
    """
    if group_size < 1:
        raise ValueError(f"group_size must be >= 1, got {group_size}")
    if advance_per_group < 1:
        raise ValueError(f"advance_per_group must be >= 1, got {advance_per_group}")

    by_name = {spec.name: spec for spec in roster}
    stats = _new_stats(list(by_name))

    # --- Group phase --------------------------------------------------------
    # Deal players round-robin into groups (rather than slicing sequential
    # chunks) so kinds spread out and no group is stacked with the strongest.
    num_groups = max(1, (len(roster) + group_size - 1) // group_size)
    groups: list[list[PlayerSpec]] = [[] for _ in range(num_groups)]
    for index, spec in enumerate(roster):
        groups[index % num_groups].append(spec)
    matchups: list[Matchup] = []
    group_blocks: list[JsonDict] = []
    seeds_by_place: list[list[str]] = [[] for _ in range(advance_per_group)]

    for g_index, members in enumerate(groups):
        name = _group_name(g_index)
        group_matchups = _round_robin(
            members, starting_states, repetitions, budgets,
            use_subprocess=use_subprocess, phase=name,
        )
        matchups.extend(group_matchups)
        for mu in group_matchups:
            for gm in mu.games:
                _tally_game(stats, gm)
        table = _group_table([spec.name for spec in members], stats)
        advancers = [row["player"] for row in table[:advance_per_group]]
        group_blocks.append(
            {"name": name, "members": [spec.name for spec in members],
             "table": table, "advance": advancers}
        )
        # Collect advancers by finishing place so seeding favors group winners.
        for place, player_name in enumerate(advancers):
            seeds_by_place[place].append(str(player_name))

    # Seed order: every 1st place (in group order), then every 2nd place, ...
    seeds: list[str] = [name for place in seeds_by_place for name in place]

    # --- Knockout bracket ---------------------------------------------------
    rounds: list[JsonDict] = []
    champion = seeds[0] if seeds else ""
    current = seeds
    while len(current) > 1:
        round_name = _round_name(len(current))
        pairs = _seed_bracket_pairs(current)
        ties: list[JsonDict] = []
        winners: list[str] = []
        for high, low in pairs:
            if low is None:  # bye: the seed advances unopposed
                ties.append(
                    {"a": high, "b": None, "a_points": 0, "b_points": 0, "winner": high}
                )
                winners.append(high)
                continue
            mu = play_matchup(
                by_name[high], by_name[low], starting_states, repetitions,
                budgets, use_subprocess=use_subprocess, phase=round_name,
            )
            matchups.append(mu)
            # More points over the match advances; a tie goes to the higher seed.
            winner = mu.winner or high
            ties.append(
                {"a": high, "b": low, "a_points": mu.a_points,
                 "b_points": mu.b_points, "winner": winner}
            )
            winners.append(winner)
        rounds.append({"name": round_name, "ties": ties})
        champion = winners[0] if len(winners) == 1 else champion
        current = winners

    structure: JsonDict = {
        "type": "championship",
        "group_size": group_size,
        "advance_per_group": advance_per_group,
        "groups": group_blocks,
        "bracket": {"rounds": rounds, "champion": champion},
    }
    return matchups, structure


# --------------------------------------------------------------------------- #
# Top-level tournament runner                                                  #
# --------------------------------------------------------------------------- #

def validate_starting_states(states: Sequence[Mapping[str, Any]]) -> list[State]:
    """Return ``states`` as clean starting graphs, or explain why they are unplayable.

    Every starting state must be a fresh game — a valid graph with every node
    free — so that both players get the same ``N`` turns and the forfeit score
    (the maximum a player can score) is well defined. Build them with
    :func:`blackholearena.game.new_game` or :mod:`blackholearena.graphs`.

    Always returns fresh states, so callers cannot alias what they passed in.

    Raises:
        ValueError: if no state is given, a state is not a mapping with
            ``edges``, ``owner`` and ``tiles``, its graph is invalid (see
            :func:`~blackholearena.game.validate_graph`), or a node is not free.
    """
    if not states:
        raise ValueError("at least one starting graph is required")
    cleaned: list[State] = []
    for state in states:
        if not isinstance(state, Mapping) or not {"edges", "owner", "tiles"} <= set(state):
            raise ValueError(
                f"a starting state must be a mapping with edges, owner and tiles, got {state!r}"
            )
        owner = list(state["owner"])
        if any(o is not None for o in owner) or any(state["tiles"]):
            raise ValueError("a starting state must have every node free")
        cleaned.append(game.new_game(len(owner), state["edges"]))
    return cleaned


def _player_directory(specs: Sequence[PlayerSpec]) -> list[JsonDict]:
    """Return one identity entry per player *kind* in the roster.

    Keyed by the kind's own name (``"hard"``), not by roster entry (``"hard_0"``),
    so this stays O(kinds) rather than O(roster) and nothing is repeated on every
    standings row. The scoreboard strips the ``_<n>`` suffix to look a player up.
    """
    seen: dict[str, JsonDict] = {}
    for spec in specs:
        name = spec.cls.get_name()
        if name not in seen:
            seen[name] = {
                "name": name,
                "icon": spec.cls.get_icon(),
                "authors": list(spec.cls.get_authors()),
                "description": spec.cls.get_description(),
            }
    return [seen[k] for k in sorted(seen)]


def run_tournament(
    roster: Sequence[Player | PlayerSpec],
    *,
    mode: str = "simple",
    starting_states: list[State] | None = None,
    repetitions: int = DEFAULT_REPETITIONS,
    budgets: Budgets | None = None,
    elo: bool = True,
    use_subprocess: bool = True,
    group_size: int = DEFAULT_GROUP_SIZE,
    advance_per_group: int = DEFAULT_ADVANCE_PER_GROUP,
    now: Callable[[], datetime] | None = None,
    extra_config: JsonDict | None = None,
) -> JsonDict:
    """Run a tournament in the requested ``mode`` and return the results dict.

    Args:
        roster: the competitors — :class:`PlayerSpec` objects (typically
            :func:`build_roster` output) or plain players, which are coerced.
        mode: one of :data:`TOURNAMENT_MODES` — ``"simple"``, ``"league"`` or
            ``"championship"``.
        starting_states: graphs to play on; defaults to
            :data:`DEFAULT_STARTING_STATES`.
        repetitions: games per (graph, first-mover) combination in each match.
        budgets: time budgets; defaults to :class:`Budgets`. Pass
            :data:`UNLIMITED` to enforce nothing.
        elo: rank by Elo rating instead of points (only in ``"league"`` mode).
            Elo ratings are computed and reported in every mode regardless.
        use_subprocess: play each game in a forked child. Set ``False`` for a
            fast, soft-budget, single-process run (handy in tests).
        group_size: players per group in the championship group phase.
        advance_per_group: players advancing from each championship group.
        now: injectable clock for deterministic ``generated_at`` timestamps.
        extra_config: extra key/values merged into the result ``config`` block.

    Returns:
        A JSON-serializable results dict with ``config``, ``standings``,
        ``matches`` (aggregated), ``player_stats``, ``totals`` and a mode-specific
        ``structure`` block.

    Raises:
        ValueError: if ``mode`` is unknown, the roster is empty, player names are
            not unique, ``repetitions`` is less than 1, or a graph is unplayable.
    """
    if mode not in TOURNAMENT_MODES:
        raise ValueError(f"Unknown tournament mode {mode!r}; expected one of {TOURNAMENT_MODES}")
    if repetitions < 1:
        raise ValueError(f"repetitions must be >= 1, got {repetitions}")

    specs = [_as_spec(entry) for entry in roster]
    if not specs:
        raise ValueError("the roster is empty; there is nothing to play")
    names = [s.name for s in specs]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        # Two entries sharing a name would collapse into one standings row, with
        # both its wins and its losses credited to the same entity.
        raise ValueError(f"roster names must be unique; duplicated: {duplicates}")

    starting_states = validate_starting_states(
        DEFAULT_STARTING_STATES if starting_states is None else starting_states
    )
    budgets = Budgets() if budgets is None else budgets
    now = now or (lambda: datetime.now(timezone.utc))
    use_elo = elo and mode == "league"

    if mode == "championship":
        matchups, structure = _run_championship(
            specs, starting_states, repetitions, budgets,
            use_subprocess=use_subprocess,
            group_size=group_size, advance_per_group=advance_per_group,
        )
    else:
        matchups = _round_robin(
            specs, starting_states, repetitions, budgets,
            use_subprocess=use_subprocess,
        )
        structure = {"type": mode, "elo": use_elo}

    all_games = [g for mu in matchups for g in mu.games]
    stats = _new_stats(names)
    for mu in matchups:
        for g in mu.games:
            _tally_game(stats, g)
    # Always rated, so the scoreboard can compare players on Elo in every mode;
    # `use_elo` only decides whether it is the ranking criterion.
    _apply_elo(stats, all_games)

    config: JsonDict = {
        "tournament": mode,
        "graphs": [
            {"nodes": game.num_nodes(s), "edges": s["edges"]} for s in starting_states
        ],
        "repetitions": repetitions,
        "game_budget_ms": budgets.game_ms,
        "build_budget_ms": budgets.build_ms,
        "elo": use_elo,
        "hard_timeout": use_subprocess and _fork_context() is not None,
    }
    if extra_config:
        config.update(extra_config)

    return {
        "generated_at": now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": config,
        "players": _player_directory(specs),
        "standings": _standings(stats, use_elo=use_elo),
        "matches": [mu.to_dict() for mu in matchups],
        "player_stats": _player_stats(stats, use_elo=use_elo),
        "totals": _totals(all_games, len(matchups), len(specs)),
        "structure": structure,
    }


# --------------------------------------------------------------------------- #
# CLI entry point                                                             #
# --------------------------------------------------------------------------- #

def _parse_graph(text: str) -> State:
    """Parse a ``--graph`` value like ``"5:0-1,1-2,2-3"`` into a starting state.

    The part before ``:`` is the number of nodes; after it, comma-separated
    ``a-b`` edges.
    """
    try:
        nodes_text, _, edges_text = text.replace(" ", "").partition(":")
        nodes = int(nodes_text)
        edges = [
            [int(a), int(b)]
            for a, b in (part.split("-") for part in edges_text.split(",") if part)
        ]
    except ValueError as exc:
        raise ValueError(
            f"bad --graph {text!r}: expected NODES:A-B,C-D,... e.g. 5:0-1,1-2"
        ) from exc
    return game.new_game(nodes, edges)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the ``blackhole-tournament`` argument parser."""
    from .manifest import BUILTIN_MANIFEST, CUSTOM_MANIFEST

    parser = argparse.ArgumentParser(
        prog="blackhole-tournament", description="Run a BlackHole Arena tournament."
    )
    parser.add_argument(
        "--builtin-manifest", default=str(BUILTIN_MANIFEST),
        help="Manifest admitting the reference ladder.",
    )
    parser.add_argument(
        "--custom-manifest", default=str(CUSTOM_MANIFEST),
        help="Manifest admitting submitted players.",
    )
    parser.add_argument("--out", default="results/leaderboard.json")
    parser.add_argument(
        "--tournament", choices=TOURNAMENT_MODES, default="simple",
        help="Tournament format (default: simple).",
    )
    parser.add_argument(
        "--time-limit", type=float, default=DEFAULT_TIME_LIMIT_S,
        help="Per-player budget in seconds, for a whole game AND for building "
             f"(default: {DEFAULT_TIME_LIMIT_S}).",
    )
    parser.add_argument(
        "--game-time-limit", type=float, default=None,
        help="Override the per-player, per-game thinking budget, in seconds.",
    )
    parser.add_argument(
        "--build-time-limit", type=float, default=None,
        help="Override the per-player construction budget, in seconds.",
    )
    parser.add_argument(
        "--no-time-limit", action="store_true",
        help="Disable all budgets. Never use with untrusted players: a hung bot "
             "hangs the run.",
    )
    parser.add_argument(
        "--graph", action="append", metavar="NODES:A-B,...",
        help="A starting graph, e.g. --graph 5:0-1,1-2,2-3,3-4,4-0. Repeat for "
             "several graphs. Defaults to the built-in set.",
    )
    parser.add_argument(
        "--player-repetition", type=int, default=None,
        help="Override the number of copies for every kind, ignoring what each "
             "player declares; seeds them 0..N-1.",
    )
    parser.add_argument(
        "--repetitions", type=int, default=DEFAULT_REPETITIONS,
        help="Games per (graph, first-mover) combination in a match (default: 3).",
    )
    parser.add_argument(
        "--group-size", type=int, default=DEFAULT_GROUP_SIZE,
        help="Championship only: players per group (default: 4).",
    )
    parser.add_argument(
        "--advance-per-group", type=int, default=DEFAULT_ADVANCE_PER_GROUP,
        help="Championship only: players advancing per group (default: 2).",
    )
    parser.add_argument(
        "--elo", action=argparse.BooleanOptionalAction, default=True,
        help="Use Elo ratings for the league classification (default: on).",
    )
    parser.add_argument(
        "--no-subprocess", action="store_true",
        help="Play games in-process (soft budgets). Faster, but cannot kill a "
             "hung bot.",
    )
    return parser


def _budgets_from_args(args: argparse.Namespace) -> Budgets:
    """Turn the parsed time-limit flags into a :class:`Budgets`."""
    if args.no_time_limit:
        return UNLIMITED

    def to_ms(seconds: float, label: str) -> int:
        if seconds <= 0:
            raise ValueError(f"{label} must be greater than 0, got {seconds}")
        return max(1, round(seconds * _MS_PER_SECOND))

    shared: float = args.time_limit
    game: float | None = args.game_time_limit
    build: float | None = args.build_time_limit
    return Budgets(
        game_ms=to_ms(game if game is not None else shared, "--game-time-limit"),
        build_ms=to_ms(build if build is not None else shared, "--build-time-limit"),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: load players from the manifest, run the tournament, write results.

    Usage::

        blackhole-tournament [--out results/leaderboard.json]
                             [--tournament simple|league|championship]
                             [--time-limit 2.0] [--graph 5:0-1,1-2,...]
                             [--repetitions 3] [--player-repetition N]
                             [--no-elo] [--no-subprocess]

    Returns:
        ``0`` on success, ``1`` on a configuration or manifest error.
    """
    import json
    from pathlib import Path

    from .manifest import BUILTIN, CUSTOM, ManifestError, load_players

    args = _build_arg_parser().parse_args(argv)

    try:
        budgets = _budgets_from_args(args)
        graphs = [_parse_graph(g) for g in args.graph] if args.graph else None
        registry = load_players(
            {BUILTIN: args.builtin_manifest, CUSTOM: args.custom_manifest}
        )
        kinds = registry.all()
        if not kinds:
            # Writing an empty leaderboard here would let the tournament workflow
            # commit it over a good one.
            print(
                "error: no players loaded from the manifest; refusing to write an "
                "empty leaderboard.",
                file=sys.stderr,
            )
            return 1
        # --player-repetition, when given, flattens every kind to one count;
        # otherwise each player's origin decides (see `copies_for`).
        roster = (
            build_roster(kinds, args.player_repetition)
            if args.player_repetition is not None
            else build_roster(kinds, copies=copies_for(registry))
        )
    except (ManifestError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    per_kind = sorted({len(_copies_of(roster, s.cls.get_name())) for s in roster})
    shape = (
        f"{per_kind[0]} per kind"
        if len(per_kind) == 1
        else f"{per_kind[0]}-{per_kind[-1]} per kind"
    )
    print(
        f"Loaded {len(kinds)} player kinds; roster of {len(roster)} "
        f"({shape}): {', '.join(s.name for s in roster)}"
    )
    limits = (
        "no time limit"
        if budgets.game_ms is None
        else f"{budgets.game_ms} ms/game + {budgets.build_ms} ms/build per player"
    )
    print(
        f"Format: {args.tournament} · {args.repetitions} reps/graph · {limits}"
        + (" · Elo" if args.elo and args.tournament == "league" else "")
    )

    try:
        leaderboard = run_tournament(
            roster,
            mode=args.tournament,
            starting_states=graphs,
            repetitions=args.repetitions,
            budgets=budgets,
            elo=args.elo,
            use_subprocess=not args.no_subprocess,
            group_size=args.group_size,
            advance_per_group=args.advance_per_group,
            extra_config={
                "time_limit_s": args.time_limit,
                # None unless --player-repetition overrode every kind at once.
                "player_repetition": args.player_repetition,
                # The per-kind counts actually used, so a published leaderboard
                # records the roster shape whatever produced it.
                "player_copies": {
                    name: len(_copies_of(roster, name))
                    for name in dict.fromkeys(s.cls.get_name() for s in roster)
                },
            },
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(leaderboard, indent=2) + "\n", encoding="utf-8")

    standings = leaderboard["standings"]
    use_elo = bool(leaderboard["config"]["elo"])
    print(f"\nClassification (written to {out_path}):")
    for row in standings:
        score = f"elo {row['elo']}" if use_elo else f"{row['points']} pts"
        print(
            f"  {row['rank']}. {row['player']:<18} {score:<12} "
            f"W {row['wins']:<4} D {row['draws']:<4} L {row['losses']:<4} "
            f"forfeits {row['forfeits']}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
