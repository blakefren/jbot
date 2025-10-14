# Player Scoring Expansion Plan

This document outlines the plan to expand the player scoring system with more dynamic point allocation based on player performance and engagement.

## 1. Project Goals

The primary goal is to make scoring more engaging by rewarding players for quick and accurate answers while adjusting points based on hints.

-   **First to Answer Bonus**: Award extra points to the player who submits the correct answer first.
-   **Fewer Guesses Bonus**: Grant more points to players who answer correctly with fewer attempts.
-   **Hint Penalty**: Reduce the points awarded for a correct answer if the player has seen a hint.

## 2. Implementation Plan

### Phase 1: Core Logic Modifications

The game's core logic will be updated to handle the new scoring parameters.

1.  **Track Hint State**: In `src/core/game_runner.py`, we will add a state variable to track when a hint has been revealed for the current question. This state will be reset with each new question. When a player guesses, we will check their guess time against the hint reveal time to determine if the hint was available to them.

2.  **Update `handle_guess`**: In `src/core/game_runner.py`, the `handle_guess` method will be enhanced to:
    -   Query the `guesses` table to check if any other player has already answered the current question correctly using the `guessed_at` timestamp.
    -   Count the number of previous incorrect guesses made by the player for the current question.
    -   Pass this information, along with whether the hint was used, to a new score calculation service.

### Phase 2: Scoring Calculator Implementation

A dedicated module for calculating scores will centralize the new logic.

1.  **Create `scoring_service.py`**: A new file at `src/core/scoring_service.py` will contain a `calculate_score` function.

2.  **Implement Scoring Logic**: The `calculate_score` function will take parameters such as `base_score`, `is_first_correct`, `guess_count`, and `was_hint_used` to determine the final score for a correct answer. The logic will be as follows:
    -   Start with a `base_score`.
    -   Add a bonus if `is_first_correct` is true.
    -   Apply a multiplier that decreases with each `guess_count`.
    -   Apply a penalty if `was_hint_used` is true.

### Phase 3: Testing

To ensure the new scoring system is working correctly, we will expand our test suite.

1.  **Unit Tests**: Add unit tests for the `scoring_service.py` module to verify that the scoring logic is correct under various conditions.

2.  **Integration Tests**: Update the tests for `GameRunner` in `tests/src/core/test_game_runner.py` to simulate different guessing scenarios and assert that players receive the correct scores. This includes testing:
    -   A player answering first.
    -   A player answering after multiple attempts.
    -   A player answering after a hint is given.
    -   A combination of the above scenarios.
