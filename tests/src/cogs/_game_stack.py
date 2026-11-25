"""Real in-memory game stack for cog and Discord bot tests."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from data.readers.question import Question
from db.database import Database
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from tests.src.core._powerup_helpers import make_config

DEFAULT_QUESTION = ("What is 2 + 2?", "4", "Math", 100)


@dataclass
class GameStack:
    db: Database
    data_manager: DataManager
    player_manager: PlayerManager
    game: GameRunner
    config: MagicMock
    question_selector: MagicMock
    question: Question


def make_game_config(
    seasons: bool = False, season_auto_create: bool = True
) -> MagicMock:
    """Return a ConfigReader double with the keys GameRunner and friends read."""
    config = make_config()
    base_get = config.get.side_effect
    extras = {
        "JBOT_RIDDLE_HISTORY_DAYS": "7",
        "JBOT_QUESTION_RETRIES": "3",
        "JBOT_TIMEZONE": "US/Pacific",
        "JBOT_FIRST_PLACE_ROLE_NAME": "Winner",
    }
    config.get.side_effect = lambda key, default=None: extras.get(
        key, base_get(key, default)
    )
    config.is_seasons_enabled.return_value = seasons
    config.get_season_mode.return_value = "calendar"
    config.get_season_auto_create.return_value = season_auto_create
    config.get_season_announce_start.return_value = False
    config.get_season_trophy_positions.return_value = 3
    config.get_season_duration_days.return_value = 30
    return config


def build_game_stack(
    test,
    *,
    players=(),
    question: Question | None = None,
    start_day: bool = True,
    seasons: bool = False,
    season_auto_create: bool = True,
) -> GameStack:
    """Build a real DataManager/PlayerManager/GameRunner over an in-memory DB.

    Only the question source (dataset/Gemini) and ConfigReader are doubles.
    `players` are (id, name[, streak]) tuples created before the day starts so
    they are captured in the daily snapshot.
    """
    db = Database(":memory:")
    test.addCleanup(db.close)
    data_manager = DataManager(db)
    player_manager = PlayerManager(data_manager)
    for player_id, name, *streak in players:
        player_manager.get_or_create_player(player_id, name)
        if streak:
            player_manager.set_streak(player_id, streak[0])

    question = question or Question(*DEFAULT_QUESTION)
    selector = MagicMock()
    selector.get_random_question.return_value = question
    selector.get_hint_from_gemini.return_value = None

    config = make_game_config(seasons, season_auto_create)
    with patch("src.core.game_runner.ConfigReader", return_value=config), patch(
        "src.core.powerup.ConfigReader", return_value=config
    ):
        game = GameRunner(selector, data_manager, player_manager)
    if start_day:
        game.set_daily_question()
    return GameStack(db, data_manager, player_manager, game, config, selector, question)
