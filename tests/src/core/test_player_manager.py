import unittest
from datetime import date

from db.database import Database
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager


class TestPlayerManager(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.manager = PlayerManager(self.data_manager)

    def tearDown(self):
        self.db.close()

    def test_get_player_and_normalize_integer_id(self):
        self.data_manager.create_player("123", "John Doe")
        self.data_manager.adjust_player_score("123", 10)
        self.data_manager.set_streak("123", 5)

        player = self.manager.get_player(123)

        self.assertEqual(
            (player.id, player.score, player.answer_streak), ("123", 10, 5)
        )

    def test_get_all_players(self):
        self.data_manager.create_player("123", "John Doe")
        self.data_manager.create_player("456", "Jane Smith")

        players = self.manager.get_all_players()

        self.assertEqual(set(players), {"123", "456"})
        self.assertEqual(players["456"].name, "Jane Smith")

    def test_update_score_persists_lifetime_score(self):
        self.data_manager.create_player("123", "Player")

        self.manager.update_score("123", 50)

        player = self.data_manager.get_player("123")
        self.assertEqual(player.score, 50)
        self.assertEqual(player.season_score, 0)

    def test_set_name_updates_existing_player(self):
        self.data_manager.create_player("123", "Old Name")

        self.manager.set_name("123", "New Name")

        self.assertEqual(self.data_manager.get_player("123").name, "New Name")

    def test_set_name_creates_missing_player(self):
        self.manager.set_name("456", "New Player")

        self.assertEqual(self.data_manager.get_player("456").name, "New Player")

    def test_increment_streak_existing_player(self):
        self.data_manager.create_player("123", "Player")
        self.data_manager.set_streak("123", 4)

        self.manager.increment_streak("123")

        self.assertEqual(self.data_manager.get_player("123").answer_streak, 5)

    def test_increment_streak_creates_missing_player(self):
        self.manager.increment_streak("456", "New Player")

        player = self.data_manager.get_player("456")
        self.assertEqual((player.name, player.answer_streak), ("New Player", 1))

    def test_reset_streak(self):
        self.data_manager.create_player("123", "Player")
        self.data_manager.set_streak("123", 5)

        self.manager.reset_streak("123")

        self.assertEqual(self.data_manager.get_player("123").answer_streak, 0)

    def test_get_or_create_updates_existing_name(self):
        self.data_manager.create_player("123", "Old Name")

        player = self.manager.get_or_create_player("123", "New Name")

        self.assertEqual(player.name, "New Name")
        self.assertEqual(self.data_manager.get_player("123").name, "New Name")

    def test_get_or_create_preserves_matching_name(self):
        self.data_manager.create_player("123", "Same Name")

        player = self.manager.get_or_create_player("123", "Same Name")

        self.assertEqual(player.name, "Same Name")

    def test_get_or_create_creates_missing_player(self):
        player = self.manager.get_or_create_player("456", "New Player")

        self.assertEqual(player.name, "New Player")
        self.assertEqual(self.data_manager.get_player("456").id, "456")

    def test_set_streak_persists_value(self):
        self.data_manager.create_player("123", "Player")

        self.manager.set_streak(123, 10)

        self.assertEqual(self.data_manager.get_player("123").answer_streak, 10)

    def test_update_score_updates_current_season(self):
        player = self.data_manager.create_player("123", "Player")
        season_id = self.data_manager.create_season(
            "Current", date.today().isoformat(), date.today().isoformat()
        )

        self.manager.update_score("123", 50)

        player = self.data_manager.get_player("123")
        season_score = self.data_manager.get_player_season_score("123", season_id)
        self.assertEqual(player.score, 50)
        self.assertEqual(player.season_score, 50)
        self.assertEqual(season_score.points, 50)

    def test_streak_updates_current_season_best(self):
        self.data_manager.create_player("123", "Player")
        season_id = self.data_manager.create_season(
            "Current", date.today().isoformat(), date.today().isoformat()
        )

        self.manager.set_streak("123", 4)
        self.manager.increment_streak("123")

        season_score = self.data_manager.get_player_season_score("123", season_id)
        self.assertEqual(season_score.current_streak, 5)
        self.assertEqual(season_score.best_streak, 5)

    def test_adjust_season_score_without_active_season_is_noop(self):
        self.data_manager.create_player("123", "Player")

        self.manager.adjust_season_score("123", 50)

        player = self.data_manager.get_player("123")
        self.assertEqual(player.score, 0)
        self.assertEqual(player.season_score, 0)

    def test_normalize_none_to_empty_id(self):
        self.assertEqual(self.manager._normalize_id(None), "")


if __name__ == "__main__":
    unittest.main()
