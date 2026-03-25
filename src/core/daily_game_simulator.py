import logging
from collections import defaultdict
from datetime import datetime
from src.core.answer_checker import AnswerChecker
from src.core.events import GameEvent, GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.state import DailyPlayerState
from src.core.scoring import ScoreCalculator
from src.core.powerup_engine import PowerUpEngine


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
        self.engine = PowerUpEngine(self.config)

        # Daily State per player
        self.daily_state = defaultdict(DailyPlayerState)

        # Global daily state
        self.first_correct_timestamp = None
        self.correct_answers_count = 0

        # Helper for answer matching
        self.checker = AnswerChecker()

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

        if ptype == "rest":
            self.engine.apply_rest(self.daily_state, user_id)

        elif ptype in ("jinx", "jinx_preload"):
            if target_id:
                self.engine.apply_jinx(self.daily_state, user_id, target_id)

        elif ptype == "jinx_late":
            if target_id:
                self.engine.apply_late_jinx(self.daily_state, user_id, target_id)

        elif ptype == "steal_preload":
            if target_id:
                self.engine.apply_steal(
                    self.daily_state,
                    user_id,
                    target_id,
                    initial_streak=0,
                    is_preload=True,
                )

        elif ptype == "steal":
            if target_id:
                player = self.initial_player_states.get(user_id)
                initial_streak = player.answer_streak if player else 0
                self.engine.apply_steal(
                    self.daily_state, user_id, target_id, initial_streak
                )

        elif ptype == "rest_wakeup":
            # Bonus from a previous day's rest was already applied live to the DB.
            # No simulator state change needed.
            pass

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
            if self.checker.is_correct(guess_text, ans):
                is_correct = True
                break
        if not is_correct:
            return

        state.is_correct = True

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

        # If player used a daytime steal, their streak was reduced by JBOT_STEAL_STREAK_COST
        # for this score calculation. For steal_preload, the cost is already in the snapshot.
        if state.stealing_from and not state.steal_is_preload:
            steal_streak_cost = int(self.config.get("JBOT_STEAL_STREAK_COST", "3"))
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
                transferred = self.engine.resolve_jinx_on_correct(
                    self.daily_state, user_id, bonuses
                )
                points -= transferred

        state.score_earned += points
        state.bonuses = bonuses
        state.streak_delta += 1

        # Resolve Steal
        if state.steal_attempt_by:
            self.engine.resolve_steal_on_correct(self.daily_state, user_id)

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
                    stolen_amount = self.score_calculator.pop_stealable_bonuses(
                        state.bonuses
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
                "badges": self._get_badges(state.bonuses),
            }
        return results

    # Maps bonus keys (from ScoreCalculator) to their display emoji config keys.
    # Add new bonus types here as they are introduced in scoring.py.
    _BONUS_EMOJI_MAP = [
        ("first_try", "JBOT_EMOJI_FIRST_TRY"),
        ("before_hint", "JBOT_EMOJI_BEFORE_HINT"),
        ("fastest", "JBOT_EMOJI_FASTEST"),
        ("streak", "JBOT_EMOJI_STREAK"),
    ]

    def _get_badges(self, bonus_keys):
        return [
            self.config.get(emoji_key)
            for bonus_key, emoji_key in self._BONUS_EMOJI_MAP
            if bonus_key in bonus_keys
        ]
