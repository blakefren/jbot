import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.discord import DiscordBot, set_bot_commands
from bot.subscriber import Subscriber
from cfg.main import ConfigReader
from modes.game_runner import GameRunner
from readers.question import Question
from readers.question_selector import QuestionSelector


class TestDiscordBot(unittest.TestCase):
    def setUp(self):
        self.mock_game_runner = MagicMock(spec=GameRunner)
        self.mock_config_reader = MagicMock(spec=ConfigReader)
        self.mock_question_selector = MagicMock(spec=QuestionSelector)
        self.mock_game_runner.question_selector = self.mock_question_selector

        self.bot = DiscordBot(
            bot_token="test_token",
            game=self.mock_game_runner,
            config=self.mock_config_reader,
        )
        set_bot_commands(self.bot)

    def test_format_question(self):
        question = Question(
            question="What is the capital of France?",
            answer="Paris",
            category="Geography",
            clue_value=200,
        )
        formatted_question = self.bot.format_question(question)
        self.assertIn("Category: **Geography**", formatted_question)
        self.assertIn("Value: **$200**", formatted_question)
        self.assertIn("Question: **What is the capital of France?**", formatted_question)

    def test_format_answer(self):
        question = Question(
            question="What is the capital of France?",
            answer="Paris",
            category="Geography",
            clue_value=200,
        )
        formatted_answer = self.bot.format_answer(question)
        self.assertIn("||**     Paris     **||", formatted_answer)


if __name__ == "__main__":
    unittest.main()
