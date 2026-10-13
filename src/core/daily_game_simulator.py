import logging
from collections import defaultdict
from src.core.answer_checker import AnswerChecker
from src.core.events import GameEvent, GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.state import DailyPlayerState
from src.core.scoring import ScoreCalculator
from src.core.game_event_service import GameEventService
from src.core.game_reducer import DailyGameReducer
from src.core.utils import parse_timestamp


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
        answer_checker: AnswerChecker = None,
        prev_streak_keepers: set[str] | None = None,
    ):
        self.question = question
        self.answers = answers  # List of valid answer strings (standard + corrections)
        # Normalize hint_timestamp to datetime for consistent comparison
        self.hint_timestamp = parse_timestamp(hint_timestamp)
        self.events = events  # List of GameEvent objects
        self.initial_player_states = initial_player_states
        self.config = config
        self.score_calculator = ScoreCalculator(self.config)
        self.event_service = GameEventService(self.config)
        self.reducer = DailyGameReducer(self.config)
        # Players who kept their streak yesterday (grace period: one missed day allowed)
        self.prev_streak_keepers: set[str] = prev_streak_keepers or set()

        # Daily State per player
        self.daily_state = defaultdict(DailyPlayerState)
        self.pending_rest_multiplier_consumed: set[str] = set()

        # Global daily state
        self.first_correct_timestamp = None
        self.correct_answers_count = 0

        # Helper for answer matching
        self.checker = answer_checker or AnswerChecker()

    def run(self, apply_end_of_day: bool = True) -> dict:
        """
        Runs the simulation.
        Args:
            apply_end_of_day (bool): Whether to apply end-of-day logic (decay, resets).
                                     Set to False for midday state restoration.
        """

        # Sort events strictly by timestamp, normalizing to datetime for comparison
        self.events.sort(key=lambda event: parse_timestamp(event.timestamp))

        for event in self.events:
            if isinstance(event, PowerUpEvent):
                self.handle_powerup(event)
            elif isinstance(event, GuessEvent):
                self.handle_guess(event)

        if apply_end_of_day:
            self.end_of_day()

        return self.calculate_final_results()

    def handle_powerup(self, event: PowerUpEvent):
        if event.powerup_type in {"rest_wakeup", "crowd_wisdom"}:
            # Rest bonus was already applied during handle_guess (before jinx resolution)
            pass
            return

        player = self.initial_player_states.get(event.user_id)
        initial_streak = player.answer_streak if player else 0
        transition = self.event_service.process_powerup(
            self.daily_state, event, initial_streak=initial_streak
        )
        if transition.rejection_reason:
            logging.warning(
                "Skipping rejected replay power-up event: user_id=%s, type=%s, "
                "target_id=%s, reason=%s",
                event.user_id,
                event.powerup_type,
                event.target_user_id,
                transition.rejection_reason,
            )

    def handle_guess(self, event: GuessEvent):
        user_id = event.user_id
        guess_text = event.guess_text
        timestamp = event.timestamp

        state = self.daily_state.get(user_id, DailyPlayerState())
        if state.is_correct or state.is_resting:
            self._reduce_guess(user_id, is_correct=False)
            return

        is_correct = False
        for ans in self.answers:
            if self.checker.is_correct(guess_text, ans):
                is_correct = True
                break

        if not is_correct:
            self._reduce_guess(user_id, is_correct=False)
            return

        # Calculate Points
        base_value = self.question.clue_value or 100

        guesses_count = state.guesses_count + 1

        is_before_hint = True
        if self.hint_timestamp:
            ts_dt = parse_timestamp(timestamp)
            if ts_dt and ts_dt > self.hint_timestamp:
                is_before_hint = False

        # Check Answer Rank
        # In live game, this is based on DB count strictly.
        self.correct_answers_count += 1
        answer_rank = self.correct_answers_count

        # Streak Prep
        player = self.initial_player_states.get(user_id)
        initial_streak = player.answer_streak if player else 0

        # If player used any steal (daytime or preload), apply the streak cost to
        # initial_streak so scoring uses the correct post-cost streak length.
        # streak_delta was set by apply_steal with the correct cost (normal vs retro),
        # so deriving from it avoids duplicating config reads and fixes the retro-steal bug.
        if state.stealing_from:
            initial_streak = max(0, initial_streak + state.streak_delta)

        streak_length = initial_streak + 1

        # Calculate via shared engine
        points, bonuses, _ = self.score_calculator.calculate_points(
            question_value=base_value,
            guesses_count=guesses_count,
            is_before_hint=is_before_hint,
            answer_rank=answer_rank,
            streak_length=streak_length,
        )

        player = self.initial_player_states.get(user_id)
        pending_mult = float(player.pending_rest_multiplier or 0.0) if player else 0.0
        transition = self._reduce_guess(
            user_id,
            is_correct=True,
            points_earned=points,
            bonuses=bonuses,
            pending_rest_multiplier=pending_mult,
        )
        if transition.consume_pending_rest_multiplier:
            self.pending_rest_multiplier_consumed.add(user_id)

    def _reduce_guess(self, player_id: str, **kwargs):
        """Apply a copy-on-write guess reduction and retain defaultdict behavior."""
        result = self.reducer.reduce_guess(self.daily_state, player_id, **kwargs)
        self.daily_state = defaultdict(DailyPlayerState, result.daily_state)
        return result.transition

    def end_of_day(self):
        # Crowd Wisdom is an end-of-day/post-resolution bonus.
        self.apply_crowd_wisdom_bonus()

        # Reset streaks for all players who didn't answer correctly and aren't resting.
        # Grace period: if a player answered correctly (or rested) on the previous day,
        # their streak is preserved even if they missed today.
        # This covers both players who submitted wrong guesses (in daily_state with
        # is_correct=False) and players who didn't guess at all (not in daily_state).
        for user_id, player in self.initial_player_states.items():
            state = self.daily_state.get(user_id)
            is_correct = state is not None and state.is_correct
            is_resting = state is not None and state.is_resting
            has_grace = user_id in self.prev_streak_keepers
            if (
                not is_correct
                and not is_resting
                and not has_grace
                and player.answer_streak > 0
            ):
                self.daily_state[user_id].streak_delta = -player.answer_streak

    def _get_crowd_wisdom_counts(self) -> tuple[int, int]:
        """
        Returns (correct_solvers, active_participants) from replay state.

        Note: this mirrors DataManager.get_daily_active_participant_count() criteria
        but lives here to keep the simulator free of DataManager/DB dependencies.
        """
        correct_solvers = 0
        active_participants = 0
        for state in self.daily_state.values():
            if state.is_correct:
                correct_solvers += 1
            if state.is_correct or state.is_resting or state.guesses_count > 0:
                active_participants += 1
        return correct_solvers, active_participants

    def apply_crowd_wisdom_bonus(self):
        """Apply crowd wisdom bonus after all daily events are resolved."""
        correct_solvers, active_participants = self._get_crowd_wisdom_counts()
        if active_participants <= 0:
            return

        multiplier = self.score_calculator.get_crowd_wisdom_multiplier(
            correct_solvers, active_participants
        )
        if multiplier <= 0:
            return

        for state in self.daily_state.values():
            if not state.is_correct:
                continue
            bonus = self.score_calculator.calculate_crowd_wisdom_bonus(
                state.score_earned, correct_solvers, active_participants
            )
            if bonus > 0:
                state.score_earned += bonus
                state.bonuses[ScoreCalculator.KEY_CROWD_WISDOM] = bonus

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

            initial_season_score = player.season_score if player else 0
            final_season_score = initial_season_score + state.score_earned

            results[user_id] = {
                "initial_score": initial_score,
                "final_score": final_score,
                "initial_season_score": initial_season_score,
                "final_season_score": final_season_score,
                "score_earned": state.score_earned,
                "initial_streak": initial_streak,
                "final_streak": final_streak,
                "streak_delta": state.streak_delta,
                "bonuses": state.bonuses,
                "badges": self._get_badges(state.bonuses),
                "consume_pending_rest_multiplier": (
                    user_id in self.pending_rest_multiplier_consumed
                ),
            }
        return results

    # Maps bonus keys (from ScoreCalculator) to their display emoji config keys.
    # Add new bonus types here as they are introduced in scoring.py.
    _BONUS_EMOJI_MAP = [
        (ScoreCalculator.KEY_FIRST_TRY, "JBOT_EMOJI_FIRST_TRY"),
        (ScoreCalculator.KEY_BEFORE_HINT, "JBOT_EMOJI_BEFORE_HINT"),
        (ScoreCalculator.KEY_FASTEST, "JBOT_EMOJI_FASTEST"),
        (ScoreCalculator.KEY_STREAK, "JBOT_EMOJI_STREAK"),
    ]

    def _get_badges(self, bonus_keys):
        return [
            self.config.get(emoji_key)
            for bonus_key, emoji_key in self._BONUS_EMOJI_MAP
            if bonus_key in bonus_keys
        ]
