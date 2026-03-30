"""
Shared test helpers for PowerUpManager test modules.

Centralises the config factory so that adding a new config key only requires
a single edit here rather than updating every test file individually.
"""

from unittest.mock import MagicMock


def make_config(steal_cost=3, retro_steal_cost=5, retro_jinx_ratio=0.5):
    """Return a MagicMock ConfigReader pre-loaded with standard test values."""
    cfg = MagicMock()

    values = {
        "JBOT_STEAL_STREAK_COST": str(steal_cost),
        "JBOT_RETRO_STEAL_STREAK_COST": str(retro_steal_cost),
        "JBOT_RETRO_JINX_BONUS_RATIO": str(retro_jinx_ratio),
        "JBOT_BONUS_STREAK_PER_DAY": "5",
        "JBOT_BONUS_STREAK_CAP": "25",
        "JBOT_BONUS_BEFORE_HINT": "10",
        "JBOT_BONUS_FASTEST_CSV": "10,5,1",
        "JBOT_BONUS_TRY_CSV": "20,10,5",
        "JBOT_REST_MULTIPLIER": "1.2",
        "JBOT_EMOJI_FASTEST": "🥇",
        "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
        "JBOT_EMOJI_FIRST_TRY": "🎯",
        "JBOT_EMOJI_STREAK": "🔥",
        "JBOT_EMOJI_BEFORE_HINT": "🧠",
        "JBOT_EMOJI_JINXED": "🥶",
        "JBOT_EMOJI_SILENCED": "🤐",
        "JBOT_EMOJI_STOLEN_FROM": "💸",
        "JBOT_EMOJI_STEALING": "💰",
        "JBOT_EMOJI_REST": "😴",
        "JBOT_EMOJI_REST_WAKEUP": "⏰",
    }

    cfg.get.side_effect = lambda key, default=None: values.get(key, default)
    return cfg
