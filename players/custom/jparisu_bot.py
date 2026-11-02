"""
The `DrJekyllBot` player
Look-ahead search that plays peacefully while the opponent do not reduce its points.
"""

from __future__ import annotations

import random
from typing import Any
from dataclasses import dataclass

from blackholearena.game import Move, State
from blackholearena.game import legal_moves, apply_move, free_nodes, is_terminal, to_move
from blackholearena.player import Player

#: Most positions one search may visit; it decides the search depth.
MAX_NODES_TO_VISIT = 10_000
TIE = -1


class DrJekyllBot(Player):
    """Maximizes its own points, or plays minimax against an adversarial opponent."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

        # Store already checked states (only final ones)
        self._memo: dict[tuple[Any, ...], DrJekyllBot.StateScore] = {}

        # Store wether it shall play peacefully or aggressive
        self._retaliation_mood = False

        # Store my seat in game
        self._my_seat: int | None = None

    @classmethod
    def create(cls, seed: int) -> DrJekyllBot:
        return cls(seed=seed)

    @classmethod
    def get_name(cls) -> str:
        return "DrJekyll"

    @classmethod
    def get_authors(cls) -> list[str]:
        return ["jparisu"]

    @classmethod
    def get_icon(cls) -> str:
        return "🐝"

    @classmethod
    def get_description(cls) -> str:
        return (
            "Looks ahead to calculate best play adapted to opponents strategy.  "
        )

    ############################################################################
    # CHOOSE MOVE
    def choose_move(self, state: State) -> Move:

        # First move, set seat
        if self._my_seat is None:
            self._my_seat = to_move(state)

        # Calculate max depth
        depth = self._calculate_depth_by_max_nodes(state)

        # Check whether it shall play peacefully
        self._retaliation_mood = self._retaliation_required(state)

        # Check future actions
        current_player = to_move(state)
        moves = {move: self._search(apply_move(state, move), depth) for move in legal_moves(state)}
        moves = self.__select_correct_moves(moves, current_player)

        # Select move depending mood
        move = self._select_best_move(
            moves=moves,
            current_player=current_player,
            peace=not self._retaliation_mood)

        return move


    def _retaliation_required(self, state: State) -> bool:
        """Check previous moves and decide whether activate war behavior."""

        # If already in war mode, keep war mode
        if self._retaliation_mood:
            return True

        # TODO
        return False


    def _select_best_move(self, moves: dict[Move, DrJekyllBot.StateScore], current_player: int, peace: bool) -> Move:
        """Return one random move that maximizes its score."""
        return self._rng.choice(self.__select_best_move(moves, current_player, peace))



    ############################################################################
    # Auxiliary functions

    @dataclass
    class StateScore:
        """The score stored for each node of the game.

        Each node stores:
         - who wins (if playing only to win) using Minimax.
         - the points expected in the case the players play peacefully or aggressive.
         - whether the state found is final
        """
        winner: int
        peace_score: list[int]
        war_score: list[int]
        complete: bool

        def get_score(self, peace: bool) -> list[int]:
            return self.peace_score if peace else self.war_score



    def _search(self, state: State, depth: int) -> StateScore:
        """Calculate every state below and return its expected score."""

        # Finish search for max depth
        if depth == 0 or is_terminal(state):
            score_0 = self._heuristic(state, 0)
            score_1 = self._heuristic(state, 1)
            w = 0 if score_0 > score_1 else (1 if score_1 > score_0 else TIE)
            c = is_terminal(state)
            return self.StateScore(
                winner=w,
                peace_score=[score_0, score_1],
                war_score=[score_0, score_1],
                complete=c,
            )

        # Check whether this state is already stored
        h = self._state_index(state)
        score = self._memo.get(h)
        if score is not None:
            return score

        # Calculate children score
        scores : dict[Move, DrJekyllBot.StateScore] = {}
        for move in legal_moves(state):
            scores[move] = self._search(apply_move(state, move), depth=depth-1)

        #####
        # Create current node score
        current_player = to_move(state)

        # Calculate whether the analysis has finished.
        # NOTE: it would be enough to check the first move, as depth is for all
        complete = all(s.complete for s in scores.values())

        # Select only those moves that win the match, or tie if any, or all if neither of both
        possible_moves = self.__select_correct_moves(scores, current_player)

        # If the opponent is playing, in war times it could use moves that are worse for me
        possible_war_moves = possible_moves
        if current_player != self._my_seat:
            possible_war_moves = scores

        # Calculate whether this player could win
        # Every filtered move has the same outcome: win, tie, or loss
        winner = next(iter(possible_moves.values())).winner

        # Calculate the best move peaceful and warmonger opponent
        best_move_peace = self.__select_best_move(
            moves=possible_moves,
            current_player=current_player,
            peace=True)
        best_p_scores = possible_moves[best_move_peace[0]].peace_score

        best_move_war = self.__select_best_move(
            moves=possible_war_moves,
            current_player=current_player,
            peace=False)
        best_w_scores = possible_war_moves[best_move_war[0]].war_score

        current_score = self.StateScore(
            winner=winner,
            peace_score=best_p_scores,
            war_score=best_w_scores,
            complete=complete
        )

        # Store current state
        if current_score.complete:
            self._memo[h] = current_score

        return current_score


    def _calculate_depth_by_max_nodes(self, state: State) -> int:
        """Return the deepest search whose full tree fits in :data:`MAX_NODES_TO_VISIT`.

        With ``F`` free nodes, ply ``k`` offers ``F - k`` moves, so depth ``d``
        costs ``F + F(F-1) + ... + F!/(F-d)!`` nodes. The game ends with one free
        node left, so the depth never exceeds ``F - 1``. It is at least 1.
        """
        free = len(free_nodes(state))
        depth, level, total = 0, 1, 0
        while depth < free - 1:
            level *= free - depth  # nodes at ply `depth + 1`
            if total + level > MAX_NODES_TO_VISIT:
                break
            total += level
            depth += 1
        return max(depth-1, 1)

    def _heuristic(self, state: State, player: int) -> int:
        """Return the points ``player`` could score, summed over every free node as the hole.

        On a finished game the only free node is the black hole, so this is the
        exact score.
        """
        owner, tiles = state["owner"], state["tiles"]
        points = 0
        for hole in free_nodes(state):
            for a, b in state["edges"]:
                if hole in (a, b):
                    neighbour = b if a == hole else a
                    if owner[neighbour] == player:
                        points += tiles[neighbour]
        return points

    @staticmethod
    def _state_index(state: State) -> tuple[int|None, ...]:
        """Calculate state index for memoization."""
        return tuple(state["owner"] + state["tiles"])

    @staticmethod
    def _other_player(current_player: int) -> int:
        """Return the opposite player: 0 if 1, 1 if 0."""
        return (current_player + 1) % 2

    @staticmethod
    def __select_correct_moves(moves: dict[Move, DrJekyllBot.StateScore], current_player: int) -> dict[Move, DrJekyllBot.StateScore]:
        """Select only those moves that make sense for the player.

        The player will try to maximize its own value, however only those moves that make him win make sense.
        This function filters a dictionary letting only those that win.
        If none wins, then returns those that tie.
        If none ties, then returns all.
        """
        possible_moves = {m: s for m, s in moves.items() if s.winner == current_player}
        if len(possible_moves) != 0:
            return possible_moves

        # It is possible that there are ties
        possible_moves = {m: s for m, s in moves.items() if s.winner == TIE}
        if len(possible_moves) != 0:
            return possible_moves

        # All losing states
        else:
            return moves

    def __select_best_move(self, moves: dict[Move, DrJekyllBot.StateScore], current_player: int, peace: bool) -> list[Move]:
        """Return list of moves that maximizes its score in both good and bad times."""
        if peace:
            return self.__select_best_move_peace(moves, current_player)
        else:
            return self.__select_best_move_war(moves, current_player)

    def __select_best_move_peace(self, moves: dict[Move, DrJekyllBot.StateScore], current_player: int) -> list[Move]:
        """Return list of moves that maximizes its score in peaceful times."""
        best_score = -1
        winner_moves = []

        for m, score in moves.items():

            if score.get_score(peace=True)[current_player] > best_score:
                best_score = score.get_score(peace=True)[current_player]
                winner_moves = [m]
            elif score.get_score(peace=True)[current_player] == best_score:
                winner_moves.append(m)

        return winner_moves

    def __select_best_move_war(self, moves: dict[Move, DrJekyllBot.StateScore], current_player: int) -> list[Move]:
        """Return list of moves that maximizes its score in war times."""
        if current_player == self._my_seat:
            return self.__select_best_move_war_own(moves, current_player)
        else:
            return self.__select_best_move_war_opponent(moves, current_player)


    @staticmethod
    def __select_best_move_war_own(moves: dict[Move, DrJekyllBot.StateScore], current_player: int) -> list[Move]:
        """Return a list of moves that maximizes its score in war times when this player is playing."""
        best_score = -1
        winner_moves = []

        for m, score in moves.items():

            if score.get_score(peace=False)[current_player] > best_score:
                best_score = score.get_score(peace=False)[current_player]
                winner_moves = [m]
            elif score.get_score(peace=False)[current_player] == best_score:
                winner_moves.append(m)

        return winner_moves

    @staticmethod
    def __select_best_move_war_opponent(moves: dict[Move, DrJekyllBot.StateScore], current_player: int) -> list[Move]:
        """Return a list of moves that minimizes my score in war times when opponent is playing."""
        worst_score = float("inf")
        winner_moves = []
        opp_player = DrJekyllBot._other_player(current_player)

        for m, score in moves.items():

            if score.get_score(peace=False)[opp_player] < worst_score:
                worst_score = score.get_score(peace=False)[opp_player]
                winner_moves = [m]
            elif score.get_score(peace=False)[opp_player] == worst_score:
                winner_moves.append(m)

        return winner_moves
