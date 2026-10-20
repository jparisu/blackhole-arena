"""The `cooperative` player — search that maximizes both players' points."""

from __future__ import annotations

from blackholearena.bots import CooperativeBot


class Cooperative(CooperativeBot):
    """Search maximizing the total score, assuming the opponent plays along."""

    @classmethod
    def get_name(cls) -> str:
        return "cooperative"

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["builtin"]

    @classmethod
    def get_icon(cls) -> str:
        return "🤝"

    @classmethod
    def get_description(cls) -> str:
        return (
            "Searches for the moves that make the most points in total, for both "
            "players, assuming the opponent plays along. Memoized, with the same "
            "node budget as the aggressive players."
        )
