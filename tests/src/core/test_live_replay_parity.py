"""Parity contracts for the live game workflow and DailyGameSimulator.

These tests deliberately use the production GuessHandler and PowerUpManager with
stateful in-memory adapters. They verify orchestration and persistence without
changing production workflows or requiring Discord/SQLite infrastructure.
"""

import copy
import os
import sqlite3
import tempfile
import unittest
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Event
from unittest.mock import patch

from data.readers.question import Question
from db.database import Database
from src.core.answer_checker import AnswerChecker
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.data_manager import DataManager
from src.core.events import GuessEvent, PowerUpEvent
from src.core.game_runner import GameRunner
from src.core.guess_handler import GuessHandler
from src.core.player import Player
from src.core.player_manager import PlayerManager
from src.core.powerup import PowerUpError, PowerUpManager
from src.core.state import DailyPlayerState
from tests.src.core._powerup_helpers import make_config


class InMemoryPlayerManager:
    """Stateful PlayerManager substitute that records every persisted score change."""

    def __init__(self, players: dict[str, Player]):
        self.players = players
        self.score_changes: list[tuple[str, int]] = []

    def get_player(self, player_id: str) -> Player | None:
        return self.players.get(str(player_id))

    def get_or_create_player(self, player_id: str, player_name: str) -> Player:
        player_id = str(player_id)
        if player_id not in self.players:
            self.players[player_id] = Player(id=player_id, name=player_name)
        return self.players[player_id]

    def update_score(self, player_id: str, amount: int) -> None:
        player = self.players[str(player_id)]
        player.score += amount
        player.season_score += amount
        self.score_changes.append((str(player_id), amount))

    def increment_streak(self, player_id: str, player_name: str) -> None:
        self.get_or_create_player(player_id, player_name).answer_streak += 1

    def set_streak(self, player_id: str, value: int) -> None:
        self.players[str(player_id)].answer_streak = value

    def reset_streak(self, player_id: str) -> None:
        self.players[str(player_id)].answer_streak = 0


class InMemoryDataManager:
    """Minimal stateful DataManager substitute for live game workflow parity."""

    def __init__(self, today: date, players: dict[str, Player]):
        self.today = today
        self.players = players
        self.guesses: list[dict] = []
        self.powerup_usage: list[dict] = []
        self.pending_powerups: list[dict] = []
        self.alternative_answers: list[str] = []
        self.hint_sent = False

    def transaction(self):
        return nullcontext()

    def get_today(self) -> date:
        return self.today

    def get_hint_sent_timestamp(self, daily_question_id: int) -> str | None:
        return "2023-01-01 12:00:00" if self.hint_sent else None

    def get_alternative_answers(self, daily_question_id: int) -> list[str]:
        return self.alternative_answers

    def read_guess_history(self, user_id: int | str) -> list[dict]:
        return [guess for guess in self.guesses if guess["user_id"] == str(user_id)]

    def log_player_guess(
        self,
        player_id: int | str,
        player_name: str,
        daily_question_id: int,
        guess_text: str,
        is_correct: bool,
    ) -> None:
        self.guesses.append(
            {
                "user_id": str(player_id),
                "player_name": player_name,
                "daily_question_id": daily_question_id,
                "guess_text": guess_text,
                "is_correct": is_correct,
            }
        )

    def get_correct_solver_count(self, daily_question_id: int) -> int:
        return len(
            {
                guess["user_id"]
                for guess in self.guesses
                if guess["daily_question_id"] == daily_question_id
                and guess["is_correct"]
            }
        )

    def get_last_correct_guess_date(self, player_id: str) -> date | None:
        if any(
            guess["user_id"] == str(player_id) and guess["is_correct"]
            for guess in self.guesses
        ):
            return self.today
        return self.today - timedelta(days=1)

    def increment_lifetime_stat(self, *args, **kwargs) -> None:
        pass

    def update_lifetime_stats(self, *args, **kwargs) -> None:
        pass

    def get_pending_multiplier(self, player_id: str) -> float:
        return self.players[str(player_id)].pending_rest_multiplier

    def clear_pending_multiplier(self, player_id: str) -> None:
        self.players[str(player_id)].pending_rest_multiplier = 0.0

    def increment_pending_multiplier(self, player_id: str, amount: float) -> None:
        self.players[str(player_id)].pending_rest_multiplier += amount

    def log_powerup_usage(
        self,
        user_id: str,
        powerup_type: str,
        target_user_id: str | None,
        question_id: int | None,
    ) -> None:
        self.powerup_usage.append(
            {
                "user_id": str(user_id),
                "powerup_type": powerup_type,
                "target_user_id": (
                    str(target_user_id) if target_user_id is not None else None
                ),
                "question_id": question_id,
            }
        )

    def get_pending_powerup(self, player_id: str):
        return None

    def get_pending_powerup_for_target(self, target_id: str, powerup_type: str):
        return None

    def apply_pending_powerups(self, question_id: int) -> list[dict]:
        pending = self.pending_powerups
        self.pending_powerups = []
        return pending


class TestLiveReplayParity(unittest.TestCase):
    """Contract tests for equivalent live and replay game-event processing."""

    question_id = 1
    today = date(2023, 1, 1)

    def setUp(self):
        self.config = make_config(steal_cost=2, retro_steal_cost=4)
        self.question = Question(
            question="What is 2 + 2?",
            answer="4",
            category="Math",
            clue_value=100,
        )
        self.players = {
            "1": Player(id="1", name="Attacker", score=100, answer_streak=3),
            "2": Player(id="2", name="Target", score=100, answer_streak=2),
            "3": Player(id="3", name="Third", score=100, answer_streak=4),
        }
        self.initial_players = copy.deepcopy(self.players)
        self.player_manager = InMemoryPlayerManager(self.players)
        self.data_manager = InMemoryDataManager(self.today, self.players)
        self.powerup_manager = PowerUpManager(
            self.player_manager, self.data_manager, self.config
        )
        self.guess_handler = GuessHandler(
            data_manager=self.data_manager,
            player_manager=self.player_manager,
            daily_question=self.question,
            daily_question_id=self.question_id,
            managers={"powerup": self.powerup_manager},
            config=self.config,
            question_db_id=self.question_id,
        )
        self.events = []
        self.messages: list[str] = []

    def _timestamp(self) -> str:
        return f"2023-01-01 09:{len(self.events):02d}:00"

    def _guess(self, player_id: str, guess: str) -> None:
        player = self.players[player_id]
        _, _, _, messages = self.guess_handler.handle_guess(
            player_id, player.name, guess
        )
        self.messages.extend(messages)
        self.events.append(
            GuessEvent(
                timestamp=self._timestamp(),
                user_id=player_id,
                guess_text=guess,
            )
        )

    def _powerup(self, action: str, user_id: str, target_id: str | None = None) -> None:
        if action == "jinx":
            message = self.powerup_manager.jinx(user_id, target_id, self.question_id)
        elif action == "steal":
            message = self.powerup_manager.steal(user_id, target_id, self.question_id)
        elif action == "rest":
            message, _ = self.powerup_manager.rest(
                user_id, self.question_id, self.question.answer
            )
        else:
            self.fail(f"Unsupported parity action: {action}")
        self.messages.append(message)
        usage = self.data_manager.powerup_usage[-1]
        self.events.append(
            PowerUpEvent(
                timestamp=self._timestamp(),
                user_id=usage["user_id"],
                powerup_type=usage["powerup_type"],
                target_user_id=usage["target_user_id"],
            )
        )

    def _preload_jinx(self, attacker_id: str, target_id: str) -> None:
        self.data_manager.pending_powerups.append(
            {
                "user_id": attacker_id,
                "target_user_id": target_id,
                "powerup_type": "jinx_preload",
            }
        )
        self.powerup_manager.hydrate_pending_powerups(self.question_id)
        self.events.append(
            PowerUpEvent(
                timestamp=self._timestamp(),
                user_id=attacker_id,
                powerup_type="jinx_preload",
                target_user_id=target_id,
            )
        )

    def _preload_steal(self, thief_id: str, target_id: str) -> None:
        self.data_manager.pending_powerups.append(
            {
                "user_id": thief_id,
                "target_user_id": target_id,
                "powerup_type": "steal_preload",
            }
        )
        self.powerup_manager.hydrate_pending_powerups(self.question_id)
        self.events.append(
            PowerUpEvent(
                timestamp=self._timestamp(),
                user_id=thief_id,
                powerup_type="steal_preload",
                target_user_id=target_id,
            )
        )

    def _set_pending_rest_multiplier(self, player_id: str, multiplier: float) -> None:
        self.players[player_id].pending_rest_multiplier = multiplier
        self.initial_players[player_id].pending_rest_multiplier = multiplier

    def _set_initial_streak(self, player_id: str, streak: int) -> None:
        self.players[player_id].answer_streak = streak
        self.initial_players[player_id].answer_streak = streak

    def _start_next_question_day(self) -> None:
        self.question_id += 1
        self.events = []
        self.initial_players = copy.deepcopy(self.players)
        self.powerup_manager.reset_daily_state()
        self.guess_handler = GuessHandler(
            data_manager=self.data_manager,
            player_manager=self.player_manager,
            daily_question=self.question,
            daily_question_id=self.question_id,
            managers={"powerup": self.powerup_manager},
            config=self.config,
            question_db_id=self.question_id,
        )

    def _assert_live_replay_parity(self) -> None:
        simulator = DailyGameSimulator(
            question=self.question,
            answers=[self.question.answer, *self.data_manager.alternative_answers],
            hint_timestamp=None,
            events=copy.deepcopy(self.events),
            initial_player_states=copy.deepcopy(self.initial_players),
            config=self.config,
        )
        replay = simulator.run(apply_end_of_day=False)
        player_ids = set(self.powerup_manager.daily_state) | set(simulator.daily_state)

        for player_id in player_ids:
            with self.subTest(player_id=player_id):
                initial_player = self.initial_players[player_id]
                self.assertEqual(
                    self.players[player_id].score,
                    replay[player_id]["final_score"],
                )
                self.assertEqual(
                    self.players[player_id].answer_streak,
                    replay[player_id]["final_streak"],
                )
                persisted_delta = sum(
                    amount
                    for changed_player_id, amount in self.player_manager.score_changes
                    if changed_player_id == player_id
                )
                self.assertEqual(
                    persisted_delta,
                    replay[player_id]["final_score"] - initial_player.score,
                )
                live_state = self.powerup_manager.daily_state.get(
                    player_id, DailyPlayerState()
                )
                replay_state = simulator.daily_state.get(player_id, DailyPlayerState())
                self.assertEqual(
                    self._state_snapshot(live_state),
                    self._state_snapshot(replay_state),
                )

    @staticmethod
    def _state_snapshot(state: DailyPlayerState) -> dict:
        return {
            "score_earned": state.score_earned,
            "score_stolen": state.score_stolen,
            "streak_delta": state.streak_delta,
            "is_correct": state.is_correct,
            "guesses_count": state.guesses_count,
            "bonuses": state.bonuses,
            "is_resting": state.is_resting,
            "jinxed_by": state.jinxed_by,
            "steal_attempt_by": state.steal_attempt_by,
            "attacked_by": state.attacked_by,
            "silenced": state.silenced,
            "jinx_target": state.jinx_target,
            "jinx_penalty_total": state.jinx_penalty_total,
            "stealing_from": state.stealing_from,
            "steal_ratio": state.steal_ratio,
        }

    def test_forward_jinx_after_wrong_guesses_matches_replay(self):
        self._powerup("jinx", "1", "2")
        self._guess("2", "wrong")
        self._guess("2", "still wrong")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_correct_guess_without_powerups_matches_replay(self):
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_incorrect_guess_without_powerups_matches_replay(self):
        self._guess("2", "wrong")

        self._assert_live_replay_parity()

    def test_every_submitted_guess_is_counted_once_live_and_replay(self):
        self._guess("2", "wrong")
        self._guess("2", "still wrong")
        self._guess("2", "4")

        simulator = DailyGameSimulator(
            question=self.question,
            answers=[self.question.answer],
            hint_timestamp=None,
            events=copy.deepcopy(self.events),
            initial_player_states=copy.deepcopy(self.initial_players),
            config=self.config,
        )
        simulator.run(apply_end_of_day=False)

        self.assertEqual(self.powerup_manager.daily_state["2"].guesses_count, 3)
        self.assertEqual(simulator.daily_state["2"].guesses_count, 3)

    def test_retroactive_jinx_matches_replay(self):
        self._guess("2", "wrong")
        self._guess("2", "4")
        self._powerup("jinx", "1", "2")

        self._assert_live_replay_parity()

    def test_late_retroactive_jinx_matches_replay(self):
        self._guess("1", "4")
        self._guess("2", "wrong")
        self._guess("2", "4")
        self._powerup("jinx", "1", "2")

        self._assert_live_replay_parity()

    def test_late_forward_jinx_matches_replay(self):
        self._guess("1", "4")
        self._powerup("jinx", "1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_jinx_includes_pending_rest_bonus_in_live_and_replay(self):
        self._set_pending_rest_multiplier("2", 0.2)
        self._powerup("jinx", "1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_jinx_and_steal_on_same_target_match_replay(self):
        self._powerup("jinx", "1", "2")
        self._powerup("steal", "3", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_jinx_then_attacker_rest_matches_replay(self):
        self._powerup("jinx", "1", "2")
        self._powerup("rest", "1")

        self._assert_live_replay_parity()

    def test_rest_then_attacker_jinx_matches_replay(self):
        self._powerup("rest", "1")
        self._powerup("jinx", "1", "2")

        self._assert_live_replay_parity()

    def test_steal_then_thief_rest_matches_replay(self):
        self._powerup("steal", "1", "2")
        self._powerup("rest", "1")

        self._assert_live_replay_parity()

    def test_rest_then_thief_steal_matches_replay(self):
        self._powerup("rest", "1")
        self._powerup("steal", "1", "2")

        self._assert_live_replay_parity()

    def test_jinxed_target_wrong_guesses_before_and_after_jinx_match_replay(self):
        self._guess("2", "wrong before")
        self._powerup("jinx", "1", "2")
        self._guess("2", "wrong after")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_forward_steal_matches_replay(self):
        self._powerup("steal", "1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_retroactive_steal_matches_replay(self):
        self._guess("2", "4")
        self._powerup("steal", "1", "2")

        self._assert_live_replay_parity()

    def test_partial_forward_steal_matches_replay(self):
        self._set_initial_streak("1", 1)
        self._powerup("steal", "1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_partial_retroactive_steal_matches_replay(self):
        self._set_initial_streak("1", 1)
        self._guess("2", "4")
        self._powerup("steal", "1", "2")

        self._assert_live_replay_parity()

    def test_late_forward_steal_matches_replay(self):
        self._guess("1", "4")
        self._powerup("steal", "1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_rest_cancels_pending_jinx_in_live_and_replay(self):
        self._powerup("jinx", "1", "2")
        self._powerup("rest", "2")

        self._assert_live_replay_parity()

    def test_rest_cancels_pending_steal_in_live_and_replay(self):
        self._powerup("steal", "1", "2")
        self._powerup("rest", "2")

        self._assert_live_replay_parity()

    def test_overnight_preloaded_jinx_matches_replay(self):
        self._preload_jinx("1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_overnight_preloaded_steal_matches_replay(self):
        self._preload_steal("1", "2")
        self._guess("2", "4")

        self._assert_live_replay_parity()

    def test_multiple_answer_corrections_match_replay(self):
        self.data_manager.alternative_answers = ["four", "iv"]
        self._guess("2", "four")
        self._guess("3", "iv")

        self._assert_live_replay_parity()

    def test_corrected_resting_player_becomes_targetable(self):
        events = [
            PowerUpEvent("2023-01-01 09:00:00", "2", "rest", None),
            GuessEvent("2023-01-01 10:00:00", "2", "wrong before correction"),
            GuessEvent("2023-01-01 10:01:00", "2", "accepted after correction"),
            PowerUpEvent("2023-01-01 10:02:00", "1", "jinx", "2"),
        ]
        simulator = DailyGameSimulator(
            question=self.question,
            answers=[self.question.answer, "accepted after correction"],
            hint_timestamp=None,
            events=copy.deepcopy(events),
            initial_player_states=copy.deepcopy(self.initial_players),
            config=self.config,
        )

        simulator.run(apply_end_of_day=False)

        corrected_state = simulator.daily_state["2"]
        self.assertTrue(corrected_state.is_correct)
        self.assertFalse(corrected_state.is_resting)
        self.assertEqual(corrected_state.guesses_count, 2)
        self.assertEqual(simulator.daily_state["1"].jinx_penalty_total, 5)
        self.assertIsNone(simulator.daily_state["1"].jinx_target)

    def test_jinx_after_correction_charges_only_prior_wrong_guesses(self):
        events = [
            GuessEvent("2023-01-01 09:00:00", "2", "wrong one"),
            GuessEvent("2023-01-01 09:01:00", "2", "wrong two"),
            GuessEvent("2023-01-01 09:02:00", "2", "accepted after correction"),
            PowerUpEvent("2023-01-01 09:03:00", "1", "jinx", "2"),
        ]
        simulator = DailyGameSimulator(
            question=self.question,
            answers=[self.question.answer, "accepted after correction"],
            hint_timestamp=None,
            events=copy.deepcopy(events),
            initial_player_states=copy.deepcopy(self.initial_players),
            config=self.config,
        )

        simulator.run(apply_end_of_day=False)

        self.assertEqual(simulator.daily_state["2"].guesses_count, 3)
        self.assertEqual(simulator.daily_state["1"].jinx_penalty_total, 10)

    def test_consecutive_rests_carry_over_to_next_question_day(self):
        self._powerup("rest", "2")
        self._start_next_question_day()
        self._powerup("rest", "2")
        self._start_next_question_day()

        self.assertEqual(self.players["2"].pending_rest_multiplier, 0.4)
        self._guess("2", "4")

        self._assert_live_replay_parity()


class TestSQLiteLiveReplayOrdering(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.data_manager.create_player("1", "Attacker")
        self.data_manager.create_player("2", "Target")
        self.data_manager.set_streak("1", 8)
        self.data_manager.set_streak("2", 3)
        self.question = Question("What is 2 + 2?", "4", "Math", 100)
        self.question_id = self.data_manager.log_daily_question(self.question)
        self.initial_players = self.data_manager.get_daily_snapshot(self.question_id)
        self.config = make_config(steal_cost=2, retro_steal_cost=4)
        self.powerups = PowerUpManager(
            self.player_manager, self.data_manager, self.config
        )
        self.guesses = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.question,
            self.question_id,
            {"powerup": self.powerups},
            config=self.config,
        )

    def tearDown(self):
        self.db.close()

    def assert_replay_matches_live(self):
        timestamp = "2023-01-01 10:00:00"
        self.db.execute_update(
            "UPDATE guesses SET guessed_at = ? WHERE daily_question_id = ?",
            (timestamp, self.question_id),
        )
        self.db.execute_update(
            "UPDATE powerup_usage SET used_at = ? WHERE question_id = ?",
            (timestamp, self.question_id),
        )
        runner = object.__new__(GameRunner)
        runner.data_manager = self.data_manager
        events = runner._fetch_daily_events(self.question_id)
        simulator = DailyGameSimulator(
            self.question,
            [self.question.answer],
            None,
            events,
            self.initial_players,
            self.config,
        )
        results = simulator.run(apply_end_of_day=False)
        for player_id, result in results.items():
            player = self.player_manager.get_player(player_id)
            self.assertEqual(player.score, result["final_score"])
            self.assertEqual(player.answer_streak, result["final_streak"])
        return events

    def test_jinx_before_guess_same_second_matches_live(self):
        self.powerups.jinx("1", "2", self.question_id)
        self.guesses.handle_guess("2", "Target", "4")

        events = self.assert_replay_matches_live()

        self.assertIsInstance(events[0], PowerUpEvent)
        self.assertIsInstance(events[1], GuessEvent)

    def test_retroactive_steal_after_guess_same_second_matches_live(self):
        self.guesses.handle_guess("2", "Target", "4")
        self.powerups.steal("1", "2", self.question_id)

        events = self.assert_replay_matches_live()

        self.assertIsInstance(events[0], GuessEvent)
        self.assertIsInstance(events[1], PowerUpEvent)

    def test_correct_guesses_same_second_preserve_fastest_order(self):
        self.guesses.handle_guess("2", "Target", "4")
        self.guesses.handle_guess("1", "Attacker", "4")

        events = self.assert_replay_matches_live()

        self.assertEqual([event.user_id for event in events], ["2", "1"])

    def test_wrong_guess_then_rest_same_second_matches_live(self):
        self.guesses.handle_guess("2", "Target", "wrong")
        self.powerups.rest("2", self.question_id, self.question.answer)

        events = self.assert_replay_matches_live()

        self.assertIsInstance(events[0], GuessEvent)
        self.assertIsInstance(events[1], PowerUpEvent)

    def test_hydrated_preload_precedes_same_second_guess(self):
        self.powerups.jinx("1", "2", None)
        self.powerups.reset_daily_state()
        self.powerups.hydrate_pending_powerups(self.question_id)
        self.guesses.handle_guess("2", "Target", "4")

        events = self.assert_replay_matches_live()

        self.assertEqual([event.event_sequence for event in events], [1, 2])
        self.assertEqual(events[0].powerup_type, "jinx_preload")

    def test_rejected_retaliation_does_not_change_event_order(self):
        self.powerups.jinx("1", "2", self.question_id)
        with self.assertRaises(PowerUpError):
            self.powerups.steal("2", "1", self.question_id)
        self.guesses.handle_guess("2", "Target", "4")

        events = self.assert_replay_matches_live()

        self.assertEqual([event.event_sequence for event in events], [1, 2])

    def test_jinx_failure_rolls_back_usage_and_daily_state(self):
        log_powerup_usage = self.data_manager.log_powerup_usage

        def fail_after_logging(*args, **kwargs):
            log_powerup_usage(*args, **kwargs)
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")

        with patch.object(
            self.data_manager, "log_powerup_usage", side_effect=fail_after_logging
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.powerups.jinx("1", "2", self.question_id)

        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.question_id), []
        )
        self.assertEqual(self.powerups.daily_state, {})

    def test_steal_failure_rolls_back_usage_streak_and_daily_state(self):
        set_streak = self.player_manager.set_streak

        def fail_after_streak_update(*args, **kwargs):
            set_streak(*args, **kwargs)
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")

        with patch.object(
            self.player_manager, "set_streak", side_effect=fail_after_streak_update
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.powerups.steal("1", "2", self.question_id)

        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.question_id), []
        )
        self.assertEqual(self.player_manager.get_player("1").answer_streak, 8)
        self.assertEqual(self.powerups.daily_state, {})

    def test_rest_failure_rolls_back_usage_multiplier_and_daily_state(self):
        increment_multiplier = self.data_manager.increment_pending_multiplier

        def fail_after_multiplier_update(*args, **kwargs):
            increment_multiplier(*args, **kwargs)
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")

        with patch.object(
            self.data_manager,
            "increment_pending_multiplier",
            side_effect=fail_after_multiplier_update,
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.powerups.rest("2", self.question_id, self.question.answer)

        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.question_id), []
        )
        self.assertEqual(self.data_manager.get_pending_multiplier("2"), 0.0)
        self.assertEqual(self.powerups.daily_state, {})

    def test_hydration_failure_rolls_back_promotion_and_daily_state(self):
        self.powerups.jinx("1", "2", None)
        self.powerups.reset_daily_state()
        reduce_powerup = self.powerups._reduce_powerup

        def fail_after_reduction(*args, **kwargs):
            result = reduce_powerup(*args, **kwargs)
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")
            return result

        with patch.object(
            self.powerups, "_reduce_powerup", side_effect=fail_after_reduction
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.powerups.hydrate_pending_powerups(self.question_id)

        pending = self.data_manager.get_pending_powerup("1")
        self.assertIsNotNone(pending)
        self.assertIsNone(pending["question_id"])
        self.assertEqual(self.powerups.daily_state, {})

    def test_snapshot_rollback_failure_preserves_database_and_daily_state(self):
        self.guesses.handle_guess("1", "Attacker", "4")
        player_before = self.player_manager.get_player("1")
        score_before = player_before.score
        streak_before = player_before.answer_streak
        state_before = self.powerups.snapshot_transaction_state()
        rollback_question_day = self.data_manager.rollback_question_day

        def fail_after_snapshot_restore(question_id):
            rollback_question_day(question_id)
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")

        with patch.object(
            self.data_manager,
            "rollback_question_day",
            side_effect=fail_after_snapshot_restore,
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.powerups.rollback_to_snapshot(self.question_id)

        player_after = self.player_manager.get_player("1")
        self.assertEqual(player_after.score, score_before)
        self.assertEqual(player_after.answer_streak, streak_before)
        self.assertEqual(len(self.data_manager.read_guess_history("1")), 1)
        self.assertEqual(
            self.powerups.daily_state,
            state_before,
        )

    def test_crowd_wisdom_failure_rolls_back_score_usage_and_daily_state(self):
        self.powerups.daily_state = {
            "1": DailyPlayerState(is_correct=True, score_earned=100),
            "2": DailyPlayerState(guesses_count=1),
        }
        state_before = self.powerups.snapshot_transaction_state()
        game = object.__new__(GameRunner)
        game.data_manager = self.data_manager
        game.player_manager = self.player_manager
        game.daily_question_id = self.question_id
        game.managers = {"powerup": self.powerups}
        game._crowd_wisdom_summary = None
        log_powerup_usage = self.data_manager.log_powerup_usage

        def log_then_fail(*args, **kwargs):
            log_powerup_usage(*args, **kwargs)
            raise RuntimeError("injected crowd-wisdom failure")

        with patch.object(
            self.data_manager, "log_powerup_usage", side_effect=log_then_fail
        ):
            with self.assertRaisesRegex(RuntimeError, "injected crowd-wisdom failure"):
                game.apply_crowd_wisdom_bonus()

        self.assertEqual(self.player_manager.get_player("1").score, 0)
        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.question_id), []
        )
        self.assertEqual(self.powerups.daily_state, state_before)
        self.assertIsNone(game._crowd_wisdom_summary)

    def test_jinx_and_guess_are_serialized_across_threads(self):
        transition_started = Event()
        release_transition = Event()
        guess_started = Event()
        guess_finished = Event()
        reduce_powerup = self.powerups._reduce_powerup

        def delayed_reduction(*args, **kwargs):
            transition_started.set()
            if not release_transition.wait(5):
                raise TimeoutError("jinx transition was not released")
            return reduce_powerup(*args, **kwargs)

        def submit_guess():
            guess_started.set()
            try:
                return self.guesses.handle_guess("2", "Target", "4")
            finally:
                guess_finished.set()

        with patch.object(
            self.powerups, "_reduce_powerup", side_effect=delayed_reduction
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                jinx = executor.submit(self.powerups.jinx, "1", "2", self.question_id)
                try:
                    self.assertTrue(transition_started.wait(5))
                    guess = executor.submit(submit_guess)
                    self.assertTrue(guess_started.wait(5))
                    self.assertFalse(guess_finished.wait(0.1))
                finally:
                    release_transition.set()
                jinx.result(timeout=5)
                guess.result(timeout=5)

        events = self.assert_replay_matches_live()
        self.assertIsInstance(events[0], PowerUpEvent)
        self.assertIsInstance(events[1], GuessEvent)


class TestSQLiteRestartAndSettlement(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "jbot.db")
        self.db = Database(self.db_path)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.player_manager.get_or_create_player("attacker", "Attacker")
        self.player_manager.get_or_create_player("target", "Target")
        self.player_manager.set_streak("attacker", 8)
        self.player_manager.set_streak("target", 3)
        self.question = Question("Question", "Answer", "Test", 100)
        self.daily_question_id = self.data_manager.log_daily_question(self.question)
        _, _, self.question_db_id = self.data_manager.get_todays_daily_question()
        self.config = make_config(steal_cost=2, retro_steal_cost=4)
        self.powerups = PowerUpManager(
            self.player_manager, self.data_manager, self.config
        )

    def tearDown(self):
        if self.db.conn is not None:
            self.db.close()
        self.temp_dir.cleanup()

    def test_preload_guess_restart_replay_and_settlement(self):
        self.powerups.jinx("attacker", "target", None)
        self.powerups.reset_daily_state()
        self.powerups.hydrate_pending_powerups(self.daily_question_id)
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.question,
            self.daily_question_id,
            {"powerup": self.powerups},
            config=self.config,
            question_db_id=self.question_db_id,
        )
        handler.handle_guess("target", "Target", "Answer")
        expected_daily_state = copy.deepcopy(self.powerups.daily_state)

        self.db.close()
        self.db = Database(self.db_path)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.question, self.question_db_id = self.data_manager.get_daily_question_by_id(
            self.daily_question_id
        )
        self.powerups = PowerUpManager(
            self.player_manager, self.data_manager, self.config
        )

        runner = object.__new__(GameRunner)
        runner.data_manager = self.data_manager
        runner.player_manager = self.player_manager
        runner.daily_q = self.question
        runner.daily_question_id = self.daily_question_id
        runner.question_db_id = self.question_db_id
        runner.config = self.config
        runner.answer_checker = AnswerChecker()
        runner.managers = {"powerup": self.powerups}
        runner.restore_game_state()

        self.assertEqual(self.powerups.daily_state, expected_daily_state)
        powerup_rows = self.data_manager.get_powerup_usages_for_question(
            self.daily_question_id
        )
        guess_rows = self.data_manager.get_guesses_for_daily_question(
            self.daily_question_id
        )
        self.assertEqual(powerup_rows[0]["event_sequence"], 1)
        self.assertEqual(guess_rows[0]["event_sequence"], 2)

        runner.season_manager = type(
            "SeasonStub", (), {"get_season_end_announcement": lambda _self: None}
        )()
        runner.pending_evening_announcements = []
        runner.end_daily_game()

        self.assertEqual(self.player_manager.get_player("attacker").answer_streak, 0)
        self.assertEqual(self.player_manager.get_player("target").answer_streak, 4)
        self.assertEqual(runner.verify_daily_play(self.daily_question_id), [])
        self.assertIsNone(runner.daily_question_id)


if __name__ == "__main__":
    unittest.main()
