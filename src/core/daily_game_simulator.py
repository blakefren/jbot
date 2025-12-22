import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional
from src.core.guess_handler import GuessHandler
from src.core.events import GameEvent, GuessEvent, PowerUpEvent
from src.core.player import Player


class DailyGameSimulator:
    """
    Replays the events of a day to calculate scores and states.
    """

    def __init__(
        self,
        question,
        answers: list[str],
        hint_timestamp: Optional[str],
        events: list[GameEvent],
        initial_player_states: dict[str, Player],
        config,
    ):
        self.question = question
        self.answers = answers  # List of valid answer strings (standard + corrections)
        self.hint_timestamp = hint_timestamp
        self.events = events  # List of GameEvent objects
        self.initial_player_states = initial_player_states
        self.config = config

        # Daily State per player
        self.daily_state = defaultdict(
            lambda: {
                "score_earned": 0,
                "streak_delta": 0,  # Change in streak
                "is_correct": False,
                "guesses_count": 0,
                "jinxed_by": None,
                "shield_active": False,
                "shield_used": False,
                "silenced": False,
                "bonuses": {},
                "steal_attempt_by": None,
                "stealing_from": None,
            }
        )

        # Global daily state
        self.first_correct_timestamp = None

        # Helper for matching
        self.guess_handler = GuessHandler(None, None, self.question, None, {})

    def run(self) -> dict:
        # Sort events strictly by timestamp
        self.events.sort(key=lambda x: x.timestamp)

        for event in self.events:
            if isinstance(event, PowerUpEvent):
                self.handle_powerup(event)
            elif isinstance(event, GuessEvent):
                self.handle_guess(event)

        self.end_of_day()

        return self.calculate_final_results()

    def handle_powerup(self, event: PowerUpEvent):
        user_id = event.user_id
        ptype = event.powerup_type
        target_id = event.target_user_id

        state = self.daily_state[user_id]

        if ptype == "shield":
            state["shield_active"] = True

        elif ptype == "jinx":
            if target_id:
                target_state = self.daily_state[target_id]
                if target_state["shield_active"]:
                    target_state["shield_used"] = True
                    # Jinx blocked
                else:
                    target_state["jinxed_by"] = user_id
                    state["silenced"] = True  # Attacker is silenced

        elif ptype == "steal":
            if target_id:
                target_state = self.daily_state[target_id]
                # Attacker resets streak immediately
                player = self.initial_player_states.get(user_id)
                initial_streak = player.answer_streak if player else 0
                state["streak_delta"] = -initial_streak

                state["stealing_from"] = target_id

                if target_state["shield_active"]:
                    target_state["shield_used"] = True
                    # Steal blocked
                else:
                    target_state["steal_attempt_by"] = user_id

    def handle_guess(self, event: GuessEvent):
        user_id = event.user_id
        guess_text = event.guess_text
        timestamp = event.timestamp

        state = self.daily_state[user_id]
        state["guesses_count"] += 1

        # Check correctness
        if state["is_correct"]:
            return  # Already answered correctly
        is_correct = False
        for ans in self.answers:
            if self.guess_handler._is_correct_guess(guess_text, ans):
                is_correct = True
                break
        if not is_correct:
            return

        state["is_correct"] = True

        # Calculate Points
        points = self.question.clue_value or 100
        bonuses = {}

        # 1. First Try Bonus
        if state["guesses_count"] == 1:
            bonus = int(self.config.get("JBOT_BONUS_FIRST_TRY", 20))
            points += bonus
            bonuses["first_try"] = bonus

        # 2. Before Hint Bonus
        is_before_hint = True
        if self.hint_timestamp:
            # Assuming timestamp is datetime or comparable string
            if timestamp > self.hint_timestamp:
                is_before_hint = False

        if is_before_hint:
            bonus = int(self.config.get("JBOT_BONUS_BEFORE_HINT", 10))
            points += bonus
            bonuses["before_hint"] = bonus

        # 3. Fastest / First Place
        if self.first_correct_timestamp is None:
            self.first_correct_timestamp = timestamp
            bonus = int(self.config.get("JBOT_BONUS_FIRST_PLACE", 20))
            points += bonus
            bonuses["fastest"] = bonus

        # 4. Streak Bonus
        player = self.initial_player_states.get(user_id)
        initial_streak = player.answer_streak if player else 0

        # If player used steal, their streak was reset to 0 for this calculation
        if state["stealing_from"]:
            initial_streak = 0

        if state["jinxed_by"] or state["silenced"]:
            # Jinxed or Silenced: No streak bonus
            pass
        else:
            per_day = int(self.config.get("JBOT_BONUS_STREAK_PER_DAY", 5))
            cap = int(self.config.get("JBOT_BONUS_STREAK_CAP", 25))
            streak_bonus = min(initial_streak * per_day, cap)
            if streak_bonus > 0:
                points += streak_bonus
                bonuses["streak"] = streak_bonus

        state["score_earned"] += points
        state["bonuses"] = bonuses
        state["streak_delta"] += 1

    def end_of_day(self):
        # Ensure all players are processed for streak resets if they didn't answer
        for user_id, player in self.initial_player_states.items():
            if user_id not in self.daily_state:
                # Player did nothing. Check if they should have answered.
                # If they didn't answer, reset streak.
                # Assuming standard rules: No answer = Streak Reset.
                if player.answer_streak > 0:
                    self.daily_state[user_id]["streak_delta"] = -player.answer_streak

        for user_id, state in self.daily_state.items():
            # Shield Decay
            if state["shield_active"] and not state["shield_used"]:
                state["score_earned"] -= 10

            # Steal Resolution
            steal_attempt_by = state.get("steal_attempt_by")
            if steal_attempt_by:
                thief_state = self.daily_state[steal_attempt_by]
                # Thief must also be correct to steal
                if thief_state["is_correct"] and state["is_correct"]:
                    target_bonuses = state.get("bonuses", {})
                    stolen_amount = 0

                    # Steal specific bonuses
                    for bonus_key in ["first_try", "fastest"]:
                        if bonus_key in target_bonuses:
                            amount = target_bonuses[bonus_key]
                            stolen_amount += amount

                    if stolen_amount > 0:
                        state["score_earned"] -= stolen_amount
                        thief_state["score_earned"] += stolen_amount

    def calculate_final_results(self):
        results = {}
        for user_id, state in self.daily_state.items():
            player = self.initial_player_states.get(user_id)
            initial_score = player.score if player else 0
            initial_streak = player.answer_streak if player else 0

            final_score = initial_score + state["score_earned"]
            final_streak = initial_streak + state["streak_delta"]
            if final_streak < 0:
                final_streak = 0

            results[user_id] = {
                "initial_score": initial_score,
                "final_score": final_score,
                "score_earned": state["score_earned"],
                "initial_streak": initial_streak,
                "final_streak": final_streak,
                "streak_delta": state["streak_delta"],
                "bonuses": state["bonuses"],
                "badges": self._get_badges(state),
            }
        return results

    def _get_badges(self, state):
        badges = []
        bonuses = state.get("bonuses", {})
        if "first_try" in bonuses:
            badges.append(self.config.get("JBOT_EMOJI_FIRST_TRY", "🎯"))
        if "before_hint" in bonuses:
            badges.append(self.config.get("JBOT_EMOJI_BEFORE_HINT", "🧠"))
        if "fastest" in bonuses:
            badges.append(self.config.get("JBOT_EMOJI_FASTEST", "🥇"))
        return badges
