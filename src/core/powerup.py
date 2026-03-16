"""
POWERUP mode logic for jbot trivia game.
Implements power-up actions: jinx, steal, and rest.
"""

import logging
from src.cfg.main import ConfigReader
from src.core.base_manager import BaseManager
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager
from src.core.state import DailyPlayerState
from src.core.scoring import ScoreCalculator


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
        self.score_calculator = ScoreCalculator(_config)
        # Config-driven constants
        self.emoji_jinxed = _config.get("JBOT_EMOJI_JINXED", "🥶")
        self.emoji_silenced = _config.get("JBOT_EMOJI_SILENCED", "🤐")
        self.emoji_stolen_from = _config.get("JBOT_EMOJI_STOLEN_FROM", "💸")
        self.emoji_stealing = _config.get("JBOT_EMOJI_STEALING", "💰")
        self.emoji_rest = _config.get("JBOT_EMOJI_REST", "😴")
        self.emoji_rest_wakeup = _config.get("JBOT_EMOJI_REST_WAKEUP", "⏰")
        self.emoji_streak = _config.get("JBOT_EMOJI_STREAK", "🔥")
        self.rest_multiplier = float(_config.get("JBOT_REST_MULTIPLIER", "1.2"))
        self.steal_streak_cost = int(_config.get("JBOT_STEAL_STREAK_COST", "2"))
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

    def on_guess(
        self,
        player_id: int,
        player_name: str,
        guess: str,
        is_correct: bool,
        points_earned: int = 0,
        bonus_values: dict = None,
        bonus_messages: list[str] = None,
        points_tracker: dict = None,
        question_id: int = None,
    ) -> list[str]:
        if bonus_values is None:
            bonus_values = {}

        pid = str(player_id)
        state = self._get_daily_state(pid)

        # Store earnings for potential theft
        if is_correct:
            state.score_earned = points_earned
            state.bonuses = bonus_values

        messages = []

        # Apply pending rest multiplier (from yesterday's rest) on correct answers
        if is_correct and points_earned > 0:
            pending_mult = self.data_manager.get_pending_multiplier(pid)
            if pending_mult > 1.0:
                bonus_amount = round(points_earned * (pending_mult - 1.0))
                if bonus_amount > 0:
                    self.player_manager.update_score(pid, bonus_amount)
                    if points_tracker:
                        points_tracker["earned"] += bonus_amount
                    state.bonuses["rest"] = bonus_amount
                    messages.append(
                        f"{self.emoji_rest_wakeup} Rest bonus! ×{pending_mult} on today's score (+{bonus_amount} pts)!"
                    )
                    self.data_manager.log_powerup_usage(
                        pid, "rest_wakeup", None, question_id
                    )
                self.data_manager.clear_pending_multiplier(pid)

        msg = self.resolve_jinx(
            pid, is_correct, bonus_values, bonus_messages, points_tracker
        )
        if msg:
            messages.append(msg)

        msg = self.resolve_steal(pid, is_correct, points_tracker)
        if msg:
            messages.append(msg)

        return messages

    def resolve_jinx(
        self,
        player_id: str,
        correct: bool,
        bonus_values: dict,
        bonus_messages: list[str] = None,
        points_tracker: dict = None,
    ) -> str:
        """
        Resolve Jinx effect on the target.
        """
        state = self._get_daily_state(player_id)
        attacker_id = state.jinxed_by

        if not attacker_id or not correct:
            return ""

        # Strip streak bonus from target and transfer it to the attacker.
        streak_bonus = bonus_values.get("streak", 0)
        if streak_bonus > 0:
            self.player_manager.update_score(player_id, -streak_bonus)
            self.player_manager.update_score(attacker_id, streak_bonus)
            if points_tracker:
                points_tracker["earned"] -= streak_bonus

            # Remove streak message if present
            if bonus_messages is not None:
                for i, msg in enumerate(bonus_messages):
                    if self.emoji_streak in msg:
                        bonus_messages.pop(i)
                        break

            return f"{self.emoji_jinxed} <@{attacker_id}> swiped <@{player_id}>'s streak bonus of {streak_bonus} pts via Jinx!"

        return f"{self.emoji_jinxed} <@{attacker_id}>'s Jinx had no effect — <@{player_id}> had no streak bonus to steal!"

    def resolve_steal(
        self, target_id: str, correct: bool, points_tracker: dict = None
    ) -> str:
        """
        Resolve Steal effect when the target answers.
        """
        target_state = self._get_daily_state(target_id)
        attacker_id = target_state.steal_attempt_by

        if not attacker_id or not correct:
            return ""

        # Success Check
        target_bonuses = target_state.bonuses
        stealable_amount = self.score_calculator.get_stealable_amount(target_bonuses)

        if stealable_amount == 0:
            # Clear the steal attempt even if nothing stolen?
            # Logic suggests yes, the attempt is used up.
            target_state.steal_attempt_by = None
            return f"{self.emoji_stealing} <@{attacker_id}> tried to steal from <@{target_id}>, but there was nothing to steal!"

        self.player_manager.update_score(target_id, -stealable_amount)
        self.player_manager.update_score(attacker_id, stealable_amount)
        if points_tracker:
            points_tracker["earned"] -= stealable_amount

        # Clear the steal attempt
        target_state.steal_attempt_by = None

        return f"{self.emoji_stealing} <@{attacker_id}> stole {stealable_amount} pts from <@{target_id}>!"

    def jinx(self, attacker_id: str, target_id: str, question_id: int = None) -> str:
        """
        Jinx another player.
        Attacker is silenced until 7 PM.
        Target's streak points are blocked if they answer correctly (unless shielded).
        """
        if question_id is None:
            raise PowerUpError("There is no active question right now.")

        attacker = self.player_manager.get_player(attacker_id)
        target = self.player_manager.get_player(target_id)

        if not attacker or not target:
            raise PowerUpError("Invalid player(s).")

        # Validation: Attacker must not have answered yet
        last_correct = self.data_manager.get_last_correct_guess_date(attacker_id)
        if last_correct == self.data_manager.get_today():
            raise PowerUpError(
                "You have already answered correctly today. You cannot use Jinx."
            )

        attacker_state = self._get_daily_state(attacker_id)
        if attacker_state.powerup_used_today:
            raise PowerUpError("You have already used a power-up today.")

        target_state = self._get_daily_state(target_id)

        # Check for duplicate Jinx
        if target_state.jinxed_by:
            raise PowerUpError(f"<@{target_id}> has already been jinxed!")

        # Mark Attacker as SILENCED until the hint is sent
        attacker_state.silenced = True
        self.data_manager.log_powerup_usage(attacker_id, "jinx", target_id, question_id)

        target_state.jinxed_by = attacker_id
        return f"{self.emoji_silenced} Your jinx is set! {target.name} won't know until it takes effect. You can't answer until the hint is revealed!"

    def steal(self, thief_id: str, target_id: str, question_id: int = None) -> str:
        """
        Steal points from another player.
        Attacker's streak is reset immediately.
        If attacker answers correctly, they steal bonuses from target.
        """
        if question_id is None:
            raise PowerUpError("There is no active question right now.")

        thief = self.player_manager.get_player(thief_id)
        target = self.player_manager.get_player(target_id)

        if not thief or not target:
            raise PowerUpError("Invalid player(s).")

        # Validation: Attacker must not have answered yet.
        last_correct = self.data_manager.get_last_correct_guess_date(thief_id)
        if last_correct == self.data_manager.get_today():
            raise PowerUpError(
                "You have already answered correctly today. You cannot use Steal."
            )

        thief_state = self._get_daily_state(thief_id)
        if thief_state.powerup_used_today:
            raise PowerUpError("You have already used a power-up today.")

        target_state = self._get_daily_state(target_id)

        # Check for duplicate Steal
        if target_state.steal_attempt_by:
            raise PowerUpError(f"<@{target_id}> is already being targeted for theft!")

        # Attacker Penalty: Reduce streak by STEAL_STREAK_COST (minimum 0)
        thief = self.player_manager.get_player(thief_id)
        new_streak = max(
            0, (thief.answer_streak if thief else 0) - self.steal_streak_cost
        )
        self.player_manager.set_streak(thief_id, new_streak)
        self.data_manager.log_powerup_usage(thief_id, "steal", target_id, question_id)
        thief_state.stealing_from = target_id

        target_state.steal_attempt_by = thief_id
        return f"{self.emoji_stealing} You sacrificed {self.steal_streak_cost} streak days to rob <@{target_id}>! If they answer correctly, you'll steal their bonuses."

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

        # Mark as resting — blocks further guesses
        state.is_resting = True
        self.data_manager.log_powerup_usage(player_id, "rest", None, question_id)

        # Store rest multiplier for tomorrow
        self.data_manager.set_pending_multiplier(player_id, self.rest_multiplier)

        # Immediately resolve any pending attacks as whiffs
        whiff_parts = []

        if state.jinxed_by:
            attacker_id = state.jinxed_by
            state.jinxed_by = None
            whiff_parts.append(
                f"{self.emoji_jinxed} <@{attacker_id}>'s Jinx had no effect — <@{player_id}> is resting!"
            )

        if state.steal_attempt_by:
            attacker_id = state.steal_attempt_by
            state.steal_attempt_by = None
            whiff_parts.append(
                f"{self.emoji_stealing} <@{attacker_id}>'s steal whiffed — "
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
