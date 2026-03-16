"""
Answer matching logic for jbot trivia game.

Extracted from GuessHandler so it can be used independently by both
GuessHandler (live game) and DailyGameSimulator (event replay).
"""

import re

import jellyfish

CRUCIAL_MODIFIERS = {"north", "south", "east", "west", "new", "no"}


class AnswerChecker:
    """
    Stateless answer-matching logic: normalization, fuzzy matching, and token comparison.
    """

    def normalize(self, text: str) -> str:
        """Applies cleaning and normalization rules to a string."""
        if not text:
            return ""

        text = text.lower().strip()

        # Convert written numbers to digits
        replacements = {
            r"\bone\b": "1",
            r"\btwo\b": "2",
            r"\bthree\b": "3",
            r"\bfour\b": "4",
            r"\bfive\b": "5",
            r"\bsix\b": "6",
            r"\bseven\b": "7",
            r"\beight\b": "8",
            r"\bnine\b": "9",
            r"\bten\b": "10",
        }
        for word, num in replacements.items():
            text = re.sub(word, num, text)

        # Remove common stop words
        stop_words = [
            "a",
            "an",
            "the",
            "and",
            "or",
            "of",
            "to",
            "in",
            "on",
            "at",
            "by",
            "for",
            "with",
        ]
        pattern = r"\b(" + "|".join(stop_words) + r")\b"
        text = re.sub(pattern, "", text)

        # Remove all non-alphanumeric characters
        text = re.sub(r"[^\w\s]", "", text)

        # Replace multiple spaces with a single space
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def get_adaptive_limit(self, text: str) -> int:
        """Returns the allowed edit distance based on string length."""
        length = len(text)
        if length < 3:
            return 0  # Exact match only
        elif length <= 5:
            return 1  # Strict for short words
        else:
            return 2  # Standard tolerance

    def is_token_match(self, token1: str, token2: str) -> bool:
        """Returns True if tokens match by Edit Distance OR Jaro-Winkler similarity."""
        limit = self.get_adaptive_limit(token2)
        dist = jellyfish.damerau_levenshtein_distance(token1, token2)
        if dist <= limit:
            return True

        score = jellyfish.jaro_winkler_similarity(token1, token2)
        if score >= 0.90:
            return True

        return False

    def smart_token_match(self, guess: str, answer: str) -> bool:
        """Checks if tokens match using Damerau-Levenshtein and adaptive thresholds."""
        tokens_g = guess.split()
        tokens_a = answer.split()

        if not tokens_g or not tokens_a:
            return False

        # Recall: percentage of answer words found in guess
        matches_a = 0
        matched_answer_tokens = set()
        for ta in tokens_a:
            if any(self.is_token_match(tg, ta) for tg in tokens_g):
                matches_a += 1
                matched_answer_tokens.add(ta)

        # Crucial modifier guard: missing important directional/qualifier words → reject
        missing_tokens = set(tokens_a) - matched_answer_tokens
        if not missing_tokens.isdisjoint(CRUCIAL_MODIFIERS):
            return False

        recall = matches_a / len(tokens_a)

        # Precision: percentage of guess words found in answer
        matches_g = 0
        for tg in tokens_g:
            if any(self.is_token_match(tg, ta) for ta in tokens_a):
                matches_g += 1

        precision = matches_g / len(tokens_g)

        # Subset match: all guess words appear in answer, and at least half answer covered
        if precision == 1.0 and recall >= 0.5:
            return True

        # Superset match: all answer words covered in a multi-word answer
        if recall == 1.0 and len(answer) > 3:
            return True

        return False

    def is_correct(self, guess: str, answer: str) -> bool:
        """Checks a guess against an answer using normalization, fuzzy matching, and token logic."""
        norm_g = self.normalize(guess)
        norm_a = self.normalize(answer)

        if not norm_g:
            return False

        # Exact match
        if norm_g == norm_a:
            return True

        # Numeric answers require exact match
        if norm_a.isdigit():
            return norm_g == norm_a

        # Single-word answer: token match
        answer_words = norm_a.split()
        if len(answer_words) == 1:
            if self.is_token_match(norm_g, norm_a):
                return True

        # Multi-word: smart token match
        return self.smart_token_match(norm_g, norm_a)
