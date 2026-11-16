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

6. **Atomic gameplay persistence** (M/L): Propagate database errors and make each event's history, scores, streaks, and related updates atomic. Include rollback/failure and retry tests; do not assume the reducer alone guarantees persisted parity. Plan migrations and operational recovery separately.
7. **Workflow integration tests** (M): Exercise production game managers and real in-memory SQLite, substituting only external services. Cover normal play, power-ups, restart, corrections, settlement, and failure recovery. Keep focused reducer tests and the existing fake-backed parity harness; add scenarios incrementally with each fix.
8. **Test audit** (L, incremental): Replace brittle exact-SQL and internal-call assertions with observable outcomes where the interaction itself is not the contract. Remove empty tests and tests that recreate a workflow's calculations without running it. Retain mocks where they test external boundaries or meaningful side effects.
9. **Cleanup inventory** (L, incremental): Review TODOs, unused paths, duplicated Discord response handling, old feature plans, and the SQL-injection TODO. Verify callers and behavior before deletion. Consider CI formatting policy separately.

## Ownership Direction

- `DailyGameReducer` should own game-rule transitions; scoring inputs and effect application are still assembled outside it. Avoid a broad rewrite: move duplicated decisions only when a concrete bug or change demonstrates the need.
- `GuessHandler` currently calculates and persists base scores, then dispatches to `PowerUpManager`, which owns daily state and applies additional effects; replay assembles similar inputs independently. Clarify who prepares event inputs, applies effects, and owns state so one action cannot be partly applied or interpreted differently.
- `GameRunner` orchestrates question lifecycle, restoration, corrections, and verification. Keep it as an orchestrator; extract a cohesive responsibility only when doing so makes a real workflow easier to test or change.
- `DataManager` owns database access, while `PlayerManager` coordinates related writes. A transaction boundary should span the complete gameplay action, not merely individual SQL statements. Keep Discord and Gemini outside domain rules.

## Review Notes

S/M/L describe expected human review effort, not risk. Ordering and persistence changes can affect production scores; preserve old data and verify recovery before deployment. Review simplifications opportunistically, without expanding a focused fix into a repository-wide cleanup.