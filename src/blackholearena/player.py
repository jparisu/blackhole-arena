"""The player API — the spine of the whole project.

Everything (the tournament, the web page, and every externally submitted bot)
depends on this one small interface. A player declares **who it is** and
implements **one method**, :meth:`Player.choose_move`.

Keeping the move contract tiny is a feature: every extra parameter is one more
thing an outsider can get wrong. Concerns that belong to the *caller* — timeouts,
move history, opponent identity — deliberately live in the tournament, not here.

There are two other things a player must provide, and both exist because the
*caller* needs them, not because the bot does:

**Identity.** :meth:`~Player.get_name`, :meth:`~Player.get_authors` and
:meth:`~Player.get_description` are ``classmethod``\\ s, so the tournament, the
docs and the web app can all read a player's identity **without constructing
it**. They are abstract, which means :class:`abc.ABCMeta` refuses to instantiate
a subclass that has not filled them in::

    TypeError: Can't instantiate abstract class MyBot without an implementation
               for abstract method 'get_name'

**Construction.** :meth:`~Player.create` is the *only* way the tournament builds
a player, and it receives only a ``seed``. A bot is free to ignore the seed (a
deterministic bot has nothing to seed), but every bot is offered one, so repeated
games can differ. Because ``create`` is a classmethod, a bot may also use the
seed to vary its own configuration.

Why a factory rather than a ``seed`` parameter on every ``__init__``: it keeps a
tournament concern out of the signature every author has to write, and it gives
the caller one uniform construction path instead of inspecting signatures to see
which bots accept what.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .game import Move, State


class Player(ABC):
    """A BlackHole player. Implement the three accessors, then :meth:`choose_move`.

    A player receives the current board — the graph, who owns each node and how
    many tiles are on it (see :class:`~blackholearena.game.State`) — and must
    return the free node it wants to place its tiles on, as an ``int``. Which
    player it is, and how many tiles it places, are read from the board with
    :func:`~blackholearena.game.to_move` and
    :func:`~blackholearena.game.tiles_to_place`.

    The goal is to **maximize your own score**, not to beat the opponent: the
    tournament ranks players by the points they score.
    """

    #: Set by the tournament on a roster copy (e.g. ``"hard#1"``). Never set this
    #: yourself — :attr:`name` falls back to :meth:`get_name` when it is unset.
    _display_name: str | None = None

    # ----------------------------------------------------------------- #
    # Identity — readable without constructing the player               #
    # ----------------------------------------------------------------- #

    @classmethod
    @abstractmethod
    def get_name(cls) -> str:
        """Return this player's unique, human-readable name.

        Shown in the scoreboard, the web app and the docs. Must be unique across
        every admitted player; the manifest loader rejects duplicates.
        """

    @classmethod
    @abstractmethod
    def get_authors(cls) -> list[str]:
        """Return the author(s) of this player, as a non-empty list of names."""

    @classmethod
    @abstractmethod
    def get_description(cls) -> str:
        """Return a one-or-two-sentence description of how this player decides.

        This is what the scoreboard and the docs show next to the name, so
        describe the *strategy*, not the implementation.
        """

    @classmethod
    @abstractmethod
    def get_icon(cls) -> str:
        """Return a single emoji shown beside this player's name.

        Emoji rather than an image because it needs to work in three places that
        cannot all render markup: the scoreboard, a native ``<select>`` option in
        the web app (which renders text only), and plain-text docs. Keep it to one
        glyph — two-glyph sequences break table alignment.
        """

    # ----------------------------------------------------------------- #
    # Construction — the tournament's only entry point                  #
    # ----------------------------------------------------------------- #

    @classmethod
    def create(cls, seed: int) -> Player:
        """Build an instance of this player for one game.

        The default implementation ignores ``seed`` and calls ``cls()``. Override
        it if your player takes constructor arguments, or if you want the seed to
        influence how it is configured.

        Args:
            seed: a reproducible seed for this game. Never ``None``.

        Returns:
            A ready-to-play instance.
        """
        return cls()

    # ----------------------------------------------------------------- #
    # Playing                                                           #
    # ----------------------------------------------------------------- #

    @abstractmethod
    def choose_move(self, state: State) -> Move:
        """Choose a move for the given board.

        Never called on a finished game: there is always at least one legal move.

        Args:
            state: the current position — ``state["edges"]``, ``state["owner"]``
                and ``state["tiles"]``. Treat it as **read-only**: do not mutate it.

        Returns:
            The index of a **free** node, ``0 <= node < len(state["owner"])`` with
            ``state["owner"][node] is None``. The move **must** be legal — an
            illegal move forfeits the game in the tournament.
        """

    # ----------------------------------------------------------------- #
    # Display name                                                      #
    # ----------------------------------------------------------------- #

    @property
    def name(self) -> str:
        """The name to display for *this instance*.

        Defaults to :meth:`get_name`. The tournament overwrites it on roster
        copies so that two copies of the same kind stay distinguishable.
        """
        return self._display_name if self._display_name is not None else self.get_name()

    @name.setter
    def name(self, value: str) -> None:
        self._display_name = value

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r}>"
