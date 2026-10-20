"""Player registry — the in-memory catalogue of available players.

The registry is a simple ``name -> Player`` dictionary. It is populated by
:mod:`blackholearena.manifest`, which reads the human-edited manifests. The
tournament and the web page both iterate over the registry; **neither ever
hard-codes player names**.

The registry is intentionally dumb: discovery (who gets admitted) lives in the
manifest so that the trust boundary is visible in a single PR diff. The one extra
thing it records is each player's **origin** — the label of the manifest that
admitted it, ``"builtin"`` or ``"custom"``. That is a fact about the admission,
and callers that treat the two differently (the tournament decides roster copies
from it) would otherwise have to re-read the YAML to recover it.
"""

from __future__ import annotations

from .player import Player


class Registry:
    """A mapping of unique player name -> :class:`~blackholearena.player.Player`."""

    def __init__(self) -> None:
        self._players: dict[str, Player] = {}
        self._origins: dict[str, str] = {}

    def register(self, player: Player, *, replace: bool = False, origin: str = "") -> None:
        """Add ``player`` to the registry.

        Args:
            player: an instance of a :class:`~blackholearena.player.Player` subclass.
            replace: if ``False`` (default), registering a name that already
                exists raises. Set ``True`` to overwrite.
            origin: label of the manifest that admitted this player, e.g.
                :data:`~blackholearena.manifest.BUILTIN`. Empty when unknown.

        Raises:
            TypeError: if ``player`` is not a :class:`Player`.
            ValueError: if the name is already taken and ``replace`` is False.
        """
        if not isinstance(player, Player):
            raise TypeError(f"{player!r} is not a Player instance")
        name = player.name
        if name in self._players and not replace:
            raise ValueError(f"A player named {name!r} is already registered")
        self._players[name] = player
        self._origins[name] = origin

    def get(self, name: str) -> Player:
        """Return the registered player named ``name`` (raises ``KeyError``)."""
        return self._players[name]

    def names(self) -> list[str]:
        """Return the registered player names, in insertion order."""
        return list(self._players)

    def all(self) -> list[Player]:
        """Return all registered player instances, in insertion order."""
        return list(self._players.values())

    def origin(self, name: str) -> str:
        """Return the label of the manifest that admitted ``name`` (``""`` if none)."""
        return self._origins.get(name, "")

    def clear(self) -> None:
        """Remove every registered player."""
        self._players.clear()
        self._origins.clear()

    def __len__(self) -> int:
        return len(self._players)

    def __contains__(self, name: object) -> bool:
        return name in self._players


#: The default, process-wide registry used by the tournament and the web page.
REGISTRY = Registry()
