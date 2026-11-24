# Architecture Improvement Plan

## Approach

Make one review-sized change at a time; favor behavior-preserving simplification over new abstractions. Run focused tests for each change and the full CI discovery suite before merge. The existing [parity plan](game_engine_parity.md) provides background; this document tracks the next work.

## First: Small Reviews

1. **Rest configuration** (S, completed): The reducer now reads documented `JBOT_REST_MULTIPLIER`; the typo key had no production configuration/documentation references, so no compatibility alias was added. A nondefault live-scoring regression test covers rest and the next correct guess.
2. **CI simulation trigger** (S, completed): Reducer and power-up changes now trigger the simulation workflow for pushes and pull requests.
3. **Verification status** (S, completed): Skipped verification now returns `None`, distinct from a clean empty diff list, and the evening task does not report skips as success.
4. **Answer correction IDs** (closed; no migration planned): Live lookup, answer display, correction storage, verification, and restoration use canonical `questions.id`. The read-only `jbot_restore.db` audit found 48 legacy alternative rows stored against daily IDs, 37 of which numerically collide with a different canonical question. This affects old-question manual investigation only; current gameplay is unaffected in this snapshot. Leave the rows untouched unless historical lookups become important.
5. **Replay ordering** (implemented):
	- **Finding:** `jbot_restore.db` has 272 exact timestamp groups spanning guesses and power-ups; 270 are derived `rest_wakeup` events, but 8 are consequential actions (3 steals, 2 late jinxes, 2 jinxes, 1 rest). There are also 14 same-second groups with two correct solvers, which can affect fastest-answer rank. Timestamps have second precision; guess queries lack an ID tie-break, power-up queries have no ordering, and the simulator's stable sort currently places all tied guesses before power-ups.
	- **Why order matters:** A tied jinx or steal can be forward versus retroactive depending on which came first; rest can suppress a tied guess; retaliation depends on the earlier attack. Independent wrong guesses usually commute, but same-second correct guesses share rank and do not.
	- **Implementation:** New guesses and power-ups receive a shared per-question sequence within their insert; preloads are sequenced when hydrated. A shared in-process lock serializes gameplay actions, and replay uses the sequence. Existing databases gain nullable sequence columns at startup; no historical rows are rewritten.
	- **Legacy/limits:** Unsequenced history sorts by timestamp, then guesses before power-ups and table row ID; its actual same-second order cannot be recovered. The lock protects a single bot process; fully atomic gameplay persistence and cross-process coordination remain item 6.

## Next: Larger Reviews

6. **Atomic gameplay persistence** (M/L, in progress): Foundation complete: `Database.transaction()` groups executor calls, rolls back and propagates errors inside the scope, supports nested savepoints, and preserves legacy standalone error results. `DataManager.transaction()` exposes the boundary. Guess handling and standalone power-up actions are transactional, with injected failures verifying persistence and in-memory rollback. Implementation order:
	- [x] **#1 Answer correction:** simulation is serialized with game actions; answer/guess changes, score/streak adjustments, audit rows, and rest multiplier clears commit together.
	- [x] **#2 Crowd-wisdom awards:** serialized reducer state, score changes, and usage logs commit together; reducer state is restored if persistence fails.
	- [x] **#3 End-of-day settlement:** serialized streak resets and stale rest-multiplier cleanup commit together; reducer state is restored on failure and manager/question state is cleared only after commit.
	- [x] **#4 Question creation and skipping:** question rows and player snapshots are atomic; skip rollback, replacement logging/snapshot, manager reset, and preload hydration share one transaction. Selection and Gemini calls remain outside it.
	- [x] **#5 Admin refunds:** slash command and quick-action modal share `PlayerManager.refund_player()`, which commits score, streak, season totals, and audit logging together.
	- [ ] **Season finalization:** combine ranking/trophy updates and marking the season inactive.
Plan migrations and operational recovery separately.
7. **Workflow integration tests** (M, first tranche complete): Real SQLite workflows cover correct/wrong guess persistence, rank-two fastest scoring, answer correction followed by retroactive jinx/steal, same-second jinx/steal/rest ordering, concurrent action serialization, preload hydration, file-backed restart/replay, leaderboard power-up badges, and end-of-day settlement with `verify_daily_play`. Discord/Gemini remain mocked at the external boundary. Injected DB write failures cover guess, power-up, answer-correction, crowd-wisdom, end-of-day settlement, question snapshot, skip/preload, and refund rollback; broader workflow failure/recovery cases remain part of #6. The full suite now has 1,125 passing tests.
8. **Test audit** (broad audit complete; ongoing maintenance): Replaced the invalid-SQL add-answer regression with real Admin/GameRunner/SQLite/power-up behavior; removed five empty tests and the no-op GameRunner fake adapter; converted DataManager CRUD, role, subscriber, question, lookup, PlayerManager, and leaderboard badge tests from SQL-result mocks to stored-state assertions; made guess history stateful in handler tests and changed fastest-rank to exercise production scoring. `test_data_manager.py` no longer replaces SQL executors. Remaining mocks are deliberate external Discord/Gemini boundaries or unit orchestration seams with corresponding SQLite workflow coverage. `coverage.py` and `scripts/run_coverage.bat` enforce a 90% combined line/branch PR floor; the current total is 90%, with `quick_actions.py` and `discord.py` at 79% each. The `coverage-exempt` PR label skips only that floor, never tests or reporting; create the label once in GitHub. Continue reviewing mocks as new tests are added. The full suite now has 1,125 passing tests.
9. **Cleanup inventory** (L, incremental): Review TODOs, unused paths, duplicated Discord response handling, old feature plans, and the SQL-injection TODO. Verify callers and behavior before deletion. Consider CI formatting policy separately.

## Ownership Direction

- `DailyGameReducer` should own game-rule transitions; scoring inputs and effect application are still assembled outside it. Avoid a broad rewrite: move duplicated decisions only when a concrete bug or change demonstrates the need.
- `GuessHandler` currently calculates and persists base scores, then dispatches to `PowerUpManager`, which owns daily state and applies additional effects; replay assembles similar inputs independently. Clarify who prepares event inputs, applies effects, and owns state so one action cannot be partly applied or interpreted differently.
- `GameRunner` orchestrates question lifecycle, restoration, corrections, and verification. Keep it as an orchestrator; extract a cohesive responsibility only when doing so makes a real workflow easier to test or change.
- `DataManager` owns database access, while `PlayerManager` coordinates related writes. A transaction boundary should span the complete gameplay action, not merely individual SQL statements. Keep Discord and Gemini outside domain rules.

## Review Notes

S/M/L describe expected human review effort, not risk. Ordering and persistence changes can affect production scores; preserve old data and verify recovery before deployment. Review simplifications opportunistically, without expanding a focused fix into a repository-wide cleanup.