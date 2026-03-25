import logging
from datetime import date, timedelta, datetime
from src.core.data_manager import DataManager
from data.readers.question import Question
from src.core.scoring import ScoreCalculator
from src.core.answer_checker import AnswerChecker
from src.cfg.main import ConfigReader
from src.core.events import GuessContext


class AlreadyAnsweredCorrectlyError(Exception):
    """Raised when a player tries to answer a question they have already answered correctly."""

    pass


class JinxedError(Exception):
    """Raised when a player is jinxed and cannot answer."""

    def __init__(self, message):
        self.message = message
        super().__init__(message)


class GuessHandler:
    """
    Handles guess processing and validation.
    """

    def __init__(
        self,
        data_manager: DataManager,
        player_manager,
        daily_question: Question,
        daily_question_id: int,
        managers: dict,
        fuzzy_threshold=2,
        reminder_time=None,
        config: ConfigReader = None,
    ):
        self.data_manager = data_manager
        self.player_manager = player_manager
        self.daily_q = daily_question
        self.daily_question_id = daily_question_id
        self.managers = managers
        self.fuzzy_threshold = fuzzy_threshold
        self.reminder_time = reminder_time
        self.config = config or ConfigReader()
        self.score_calculator = ScoreCalculator(self.config)
        self._checker = AnswerChecker()

        if self.data_manager:
            self.alternative_answers = self.data_manager.get_alternative_answers(
                self.daily_question_id
            )
        else:
            self.alternative_answers = []

    def get_player_guesses(self, player_id: int) -> list:
        """
        Returns all guesses for the current daily question for the given player.
        """
        if not self.daily_question_id:
            return []
        guesses = self.data_manager.read_guess_history(user_id=player_id)
        # Only include guesses for the current daily question
        return [
            g.get("guess_text")
            for g in guesses
            if g.get("daily_question_id") == self.daily_question_id
        ]

    def has_answered_correctly_today(self, player_id: int) -> bool:
        """
        Checks if the player has already answered today's question correctly.
        """
        if not self.daily_question_id:
            return False

        guesses = self.data_manager.read_guess_history(user_id=player_id)
        for guess in guesses:
            if guess.get("daily_question_id") == self.daily_question_id and guess.get(
                "is_correct"
            ):
                return True
        return False

    def handle_guess(
        self, player_id: int, player_name: str, guess: str
    ) -> tuple[bool, int, int, list[str]]:
        """
        Handles the answer submitted by a player, logs it, and returns correctness.

        Args:
            player_id (int): The Discord ID of the player.
            player_name (str): The Discord display name of the player.
            guess (str): The player's guess.

        Returns:
            tuple: (is_correct, num_guesses, points_earned, bonus_messages)
        """
        if not self.daily_q:
            return False, 0, 0, []  # No active question

        # Check if the player has already answered correctly today
        if self.has_answered_correctly_today(player_id):
            raise AlreadyAnsweredCorrectlyError()

        # Check if hint has been sent
        hint_timestamp = self.data_manager.get_hint_sent_timestamp(
            self.daily_question_id
        )
        hint_sent = hint_timestamp is not None

        # Check if player is allowed to answer (e.g. Jinxed)
        for manager in self.managers.values():
            if hasattr(manager, "can_answer"):
                try:
                    can_answer, reason = manager.can_answer(
                        str(player_id), hint_sent=hint_sent
                    )
                except TypeError:
                    # Fallback for managers that don't accept hint_sent
                    can_answer, reason = manager.can_answer(str(player_id))

                if not can_answer:
                    raise JinxedError(reason)

        g = guess.strip().lower()
        a = str(self.daily_q.answer).strip().lower()
        is_correct = self._checker.is_correct(g, a)

        # Check alternative answers if primary answer is incorrect
        if not is_correct:
            for alt_answer in self.alternative_answers:
                alt_a = str(alt_answer).strip().lower()
                if self._checker.is_correct(g, alt_a):
                    is_correct = True
                    break

        points_earned = 0
        bonus_messages = []
        bonus_values = {}

        if is_correct:
            # Gather inputs for ScoreCalculator
            base_value = self.daily_q.clue_value or 100

            # Check Rank (before logging this guess)
            existing_correct_count = self.data_manager.get_correct_guess_count(
                self.daily_question_id
            )
            answer_rank = existing_correct_count + 1

            # Check Attempt Number (before logging this guess)
            previous_guesses = self.get_player_guesses(player_id)
            guesses_count = len(previous_guesses) + 1

            # Check Before Hint (before logging this guess)
            is_before_hint = False
            if self.reminder_time:
                now = datetime.now(self.reminder_time.tzinfo)
                if now.timetz() < self.reminder_time:
                    is_before_hint = True

            # Determine Streak details
            player = self.player_manager.get_player(str(player_id))
            current_streak = player.answer_streak if player else 0

            last_correct_date = self.data_manager.get_last_correct_guess_date(
                str(player_id)
            )
            today = self.data_manager.get_today()

            if last_correct_date == today:
                # Already answered correctly today (e.g. skipped question)
                new_streak = current_streak
            else:
                new_streak = current_streak + 1

            # Calculate Points via shared engine
            points_earned, bonus_values, bonus_messages = (
                self.score_calculator.calculate_points(
                    question_value=base_value,
                    guesses_count=guesses_count,
                    is_before_hint=is_before_hint,
                    answer_rank=answer_rank,
                    streak_length=new_streak,
                )
            )

            # Apply Score & Streak
            self.player_manager.get_or_create_player(str(player_id), player_name)
            self.player_manager.update_score(str(player_id), points_earned)
            if last_correct_date != today:
                self.player_manager.increment_streak(str(player_id), player_name)

        self.data_manager.log_player_guess(
            player_id, player_name, self.daily_question_id, g, is_correct
        )
        logging.info(f"Player {player_name} guessed '{g}'. Correct: {is_correct}")

        # Build context and pass to all managers
        ctx = GuessContext(
            player_id=player_id,
            player_name=player_name,
            guess=guess,
            is_correct=is_correct,
            points_earned=points_earned,
            bonus_values=bonus_values,
            bonus_messages=bonus_messages,
            question_id=self.daily_question_id,
        )

        for manager in self.managers.values():
            if manager is not None and not isinstance(manager, type):
                msgs = manager.on_guess(ctx)
                if msgs and isinstance(msgs, list):
                    bonus_messages.extend(msgs)

        # Get the number of guesses for this question
        num_guesses = len(self.get_player_guesses(player_id))

        return is_correct, num_guesses, ctx.points_earned, bonus_messages
