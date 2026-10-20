"""The `aggressive-max` player — search that maximizes its own score."""

from __future__ import annotations

from blackholearena.bots import MaxOwnBot


class AggressiveMax(MaxOwnBot):
    """Alpha-beta search maximizing its own score against a hostile opponent."""

    @classmethod
    def get_name(cls) -> str:
        return "aggressive-max"

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["builtin"]

    @classmethod
    def get_icon(cls) -> str:
        return "⚔️"

    @classmethod
    def get_description(cls) -> str:
        return (
            "Minimax with alpha-beta pruning and memoization, maximizing its own "
            "score while assuming the opponent tries to minimize it. Searches as "
            "deep as a fixed node budget allows, then estimates."
        )
