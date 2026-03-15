import logging
from collections import defaultdict
from datetime import datetime
from src.core.guess_handler import GuessHandler
from src.core.events import GameEvent, GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.state import DailyPlayerState
from src.core.scoring import ScoreCalculator


class DailyGameSimulator:
    """
    Replays the events of a day to calculate scores and states.
    """

    def __init__(
        self,
        question,
        answers: list[str],
        hint_timestamp: str | None,
        events: list[GameEvent],
        initial_player_states: dict[str, Player],
        config,
    ):
        self.question = question
        self.answers = answers  # List of valid answer strings (standard + corrections)
        # Normalize hint_timestamp to datetime for consistent comparison
        if isinstance(hint_timestamp, str):
            self.hint_timestamp = datetime.fromisoformat(hint_timestamp)
        else:
            self.hint_timestamp = hint_timestamp  # datetime or None
        self.events = events  # List of GameEvent objects
        self.initial_player_states = initial_player_states
        self.config = config
        self.score_calculator = ScoreCalculator(self.config)

        # Daily State per player
        self.daily_state = defaultdict(DailyPlayerState)

        # Global daily state
        self.first_correct_timestamp = None
        self.correct_answers_count = 0

        # Helper for matching
        self.guess_handler = GuessHandler(None, None, self.question, None, {})

    def run(self, apply_end_of_day: bool = True) -> dict:
        """
        Runs the simulation.
        Args:
            apply_end_of_day (bool): Whether to apply end-of-day logic (decay, resets).
                                     Set to False for midday state restoration.
        """

        # Sort events strictly by timestamp, normalizing to datetime for comparison
        def _ts_key(event):
            ts = event.timestamp
            if isinstance(ts, datetime):
                return ts
            if isinstance(ts, str):
                return datetime.fromisoformat(ts)
            return datetime.fromisoformat(str(ts))

        self.events.sort(key=_ts_key)

        for event in self.events:
            if isinstance(event, PowerUpEvent):
                self.handle_powerup(event)
            elif isinstance(event, GuessEvent):
                self.handle_guess(event)

        if apply_end_of_day:
            self.end_of_day()

        return self.calculate_final_results()

    def handle_powerup(self, event: PowerUpEvent):
        user_id = event.user_id
        ptype = event.powerup_type
        target_id = event.target_user_id

        state = self.daily_state[user_id]

        if ptype == "rest":
            state.is_resting = True
            # Immediately resolve pending attacks as whiffs (same as live game)
            if state.jinxed_by:
                state.jinxed_by = None
            if state.steal_attempt_by:
                state.steal_attempt_by = None

        elif ptype == "jinx":
            if target_id:
                target_state = self.daily_state[target_id]
                target_state.jinxed_by = user_id
                state.silenced = True  # Attacker is silenced

        elif ptype == "steal":
            if target_id:
                target_state = self.daily_state[target_id]
                # Attacker loses JBOT_STEAL_STREAK_COST streak days (minimum 0)
                steal_streak_cost = int(self.config.get("JBOT_STEAL_STREAK_COST", "2"))
                player = self.initial_player_states.get(user_id)
                initial_streak = player.answer_streak if player else 0
                state.streak_delta = -min(steal_streak_cost, initial_streak)

                state.stealing_from = target_id

                target_state.steal_attempt_by = user_id

        elif ptype == "wager":
            try:
                amount = int(event.amount)
            except (ValueError, TypeError):
                amount = 0
            state.wager = amount
            # Wager is deducted immediately in real-time.
            state.score_earned -= amount

        elif ptype == "teamup":
            if target_id:
                state.team_partner = target_id
                # Also set partner's partner
                partner_state = self.daily_state[target_id]
                partner_state.team_partner = user_id

                # Teamup cost
                cost = int(self.config.get("JBOT_REINFORCE_COST"))
                state.score_earned -= cost
                partner_state.score_earned -= cost

        else:
            logging.warning(
                "DailyGameSimulator: unrecognised powerup type %r for user %s — skipping.",
                ptype,
                user_id,
            )

    def handle_guess(self, event: GuessEvent):
        user_id = event.user_id
        guess_text = event.guess_text
        timestamp = event.timestamp

        state = self.daily_state[user_id]
        state.guesses_count += 1

        # Check correctness
        if state.is_correct or state.is_resting:
            return  # Already answered or resting
        is_correct = False
        for ans in self.answers:
            if self.guess_handler._is_correct_guess(guess_text, ans):
                is_correct = True
                break
        if not is_correct:
            # Resolve Wager (Loss)
            if state.wager > 0:
                state.wager = 0
            return

        state.is_correct = True

        # Resolve Wager (Win)
        wager = state.wager
        if wager > 0:
            # Calculate winnings
            player = self.initial_player_states.get(user_id)
            initial_score = player.score if player else 0
            # Current score before this guess (including wager deduction)
            current_score = initial_score + state.score_earned

            # Match PowerUpManager logic: winnings = int(wager * (100 / (score + 100)))
            # We add back the wager amount plus the winnings
            winnings = int(wager * (100 / (current_score + 100)))

            state.score_earned += winnings + wager
            state.wager = 0  # Consumed

        # Resolve Teamup
        partner_id = state.team_partner
        if partner_id:
            state.team_success = True
            self.daily_state[partner_id].team_success = True

        # Calculate Points
        base_value = self.question.clue_value or 100

        guesses_count = state.guesses_count

        is_before_hint = True
        if self.hint_timestamp:
            # Normalize event timestamp to datetime for comparison
            ts_dt = (
                datetime.fromisoformat(timestamp)
                if isinstance(timestamp, str)
                else timestamp
            )
            if ts_dt > self.hint_timestamp:
                is_before_hint = False

        # Check Answer Rank
        # In live game, this is based on DB count strictly.
        self.correct_answers_count += 1
        answer_rank = self.correct_answers_count

        # Streak Prep
        player = self.initial_player_states.get(user_id)
        initial_streak = player.answer_streak if player else 0

        # If player used steal, their streak was reduced by JBOT_STEAL_STREAK_COST for this calculation
        if state.stealing_from:
            steal_streak_cost = int(self.config.get("JBOT_STEAL_STREAK_COST", "2"))
            initial_streak = max(0, initial_streak - steal_streak_cost)

        streak_length = initial_streak + 1

        # Calculate via shared engine
        points, bonuses, _ = self.score_calculator.calculate_points(
            question_value=base_value,
            guesses_count=guesses_count,
            is_before_hint=is_before_hint,
            answer_rank=answer_rank,
            streak_length=streak_length,
        )

        # Apply Jinx/Silence Logic (Remove Streak Bonus, Transfer to Attacker)
        if state.jinxed_by or state.silenced:
            if "streak" in bonuses:
                streak_val = bonuses.pop("streak")
                points -= streak_val
                if state.jinxed_by:
                    attacker_state = self.daily_state[state.jinxed_by]
                    attacker_state.score_earned += streak_val

        state.score_earned += points
        state.bonuses = bonuses
        state.streak_delta += 1

        # Resolve Steal
        attacker_id = state.steal_attempt_by
        if attacker_id:
            stealable = self.score_calculator.get_stealable_amount(bonuses)

            if stealable > 0:
                state.score_earned -= stealable
                attacker_state = self.daily_state[attacker_id]
                attacker_state.score_earned += stealable
                # Do not clear stealing_from, as it marks the player as having used steal (resetting streak)

            state.steal_attempt_by = None

    def end_of_day(self):
        # Ensure all players are processed for streak resets if they didn't answer
        for user_id, player in self.initial_player_states.items():
            if user_id not in self.daily_state:
                # Player did nothing. Check if they should have answered.
                # If they didn't answer, reset streak.
                # Assuming standard rules: No answer = Streak Reset.
                if player.answer_streak > 0:
                    self.daily_state[user_id].streak_delta = -player.answer_streak

        for user_id, state in self.daily_state.items():
            # Resting players: streak is frozen (streak_delta stays 0)
            if state.is_resting:
                continue

            # Steal Resolution
            steal_attempt_by = state.steal_attempt_by
            if steal_attempt_by:
                thief_state = self.daily_state[steal_attempt_by]
                # Thief must also be correct to steal
                if thief_state.is_correct and state.is_correct:
                    target_bonuses = state.bonuses
                    stolen_amount = self.score_calculator.get_stealable_amount(
                        target_bonuses
                    )

                    if stolen_amount > 0:
                        state.score_earned -= stolen_amount
                        thief_state.score_earned += stolen_amount

    def calculate_final_results(self):
        results = {}
        for user_id, state in self.daily_state.items():
            player = self.initial_player_states.get(user_id)
            initial_score = player.score if player else 0
            initial_streak = player.answer_streak if player else 0

            final_score = initial_score + state.score_earned
            final_streak = initial_streak + state.streak_delta
            if final_streak < 0:
                final_streak = 0

            results[user_id] = {
                "initial_score": initial_score,
                "final_score": final_score,
                "score_earned": state.score_earned,
                "initial_streak": initial_streak,
                "final_streak": final_streak,
                "streak_delta": state.streak_delta,
                "bonuses": state.bonuses,
                "badges": self._get_badges(state),
            }
        return results

    def _get_badges(self, state):
        badges = []
        bonuses = state.bonuses
        if "first_try" in bonuses:
            badges.append(self.config.get("JBOT_EMOJI_FIRST_TRY"))
        if "before_hint" in bonuses:
            badges.append(self.config.get("JBOT_EMOJI_BEFORE_HINT"))
        if "fastest" in bonuses:
            badges.append(self.config.get("JBOT_EMOJI_FASTEST"))
        return badges
