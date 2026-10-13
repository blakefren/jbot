"""Shared mutable state transitions for live play and replay."""

from dataclasses import dataclass

from src.cfg.main import ConfigReader
from src.core.events import PowerUpEvent
from src.core.powerup_engine import PowerUpEngine
from src.core.state import DailyPlayerState


@dataclass
class GuessTransition:
    """State changes produced by one submitted guess."""

    points_earned: int
    rest_bonus: int = 0
    consume_pending_rest_multiplier: bool = False
    jinx_attacker_id: str | None = None
    jinx_transfer: int = 0
    jinx_wrong_guess_penalty: int = 0
    steal_thief_id: str | None = None
    steal_transfer: int = 0


@dataclass
class PowerUpTransition:
    """State changes produced by one power-up event."""

    rejection_reason: str | None = None
    whiffed_jinx_id: str | None = None
    whiffed_steal_id: str | None = None
    jinx_cost: int = 0
    jinx_transfer: int = 0
    jinx_wrong_guess_penalty: int = 0
    streak_deducted: int = 0
    steal_transfer: int = 0
    steal_bonus_delta: int = 0


class GameEventService:
    """Applies shared guess and power-up transitions to daily player state."""

    def __init__(self, config: ConfigReader):
        self.engine = PowerUpEngine(config)

    def is_retaliation_blocked(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> bool:
        """Return whether the target has already attacked the attacker today."""
        attacker_state = self.engine._get_state(daily_state, str(attacker_id))
        return str(target_id) in attacker_state.attacked_by

    def process_guess(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
        is_correct: bool,
        points_earned: int = 0,
        bonuses: dict[str, int] | None = None,
        pending_rest_multiplier: float = 0.0,
    ) -> GuessTransition:
        """Apply all power-up-related consequences of a submitted guess."""
        player_id = str(player_id)
        state = self.engine._get_state(daily_state, player_id)
        state.guesses_count += 1

        if state.is_correct or state.is_resting:
            return GuessTransition(points_earned=0)

        return self._process_eligible_guess(
            daily_state,
            player_id,
            is_correct=is_correct,
            points_earned=points_earned,
            bonuses=bonuses,
            pending_rest_multiplier=pending_rest_multiplier,
        )

    def _process_eligible_guess(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
        is_correct: bool,
        points_earned: int = 0,
        bonuses: dict[str, int] | None = None,
        pending_rest_multiplier: float = 0.0,
    ) -> GuessTransition:
        """Process a guess after its count and eligibility have been resolved."""
        state = self.engine._get_state(daily_state, str(player_id))

        if not is_correct:
            attacker_id = state.jinxed_by
            penalty = self.engine.apply_jinx_wrong_guess_penalty(daily_state, player_id)
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
        jinx_transfer = self.engine.resolve_jinx_on_correct(daily_state, player_id)

        steal_thief_id = state.steal_attempt_by
        steal_transfer = self.engine.resolve_steal_on_correct(daily_state, player_id)

        return GuessTransition(
            points_earned=points_earned + rest_bonus - jinx_transfer - steal_transfer,
            rest_bonus=rest_bonus,
            consume_pending_rest_multiplier=consume_pending_rest_multiplier,
            jinx_attacker_id=jinx_attacker_id,
            jinx_transfer=jinx_transfer,
            steal_thief_id=steal_thief_id,
            steal_transfer=steal_transfer,
        )

    def process_powerup(
        self,
        daily_state: dict[str, DailyPlayerState],
        event: PowerUpEvent,
        initial_streak: int = 0,
    ) -> PowerUpTransition:
        """Apply a power-up event using the same transition for live play and replay."""
        user_id = str(event.user_id)
        target_id = (
            str(event.target_user_id) if event.target_user_id is not None else None
        )

        if (
            event.powerup_type
            in {"jinx", "jinx_late", "jinx_preload", "steal", "steal_preload"}
            and target_id
            and self.is_retaliation_blocked(daily_state, user_id, target_id)
        ):
            return PowerUpTransition(rejection_reason="retaliation_blocked")

        if event.powerup_type == "rest":
            whiffed_jinx_id, whiffed_steal_id = self.engine.apply_rest(
                daily_state, user_id
            )
            return PowerUpTransition(
                whiffed_jinx_id=whiffed_jinx_id,
                whiffed_steal_id=whiffed_steal_id,
            )

        if event.powerup_type == "jinx" and target_id:
            attacker = self.engine._get_state(daily_state, user_id)
            previous_penalty = attacker.jinx_penalty_total
            transfer = self.engine.apply_jinx(daily_state, user_id, target_id)
            return PowerUpTransition(
                jinx_transfer=transfer,
                jinx_wrong_guess_penalty=(
                    attacker.jinx_penalty_total - previous_penalty
                ),
            )

        if event.powerup_type == "jinx_late" and target_id:
            attacker = self.engine._get_state(daily_state, user_id)
            previous_penalty = attacker.jinx_penalty_total
            cost, transfer = self.engine.apply_late_jinx(
                daily_state, user_id, target_id
            )
            return PowerUpTransition(
                jinx_cost=cost,
                jinx_transfer=transfer,
                jinx_wrong_guess_penalty=(
                    attacker.jinx_penalty_total - previous_penalty
                ),
            )

        if event.powerup_type == "jinx_preload" and target_id:
            self.engine.apply_preload_jinx(daily_state, user_id, target_id)
            return PowerUpTransition()

        if event.powerup_type in {"steal", "steal_preload"} and target_id:
            deducted, transfer, bonus_delta = self.engine.apply_steal(
                daily_state, user_id, target_id, initial_streak
            )
            return PowerUpTransition(
                streak_deducted=deducted,
                steal_transfer=transfer,
                steal_bonus_delta=bonus_delta,
            )

        return PowerUpTransition()
