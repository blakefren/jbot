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
        self.jinx_share_ratio = float(config.get("JBOT_JINX_SHARE_RATIO", "0.25"))
        self.jinx_wrong_guess_penalty = int(
            config.get("JBOT_JINX_WRONG_GUESS_PENALTY", "5")
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

        Silences the attacker and establishes the parasitic link (``jinx_target`` on
        attacker, ``jinxed_by`` on target). If the target has already answered correctly,
        transfers ``jinx_share_ratio`` of their total points to the attacker immediately
        and marks the link resolved (clears ``jinx_target``).

        Returns the number of points transferred (0 if target has not answered yet).
        """
        attacker_state = self._get_state(daily_state, attacker_id)
        target_state = self._get_state(daily_state, target_id)
        attacker_state.silenced = True
        attacker_state.jinx_target = target_id
        target_state.jinxed_by = attacker_id

        if target_state.is_correct:
            # Retroactive: target already answered — transfer share immediately.
            share = int(target_state.score_earned * self.jinx_share_ratio)
            if share > 0:
                target_state.score_earned -= share
                attacker_state.score_earned += share
            attacker_state.jinx_target = (
                None  # Mark resolved to prevent double-transfer
            )
            return share

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

        Returns ``(cost_deducted, points_transferred_from_target)``.
        """
        cost = self.strip_late_day_jinx_cost(daily_state, attacker_id)
        transferred = self.apply_jinx(daily_state, attacker_id, target_id)
        return cost, transferred

    def resolve_jinx_on_correct(
        self,
        daily_state: dict[str, DailyPlayerState],
        target_id: str,
    ) -> int:
        """Transfer share of target's points to attacker when the target answers correctly.

        Clears ``attacker.jinx_target`` to prevent a double-transfer.
        Returns points transferred (0 if no active link or already resolved).
        """
        target_state = self._get_state(daily_state, target_id)
        attacker_id = target_state.jinxed_by
        if not attacker_id:
            return 0

        attacker_state = self._get_state(daily_state, attacker_id)
        # Guard against double-transfer
        if attacker_state.jinx_target is None:
            return 0

        share = int(target_state.score_earned * self.jinx_share_ratio)
        if share > 0:
            target_state.score_earned -= share
            attacker_state.score_earned += share
        attacker_state.jinx_target = None  # Mark resolved
        return share

    def apply_jinx_wrong_guess_penalty(
        self,
        daily_state: dict[str, DailyPlayerState],
        target_id: str,
    ) -> int:
        """Deduct the wrong-guess penalty from the attacker when a jinxed target guesses wrong.

        Returns the penalty deducted (0 if the target is not jinxed).
        """
        target_state = self._get_state(daily_state, target_id)
        attacker_id = target_state.jinxed_by
        if not attacker_id:
            return 0

        attacker_state = self._get_state(daily_state, attacker_id)
        penalty = self.jinx_wrong_guess_penalty
        attacker_state.score_earned -= penalty
        attacker_state.jinx_penalty_total += penalty
        return penalty

    # ------------------------------------------------------------------
    # Steal
    # ------------------------------------------------------------------

    def apply_steal(
        self,
        daily_state: dict[str, DailyPlayerState],
        thief_id: str,
        target_id: str,
        initial_streak: int,
    ) -> tuple[int, int, int]:
        """Set up a steal attempt and record streak cost in state.

        The streak cost is always applied as a negative ``streak_delta`` on the
        thief's state — whether the steal was queued overnight (preload) or placed
        during the day.

        If the target **has already answered** (retroactive steal), the stealable
        bonuses are transferred immediately and the higher retro cost is used.

        If the thief **has already answered** (late-day steal), the streak bonus in
        state is recalculated using ``effective_streak - cost`` and the delta is
        returned so callers can sync the DB.

        **Partial steal**: if ``initial_streak < cost``, the thief pays their full
        remaining streak and receives a proportional fraction (``initial_streak / cost``)
        of the stealable bonuses. The thief's ``steal_ratio`` is stored in state so
        ``resolve_steal_on_correct`` can apply the same scaling for forward steals.

        Callers are responsible for enforcing that ``initial_streak > 0`` before
        calling this method (``PowerUpManager.steal`` raises ``PowerUpError`` earlier).

        Returns ``(streak_days_deducted, stolen_amount, bonus_delta)``:
        - ``streak_days_deducted``: use ``initial_streak - deducted`` for ``set_streak``.
        - ``stolen_amount``: points transferred from target (retroactive only; 0 otherwise).
        - ``bonus_delta``: streak bonus adjustment already applied to ``score_earned``
          (non-zero only when thief already answered). Caller applies this to the DB.
        """
        thief_state = self._get_state(daily_state, thief_id)
        target_state = self._get_state(daily_state, target_id)

        if target_state.is_correct:
            cost = self.retro_steal_streak_cost
        else:
            cost = self.steal_streak_cost

        bonus_delta = 0
        if thief_state.is_correct:
            # Thief already answered — use effective streak (initial+1) for ratio,
            # deduction, and bonus recalculation so everything reflects this day.
            # A thief who just started their streak (initial=0) has effective=1 and
            # CAN still steal, so the guard is skipped for this branch.
            effective_streak = initial_streak + 1
            streak_deducted = min(cost, effective_streak)
            steal_ratio = min(1.0, effective_streak / cost)
            new_bonus_streak = max(0, effective_streak - cost)
            thief_state.streak_delta = new_bonus_streak - initial_streak
            # Only recalculate if the streak bonus is still present in state.
            # If jinx already transferred it away, bonuses["streak"] is gone and there
            # is nothing to revise — the streak bonus belongs to the jinxer.
            if "streak" in thief_state.bonuses:
                bonus_delta = self.recalculate_streak_bonus(
                    daily_state, thief_id, new_bonus_streak
                )
        else:
            # Enforce: player must have at least 1 streak day to steal
            if initial_streak == 0:
                return 0, 0, 0
            streak_deducted = min(cost, initial_streak)
            steal_ratio = min(1.0, initial_streak / cost)
            thief_state.streak_delta = -streak_deducted

        thief_state.steal_ratio = steal_ratio
        thief_state.stealing_from = target_id

        stolen_amount = 0
        if target_state.is_correct:
            # Retroactive: pop all bonuses to prevent re-stealing, then scale transfer.
            total_stealable = self.score_calculator.pop_stealable_bonuses(
                target_state.bonuses
            )
            stolen_amount = round(total_stealable * steal_ratio)
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

        The amount transferred is scaled by the thief's ``steal_ratio`` (set during
        ``apply_steal``).  A ratio of 1.0 means full steal; less than 1.0 means the
        thief only paid a partial cost and receives a proportional share.

        Returns the number of points stolen (0 if nothing stealable or no pending steal).
        """
        target_state = self._get_state(daily_state, target_id)
        attacker_id = target_state.steal_attempt_by
        if not attacker_id:
            return 0

        stealable = self.score_calculator.pop_stealable_bonuses(target_state.bonuses)
        # steal_attempt_by is intentionally kept set — it permanently records that this
        # target was stolen from, preventing a second attacker from targeting them.
        # pop_stealable_bonuses already empties the bonus dict, so re-invocation is a no-op.

        if stealable > 0:
            attacker_state = self._get_state(daily_state, attacker_id)
            stolen = round(stealable * attacker_state.steal_ratio)
            if stolen > 0:
                target_state.score_earned -= stolen
                attacker_state.score_earned += stolen
            return stolen

        return 0

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
        attacker_state.jinx_target = target_id
        target_state.jinxed_by = attacker_id

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
