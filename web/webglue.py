"""Thin Python bridge exposed to the browser (via Pyodide).

The web page calls into this module so that the *same* Python game rules and AI
players run in the browser exactly as they do in the CI tournament — there is no
duplicated game logic in JavaScript.

Everything crosses the Python<->JS boundary as **JSON strings** (a state is the
``{"edges", "owner", "tiles"}`` mapping, a move is a node index). That keeps the
boundary dumb and avoids fragile object marshalling. JavaScript
``JSON.stringify``/``JSON.parse`` on its side; we ``json.loads``/``json.dumps`` on
ours.

No timeouts are enforced here — live play is best-effort, by design.
"""

from __future__ import annotations

import copy
import json
import time

from blackholearena import game, graphs
from blackholearena.game import State
from blackholearena.manifest import BUILTIN, CUSTOM, load_players
from blackholearena.player import Player
from blackholearena.registry import Registry

#: Milliseconds per second, used to report per-move timing.
_MS_PER_SECOND = 1000.0

#: Human-readable names for the presets in :data:`blackholearena.graphs.PRESETS`.
_PRESET_LABELS = {
    "classic": "Classic — 5 nodes (the rules example)",
    "wheel-7": "Wheel — 7 nodes",
    "grid-3x3": "Grid 3×3 — 9 nodes",
    "wheel-11": "Wheel — 11 nodes",
}

_REGISTRY: Registry | None = None

#: Independent player instances for the bracket on the Tournament page, keyed by
#: slot id. A kind may enter a bracket several times, and each entrant must have
#: its own instance and seed — sharing one would make two `random` entrants
#: correlated, and let one entrant's cache leak into another's game.
_ENTRANTS: dict[str, Player] = {}


def _require_registry() -> Registry:
    """Return the loaded registry, or fail with an actionable message.

    Every entry point below goes through this rather than touching the global
    directly: an un-awaited ``init`` otherwise surfaced as
    ``AttributeError: 'NoneType' object has no attribute 'all'``, which says
    nothing about what actually went wrong.
    """
    if _REGISTRY is None:
        raise RuntimeError("webglue.init(base_dir) must be called before using the bridge")
    return _REGISTRY


def init(base_dir: str) -> str:
    """Load players from the manifests under ``base_dir`` and return them as JSON."""
    global _REGISTRY
    _REGISTRY = load_players({
        BUILTIN: f"{base_dir}/players/{BUILTIN}/players.yaml",
        CUSTOM: f"{base_dir}/players/{CUSTOM}/players.yaml",
    })
    return players_json()


def players_json() -> str:
    """Return the registered players as JSON, with their declared identity.

    Each entry is ``{"name", "icon", "authors", "description"}``, read from the
    player's class rather than from any instance, so the UI can label and
    describe an opponent without playing a game.
    """
    return json.dumps(
        [
            {
                "name": type(p).get_name(),
                "icon": type(p).get_icon(),
                "authors": type(p).get_authors(),
                "description": type(p).get_description(),
            }
            for p in _require_registry().all()
        ]
    )


# --- graphs ---------------------------------------------------------------- #

def presets_json() -> str:
    """Return the named starting graphs as JSON ``[{"name", "label", "state"}]``."""
    return json.dumps(
        [
            {"name": name, "label": _PRESET_LABELS.get(name, name), "state": state}
            for name, state in graphs.PRESETS.items()
        ]
    )


def new_game(nodes: int, edges_json: str) -> str:
    """Return the starting state for a graph, as JSON.

    Raises:
        ValueError: with a readable reason if the graph is unusable.
    """
    return json.dumps(game.new_game(int(nodes), json.loads(edges_json)))


def random_graph(nodes: int, density: float, seed: int) -> str:
    """Return the starting state of a random connected graph, as JSON."""
    return json.dumps(graphs.random_graph(int(nodes), float(density), int(seed)))


# --- pure game rules (single source of truth) ------------------------------ #

def legal_moves(state_json: str) -> str:
    """Return the legal moves (free nodes) for a JSON-encoded state, as a JSON list."""
    return json.dumps(game.legal_moves(json.loads(state_json)))


def apply_move(state_json: str, move: int) -> str:
    """Apply ``move`` (a node index) to a JSON-encoded state; return the new state."""
    return json.dumps(game.apply_move(json.loads(state_json), int(move)))


def is_terminal(state_json: str) -> bool:
    """Return ``True`` if the JSON-encoded state is a finished game."""
    return game.is_terminal(json.loads(state_json))


def analysis(state_json: str) -> str:
    """Describe a position for the page: whose turn, and what each hole would score.

    Returns JSON::

        {"to_move": 0|1, "tiles_to_place": int, "tiles_per_player": int,
         "turns_per_player": int, "terminal": bool,
         "black_hole": int|null, "scores": [first, second]|null,
         "hole_payoffs": {node: [first, second], ...}}

    ``hole_payoffs`` maps every free node to the scores *if that node became the
    black hole now*, counting only the tiles already placed — the X-ray view.
    On a finished game it holds just the black hole, and ``scores`` is final.
    """
    state: State = json.loads(state_json)
    terminal = game.is_terminal(state)
    payoffs = {
        str(node): list(game.scores_if_hole(state, node)) for node in game.free_nodes(state)
    }
    return json.dumps({
        "to_move": game.to_move(state),
        "tiles_to_place": game.tiles_to_place(state),
        "tiles_per_player": game.tiles_per_player(state),
        "turns_per_player": game.turns_per_player(state),
        "terminal": terminal,
        "black_hole": game.black_hole(state) if terminal else None,
        "scores": list(game.scores(state)) if terminal else None,
        "hole_payoffs": payoffs,
    })


# --- tournament entrants --------------------------------------------------- #

def reset_entrants() -> str:
    """Discard every entrant. Called when a new bracket is configured."""
    _ENTRANTS.clear()
    return "ok"


def create_entrant(entrant_id: str, kind: str, seed: int) -> str:
    """Build an independent instance of ``kind`` for one bracket slot.

    Uses :meth:`~blackholearena.player.Player.create`, the same factory the real
    tournament uses, so a bot may configure itself from the seed.

    Raises:
        KeyError: if ``kind`` is not a registered player.
    """
    cls = type(_require_registry().get(kind))
    _ENTRANTS[entrant_id] = cls.create(seed=seed)
    return entrant_id


def _entrant(entrant_id: str) -> Player:
    """Return a built entrant, or explain that the bracket was not set up."""
    try:
        return _ENTRANTS[entrant_id]
    except KeyError:
        raise KeyError(f"unknown entrant {entrant_id!r}; call create_entrant first") from None


def entrant_move(entrant_id: str, state_json: str) -> str:
    """Ask one bracket entrant for its move. Same payload as :func:`ask_move`."""
    return _timed_move(_entrant(entrant_id), json.loads(state_json))


def play_auto(a_id: str, b_id: str, state_json: str) -> str:
    """Play a whole game between two entrants and return it in one call.

    Running the loop here rather than move-by-move from JavaScript keeps a
    bot-vs-bot match to a single crossing of the Python/JS boundary. A game always
    ends after ``2N`` moves, so no move cap is needed.

    A player that raises or returns an illegal move **forfeits**, mirroring the
    real tournament: it scores 0 and its opponent the maximum. The browser
    enforces no timeout, so a page must never be taken down by one bad player.

    Returns JSON ``{"moves": [node, ...], "scores": [a, b], "result": ...,
    "forfeit_seat": 0|1|null, "detail": str, "elapsed_ms": [a_total, b_total]}``.
    """
    state: State = json.loads(state_json)
    players = [_entrant(a_id), _entrant(b_id)]
    best = game.tiles_per_player(state)
    moves: list[int] = []
    spent = [0.0, 0.0]

    def forfeit(seat: int, result: str, detail: str) -> str:
        score = [best, best]
        score[seat] = 0
        return json.dumps({
            "moves": moves, "scores": score, "result": result,
            "forfeit_seat": seat, "detail": detail, "elapsed_ms": spent,
        })

    while not game.is_terminal(state):
        turn = game.to_move(state)
        t0 = time.perf_counter()
        try:
            move = players[turn].choose_move(copy.deepcopy(state))
        except BaseException as exc:  # noqa: BLE001 - any failure forfeits
            spent[turn] += (time.perf_counter() - t0) * _MS_PER_SECOND
            return forfeit(turn, "forfeit_error", f"raised: {exc!r}")
        spent[turn] += (time.perf_counter() - t0) * _MS_PER_SECOND

        if not game.is_legal(state, move):
            return forfeit(
                turn, "forfeit_illegal",
                f"returned illegal move {move!r}; free nodes were {game.free_nodes(state)}",
            )
        moves.append(int(move))
        state = game.apply_move(state, int(move))

    return json.dumps({
        "moves": moves, "scores": list(game.scores(state)), "result": "normal",
        "forfeit_seat": None, "detail": "", "elapsed_ms": spent,
    })


# --- AI moves -------------------------------------------------------------- #

def _timed_move(player: Player, state: State) -> str:
    """Ask ``player`` for a move on ``state`` and report it with its timing."""
    if game.is_terminal(state):
        raise ValueError("no move to make: the game is over")
    t0 = time.perf_counter()
    move = player.choose_move(copy.deepcopy(state))
    elapsed_ms = (time.perf_counter() - t0) * _MS_PER_SECOND
    info = getattr(player, "last_info", None)
    return json.dumps({"move": move, "elapsed_ms": elapsed_ms, "info": info})


def ask_move(name: str, state_json: str) -> str:
    """Ask the registered player ``name`` for its move on ``state``.

    Returns JSON ``{"move": node, "elapsed_ms": float, "info": {...}|null}``
    where ``info`` is the player's optional ``last_info`` (shown in the move log,
    for bots that explain themselves).
    """
    return _timed_move(_require_registry().get(name), json.loads(state_json))
