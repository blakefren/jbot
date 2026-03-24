"""
Pure power-up state logic for jbot trivia game.

PowerUpEngine is stateless — it holds no daily_state of its own.
Callers (PowerUpManager for live play, DailyGameSimulator for replay)
own their daily_state dicts and pass them in. The engine only mutates
DailyPlayerState objects; it never touches the database.
"""

from src.cfg.main import ConfigReader
from src.core.state import DailyPlayerState
from src.core.scoring import ScoreCalculator


class PowerUpEngine:
    """
    Pure state-mutation logic for power-up resolution.

    All methods accept a ``daily_state`` dict keyed by player_id (str)
    and mutate the relevant DailyPlayerState entries in place.
    """

    def __init__(self, config: ConfigReader):
        self.score_calculator = ScoreCalculator(config)
        self.steal_streak_cost = int(config.get("JBOT_STEAL_STREAK_COST", "3"))
        self.retro_steal_streak_cost = int(
            config.get("JBOT_RETRO_STEAL_STREAK_COST", "5")
        )
        self.retro_jinx_bonus_ratio = float(
            config.get("JBOT_RETRO_JINX_BONUS_RATIO", "0.5")
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_state(
        self, daily_state: dict[str, DailyPlayerState], player_id: str
    ) -> DailyPlayerState:
        if player_id not in daily_state:
            daily_state[player_id] = DailyPlayerState()
        return daily_state[player_id]

    # ------------------------------------------------------------------
    # Jinx
    # ------------------------------------------------------------------

    def apply_jinx(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> int:
        """Set jinx state flags. If target already answered, resolve retroactively.

        Silences the attacker. If the target has already answered correctly, transfers
        ``retro_jinx_bonus_ratio`` of their streak bonus to the attacker immediately.

        Returns the number of points transferred (0 if none).
        """
        attacker_state = self._get_state(daily_state, attacker_id)
        target_state = self._get_state(daily_state, target_id)
        attacker_state.silenced = True

        if target_state.is_correct:
            streak_val = target_state.bonuses.get("streak", 0)
            transferred = int(streak_val * self.retro_jinx_bonus_ratio)
            if transferred > 0:
                target_state.score_earned -= transferred
                attacker_state.score_earned += transferred
                target_state.bonuses.pop("streak", None)
            target_state.jinxed_by = attacker_id  # mark resolved
            return transferred

        target_state.jinxed_by = attacker_id
        return 0

    def apply_late_jinx(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> tuple[int, int]:
        """Apply a late-day jinx where the attacker has already answered.

        Strips the attacker's before_hint and fastest bonuses as the cost, then
        applies jinx state flags and retroactive resolution against the target.

        ``strip_late_day_jinx_cost`` mutates score_earned directly.
        ``apply_jinx`` handles silencing and retroactive transfer independently.

        Returns ``(cost_deducted, points_transferred_from_target)``.
        """
        cost = self.strip_late_day_jinx_cost(daily_state, attacker_id)
        transferred = self.apply_jinx(daily_state, attacker_id, target_id)
        return cost, transferred

    def resolve_jinx_on_correct(
        self,
        daily_state: dict[str, DailyPlayerState],
        target_id: str,
        bonus_values: dict,
    ) -> int:
        """Transfer streak bonus from a jinxed target to their attacker when they answer.

        ``bonus_values`` is the mutable bonuses dict from score calculation (modified
        in place to remove the streak entry). Returns the number of points transferred.
        """
        target_state = self._get_state(daily_state, target_id)
        attacker_id = target_state.jinxed_by
        if not attacker_id:
            return 0

        streak_bonus = bonus_values.get("streak", 0)
        if streak_bonus > 0:
            bonus_values.pop("streak")
            attacker_state = self._get_state(daily_state, attacker_id)
            attacker_state.score_earned += streak_bonus
        return streak_bonus

    # ------------------------------------------------------------------
    # Steal
    # ------------------------------------------------------------------

    def apply_steal(
        self,
        daily_state: dict[str, DailyPlayerState],
        thief_id: str,
        target_id: str,
        initial_streak: int,
        is_preload: bool = False,
    ) -> tuple[int, int, int]:
        """Set up a steal attempt and record streak cost in state.

        For ``is_preload=True`` the streak cost was already deducted before the daily
        snapshot; this method only sets the state flags (no streak_delta change).

        For a normal daytime steal the streak cost is applied as a negative
        ``streak_delta`` on the thief's state.

        If the target **has already answered** (retroactive steal), the stealable
        bonuses are transferred immediately and the higher retro cost is used.

        If the thief **has already answered** (late-day steal), the streak bonus in
        state is recalculated using ``effective_streak - cost`` and the delta is
        returned so callers can sync the DB.

        Returns ``(streak_days_deducted, stolen_amount, bonus_delta)``:
        - ``streak_days_deducted``: use ``initial_streak - deducted`` for ``set_streak``.
        - ``stolen_amount``: points transferred from target (retroactive only; 0 otherwise).
        - ``bonus_delta``: streak bonus adjustment already applied to ``score_earned``
          (non-zero only when thief already answered). Caller applies this to the DB.
        """
        thief_state = self._get_state(daily_state, thief_id)
        target_state = self._get_state(daily_state, target_id)

        if is_preload:
            thief_state.stealing_from = target_id
            thief_state.steal_is_preload = True
            target_state.steal_attempt_by = thief_id
            return 0, 0, 0

        if target_state.is_correct:
            cost = self.retro_steal_streak_cost
        else:
            cost = self.steal_streak_cost

        streak_deducted = min(cost, initial_streak)

        bonus_delta = 0
        if thief_state.is_correct:
            # Thief already answered — adjust streak_delta and recalculate streak bonus.
            # Use effective streak (initial+1) so the penalty reflects this day's scoring.
            effective_streak = initial_streak + 1
            new_bonus_streak = max(0, effective_streak - cost)
            thief_state.streak_delta = new_bonus_streak - initial_streak
            bonus_delta = self.recalculate_streak_bonus(
                daily_state, thief_id, new_bonus_streak
            )
        else:
            thief_state.streak_delta = -streak_deducted

        thief_state.stealing_from = target_id

        stolen_amount = 0
        if target_state.is_correct:
            # Retroactive: resolve immediately
            stolen_amount = self.score_calculator.get_stealable_amount(
                target_state.bonuses
            )
            if stolen_amount > 0:
                target_state.score_earned -= stolen_amount
                thief_state.score_earned += stolen_amount
            target_state.steal_attempt_by = thief_id  # mark resolved
        else:
            target_state.steal_attempt_by = thief_id

        return streak_deducted, stolen_amount, bonus_delta

    def resolve_steal_on_correct(
        self,
        daily_state: dict[str, DailyPlayerState],
        target_id: str,
    ) -> int:
        """Transfer stealable bonuses from target to thief when the target answers.

        Returns the number of points stolen (0 if nothing stealable or no pending steal).
        """
        target_state = self._get_state(daily_state, target_id)
        attacker_id = target_state.steal_attempt_by
        if not attacker_id:
            return 0

        stealable = self.score_calculator.get_stealable_amount(target_state.bonuses)
        target_state.steal_attempt_by = None  # consume the attempt regardless

        if stealable > 0:
            target_state.score_earned -= stealable
            attacker_state = self._get_state(daily_state, attacker_id)
            attacker_state.score_earned += stealable

        return stealable

    # ------------------------------------------------------------------
    # Rest
    # ------------------------------------------------------------------

    def apply_rest(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
    ) -> tuple[str | None, str | None]:
        """Mark player as resting and whiff any pending attacks.

        Returns ``(whiffed_jinx_attacker_id, whiffed_steal_attacker_id)`` — each is
        the attacker's player_id if an attack was whiffed, or None.
        """
        state = self._get_state(daily_state, player_id)
        state.is_resting = True

        whiffed_jinx = None
        whiffed_steal = None

        if state.jinxed_by:
            whiffed_jinx = state.jinxed_by
            state.jinxed_by = None

        if state.steal_attempt_by:
            whiffed_steal = state.steal_attempt_by
            state.steal_attempt_by = None

        return whiffed_jinx, whiffed_steal

    # ------------------------------------------------------------------
    # Preload (overnight hydration)
    # ------------------------------------------------------------------

    def apply_preload_jinx(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> None:
        """Apply an overnight pre-loaded jinx at the start of the question day."""
        attacker_state = self._get_state(daily_state, attacker_id)
        target_state = self._get_state(daily_state, target_id)
        attacker_state.silenced = True
        target_state.jinxed_by = attacker_id

    def apply_preload_steal(
        self,
        daily_state: dict[str, DailyPlayerState],
        attacker_id: str,
        target_id: str,
    ) -> None:
        """Apply an overnight pre-loaded steal at the start of the question day."""
        attacker_state = self._get_state(daily_state, attacker_id)
        target_state = self._get_state(daily_state, target_id)
        attacker_state.stealing_from = target_id
        attacker_state.steal_is_preload = True
        target_state.steal_attempt_by = attacker_id

    # ------------------------------------------------------------------
    # Streak bonus helpers
    # ------------------------------------------------------------------

    def strip_late_day_jinx_cost(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
    ) -> int:
        """Strip before_hint and fastest bonuses as the cost for a late-day jinx.

        Mutates state.bonuses and state.score_earned.
        Returns the total points deducted.
        """
        state = self._get_state(daily_state, player_id)
        before_hint_val = state.bonuses.pop("before_hint", 0)
        fastest_val = sum(
            state.bonuses.pop(k)
            for k in list(state.bonuses)
            if k.startswith("fastest_")
        )
        state.bonuses.pop("fastest", None)  # alias key
        total_cost = before_hint_val + fastest_val
        state.score_earned -= total_cost
        return total_cost

    def recalculate_streak_bonus(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
        new_streak: int,
    ) -> int:
        """Recalculate streak bonus after a steal reduces the thief's effective streak.

        Mutates state.bonuses and state.score_earned.
        Returns the net score delta (negative means score went down).
        """
        state = self._get_state(daily_state, player_id)
        old_bonus = state.bonuses.get("streak", 0)
        new_bonus = self.score_calculator.get_streak_bonus(new_streak)
        delta = new_bonus - old_bonus
        if delta != 0:
            state.score_earned += delta
        if new_bonus > 0:
            state.bonuses["streak"] = new_bonus
        else:
            state.bonuses.pop("streak", None)
        return delta
