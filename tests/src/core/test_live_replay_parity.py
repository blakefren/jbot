"""Parity contracts for the live game workflow and DailyGameSimulator.

These tests deliberately use the production GuessHandler and PowerUpManager with
stateful in-memory adapters. They verify orchestration and persistence without
changing production workflows or requiring Discord/SQLite infrastructure.
"""

import copy
import unittest
from datetime import date, timedelta

from data.readers.question import Question
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.guess_handler import GuessHandler
from src.core.player import Player
from src.core.powerup import PowerUpManager
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

    def test_consecutive_rests_carry_over_to_next_question_day(self):
        self._powerup("rest", "2")
        self._start_next_question_day()
        self._powerup("rest", "2")
        self._start_next_question_day()

        self.assertEqual(self.players["2"].pending_rest_multiplier, 0.4)
        self._guess("2", "4")

        self._assert_live_replay_parity()


if __name__ == "__main__":
    unittest.main()
