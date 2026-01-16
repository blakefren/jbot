from src.cfg.main import ConfigReader


class ScoreCalculator:
    """
    Centralized logic for calculating scores and bonuses to ensure consistency
    between the live game (GuessHandler) and the simulator (DailyGameSimulator).
    """

    def __init__(self, config: ConfigReader = None):
        if config is None:
            config = ConfigReader()
        self.config = config

        # Cache config values
        self.bonus_first_try = int(self.config.get("JBOT_BONUS_FIRST_TRY", 20))
        self.bonus_before_hint = int(self.config.get("JBOT_BONUS_BEFORE_HINT", 10))
        # Discrepancy Resolved: Defaulting to 10 (Live value) instead of 20 (Sim value)
        self.bonus_fastest = int(self.config.get("JBOT_BONUS_FASTEST", 10))

        self.streak_per_day = int(self.config.get("JBOT_BONUS_STREAK_PER_DAY", 5))
        self.streak_cap = int(self.config.get("JBOT_BONUS_STREAK_CAP", 25))

        # Emojis for display
        self.emoji_first_try = self.config.get("JBOT_EMOJI_FIRST_TRY", "🎯")
        self.emoji_before_hint = self.config.get("JBOT_EMOJI_BEFORE_HINT", "🧠")
        self.emoji_fastest = self.config.get("JBOT_EMOJI_FASTEST", "🥇")
        self.emoji_streak = self.config.get("JBOT_EMOJI_STREAK", "🔥")

    def calculate_points(
        self,
        question_value: int,
        is_first_try: bool,
        is_before_hint: bool,
        is_fastest: bool,
        streak_length: int = 0,
    ) -> tuple[int, dict, list]:
        """
        Calculates the total points, a breakdown of bonuses, and display messages.

        Args:
            question_value (int): The base value of the question.
            is_first_try (bool): Whether the player answered on their first guess.
            is_before_hint (bool): Whether the answer was submitted before the hint.
            is_fastest (bool): Whether this is the first correct answer of the day.
            streak_length (int): The player's current streak (already incremented for today).
                                 If 0 or 1, no bonus is applied usually.

        Returns:
            points_earned (int): Total score.
            bonuses (dict): Dictionary mapping bonus keys ('first_try', etc.) to amounts.
            messages (list): List of formatted strings confirming bonuses.
        """
        points_earned = question_value
        bonuses = {}
        messages = []

        # 1. First Try Bonus
        if is_first_try:
            points_earned += self.bonus_first_try
            bonuses["first_try"] = self.bonus_first_try
            messages.append(
                f"{self.emoji_first_try} First try! (+{self.bonus_first_try})"
            )

        # 2. Before Hint Bonus
        if is_before_hint:
            points_earned += self.bonus_before_hint
            bonuses["before_hint"] = self.bonus_before_hint
            messages.append(
                f"{self.emoji_before_hint} Pre-hint! (+{self.bonus_before_hint})"
            )

        # 3. Fastest Bonus
        if is_fastest:
            points_earned += self.bonus_fastest
            bonuses["fastest"] = self.bonus_fastest
            messages.append(f"{self.emoji_fastest} Fastest! (+{self.bonus_fastest})")

        # 4. Streak Bonus
        # Streak bonus logic: min(streak * per_day, cap)
        # Usually applied if streak >= 2
        if streak_length >= 2:
            streak_bonus = min(streak_length * self.streak_per_day, self.streak_cap)
            if streak_bonus > 0:
                points_earned += streak_bonus
                bonuses["streak"] = streak_bonus
                messages.append(
                    f"{self.emoji_streak} {streak_length}-day streak! (+{streak_bonus})"
                )

        return points_earned, bonuses, messages

    def get_stealable_amount(self, bonuses: dict) -> int:
        """
        Determines how many points can be stolen based on the bonuses earned.
        Standardizes 'Steal' logic across Live and Sim.

        Rules:
        - Fastest bonus is stealable.
        - First Try bonus is stealable.
        """
        stealable = 0
        if "fastest" in bonuses:
            stealable += bonuses["fastest"]
        # Handle 'first_place' key alias if it exists from legacy data
        elif "first_place" in bonuses:
            stealable += bonuses["first_place"]

        if "first_try" in bonuses:
            stealable += bonuses["first_try"]

        return stealable
