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
from src.core.scoring import ScoreCalculator
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
        self._score_calculator = ScoreCalculator(config)
        self._jinx_share_ratio = float(config.get("JBOT_JINX_SHARE_RATIO", "0.25"))
        self._jinx_wrong_guess_penalty = int(
            config.get("JBOT_JINX_WRONG_GUESS_PENALTY", "5")
        )
        self._rest_bonus_per_day = float(
            config.get("JBOT_REST_BONUS_PER_DAY", "0.2") or "0.2"
        )

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

        transition = self._reduce_eligible_guess(
            next_state,
            normalized_player_id,
            is_correct,
            points_earned,
            bonuses,
            pending_rest_multiplier,
        )
        return ReducerResult(next_state, transition)

    def _reduce_eligible_guess(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
        is_correct: bool,
        points_earned: int,
        bonuses: dict[str, int] | None,
        pending_rest_multiplier: float,
    ) -> GuessTransition:
        """Apply the complete native reducer transition for an eligible guess."""
        state = daily_state[player_id]

        if not is_correct:
            attacker_id = state.jinxed_by
            penalty = 0
            if attacker_id:
                attacker_state = daily_state.setdefault(attacker_id, DailyPlayerState())
                penalty = self._jinx_wrong_guess_penalty
                attacker_state.score_earned -= penalty
                attacker_state.jinx_penalty_total += penalty
            return GuessTransition(
                points_earned=0,
                jinx_attacker_id=attacker_id,
                jinx_wrong_guess_penalty=penalty,
            )

        state.is_correct = True
        state.score_earned += points_earned
        state.bonuses = bonuses if bonuses is not None else {}
        state.streak_delta += 1

        rest_bonus = 0
        consume_pending_rest_multiplier = (
            pending_rest_multiplier > 0.0 and points_earned > 0
        )
        if consume_pending_rest_multiplier:
            rest_bonus = round(points_earned * pending_rest_multiplier)
            if rest_bonus > 0:
                state.score_earned += rest_bonus
                state.bonuses["rest"] = rest_bonus

        jinx_attacker_id = state.jinxed_by
        jinx_transfer = self._resolve_jinx(daily_state, player_id)
        steal_thief_id = state.steal_attempt_by
        steal_transfer = self._resolve_steal(daily_state, player_id)

        return GuessTransition(
            points_earned=points_earned + rest_bonus - jinx_transfer - steal_transfer,
            rest_bonus=rest_bonus,
            consume_pending_rest_multiplier=consume_pending_rest_multiplier,
            jinx_attacker_id=jinx_attacker_id,
            jinx_transfer=jinx_transfer,
            steal_thief_id=steal_thief_id,
            steal_transfer=steal_transfer,
        )

    def _resolve_jinx(
        self, daily_state: dict[str, DailyPlayerState], target_id: str
    ) -> int:
        target_state = daily_state[target_id]
        attacker_id = target_state.jinxed_by
        if not attacker_id:
            return 0

        attacker_state = daily_state.setdefault(attacker_id, DailyPlayerState())
        if attacker_state.jinx_target is None:
            return 0

        earned_only = target_state.score_earned - target_state.score_stolen
        share = int(earned_only * self._jinx_share_ratio)
        if share > 0:
            target_state.score_earned -= share
            attacker_state.score_earned += share
            attacker_state.score_stolen += share
        attacker_state.jinx_target = None
        return share

    def _resolve_steal(
        self, daily_state: dict[str, DailyPlayerState], target_id: str
    ) -> int:
        target_state = daily_state[target_id]
        thief_id = target_state.steal_attempt_by
        if not thief_id:
            return 0

        stealable = self._score_calculator.pop_stealable_bonuses(target_state.bonuses)
        if stealable <= 0:
            return 0

        thief_state = daily_state.setdefault(thief_id, DailyPlayerState())
        stolen = round(stealable * thief_state.steal_ratio)
        if stolen > 0:
            target_state.score_earned -= stolen
            thief_state.score_earned += stolen
            thief_state.score_stolen += stolen
        return stolen

    def reduce_powerup(
        self,
        daily_state: Mapping[str, DailyPlayerState],
        event: PowerUpEvent,
        initial_streak: int = 0,
    ) -> ReducerResult:
        """Return the next state and effects for a power-up event."""
        next_state = self._copy_state(daily_state)
        user_id = str(event.user_id)
        target_id = (
            str(event.target_user_id) if event.target_user_id is not None else None
        )

        if (
            event.powerup_type
            in {"jinx", "jinx_late", "jinx_preload", "steal", "steal_preload"}
            and target_id
            and self._is_retaliation_blocked(next_state, user_id, target_id)
        ):
            return ReducerResult(
                next_state,
                PowerUpTransition(rejection_reason="retaliation_blocked"),
            )

        if event.powerup_type == "rest":
            state = self._get_state(next_state, user_id)
            state.is_resting = True
            whiffed_jinx_id = state.jinxed_by
            whiffed_steal_id = state.steal_attempt_by
            state.jinxed_by = None
            state.steal_attempt_by = None
            return ReducerResult(
                next_state,
                PowerUpTransition(
                    pending_rest_multiplier_increment=self._rest_bonus_per_day,
                    whiffed_jinx_id=whiffed_jinx_id,
                    whiffed_steal_id=whiffed_steal_id,
                ),
            )

        if event.powerup_type == "jinx" and target_id:
            transfer, penalty = self._apply_jinx(next_state, user_id, target_id)
            return ReducerResult(
                next_state,
                PowerUpTransition(
                    jinx_transfer=transfer,
                    jinx_wrong_guess_penalty=penalty,
                ),
            )

        if event.powerup_type == "jinx_late" and target_id:
            cost = self._strip_late_jinx_cost(next_state, user_id)
            transfer, penalty = self._apply_jinx(next_state, user_id, target_id)
            return ReducerResult(
                next_state,
                PowerUpTransition(
                    jinx_cost=cost,
                    jinx_transfer=transfer,
                    jinx_wrong_guess_penalty=penalty,
                ),
            )

        if event.powerup_type == "jinx_preload" and target_id:
            self._apply_preload_jinx(next_state, user_id, target_id)
            return ReducerResult(next_state, PowerUpTransition())

        transition = self._service.process_powerup(
            next_state, event, initial_streak=initial_streak
        )
        return ReducerResult(next_state, transition)

    @staticmethod
    def _get_state(
        daily_state: dict[str, DailyPlayerState], player_id: str
    ) -> DailyPlayerState:
        return daily_state.setdefault(player_id, DailyPlayerState())

    def _is_retaliation_blocked(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> bool:
        attacker_state = self._get_state(daily_state, attacker_id)
        return target_id in attacker_state.attacked_by

    def _apply_jinx(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> tuple[int, int]:
        attacker_state = self._get_state(daily_state, attacker_id)
        target_state = self._get_state(daily_state, target_id)
        attacker_state.silenced = True
        attacker_state.jinx_target = target_id
        target_state.jinxed_by = attacker_id
        target_state.attacked_by.add(attacker_id)

        if not target_state.is_correct:
            return 0, 0

        earned_only = target_state.score_earned - target_state.score_stolen
        transfer = int(earned_only * self._jinx_share_ratio)
        if transfer > 0:
            target_state.score_earned -= transfer
            attacker_state.score_earned += transfer
            attacker_state.score_stolen += transfer

        wrong_guesses = max(0, target_state.guesses_count - 1)
        penalty = wrong_guesses * self._jinx_wrong_guess_penalty
        if penalty > 0:
            attacker_state.score_earned -= penalty
            attacker_state.jinx_penalty_total += penalty

        attacker_state.jinx_target = None
        return transfer, penalty

    def _apply_preload_jinx(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> None:
        attacker_state = self._get_state(daily_state, attacker_id)
        target_state = self._get_state(daily_state, target_id)
        attacker_state.silenced = True
        attacker_state.jinx_target = target_id
        target_state.jinxed_by = attacker_id
        target_state.attacked_by.add(attacker_id)

    def _strip_late_jinx_cost(
        self, daily_state: dict[str, DailyPlayerState], player_id: str
    ) -> int:
        state = self._get_state(daily_state, player_id)
        before_hint = state.bonuses.pop("before_hint", 0)
        fastest = sum(
            state.bonuses.pop(key)
            for key in list(state.bonuses)
            if key.startswith("fastest_")
        )
        state.bonuses.pop("fastest", None)
        cost = before_hint + fastest
        state.score_earned -= cost
        return cost
