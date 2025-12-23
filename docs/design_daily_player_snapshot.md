# Design: Daily Player State Snapshots

## Problem Statement

The `jbot` project currently stores player state (score, streak, shield status) in the `players` table. This table represents the *current* state of the players.

However, the project uses an Event Sourcing pattern (`DailyGameSimulator`) for retroactive corrections (e.g., when an answer is corrected later in the day). To accurately recalculate scores and streaks for the day, the simulator requires the player state as it existed *at the beginning of the day* (before any events for that day occurred).

Currently, this "start-of-day" state is not persisted. If the bot restarts midday, or if we need to perform a manual refund/correction, we lack the baseline state required to replay the day's events correctly. This leads to manual effort to reconstruct streaks and scores or potential data inaccuracies.

## Proposed Solution

We will introduce a new table, `daily_player_states`, to store a snapshot of each player's state at the time a new daily question is posted.

This snapshot will serve as the immutable "initial state" for the `DailyGameSimulator` for that specific day.

### Schema Changes

New table `daily_player_states`:

```sql
CREATE TABLE IF NOT EXISTS daily_player_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_question_id INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    answer_streak INTEGER NOT NULL,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_question_id) REFERENCES daily_questions (id),
    FOREIGN KEY (player_id) REFERENCES players (id),
    UNIQUE(daily_question_id, player_id)
);
```

### Workflow

#### 1. Snapshot Creation (Start of Day)

When a new daily question is posted (specifically, when `DataManager.log_daily_question` is called), we will trigger a snapshot creation process.

*   **Action**: Copy `score` and `answer_streak` from the `players` table into `daily_player_states`, associated with the new `daily_question_id`.
*   **Scope**: All players currently in the `players` table.
*   **New Players**: Players who join *after* the snapshot is taken (midday) will not have a record in this table. The simulator should treat missing records as having default values (Score: 0, Streak: 0).

#### 2. Simulator Integration

The `DailyGameSimulator` currently accepts `initial_player_states`. We will modify the calling logic (likely in `GameRunner` or a dedicated `CorrectionManager`) to populate this from `daily_player_states`.

*   **Logic**:
    1.  Fetch all rows from `daily_player_states` for the target `daily_question_id`.
    2.  Convert these rows into `Player` objects.
    3.  Pass this map to `DailyGameSimulator`.

#### 3. Retroactive Correction (The "Refund" Scenario)

When an admin corrects an answer or manually triggers a recalculation:

1.  **Identify Day**: Determine the `daily_question_id` for the correction.
2.  **Fetch Context**:
    *   Load the snapshot from `daily_player_states`.
    *   Load all `guesses` and `powerup` events for that day from the DB.
3.  **Simulate**: Run `DailyGameSimulator` with the snapshot and the events.
4.  **Apply**: Update the `players` table with the *final* results from the simulator.

### Benefits

*   **Reliability**: We can restart the bot at any time without losing the "baseline" for the day.
*   **Accuracy**: Retroactive corrections become mathematically precise, as we are replaying from a known good state rather than a potentially modified "current" state.
*   **Auditability**: We have a historical record of player scores at the start of each day.

### Alternatives Considered

*   **Audit Logs**: Logging every single change to `players` (score +10, streak +1).
    *   *Pros*: Granular history.
    *   *Cons*: Reconstructing state requires replaying potentially thousands of events from the beginning of time (or a checkpoint). Snapshots are essentially daily checkpoints.
*   **Versioning `players` table**: Adding `valid_from`/`valid_to` columns.
    *   *Pros*: Full history in one table.
    *   *Cons*: Complicates all standard queries (leaderboards, profiles) which just want the "current" state.

### Implementation Plan

1.  **Database**: Add `daily_player_states` to `schema.sql` and create a migration script.
2.  **DataManager**: Add methods to `create_daily_snapshot(daily_question_id)` and `get_daily_snapshot(daily_question_id)`.
3.  **Game Lifecycle**: Call `create_daily_snapshot` immediately after a new daily question is created.
4.  **Simulator**: Update the usage of `DailyGameSimulator` to prefer the snapshot when available.
