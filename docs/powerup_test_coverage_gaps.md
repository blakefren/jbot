# Power-Up Test Coverage Gaps

Cross-reference of `docs/powerup_mechanics.md` against the current test suite.
Use this as a checklist — close one gap at a time and mark it done.

**Test files in scope:**
- `tests/src/core/test_powerup.py` — manager, live-game orchestration
- `tests/src/core/test_powerup_late_day.py` — late-day jinx/steal + simulator
- `tests/src/core/test_powerup_overnight_retro.py` — overnight pre-load, retro + simulator
- `tests/src/core/test_powerup_engine.py` — pure engine logic (well covered, not listed here)
- `tests/src/core/test_daily_game_simulator.py` — basic simulator scenarios
- `tests/src/cogs/test_power.py` — Discord cog layer

Legend: **H** = high priority · **M** = medium priority · **L** = low priority

---

## Section 1: Common Rules

### GAP 1.1 — Self-targeting not blocked · **H**
**Doc rule**: "No self-targeting: Jinx and steal require a different player as the target."
**Current coverage**: Zero — no test calls `jinx("1", "1", "q1")` or `steal("1", "1", "q1")`.
**Target file**: `test_powerup.py` → `TestGuards`
**Tests to add**:
- `test_jinx_self_target_blocked` — `jinx("1", "1", "q1")` raises `PowerUpError` containing "self"
- `test_steal_self_target_blocked` — `steal("1", "1", "q1")` raises `PowerUpError` containing "self"

---

### GAP 1.2 — "One power-up per day" missing two permutations · **L**
**Doc rule**: A player cannot use a second power-up on the same day.
**Current coverage**: jinx→jinx, steal→steal, jinx→steal, rest→jinx are each tested.
**Missing permutations**: jinx→rest and steal→rest (player attacks then tries to rest).
**Target file**: `test_powerup.py` → `TestGuards`
**Tests to add**:
- `test_rest_blocked_after_jinx` — jinx then rest raises "already used a power-up today"
- `test_rest_blocked_after_steal` — steal then rest raises "already used a power-up today"

---

## Section 2: REST

### GAP 2.1 — Resting player cannot be targeted · **H**
**Doc rule** (Steal "When Available"): "Target is not resting today." Same gate for Jinx.
**Current coverage**: None — no test tries to jinx or steal a player who has already invoked rest that day.
**Target file**: `test_powerup.py` → `TestGuards`
**Tests to add**:
- `test_jinx_blocked_when_target_is_resting` — set `target.is_resting = True`; `jinx("1", "2", "q1")` raises `PowerUpError`
- `test_steal_blocked_when_target_is_resting` — same setup; `steal("1", "2", "q1")` raises `PowerUpError`

---

### GAP 2.2 — Attacker silence NOT lifted when target rests · **M**
**Doc rule**: "jinxer's costs remain paid — if early, they stay silenced until the hint"
**Current coverage**: `test_rest_cancels_incoming_jinx` checks `jinxed_by` is cleared, but never asserts `attacker.silenced` is still `True` after the target rests.
**Target file**: `test_powerup.py` → `TestRestBehavior`
**Test to add**:
- `test_rest_does_not_lift_attacker_silence` — jinx("1","2","q1") then rest("2","q1","Ans"); assert `_get_daily_state("1").silenced is True`

---

### GAP 2.3 — Steal streak cost is forfeit when target rests · **M**
**Doc rule**: "The thief's streak cost is not refunded — it was paid when the steal was initiated and is forfeit."
**Current coverage**: `test_rest_cancels_incoming_steal` only asserts `steal_attempt_by` is `None` after rest. It does not assert that the thief's streak was not restored.
**Target file**: `test_powerup.py` → `TestRestBehavior`
**Test to add**:
- `test_rest_steal_cost_not_refunded` — `steal("1","2","q1")` then `rest("2","q1","Ans")`; assert `players["1"].answer_streak` equals the post-steal value (not the pre-steal value)

---

### GAP 2.4 — Late-jinx stripped bonuses NOT refunded when target rests · **M**
**Doc rule**: "if late, any bonuses already stripped as the jinx cost are not refunded."
**Current coverage**: None.
**Target file**: `test_powerup_late_day.py` → `TestJinxLateDay`
**Test to add**:
- `test_late_jinx_bonuses_not_refunded_when_target_rests` — set attacker state to already-answered with `before_hint` bonus; invoke late jinx; then `rest` target; assert attacker's `before_hint` bonus is still gone and score unchanged from post-jinx value

---

## Section 3: JINX

### GAP 3.1 — Retroactive jinx: attacker blocked when target has zero streak bonus · **M**
**Doc rule** (Expected Behavior table): "Retroactive jinx, target has no streak bonus → Blocked — nothing to steal, power-up slot preserved."
**Current coverage**: `test_retro_jinx_no_streak_bonus_blocked` in `test_powerup_overnight_retro.py` ✅ covers the manager-level block. Also `test_late_jinx_retro_no_streak_blocked` covers the late-day variant. This gap is **already covered** — no action needed.

---

## Section 4: STEAL

### GAP 4.1 — Attacker timing symmetry for steal (early ≡ late net cost) · **M**
**Doc rule** (Design Principle 1): "An attacker's net cost and gain must be identical whether they use a power-up before or after answering."
**Current coverage**: Both early and late steal paths are tested independently, but no test explicitly compares their net scores to assert equality.
**Target file**: `test_powerup_late_day.py` → `TestStealLateDay`
**Test to add**:
- `test_early_and_late_steal_same_net_cost` — two fresh managers with same fixture; one does early-forward steal, one does late-forward steal; after target answers, assert `thief.score` and `thief.answer_streak` are equal in both

---

## Section 5: Interaction Matrix

The doc defines 13 multi-player combination scenarios. Current coverage per row:

| # | Scenario | Status |
|---|---|---|
| 1 | Jinxed/stolen player rests → whiff | 🟡 Partial — attack cleared, but see Gaps 2.2–2.4 |
| 2 | Rested player targeted → blocked | ❌ Gap 2.1 |
| 3 | Two players jinx same target → 2nd blocked | ✅ `test_duplicate_jinx_on_same_target_blocked` |
| 4 | Two players steal same target → 2nd blocked | ✅ `test_duplicate_steal_on_same_target_blocked` |
| 5 | A jinxes B while C steals from B | ❌ Gap 5.1 — most important missing scenario |
| 6 | A forward steals B, B early jinxes C | ❌ Gap 5.2 |
| 7 | A forward steals B, B late jinxes C | 🟡 `test_steal_target_then_late_jinx_no_double_deduction` — checks no double deduction, not full bonus split |
| 8 | A retro steals B, B early jinxes C | ❌ Gap 5.3 |
| 9 | A retro steals B, B late jinxes C | ❌ Gap 5.3 |
| 10 | A forward jinxes B, B early steals C | ❌ Gap 5.4 |
| 11 | A forward jinxes B, B late steals C | 🟡 `test_late_steal_after_jinx_took_streak_no_recalculation` — checks streak recalc, not full resolution |
| 12 | A retro jinxes B, B early steals C | ❌ Gap 5.4 |
| 13 | A retro jinxes B, B late steals C | ❌ Gap 5.4 |

---

### GAP 5.1 — Simultaneous jinx + steal on same target · **H**
**Doc rule**: Both attacks coexist — bonus pools don't overlap. A gets B's streak bonus (100% forward or 50% retro); C gets all non-streak bonuses. B keeps only base score (plus remaining 50% streak if retro jinx).
**Current coverage**: None.
**Target file**: New class `TestInteractionMatrix` in `test_powerup_overnight_retro.py` (or a new `test_powerup_interactions.py`)
**Tests to add**:
- `test_jinx_and_steal_coexist_on_same_target` — A jinxes B (forward), C steals from B (forward); B answers with streak bonus + other bonuses; assert A gets streak, C gets non-streak, B keeps base
- `test_retro_jinx_and_steal_coexist_on_same_target` — same but A retro-jinxes (B already answered); assert A gets 50% streak, C gets non-streak

---

### GAP 5.2 — A forward-steals B, B early-jinxes C · **L**
**Doc rule**: B paid jinx silence cost; A only gets remaining bonuses (those not consumed by jinx silence).
**Current coverage**: None.
**Target file**: `TestInteractionMatrix`
**Test to add**:
- `test_forward_steal_target_jinxes_attacker` — A steals from B; B jinxes C (B pays silence/no before_hint); B answers; assert A only receives bonuses B actually earned (silence cost already excluded)

---

### GAP 5.3 — A retro-steals B who jinxed C · **L**
**Doc rule**: A takes relevant/remaining bonuses from B that weren't already consumed by B's jinx cost.
**Current coverage**: None.
**Target file**: `TestInteractionMatrix`
**Tests to add**:
- `test_retro_steal_target_had_early_jinxed` — B early-jinxes C then answers; A retro-steals B; assert A receives bonuses minus any that B couldn't earn due to silence
- `test_retro_steal_target_had_late_jinxed` — B answers then late-jinxes C (bonuses stripped); A retro-steals B; assert A receives remaining bonuses after jinx-late cost

---

### GAP 5.4 — A jinxes B who steals from C · **L**
**Doc rule**: A gets streak bonus based on B's streak at answer time (reduced by steal cost if B stole from C).
**Current coverage**: `test_late_steal_after_jinx_took_streak_no_recalculation` covers one direction (A's jinx already took B's streak bonus, B does late steal). The forward variant and retro-jinx variants are uncovered.
**Target file**: `TestInteractionMatrix`
**Tests to add**:
- `test_forward_jinx_target_also_steals` — A forward-jinxes B; B steals from C (paying streak cost); B answers; assert A gets B's streak bonus based on B's reduced streak

---

## Section 6: Simulator Event Dispatch

### GAP 6.1 — `jinx_preload` event dispatch not tested · **M**
**Doc rule** (Event Dispatch table): "`jinx_preload` → Preload jinx applied — sets flags only, no retroactive transfer check."
**Current coverage**: `test_hydrate_jinx_preload_sets_flags` tests the manager-level hydration path. There is no simulator-level test that feeds a `jinx_preload` row through `DailyGameSimulator` and confirms only flags are set with no immediate score effect.
**Target file**: `test_powerup_overnight_retro.py` — add to or alongside `TestSimulatorOvernightStealPreload`
**Test to add**:
- `test_simulator_jinx_preload_sets_flags_only` — simulator replays a `jinx_preload` row; assert attacker silenced, target jinxed_by set, no score change yet

---

### GAP 6.2 — `rest_wakeup` event is silently skipped · **M**
**Doc rule** (Event Dispatch table): "`rest_wakeup` → Skipped — already applied to the DB at live time."
**Current coverage**: None — no test verifies the simulator ignores `rest_wakeup` rows without side effects.
**Target file**: `test_daily_game_simulator.py` or `test_daily_game_simulator_additions.py`
**Test to add**:
- `test_simulator_rest_wakeup_is_noop` — simulator replays a sequence containing a `rest_wakeup` row; assert scores are identical to the same sequence without it

---

## Completion Tracker

| Gap | Description | Priority | Done? |
|-----|-------------|----------|-------|
| 1.1 | Self-targeting blocked (jinx + steal) | H | [ ] |
| 1.2 | One-per-day: jinx→rest, steal→rest | L | [ ] |
| 2.1 | Resting player cannot be targeted | H | [ ] |
| 2.2 | Attacker silence not lifted on target rest | M | [ ] |
| 2.3 | Steal streak cost forfeit on target rest | M | [ ] |
| 2.4 | Late-jinx bonuses not refunded on target rest | M | [ ] |
| 4.1 | Steal attacker timing symmetry assertion | M | [ ] |
| 5.1 | Simultaneous jinx + steal on same target | H | [ ] |
| 5.2 | Forward steal target early-jinxes | L | [ ] |
| 5.3 | Retro steal target had jinxed | L | [ ] |
| 5.4 | Jinx target also steals | L | [ ] |
| 6.1 | Simulator: `jinx_preload` dispatch | M | [ ] |
| 6.2 | Simulator: `rest_wakeup` skipped | M | [ ] |
