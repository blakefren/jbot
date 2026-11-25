# Architecture Improvement Plan

## Approach

Make one review-sized change at a time; favor behavior-preserving simplification over new abstractions. Run focused tests for each change and the full CI discovery suite before merge. The existing [parity plan](game_engine_parity.md) provides background; this document tracks the next work.

## First: Small Reviews

1. **Rest configuration** (S, completed): The reducer now reads documented `JBOT_REST_MULTIPLIER`. The typo key (`JBOT_REST_BONUS_PER_DAY`) had no production configuration/documentation references, so no compatibility alias was added; its only remaining use was `scripts/simulate_powerups.py` (the CI simulation), which now reads `JBOT_REST_MULTIPLIER` too. Internal names are aligned (`rest_multiplier`). A nondefault live-scoring regression test covers rest and the next correct guess.
2. **CI simulation trigger** (S, completed): Reducer and power-up changes now trigger the simulation workflow for pushes and pull requests.
3. **Verification status** (S, completed): Skipped verification now returns `None`, distinct from a clean empty diff list, and the evening task does not report skips as success.
4. **Answer correction IDs** (closed; no migration planned): Live lookup, answer display, correction storage, verification, and restoration use canonical `questions.id`. The read-only `jbot_restore.db` audit found 48 legacy alternative rows stored against daily IDs, 37 of which numerically collide with a different canonical question. This affects old-question manual investigation only; current gameplay is unaffected in this snapshot. Leave the rows untouched unless historical lookups become important.
5. **Replay ordering** (implemented):
	- **Finding (historical, before the fix):** `jbot_restore.db` has 272 exact timestamp groups spanning guesses and power-ups; 270 are derived `rest_wakeup` events, but 8 are consequential actions (3 steals, 2 late jinxes, 2 jinxes, 1 rest). There are also 14 same-second groups with two correct solvers, which can affect fastest-answer rank. Timestamps have second precision; guess queries lacked an ID tie-break, power-up queries had no ordering, and the simulator's stable sort placed all tied guesses before power-ups.
	- **Why order matters:** A tied jinx or steal can be forward versus retroactive depending on which came first; rest can suppress a tied guess; retaliation depends on the earlier attack. Independent wrong guesses usually commute, but same-second correct guesses share rank and do not.
	- **Implementation:** New guesses and power-ups receive a shared per-question sequence within their insert; preloads are sequenced when hydrated. A shared in-process lock serializes gameplay actions, and replay uses the sequence. Existing databases gain nullable sequence columns at startup; no historical rows are rewritten.
	- **Read-side follow-up:** `read_guess_history` now orders by `guessed_at, id`, and the leaderboard's fastest-answer badges tie-break same-second solvers by guess id, matching live ranking and replay. The before-hint badge counts a guess in the same second as the hint as before the hint (as the simulator does); it previously used a strict `<`. Regression tests cover history order and both badge cases.
	- **Legacy/limits:** Unsequenced history sorts by timestamp, then guesses before power-ups and table row ID; its actual same-second order cannot be recovered. The lock protects a single bot process; fully atomic gameplay persistence and cross-process coordination remain item 6.

## Next: Larger Reviews

6. **Atomic gameplay persistence** (M/L, complete): Foundation complete: `Database.transaction()` groups executor calls, rolls back and propagates errors inside the scope, supports nested savepoints, and preserves legacy standalone error results. `DataManager.transaction()` exposes the boundary. Guess handling and standalone power-up actions are transactional, with injected failures verifying persistence and in-memory rollback. Implementation order:
	- [x] **#1 Answer correction:** simulation is serialized with game actions; answer/guess changes, score/streak adjustments, audit rows, and rest multiplier clears commit together.
	- [x] **#2 Crowd-wisdom awards:** serialized reducer state, score changes, and usage logs commit together; reducer state is restored if persistence fails.
	- [x] **#3 End-of-day settlement:** serialized streak resets and stale rest-multiplier cleanup commit together; reducer state is restored on failure and manager/question state is cleared only after commit.
	- [x] **#4 Question creation and skipping:** question rows and player snapshots are atomic; skip rollback, replacement logging/snapshot, manager reset, and preload hydration share one transaction. Selection and Gemini calls remain outside it.
	- [x] **#5 Admin refunds:** slash command and quick-action modal share `PlayerManager.refund_player()`, which commits score, streak, season totals, and audit logging together.
	- [x] **Season finalization:** ranking/trophy updates and marking the season inactive commit together; an injected failure verifies the finalization state rolls back.
	- [x] **Post-audit follow-ups:** season rollover (finalize/create/reset) and role refresh (clear/reassign, including role creation) are transactional and covered by failure-injection tests. New-season challenge creation remains best-effort, with its insert isolated transactionally.
Plan migrations and operational recovery separately.
7. **Workflow integration tests** (M, complete): Real SQLite workflows cover correct/wrong guess persistence, rank-two fastest scoring, answer correction followed by retroactive jinx/steal, same-second jinx/steal/rest ordering, concurrent action serialization, preload hydration, file-backed restart/replay, leaderboard power-up badges, and end-of-day settlement with `verify_daily_play`. Slash/button parity tests compare shared guess outcomes, forward/retroactive jinx and steal visibility, rest messaging/state, refund persistence, answer-correction formatting/state sync, and skip outcomes. Discord/Gemini remain mocked at the external boundary. Injected DB write failures cover guess, power-up, answer-correction, crowd-wisdom, end-of-day settlement, question snapshot, skip/preload, refund, season-finalization, season-rollover, and role-refresh rollback.
8. **Test audit** (complete; ongoing maintenance): Replaced the invalid-SQL add-answer regression with real Admin/GameRunner/SQLite/power-up behavior; removed five empty tests and the no-op GameRunner fake adapter; converted DataManager CRUD, role, subscriber, question, lookup, PlayerManager, and leaderboard badge tests from SQL-result mocks to stored-state assertions; made guess history stateful in handler tests and changed fastest-rank to exercise production scoring. `test_data_manager.py` no longer replaces SQL executors. The remaining DataManager/PlayerManager/GameRunner/PowerUpManager mocks in the cog, Discord, game-runner, power-up, guess-handler, season and challenge tests were later replaced with real in-memory SQLite stacks (shared helpers: `RealStack`/`make_stack` in `tests/src/core/_powerup_helpers.py` and `build_game_stack` in `tests/src/cogs/_game_stack.py`). Remaining mocks are deliberate external Discord/Gemini/`ConfigReader`/question-source boundaries, failure injection via `patch.object` on real objects, or unit orchestration seams with corresponding SQLite workflow coverage. One exception remains: `TestDiscordBotBackup` in `test_discord.py` still mocks `data_manager` (see the backup bug below). `coverage.py` and `scripts/run_coverage.bat` enforce a 90% combined line/branch PR floor (last run: 1116 tests, 92% total); the lowest-covered modules are `game.py` (77%), `logging_config.py` (80%), `discord.py` (81%), `quick_actions.py` (84%) and `cfg/main.py` (84%). The `coverage-exempt` PR label skips only that floor, never tests or reporting; create the label once in GitHub. Continue reviewing mocks as new tests are added.
9. **Cleanup inventory** (L, complete): Removed unused player-streak reset helpers and their direct tests; retained `get_grace_period_players()` because production code uses it. Removed obsolete refund TODOs and replaced dynamic SQL identifier paths with allowlists and rejection tests. Shared guess outcomes and correction formatters now serve slash and Quick Action paths; jinx/steal visibility comes from structured outcomes, rest initializes season state in the shared power-up workflow, and refunds/skips continue through shared application methods. Remaining repeated Discord handling is presentation-only: slash and button adapters intentionally differ in defer/followup/channel semantics. CI formatting is currently Black's non-checking, auto-commit behavior; keep it as an existing policy unless maintainers want PRs to fail rather than auto-commit formatting. A later pass removed the remaining dead code: unused `DataManager` stats and hint-solver helpers, `has_crowd_wisdom_awards`, `mark_guess_as_correct`, `get_correct_guess_count`; `DailyGameSimulator._get_crowd_wisdom_counts` and `apply_crowd_wisdom_bonus`; `PlayerManager.set_name`; `SeasonManager.initialize_player_for_season` and `get_season_summary`; `Season.is_current`; the unused season shield/double-points fields in the dataclass and allowlists; `Player.to_dict`/`from_dict`; `Question.to_dict`/`from_dict`/`get_metadata` and its demo block; `Database.get_conn`; `DailyPlayerState.powerup_used_today`; `compare_schemas` and `update_schema` in `db/update_schema.py`; unused script helpers/constants; and unused imports. Deliberately retained: the season-challenge progress cluster (see Open by decision), the `shields_used`/`double_points_used` schema columns (no migration), and `DataManager.initialize_database()` (documented test bootstrap). No mock cleanup remains for external Gemini/Discord boundaries or SQL/database behavior except the backup test above; mocks beyond those boundaries must be justified as unit orchestration seams.

## Ownership Direction

- `DailyGameReducer` should own game-rule transitions; scoring inputs and effect application are still assembled outside it. Avoid a broad rewrite: move duplicated decisions only when a concrete bug or change demonstrates the need.
- `GuessHandler` currently calculates and persists base scores, then dispatches to `PowerUpManager`, which owns daily state and applies additional effects; replay assembles similar inputs independently. Clarify who prepares event inputs, applies effects, and owns state so one action cannot be partly applied or interpreted differently.
- `GameRunner` orchestrates question lifecycle, restoration, corrections, and verification. Keep it as an orchestrator; extract a cohesive responsibility only when doing so makes a real workflow easier to test or change.
- `DataManager` owns database access, while `PlayerManager` coordinates related writes. A transaction boundary should span the complete gameplay action, not merely individual SQL statements. Keep Discord and Gemini outside domain rules.

## Review Notes

S/M/L describe expected human review effort, not risk. Ordering and persistence changes can affect production scores; preserve old data and verify recovery before deployment. Review simplifications opportunistically, without expanding a focused fix into a repository-wide cleanup.

# 2026-11-25 Update

## Status of the plan above

Items 1–9 are complete as written (with the corrections noted inline), with these exceptions:

- `TestDiscordBotBackup` in `test_discord.py` still mocks `data_manager`; the production bug behind it (Fix first #1) is unfixed.
- The season-challenge progress-tracking cluster is deliberately kept (see Open by decision).
- Ownership Direction is a set of design directions, not tasks.

Done in this pass: live/replay parity tests moved onto real SQLite (fixing seven failures caused by a test fake missing `get_current_season`); `JBOT_REST_MULTIPLIER` aligned across code, simulation script and tests; read-side ordering edge cases fixed (item 5); remaining database mocks replaced with real stacks (item 8); dead code removed (item 9). Final state: 1116 tests passing, 92% combined coverage, Black clean. The 28-day `scripts/simulate_powerups.py` was not re-run after these changes (compile check only).

## Additional gaps identified

### Fix first (real bugs)

1. **Nightly backup always fails.** `discord.py` (`_backup_database`, ~line 555) reads `self.data_manager.db.db_path`, but `DataManager` only has `_db`. The `AttributeError` is caught and logged by the evening task. Fix: add a `db_path` accessor on `DataManager`, then convert `TestDiscordBotBackup` to a real `DataManager`; that mock is what hid the bug.
2. **`end_daily_game()` is unguarded.** In `evening_message_task` it is called bare. Settlement now re-raises on failure, so the task aborts before season announcements, verification and backup, and the question stays active. Wrap it like the other steps using `_log_task_error`, and add a test.
3. **Empty-snapshot handling is inconsistent.** `get_daily_snapshot` returns `{}`, never `None`. `restore_game_state`, `end_daily_game` and `apply_crowd_wisdom_bonus` all use `snapshot if snapshot is not None else get_all_players()`, so the fallback to current players never runs. `recalculate_scores_for_new_answer` uses `if snapshot:`, so the paths disagree. Pick one rule and apply it everywhere.
4. **A bad overnight preload can block the day's question.** `PowerUpManager.hydrate_pending_powerups` raises `PowerUpError` on a rejected preload (for example a retaliation conflict). Hydration runs inside the question-setup transaction, so question creation rolls back and every retry fails the same way. Fix: log and skip the bad row instead of raising.
5. **Guess errors are no longer logged.** `guess_display.process_guess` has a bare `except Exception` returning a generic message; the old cogs logged `logging.error`. Add `logging.exception`.
6. **Rest leaks raw error text to users.** `/power rest` in `cogs/power.py` and `confirm_rest` in `quick_actions.py` send `str(e)` for any exception. Show only `PowerUpError` text, send a generic message otherwise, and log it in both paths.
7. **A correction on a past day overwrites live state.** `recalculate_scores_for_new_answer` copies `scorer_new.daily_state` into `PowerUpManager.daily_state` even when the question is not the active one. Only do this when `is_active_question`. Commit `7935983` moved this behavior; it did not introduce it.
8. **Evening verification is untested end to end.** No test checks that `verify_daily_play` reports clean for the full evening-task scenario; the task test only asserts admins are not notified.

### Lower priority

- `Database.execute_query` and `execute_update` read `_transaction_depth` outside the lock in their error path. Under threads, a standalone failing query could raise instead of returning `[]`.
- `set_daily_question` runs under `asyncio.to_thread` while holding the global action lock, so commands wait during setup. No deadlock was found; lock order is consistent. `restore_game_state` on the restart path is not under the action lock.
- Simulation runtime: a 3-day `simulate_powerups.py` run took 3.5 min at HEAD against 1.4 min before the transaction work (`7e307ae^`). The CPU was shared during those runs, so the timing is unreliable. A 28-day run did not finish in about 10 minutes, and the CI simulation workflow has no timeout. Needs a clean measurement.
- Docs and config:
  - `database_access_architecture.md` does not mention `transaction()` and still recommends mocking DataManager.
  - `.coveragerc` has `source = db` and excludes every line containing `pass` from coverage.
  - The `coverage-exempt` label must be created by hand in GitHub (done).
- `RolesGameMode.on_guess` has a signature that does not match `BaseManager`.
- The 48 legacy alternative-answer rows (37 colliding with a different canonical ID) can still skew replay of those old days. Per item 4, no action unless historical lookups matter.

### Open by decision

- Season challenge progress tracking is never called in production; these are only reached by tests: `check_challenge_progress`, `_get_challenge_goal`, `update_challenge_progress`, `get_challenge_display`, `get_all_challenge_completions`. Challenges are created and announced, but progress is never recorded, evaluated or shown.
- Kept deliberately: the schema columns `shields_used` and `double_points_used`, and `DataManager.initialize_database()`.

## Test harness

- `build_game_stack` (`tests/src/cogs/_game_stack.py`) builds a real in-memory DB with `DataManager`, `PlayerManager` and a real `GameRunner` with `PowerUpManager`. `ConfigReader` and the question selector are doubles. It optionally enables seasons and starts the day, and imports `make_config` from `_powerup_helpers.py`. Seven files use it: `test_admin`, `test_admin_add_answer`, `test_game`, `test_power`, `test_quick_actions`, `test_trivia` and `test_discord`.
- `RealStack` / `make_stack` (`tests/src/core/_powerup_helpers.py`) is a lighter version: DB, `DataManager` and `PlayerManager`, with seeded players (score, streak) and today's daily question, and no `GameRunner`. It also offers `mark_answered_today`, `answer_on_earlier_day`, `send_hint` and `usages()`; `players[...]` re-reads each player from the DB. Six files use it: `test_powerup`, `test_powerup_late_day`, `test_powerup_overnight_retro`, `test_retaliation_blocking`, `test_guess_handler` and `test_guess_handler_alternatives`.
- Not consolidated: `test_action_parity`, `test_add_answer_jinx_steal_regression`, `test_live_replay_parity`, `test_gamerunner_format`, `test_game_runner` and `test_season_manager_integration` each keep their own inline setUp. Moving them onto these helpers is a reasonable later cleanup.
