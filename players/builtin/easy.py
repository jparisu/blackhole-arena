"""The `easy` player — a single rule of thumb."""

from __future__ import annotations

from blackholearena.bots import FreeNeighbourBot


class Easy(FreeNeighbourBot):
    """Plays a random free node that has a free neighbour."""

    @classmethod
    def get_name(cls) -> str:
        return "easy"

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["builtin"]

    @classmethod
    def get_icon(cls) -> str:
        return "🌱"

    @classmethod
    def get_description(cls) -> str:
        return (
            "One rule: play on a node that still has a free neighbour, chosen at "
            "random among those. On the last move it means scoring the biggest "
            "batch of tiles whenever the two remaining nodes are adjacent."
        )
