# Live and Replay Game Engine Parity

## Problem

jbot calculates a question day's scores in two places:

- `PowerUpManager` and `GuessHandler` update the live game as Discord events arrive.
- `DailyGameSimulator` replays persisted events for answer corrections, midday restoration, and end-of-day reconciliation.

Both paths use `PowerUpEngine`, but sharing individual helpers does not guarantee that they:

- receive the same state,
- process events in the same order,
- apply the same side effects, or
- persist the same score deltas.

Recent jinx issues demonstrate the failure mode:

- The live path did not increment `guesses_count`, so retroactive jinxes could not charge prior wrong guesses.
- The live path applied a rest bonus to the context score after copying the pre-rest score into daily state.
- The replay path applied the rest bonus before resolving jinx.
- A penalty could be deducted from transient state without being persisted to the attacker's score.

The pure power-up calculations were individually plausible, while the complete live and replay workflows were not equivalent.

## Goals

1. Make live play and replay produce the same player state and score movements for the same ordered event stream.
2. Make every score movement attributable to a specific event and rule.
3. Keep Discord, database, and external-service concerns out of pure game-rule calculations.
4. Make parity failures easy to diagnose without manually reconstructing a day.
5. Preserve the ability to restore midday state and recalculate after answer corrections.
6. Continue persisting game events and use the current daily snapshot plus in-memory state to keep live responses low-latency.

## Non-goals

- Replacing SQLite.
- Requiring a full event-sourcing rewrite before improving current reliability.
- Making Discord presentation messages part of the scoring domain model.
- Removing configurable game rules such as `JBOT_JINX_SHARE_RATIO`.

## Current failure boundaries

### 1. Shared engine, separate orchestration

`PowerUpEngine` mutates `DailyPlayerState`, but each caller decides when to:

- increment guesses,
- calculate points,
- apply rest,
- resolve jinx,
- resolve steal, and
- persist score changes.

The same helper can therefore be called with different state or at a different point in the lifecycle.

### 2. State and persistence are separate

The live manager maintains transient state and separately calls `update_score()`. A change can be correct in memory but missing from the database, or persisted before the in-memory state is updated.

### 3. Replay has no live side-effect contract

The simulator reconstructs final state but does not produce a formal list of score deltas that can be compared with live persistence operations.

### 4. Tests are strong at the pure-engine layer but weaker at workflow parity

Unit tests that construct `DailyPlayerState` directly can prove that a transfer includes a rest bonus. They do not prove that live orchestration placed the rest bonus into that state before transfer.

## Options

### Option A: Shared transition reducer

Create a domain-level reducer with an interface such as:

```text
next_state, effects = reduce(state, event, context)
```

The reducer would own the complete ordering for a guess or power-up event:

1. Count the guess.
2. Reject or ignore guesses that cannot score.
3. Determine correctness.
4. Calculate ordinary points and bonuses.
5. Apply rest multiplier.
6. Update earned score and bonuses.
7. Resolve jinx.
8. Resolve steal.
9. Emit score and persistence effects.

Live handling would apply the effects to `PlayerManager` and `DataManager`. Replay would apply the same reducer without external side effects.

**Advantages**

- Strongest guarantee that ordering is shared.
- Rules are testable without Discord or SQLite.
- Effects make persistence requirements explicit.

**Costs**

- Requires refactoring the current manager orchestration.
- Requires a clear immutable/mutable state convention.
- Existing tests and callers need migration.

### Option B: Shared event-to-effects service, minimal state refactor

Keep `DailyPlayerState` mutable, but move each complete event workflow into shared functions:

```text
process_guess(state, guess, context) -> effects
process_jinx(state, target, context) -> effects
```

Both live handling and replay call these functions. The functions return explicit score deltas and messages/data needed by the caller.

**Advantages**

- Smaller change than a full reducer.
- Directly addresses duplicated sequencing.
- Easier incremental migration from current code.

**Costs**

- Mutable-state ordering remains a risk if callers can mutate state outside the service.
- The boundary must be enforced by convention or API design.

## Considered alternatives (not selected)

### Option C: Score ledger and reconciliation

Keep the existing live path, but record every score movement as a structured ledger entry:

```text
question_id
event_id
player_id
source
amount
metadata
```

Examples of `source` include:

- `base_score`
- `rest_bonus`
- `jinx_transfer`
- `jinx_wrong_guess_penalty`
- `steal_transfer`
- `crowd_wisdom`

Replay emits the same ledger categories. End-of-day reconciliation compares live and replay ledgers by event and player rather than comparing only final totals.

This is not part of the agreed roadmap. The existing game-event history remains authoritative; diagnostics should be derived from event-level before/after state rather than persisted as a second score ledger.

**Advantages**

- Excellent diagnostics.
- Can be introduced without immediately rewriting all orchestration.
- Makes score discrepancies explainable to operators.

**Costs**

- Does not inherently prevent the live and replay calculations from diverging.
- Adds persistence/storage complexity.
- Requires stable event identifiers and idempotency rules.

### Option D: Replay as the authoritative live calculator

Persist events first, then calculate scores by running the simulator for the current day. The live path would use the resulting state/deltas after each event or at controlled checkpoints.

**Advantages**

- One calculation path.
- Reconciliation becomes a normal replay rather than a second implementation.

**Costs**

- More latency and complexity during live guesses.
- Requires careful handling of concurrent Discord events.
- Requires transactional event persistence and state publication.
- Larger operational change than the current architecture needs immediately.

This is a long-term architectural alternative, not part of the current roadmap. The reducer introduced in Phase 3 should merge the live and simulated rule paths while preserving the current in-memory state for latency. Event persistence and daily snapshots remain part of the design.

## Agreed roadmap: Option E

### Option E: Parity harness without major architecture changes

Build a reusable test harness that runs the same event sequence through:

1. The live manager with an in-memory persistence adapter.
2. `DailyGameSimulator`.

Compare:

- final score,
- earned score,
- stolen score,
- guesses count,
- bonuses,
- streak delta,
- jinx penalty totals,
- active/resolved power-up flags, and
- emitted score deltas.

Add scenario fixtures for ordering-sensitive combinations:

- jinx plus rest,
- forward jinx plus wrong guesses,
- retroactive jinx after wrong guesses,
- late retroactive jinx,
- jinx plus steal,
- rest cancellation,
- overnight preload hydration, and
- answer corrections.

**Advantages**

- Lowest-risk immediate improvement.
- Finds integration bugs that pure engine tests miss.
- Useful regardless of the eventual architecture.

**Costs**

- Detects divergence rather than preventing it.
- The live adapter must accurately model persistence behavior.
- Scenario coverage must be maintained as features grow.

## Recommendation: E -> B -> A

Implement **Option E**, then **Option B**, then formalize the result as **Option A**.

### Phase 1: Establish parity protection now

1. Create a shared live/replay parity harness that feeds the same ordered game events through the live workflow and `DailyGameSimulator`.
2. Use an in-memory persistence adapter for the live side so tests observe real manager orchestration without Discord or SQLite setup.
3. Compare complete before/after player state, not only final totals:
   - score and earned score;
   - stolen score;
   - guesses and bonuses;
   - streak delta;
   - jinx penalty totals;
   - rest, jinx, and steal flags; and
   - persisted score changes and emitted messages.
4. Add explicit invariant tests:
   - every submitted guess increments `guesses_count` exactly once;
   - a rest bonus is applied before jinx transfer;
   - every transient score mutation has a corresponding live persistence effect;
   - a retroactive jinx charges one penalty per prior wrong guess;
   - forward and retroactive jinx use the same share calculation.
5. Add message tests for forward, retroactive, and late-retroactive penalty visibility.
6. Consolidate duplicate tests by responsibility:
   - retain focused pure-engine tests for arithmetic and state rules;
   - move multi-feature workflows into integration/parity tests;
   - remove tests that repeat the same behavior through different setup details.

This phase would have caught the recent jinx issues without requiring a broad rewrite.

### Phase 2: Centralize complete event workflows

Create a shared event-processing service that owns complete guess and power-up transitions. The live manager should become an adapter that:

- validates Discord-facing input,
- constructs or dispatches a domain event,
- invokes the shared transition,
- persists the returned score/state effects, and
- formats user-facing messages.

The simulator should dispatch the same event and collect the same effects without performing external side effects.

The initial implementation may retain mutable `DailyPlayerState`, but mutation should be private to the service. Managers should receive read-only snapshots and returned results rather than directly changing daily state.

Recommended enforcement mechanisms:

- make the service the only approved writer of daily state;
- keep manager state private and expose snapshots rather than mutable objects;
- return explicit effects for score/database changes;
- add a lightweight code-review or lint rule against direct daily-state writes outside the service; and
- compare state snapshots before and after every event in parity tests.

The service should not make the exact score-effect ledger authoritative. Effects are an execution result used by live persistence and diagnostics; persisted game events remain the source of truth.

### Phase 3: Formalize the reducer architecture

Formalize the Phase 2 service as a reducer:

```text
new_state, effects = reduce(previous_state, event, context)
```

The reducer should:

1. Dispatch all persisted game event types through one domain boundary.
2. Own event ordering, including guess counting, scoring, rest, jinx, steal, and streak updates.
3. Return a new state or controlled state transition plus derived effects.
4. Be deterministic for the same event sequence, question, configuration, and rule version.
5. Support both live incremental processing and replay from the daily snapshot.

The live path should continue using in-memory state for low latency. It should persist each game event and apply the reducer result immediately. The simulator should use the same reducer from the snapshot. This removes duplicated rule orchestration without requiring every live request to run a full-day replay.

At this stage, immutable or copy-on-write state can be introduced if the mutable service boundary is still too permissive. That is an implementation hardening step, not a prerequisite for Phase 2.

## Suggested domain invariants

These should be encoded as tests and, where practical, assertions or validation logs:

1. A guess event is counted exactly once.
2. A player's first correct answer resolves scoring exactly once.
3. Rest bonus is included in the target's earned score before jinx resolution.
4. Jinx share uses the configured ratio consistently for forward and retroactive paths.
5. Previously stolen points are not included in the jinx share.
6. Each wrong target guess while jinxed produces exactly one penalty.
7. Retroactive jinx applies penalties for all prior wrong guesses exactly once.
8. Every live state/effect change emitted by the domain transition is persisted or intentionally represented by a documented non-persistent effect.
9. Replay and live processing of the same ordered events produce equivalent state and derived effects.
10. Replaying the same event stream twice is deterministic and does not double-apply effects.

## Operational diagnostics

When reconciliation fails, report component-level differences:

- base points,
- try bonus,
- before-hint bonus,
- fastest bonus,
- streak bonus,
- rest bonus,
- jinx received,
- jinx paid,
- jinx wrong-guess penalties,
- steal received,
- steal paid, and
- end-of-day bonuses.

This is more actionable than reporting only a final score mismatch and should be retained with the question-day reconciliation record. The report should be derived from persisted game events and state snapshots, not from a second authoritative score ledger.
