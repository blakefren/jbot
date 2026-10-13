"""Copy-on-write game transitions used to migrate Phase 2 toward a reducer."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping

from src.cfg.main import ConfigReader
from src.core.events import PowerUpEvent
from src.core.game_event_service import (
    GameEventService,
    GuessTransition,
    PowerUpTransition,
)
from src.core.state import DailyPlayerState


@dataclass(frozen=True)
class ReducerResult:
    """The next daily state and effects produced by one domain transition."""

    daily_state: dict[str, DailyPlayerState]
    transition: GuessTransition | PowerUpTransition


class DailyGameReducer:
    """Provides copy-on-write equivalents of the Phase 2 event transitions."""

    def __init__(self, config: ConfigReader):
        self._service = GameEventService(config)

    @staticmethod
    def _copy_state(
        daily_state: Mapping[str, DailyPlayerState],
    ) -> dict[str, DailyPlayerState]:
        return deepcopy(dict(daily_state))

    def reduce_guess(
        self,
        daily_state: Mapping[str, DailyPlayerState],
        player_id: str,
        is_correct: bool,
        points_earned: int = 0,
        bonuses: dict[str, int] | None = None,
        pending_rest_multiplier: float = 0.0,
    ) -> ReducerResult:
        """Return the next state and effects for a submitted guess."""
        next_state = self._copy_state(daily_state)
        normalized_player_id = str(player_id)
        state = next_state.setdefault(normalized_player_id, DailyPlayerState())
        state.guesses_count += 1

        if state.is_correct or state.is_resting:
            return ReducerResult(next_state, GuessTransition(points_earned=0))

        transition = self._service._process_eligible_guess(
            next_state,
            normalized_player_id,
            is_correct=is_correct,
            points_earned=points_earned,
            bonuses=bonuses,
            pending_rest_multiplier=pending_rest_multiplier,
        )
        return ReducerResult(next_state, transition)

    def reduce_powerup(
        self,
        daily_state: Mapping[str, DailyPlayerState],
        event: PowerUpEvent,
        initial_streak: int = 0,
    ) -> ReducerResult:
        """Return the next state and effects for a power-up event."""
        next_state = self._copy_state(daily_state)
        transition = self._service.process_powerup(
            next_state, event, initial_streak=initial_streak
        )
        return ReducerResult(next_state, transition)
