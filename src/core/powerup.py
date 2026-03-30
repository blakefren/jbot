"""
POWERUP mode logic for jbot trivia game.
Implements power-up actions: jinx, steal, and rest.
"""

import logging
from src.cfg.main import ConfigReader
from src.core.base_manager import BaseManager
from src.core.data_manager import DataManager
from src.core.events import GuessContext
from src.core.player_manager import PlayerManager
from src.core.powerup_engine import PowerUpEngine
from src.core.state import DailyPlayerState


class PowerUpError(Exception):
    """Exception raised for errors in power-up usage."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class PowerUpManager(BaseManager):
    """
    Manages power-up actions for jbot trivia game, including jinx, steal, and rest.
    """

    def __init__(
        self,
        player_manager: PlayerManager,
        data_manager: DataManager,
        config: ConfigReader = None,
    ):
        """
        Initialize the PowerUpManager.
        Args:
            player_manager (PlayerManager): The player manager instance.
            data_manager (DataManager): The data manager instance.
            config (ConfigReader): Optional config instance; creates one if not provided.
        """
        self.player_manager = player_manager
        self.data_manager = data_manager
        _config = config or ConfigReader()
        self.engine = PowerUpEngine(_config)
        # Config-driven constants
        self.emoji_jinxed = _config.get("JBOT_EMOJI_JINXED", "🥶")
        self.emoji_silenced = _config.get("JBOT_EMOJI_SILENCED", "🤐")
        self.emoji_stolen_from = _config.get("JBOT_EMOJI_STOLEN_FROM", "💸")
        self.emoji_stealing = _config.get("JBOT_EMOJI_STEALING", "💰")
        self.emoji_rest = _config.get("JBOT_EMOJI_REST", "😴")
        self.emoji_rest_wakeup = _config.get("JBOT_EMOJI_REST_WAKEUP", "⏰")
        self.emoji_streak = _config.get("JBOT_EMOJI_STREAK", "🔥")
        self.rest_multiplier = float(_config.get("JBOT_REST_MULTIPLIER", "1.2"))
        # Transient state for the day
        self.daily_state: dict[str, DailyPlayerState] = {}

    def _get_daily_state(self, player_id: str) -> DailyPlayerState:
        if player_id not in self.daily_state:
            self.daily_state[player_id] = DailyPlayerState()
        return self.daily_state[player_id]

    def reset_daily_state(self):
        """
        Reset the transient daily state for all players.
        Called at the end of the game day.
        """
        self.daily_state.clear()
        logging.info("PowerUpManager daily state reset.")

    def restore_daily_state(self, player_id: str, simulated_state: DailyPlayerState):
        """
        Restores the daily state for a player from the simulator.
        """
        # If simulated_state is already the class (which it should be now), just assign it
        if isinstance(simulated_state, DailyPlayerState):
            self.daily_state[player_id] = simulated_state
        else:
            # Fallback for safety if passed a dict (e.g. from old tests)
            # But we should update tests too.
            pass

    def can_answer(self, player_id: str, hint_sent: bool = False) -> tuple[bool, str]:
        """
        Check if a player is allowed to answer.
        Returns (bool, reason).
        """
        state = self._get_daily_state(player_id)
        if state.is_resting:
            return False, "You are resting today. You cannot submit any guesses."
        if not state.silenced or hint_sent:
            return True, ""
        return (
            False,
            "You are Jinxed! You cannot answer until the hint is revealed.",
        )

    def on_guess(self, ctx: GuessContext) -> list[str]:
        pid = str(ctx.player_id)
        state = self._get_daily_state(pid)

        # Store earnings for potential theft
        if ctx.is_correct:
            state.is_correct = True
            state.score_earned = ctx.points_earned
            state.bonuses = ctx.bonus_values

        messages = []

        # Apply pending rest multiplier (from yesterday's rest) on correct answers
        if ctx.is_correct and ctx.points_earned > 0:
            pending_mult = self.data_manager.get_pending_multiplier(pid)
            if pending_mult > 1.0:
                bonus_amount = round(ctx.points_earned * (pending_mult - 1.0))
                if bonus_amount > 0:
                    self.player_manager.update_score(pid, bonus_amount)
                    ctx.points_earned += bonus_amount
                    state.bonuses["rest"] = bonus_amount
                    messages.append(
                        f"{self.emoji_rest_wakeup} Rest bonus! ×{pending_mult} on today's score (+{bonus_amount} pts)!"
                    )
                    self.data_manager.log_powerup_usage(
                        pid, "rest_wakeup", None, ctx.question_id
                    )
                self.data_manager.clear_pending_multiplier(pid)

        msg = self.resolve_jinx(pid, ctx)
        if msg:
            messages.append(msg)

        msg = self.resolve_steal(pid, ctx)
        if msg:
            messages.append(msg)

        return messages

    def resolve_jinx(self, player_id: str, ctx: GuessContext) -> str:
        """
        Resolve Jinx effect on the target.
        """
        state = self._get_daily_state(player_id)
        attacker_id = state.jinxed_by

        if not attacker_id or not ctx.is_correct:
            return ""

        # Engine: transfer streak bonus in state, strip from bonus_values dict
        transferred = self.engine.resolve_jinx_on_correct(
            self.daily_state, player_id, ctx.bonus_values
        )

        if transferred > 0:
            self.player_manager.update_score(player_id, -transferred)
            self.player_manager.update_score(attacker_id, transferred)
            ctx.points_earned -= transferred

            # Remove streak message if present
            for i, msg in enumerate(ctx.bonus_messages):
                if self.emoji_streak in msg:
                    ctx.bonus_messages.pop(i)
                    break

            return f"{self.emoji_jinxed} <@{attacker_id}> swiped <@{player_id}>'s streak bonus of {transferred} pts via Jinx!"

        return f"{self.emoji_jinxed} <@{attacker_id}>'s Jinx had no effect — <@{player_id}> had no streak bonus to steal!"

    def resolve_steal(self, target_id: str, ctx: GuessContext) -> str:
        """
        Resolve Steal effect when the target answers.
        """
        target_state = self._get_daily_state(target_id)
        attacker_id = target_state.steal_attempt_by

        if not attacker_id or not ctx.is_correct:
            return ""

        # Engine: transfer stealable bonuses in state
        stealable_amount = self.engine.resolve_steal_on_correct(
            self.daily_state, target_id
        )

        if stealable_amount == 0:
            return f"{self.emoji_stealing} <@{attacker_id}> tried to steal from <@{target_id}>, but there was nothing to steal!"

        self.player_manager.update_score(target_id, -stealable_amount)
        self.player_manager.update_score(attacker_id, stealable_amount)
        ctx.points_earned -= stealable_amount

        thief_state = self._get_daily_state(attacker_id)
        partial_note = " (partial steal)" if thief_state.steal_ratio < 1.0 else ""
        return f"{self.emoji_stealing} <@{attacker_id}> stole {stealable_amount} pts from <@{target_id}>!{partial_note}"

    def hydrate_pending_powerups(self, question_id: int):
        """
        Applies overnight pre-loaded powerups to the current day's daily_state.
        Called at the start of a new question day before the question is announced.
        Streak costs for steal_preload are deducted here at hydration, not at pre-load time.
        """
        if not isinstance(question_id, int) or question_id <= 0:
            logging.warning(
                "hydrate_pending_powerups called with invalid question_id=%r; skipping.",
                question_id,
            )
            return
        pending = self.data_manager.apply_pending_powerups(question_id)
        for row in pending:
            attacker_id = row["user_id"]
            target_id = row["target_user_id"]
            ptype = row["powerup_type"]

            if ptype == "jinx_preload":
                self.engine.apply_preload_jinx(self.daily_state, attacker_id, target_id)
                logging.info(
                    "[Hydration] Overnight jinx applied: %s \u2192 %s",
                    attacker_id,
                    target_id,
                )
            elif ptype == "steal_preload":
                thief = self.player_manager.get_player(attacker_id)
                initial_streak = thief.answer_streak if thief else 0
                streak_deducted, _, _ = self.engine.apply_steal(
                    self.daily_state, attacker_id, target_id, initial_streak
                )
                if streak_deducted > 0:
                    self.player_manager.set_streak(
                        attacker_id, initial_streak - streak_deducted
                    )
                logging.info(
                    "[Hydration] Overnight steal applied: %s \u2192 %s (-%d streak)",
                    attacker_id,
                    target_id,
                    streak_deducted,
                )

    def jinx(self, attacker_id: str, target_id: str, question_id: int = None) -> str:
        """
        Jinx another player.

        Overnight (question_id is None): pre-loads the jinx for the next question day.
        Daytime: silences attacker until hint; if target already answered, resolves
        immediately at a reduced ratio (retro_jinx_bonus_ratio) of the streak bonus.
        """
        attacker = self.player_manager.get_player(attacker_id)
        target = self.player_manager.get_player(target_id)

        if not attacker or not target:
            raise PowerUpError("Invalid player(s).")

        if attacker_id == target_id:
            raise PowerUpError("You cannot target yourself.")

        if question_id is None:
            # --- Overnight pre-load path ---
            if self.data_manager.get_pending_powerup(attacker_id):
                raise PowerUpError("You already have a powerup queued for tomorrow.")
            if self.data_manager.get_pending_powerup_for_target(
                target_id, "jinx_preload"
            ):
                raise PowerUpError(
                    f"<@{target_id}> is already being targeted by a Jinx!"
                )

            # Silence attacker in-memory immediately; hydration will re-apply at morning
            attacker_state = self._get_daily_state(attacker_id)
            attacker_state.silenced = True
            self.data_manager.log_powerup_usage(
                attacker_id, "jinx_preload", target_id, None
            )
            return (
                f"{self.emoji_silenced} Your jinx is queued for tomorrow! "
                f"{target.name} won't know until it takes effect. "
                f"You can't answer until the hint is revealed!"
            )

        # --- Daytime path ---
        last_correct = self.data_manager.get_last_correct_guess_date(attacker_id)
        is_late_day = last_correct == self.data_manager.get_today()

        attacker_state = self._get_daily_state(attacker_id)
        if attacker_state.powerup_used_today:
            raise PowerUpError("You have already used a power-up today.")

        target_state = self._get_daily_state(target_id)

        if target_state.is_resting:
            raise PowerUpError(
                f"<@{target_id}> is resting today — you can't jinx a resting player!"
            )

        if target_state.jinxed_by:
            raise PowerUpError(f"<@{target_id}> has already been jinxed!")

        # Block retroactive jinx when the target has no streak bonus — the attacker
        # would consume their power-up slot (and pay late costs) for zero gain.
        if target_state.is_correct and not target_state.bonuses.get("streak", 0):
            raise PowerUpError(
                f"<@{target_id}> already answered but has no streak bonus — nothing to jinx!"
            )

        attacker_state.silenced = True

        if is_late_day:
            # --- Late-day jinx: attacker already answered ---
            # Engine handles cost stripping and jinx/retro application; DB write happens here.
            cost, transferred = self.engine.apply_late_jinx(
                self.daily_state, attacker_id, target_id
            )
            # DB: deduct cost, credit transferred amount
            if cost > 0:
                self.player_manager.update_score(attacker_id, -cost)
            if transferred > 0:
                self.player_manager.update_score(target_id, -transferred)
                self.player_manager.update_score(attacker_id, transferred)
            self.data_manager.log_powerup_usage(
                attacker_id, "jinx_late", target_id, question_id
            )
            cost_str = (
                f" (cost you {cost} pts)"
                if cost > 0
                else " (free \u2014 no bonuses to lose)"
            )

            if self._get_daily_state(target_id).is_correct:
                if transferred > 0:
                    return (
                        f"{self.emoji_jinxed} Late jinx on <@{target_id}>! "
                        f"Swiped {transferred} pts of their streak bonus{cost_str}."
                    )
                return (
                    f"{self.emoji_jinxed} Late jinx landed on <@{target_id}>, "
                    f"but they had no streak bonus{cost_str}."
                )

            return (
                f"{self.emoji_jinxed} Late jinx set on {target.name}{cost_str}! "
                f"Their streak bonus is forfeit when they answer."
            )

        # --- Normal daytime path ---
        self.data_manager.log_powerup_usage(attacker_id, "jinx", target_id, question_id)
        transferred = self.engine.apply_jinx(self.daily_state, attacker_id, target_id)

        if self._get_daily_state(target_id).is_correct:
            # Retroactive: target already answered (no-streak case blocked above)
            self.player_manager.update_score(target_id, -transferred)
            self.player_manager.update_score(attacker_id, transferred)
            return (
                f"{self.emoji_jinxed} <@{target_id}> already answered \u2014 retroactive jinx! "
                f"You swiped half their streak bonus ({transferred} pts). "
                f"{self.emoji_silenced} You still can't answer until the hint is revealed."
            )

        # Normal daytime path (target hasn't answered yet)
        return (
            f"{self.emoji_silenced} Your jinx is set! {target.name} won't know until it takes effect. "
            f"You can't answer until the hint is revealed!"
        )

    def steal(self, thief_id: str, target_id: str, question_id: int = None) -> str:
        """
        Steal points from another player.

        Overnight (question_id is None): pre-loads the steal for the next question day;
        streak cost deducted immediately.
        Daytime normal: streak cost deducted, bonuses stolen when target answers.
        Daytime retroactive (target already answered): higher streak cost
        (retro_steal_streak_cost), bonuses transferred immediately.
        """
        thief = self.player_manager.get_player(thief_id)
        target = self.player_manager.get_player(target_id)

        if not thief or not target:
            raise PowerUpError("Invalid player(s).")

        if thief_id == target_id:
            raise PowerUpError("You cannot target yourself.")

        current_streak = thief.answer_streak if thief else 0

        if question_id is None:
            # --- Overnight pre-load path ---
            if self.data_manager.get_pending_powerup(thief_id):
                raise PowerUpError("You already have a powerup queued for tomorrow.")
            if self.data_manager.get_pending_powerup_for_target(
                target_id, "steal_preload"
            ):
                raise PowerUpError(
                    f"<@{target_id}> is already being targeted for theft!"
                )
            if current_streak == 0:
                raise PowerUpError(
                    "You don't have any streak days to sacrifice. "
                    "Keep your streak going before stealing!"
                )

            # Streak cost is deducted at hydration (when the question goes live),
            # not here, so we don't bake an early penalty into the DB snapshot.
            steal_cost = self.engine.steal_streak_cost
            actual_lost = min(steal_cost, current_streak)
            self.data_manager.log_powerup_usage(
                thief_id, "steal_preload", target_id, None
            )
            if current_streak < steal_cost:
                return (
                    f"{self.emoji_stealing} Partial steal queued! You only have "
                    f"{current_streak}/{steal_cost} streak days toward the cost — "
                    f"will sacrifice all {actual_lost} for a partial steal when the question drops."
                )
            return (
                f"{self.emoji_stealing} You've queued a steal for tomorrow! "
                f"Will sacrifice {actual_lost} streak days when the question drops. "
                f"If they answer correctly, you'll steal their bonuses."
            )

        # --- Daytime path ---
        last_correct = self.data_manager.get_last_correct_guess_date(thief_id)
        is_late_day = last_correct == self.data_manager.get_today()

        thief_state = self._get_daily_state(thief_id)
        if thief_state.powerup_used_today:
            raise PowerUpError("You have already used a power-up today.")

        target_state = self._get_daily_state(target_id)

        if target_state.is_resting:
            raise PowerUpError(
                f"<@{target_id}> is resting today — you can't steal from a resting player!"
            )

        if target_state.steal_attempt_by:
            raise PowerUpError(f"<@{target_id}> is already being targeted for theft!")

        if current_streak == 0:
            raise PowerUpError(
                "You don't have any streak days to sacrifice. "
                "Keep your streak going before stealing!"
            )

        if target_state.is_correct:
            # --- Retroactive: target already answered — higher cost, immediate resolution ---
            self.data_manager.log_powerup_usage(
                thief_id, "steal", target_id, question_id
            )
            # Engine: sets state flags, streak_delta, bonus recalc (if late-day), score transfer.
            deducted, stealable_amount, bonus_delta = self.engine.apply_steal(
                self.daily_state, thief_id, target_id, current_streak
            )
            new_streak = max(0, current_streak - deducted)
            actual_lost = deducted
            is_partial = current_streak < self.engine.retro_steal_streak_cost
            self.player_manager.set_streak(thief_id, new_streak)
            if is_late_day and bonus_delta != 0:
                self.player_manager.update_score(thief_id, bonus_delta)
            if stealable_amount == 0:
                return (
                    f"{self.emoji_stealing} You sacrificed {actual_lost} streak days "
                    f"to rob <@{target_id}>, but there was nothing to steal!"
                )
            self.player_manager.update_score(target_id, -stealable_amount)
            self.player_manager.update_score(thief_id, stealable_amount)
            if is_partial:
                return (
                    f"{self.emoji_stealing} <@{target_id}> already answered! "
                    f"You only had {actual_lost}/{self.engine.retro_steal_streak_cost} streak days — "
                    f"partial steal: swiped {stealable_amount} pts!"
                )
            return (
                f"{self.emoji_stealing} <@{target_id}> already answered! "
                f"You paid {actual_lost} streak days and instantly swiped "
                f"{stealable_amount} pts!"
            )

        # --- Normal / forward daytime path ---
        self.data_manager.log_powerup_usage(thief_id, "steal", target_id, question_id)
        # Engine: sets state flags, streak_delta, bonus recalc (if late-day).
        deducted, _, bonus_delta = self.engine.apply_steal(
            self.daily_state, thief_id, target_id, current_streak
        )
        new_streak = max(0, current_streak - deducted)
        actual_lost = deducted
        is_partial = current_streak < self.engine.steal_streak_cost
        self.player_manager.set_streak(thief_id, new_streak)
        if is_late_day and bonus_delta != 0:
            self.player_manager.update_score(thief_id, bonus_delta)
        if is_partial:
            return (
                f"{self.emoji_stealing} Partial steal! You only had "
                f"{actual_lost}/{self.engine.steal_streak_cost} streak days — "
                f"sacrificing all {actual_lost} to steal a proportional share of "
                f"<@{target_id}>'s bonuses if they answer correctly."
            )
        return (
            f"{self.emoji_stealing} You sacrificed {actual_lost} streak days "
            f"to rob <@{target_id}>! If they answer correctly, you'll steal their bonuses."
        )

    def rest(
        self, player_id: str, question_id: int, question_answer: str
    ) -> tuple[str, str]:
        """
        Activate rest for a player. They opt out of today's scoring in exchange for
        a frozen streak and a 1.2x multiplier on tomorrow's earned score.

        Args:
            player_id: The player resting.
            question_id: Today's active daily question ID.
            question_answer: The correct answer (disclosed privately).

        Returns:
            (public_msg, private_msg) — caller sends both.
        """
        if question_id is None:
            raise PowerUpError("There is no active question right now.")

        player = self.player_manager.get_player(player_id)
        if not player:
            raise PowerUpError("Invalid player.")

        # Must not have already answered correctly today
        last_correct = self.data_manager.get_last_correct_guess_date(player_id)
        if last_correct == self.data_manager.get_today():
            raise PowerUpError(
                "You have already answered correctly today. You cannot rest."
            )

        state = self._get_daily_state(player_id)
        if state.is_resting:
            raise PowerUpError("You are already resting today.")
        if state.powerup_used_today:
            raise PowerUpError("You have already used a power-up today.")

        # Engine: mark resting, whiff pending attacks, return attacker IDs
        whiffed_jinx_id, whiffed_steal_id = self.engine.apply_rest(
            self.daily_state, player_id
        )
        self.data_manager.log_powerup_usage(player_id, "rest", None, question_id)

        # Store rest multiplier for tomorrow
        self.data_manager.set_pending_multiplier(player_id, self.rest_multiplier)

        whiff_parts = []
        if whiffed_jinx_id:
            whiff_parts.append(
                f"{self.emoji_jinxed} <@{whiffed_jinx_id}>'s Jinx had no effect — <@{player_id}> is resting!"
            )
        if whiffed_steal_id:
            whiff_parts.append(
                f"{self.emoji_stealing} <@{whiffed_steal_id}>'s steal whiffed — "
                f"<@{player_id}> has nothing to steal while resting "
                f"(but the streak reset still stands)!"
            )

        public_parts = [
            f"{self.emoji_rest} <@{player_id}> is resting today. "
            f"Streak frozen. ×{self.rest_multiplier} bonus applies to tomorrow's score."
        ]
        public_parts.extend(whiff_parts)
        public_msg = "\n".join(public_parts)

        private_msg = (
            f"{self.emoji_rest} You're resting today. The answer was: **{question_answer}**\n"
            "Your streak is frozen (not reset). "
            f"You'll earn a **×{self.rest_multiplier} multiplier** on your base + bonuses the next day you answer correctly."
        )

        return public_msg, private_msg
