"""The `aggressive-min` player — search that minimizes the opponent's score."""

from __future__ import annotations

from blackholearena.bots import MinRivalBot


class AggressiveMin(MinRivalBot):
    """Alpha-beta search minimizing the opponent's score."""

    @classmethod
    def get_name(cls) -> str:
        return "aggressive-min"

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["builtin"]

    @classmethod
    def get_icon(cls) -> str:
        return "🗡️"

    @classmethod
    def get_description(cls) -> str:
        return (
            "Minimax with alpha-beta pruning and memoization, minimizing the "
            "opponent's score while assuming the opponent maximizes it. It never "
            "counts its own points: denying the rival is all it wants."
        )
