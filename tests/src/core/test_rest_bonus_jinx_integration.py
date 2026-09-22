"""
Integration test: Rest bonus + jinx scenario.
Proves that DailyGameSimulator correctly includes rest bonus in jinx transfers.
"""

from datetime import datetime, timedelta
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.player import Player
from src.cfg.main import ConfigReader
from data.readers.question import Question


def test_rest_bonus_jinx_integration():
    """
    Minimal scenario to test rest + jinx:
    1. Player A rests yesterday (has rest_multiplier for today)
    2. Player A answers correctly today, earns 250 points + 50 rest bonus = 300 total
    3. Player B (late) jinxes Player A retroactively
    4. Expected: Player B gets 25% of 300 = 75 points (includes rest bonus)
    """
    config = ConfigReader()

    # Setup players
    player_a_id = "player_a"
    player_b_id = "player_b"

    # Player A had rest bonus from yesterday
    player_a = Player(
        id=player_a_id,
        name="PlayerA",
        score=0,
        season_score=0,
        answer_streak=1,
        pending_rest_multiplier=0.2,  # 20% multiplier from rest (0.2, not 1.2!)
    )

    player_b = Player(
        id=player_b_id,
        name="PlayerB",
        score=0,
        season_score=0,
        answer_streak=0,
        pending_rest_multiplier=0.0,
    )

    initial_player_states = {
        player_a_id: player_a,
        player_b_id: player_b,
    }

    # Question and answer
    # Base value 200: gives us the expected bonuses
    # With clue_value=200, score_calculator gives:
    #   200 (base) + 20 (try_1) + 10 (fastest) + 10 (before_hint) + 10 (streak) = 250
    #   rest bonus = 20% of 250 = 50
    #   total = 300
    question = Question(
        question="Test question",
        answer="correct_answer",
        category="TEST",
        clue_value=200,
    )
    answers = ["correct_answer"]

    # Timeline
    now = datetime.now()
    guess_time = now.strftime("%Y-%m-%d %H:%M:%S")
    jinx_time = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

    # Events
    events = [
        # Player A answers correctly (with rest multiplier already active)
        GuessEvent(
            timestamp=guess_time, user_id=player_a_id, guess_text="correct_answer"
        ),
        # Player B does a late jinx (2 hours later, after A already answered)
        PowerUpEvent(
            timestamp=jinx_time,
            user_id=player_b_id,
            powerup_type="jinx_late",
            target_user_id=player_a_id,
        ),
    ]

    # Run simulator
    simulator = DailyGameSimulator(
        question=question,
        answers=answers,
        hint_timestamp=None,
        events=events,
        initial_player_states=initial_player_states,
        config=config,
    )

    results = simulator.run()

    # Debug: print all daily_state
    print("\nDebug - daily_state contents:")
    for user_id, state in simulator.daily_state.items():
        print(f"  {user_id}:")
        print(f"    score_earned={state.score_earned}")
        print(f"    score_stolen={state.score_stolen}")
        print(f"    bonuses={state.bonuses}")
        print(f"    is_correct={state.is_correct}")
        print(f"    jinxed_by={state.jinxed_by}")
        print(f"    jinx_target={state.jinx_target}")

    print(f"\nDebug - Jinx logic:")
    print(f"  Player A earned: {simulator.daily_state[player_a_id].score_earned}")
    print(f"  Player A stolen: {simulator.daily_state[player_a_id].score_stolen}")
    earnedonly_a = (
        simulator.daily_state[player_a_id].score_earned
        - simulator.daily_state[player_a_id].score_stolen
    )
    jinx_transfer = int(earnedonly_a * 0.25)
    print(f"  Jinx should transfer: 25% of {earnedonly_a} = {jinx_transfer}")
    print(f"  Player B actually got: {simulator.daily_state[player_b_id].score_earned}")
    print(
        f"  Player B stolen (from jinx): {simulator.daily_state[player_b_id].score_stolen}"
    )

    print(f"\nDebug - results dict keys: {list(results.keys())}")

    # Extract scores
    player_a_result = results.get(player_a_id, {})
    player_b_result = results.get(player_b_id, {})

    player_a_score = player_a_result.get("final_score", 0)
    player_b_score = player_b_result.get("final_score", 0)

    # Player A: 200 base + 20 try + 10 fastest + 10 before_hint + 10 streak = 250
    #            + 50 rest bonus (20% of 250) = 300
    #            - 75 jinx transfer (25% of 300) = 225 final
    # Player B: 0 + 75 from jinx = 75 final
    expected_a_score = 225  # 300 - 75
    expected_b_score = 75  # 0 + 75

    print("\n" + "=" * 70)
    print("REST BONUS + JINX INTEGRATION TEST")
    print("=" * 70)
    print(f"\nScenario:")
    print(f"  Player A: Answers correctly with rest multiplier")
    print(f"    - Base: 200, Bonuses (try+fastest+before_hint+streak): 50")
    print(f"    - Subtotal: 250")
    print(f"    - Rest multiplier bonus: 50 (20% of 250)")
    print(f"    - Total earned: 300")
    print(f"  Player B: Jinxes Player A retroactively (late)")
    print(f"    - Jinx transfers: 25% of 300 = 75 points")

    print(f"\nResults from DailyGameSimulator:")
    print(f"  Player A final score: {player_a_score}")
    print(f"    Expected: {expected_a_score} (300 - 75 transferred)")
    print(f"    Match: {'OK' if player_a_score == expected_a_score else 'FAIL'}")

    print(f"\n  Player B final score: {player_b_score}")
    print(f"    Expected: {expected_b_score} (0 + 75 from jinx)")
    print(f"    Match: {'OK' if player_b_score == expected_b_score else 'FAIL'}")

    print("\n" + "=" * 70)

    # Assertions
    assert (
        player_a_score == expected_a_score
    ), f"Player A score mismatch: got {player_a_score}, expected {expected_a_score}"
    assert (
        player_b_score == expected_b_score
    ), f"Player B score mismatch: got {player_b_score}, expected {expected_b_score}"

    print("✓ TEST PASSED: Rest bonus is correctly included in jinx transfer!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_rest_bonus_jinx_integration()
