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
        self.bonus_try_list = self._parse_csv_config("JBOT_BONUS_TRY_CSV", "20,10,5")
        self.bonus_fastest_list = self._parse_csv_config(
            "JBOT_BONUS_FASTEST_CSV", "10,5,5"
        )

        self.bonus_before_hint = int(self.config.get("JBOT_BONUS_BEFORE_HINT", 10))

        self.streak_per_day = int(self.config.get("JBOT_BONUS_STREAK_PER_DAY", 5))
        self.streak_cap = int(self.config.get("JBOT_BONUS_STREAK_CAP", 25))

        # Emojis for display
        self.emoji_first_try = self.config.get("JBOT_EMOJI_FIRST_TRY", "🎯")
        self.emoji_before_hint = self.config.get("JBOT_EMOJI_BEFORE_HINT", "🧠")
        self.emoji_fastest = self.config.get("JBOT_EMOJI_FASTEST", "🥇")
        self.emoji_fastest_list = self._parse_csv_string_config(
            "JBOT_EMOJI_FASTEST_CSV", "🥇,🥈,🥉"
        )
        self.emoji_streak = self.config.get("JBOT_EMOJI_STREAK", "🔥")

    def _parse_csv_config(self, key: str, default: str) -> list[int]:
        """Parses a CSV string from config into a list of integers."""
        raw = self.config.get(key, default)
        try:
            return [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError:
            # Fallback for bad format
            return [int(x.strip()) for x in default.split(",") if x.strip()]

    def _parse_csv_string_config(self, key: str, default: str) -> list[str]:
        """Parses a CSV string from config into a list of strings."""
        raw = self.config.get(key, default)
        return [x.strip() for x in raw.split(",") if x.strip()]

    def _get_ordinal(self, n: int) -> str:
        """Returns the ordinal representation of a number (1st, 2nd, 3rd, etc.)."""
        if 11 <= (n % 100) <= 13:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"

    def calculate_points(
        self,
        question_value: int,
        is_before_hint: bool = False,
        streak_length: int = 0,
        guesses_count: int = 1,  # Which attempt number is this? (1-based)
        answer_rank: int = 0,  # What rank is this answer? (1 for fastest, 0 for none)
    ) -> tuple[int, dict, list]:
        """
        Calculates the total points, a breakdown of bonuses, and display messages.

        Args:
            question_value (int): The base value of the question.
            is_before_hint (bool): Whether the answer was submitted before the hint.
            streak_length (int): The player's current streak (already incremented for today).
                                 If 0 or 1, no bonus is applied usually.
            guesses_count (int): The number of guesses made including this one (1=1st try).
            answer_rank (int): The rank of this correct answer (1=1st fastest). 0 if no rank bonus applies or unknown.

        Returns:
            points_earned (int): Total score.
            bonuses (dict): Dictionary mapping bonus keys ('first_try', etc.) to amounts.
            messages (list): List of formatted strings confirming bonuses.
        """

        points_earned = question_value
        bonuses = {}
        messages = []

        # 1. Try/Guess Bonus (Tiered)
        if 0 < guesses_count <= len(self.bonus_try_list):
            bonus = self.bonus_try_list[guesses_count - 1]
            if bonus > 0:
                points_earned += bonus
                bonuses[f"try_{guesses_count}"] = bonus

                # Special messaging/aliasing for 1st try
                if guesses_count == 1:
                    bonuses["first_try"] = bonus
                    messages.append(f"{self.emoji_first_try} First try! (+{bonus})")
                else:
                    messages.append(f"Try #{guesses_count}! (+{bonus})")

        # 2. Before Hint Bonus
        if is_before_hint:
            points_earned += self.bonus_before_hint
            bonuses["before_hint"] = self.bonus_before_hint
            messages.append(
                f"{self.emoji_before_hint} Pre-hint! (+{self.bonus_before_hint})"
            )

        # 3. Fastest Bonus (Tiered)
        if 0 < answer_rank <= len(self.bonus_fastest_list):
            bonus = self.bonus_fastest_list[answer_rank - 1]
            if bonus > 0:
                points_earned += bonus
                bonuses[f"fastest_{answer_rank}"] = bonus

                # Get emoji for this rank
                rank_emoji = self.emoji_fastest  # Default fallback
                if 0 < answer_rank <= len(self.emoji_fastest_list):
                    rank_emoji = self.emoji_fastest_list[answer_rank - 1]

                # Special messaging/aliasing for 1st fastest
                if answer_rank == 1:
                    bonuses["fastest"] = bonus
                    messages.append(f"{rank_emoji} Fastest! (+{bonus})")
                else:
                    ordinal = self._get_ordinal(answer_rank)
                    messages.append(f"{rank_emoji} {ordinal} Fastest! (+{bonus})")

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

        # Check explicit fastest keys
        for key, val in bonuses.items():
            if key.startswith("fastest_"):
                stealable += val

        # Fallback/Legacy: If 'fastest' is present but 'fastest_1' is not (shouldn't happen with new logic but for safety)
        if "fastest" in bonuses and "fastest_1" not in bonuses:
            stealable += bonuses["fastest"]

        # Check explicit try keys
        for key, val in bonuses.items():
            if key.startswith("try_"):
                stealable += val

        # Fallback/Legacy
        if "first_try" in bonuses and "try_1" not in bonuses:
            stealable += bonuses["first_try"]

        # Handle 'first_place' key alias if it exists from legacy data
        if "first_place" in bonuses:
            stealable += bonuses["first_place"]

        return stealable
