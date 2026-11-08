# Architecture Improvement Plan

## Approach

Make one review-sized change at a time; favor behavior-preserving simplification over new abstractions. Run focused tests for each change and the full CI discovery suite before merge. The existing [parity plan](game_engine_parity.md) provides background; this document tracks the next work.

## First: Small Reviews

1. **Rest configuration** (S, completed): The reducer now reads documented `JBOT_REST_MULTIPLIER`; the typo key had no production configuration/documentation references, so no compatibility alias was added. A nondefault live-scoring regression test covers rest and the next correct guess.
2. **CI simulation trigger** (S): Include reducer and power-up changes in the simulation workflow's path filters. Check other direct simulation dependencies; keep this independent of formatting-workflow changes.
3. **Verification status** (S): Distinguish a skipped verification from a successful match, and test the caller's reporting.
4. **Answer correction IDs** (S/M): Make correction storage, live lookup, verification, and restoration consistently use the intended question identifier. Test with distinct question and daily-question IDs, including correction and restart. Inspect existing data and compatibility before deciding on a migration.
5. **Replay ordering** (investigation S, implementation M or larger): Reproduce same-second guess/power-up ordering with real SQLite. Design a durable cross-type order for new events and a deterministic fallback for historical events; timestamps and separate table IDs cannot recover the original order of old ties. Review any schema migration and preload semantics separately before implementation.

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