"""The `random` player — difficulty level 0, the baseline."""

from __future__ import annotations

from blackholearena.bots import RandomBot


class Random(RandomBot):
    """Places its tiles on a uniformly random free node."""

    @classmethod
    def get_name(cls) -> str:
        return "random"

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["builtin"]

    @classmethod
    def get_icon(cls) -> str:
        return "🎲"

    @classmethod
    def get_description(cls) -> str:
        return (
            "Places its tiles on a free node chosen uniformly at random. No "
            "strategy at all — the baseline every other player has to beat."
        )
