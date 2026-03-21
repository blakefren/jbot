# Powerup Targeting v2 — Design Document

**Status**: Decisions recorded — ready for implementation
**Features**:
- A. Overnight pre-loading of jinx and steal
- B. Retroactive targeting of already-answered players at reduced benefit

---

## Background

### Current Lifecycle

```
Morning (JBOT_MORNING_TIME)
  → GameRunner sends question → daily_state initialized empty

During day
  → /power jinx @target  → attacker silenced, target.jinxed_by set
  → /power steal @target → attacker streak -STEAL_COST, target.steal_attempt_by set
  → /answer <guess>      → on_guess() resolves jinx/steal if correct

Evening (JBOT_EVENING_TIME)
  → Answer revealed, scores finalized
  → reset_daily_state() clears all DailyPlayerState
```

Currently both `jinx()` and `steal()` raise `PowerUpError("There is no active question right now.")` when `question_id is None`, which blocks overnight use entirely. Both also block usage if the attacker has already answered correctly today.

### Current Validation Guards (both jinx and steal)

| Check | Behavior |
|---|---|
| `question_id is None` | Raise — no active question |
| Attacker already answered today | Raise — can't use powerups after answering |
| `powerup_used_today` | Raise — one powerup per day |
| Target already jinxed/stolen-from | Raise — can't stack |

---

## Feature A: Overnight Pre-loading

### Proposal

After the evening resolution, players can `/power jinx @target` or `/power steal @target` to **pre-load** for the following day. The powerup is stored persistently (DB) and applied when the next morning question fires.

### DB Approach: No new table

`powerup_usage.question_id` is already nullable. Overnight powerups are logged there the same as live ones, with `question_id = NULL`.

- **Pending**: `question_id IS NULL AND powerup_type IN ('jinx', 'steal')`
- **Applied**: morning hydration runs `UPDATE powerup_usage SET question_id = <new_id> WHERE question_id IS NULL AND powerup_type IN ('jinx', 'steal')`
- After that, `_fetch_daily_events(daily_question_id)` picks them up via the existing `get_powerup_usages_for_question()` query — no simulator changes needed for Feature A.

### Morning Hydration Flow

Hydration happens at the end of `GameRunner.set_daily_question()`, after `self.daily_question_id` is set, before the question is announced. This covers both the fresh-question path and the restart-recovery path. On restart, pending rows have already been updated (non-NULL `question_id`), so the NULL query returns nothing safely.

```
set_daily_question() fires
  → question selected and daily_question_id established
  → hydrate_pending_powerups(daily_question_id):
      SELECT * FROM powerup_usage WHERE question_id IS NULL AND powerup_type IN ('jinx', 'steal')
      → for each row:
          inject into daily_state (silenced, stealing_from, jinxed_by, steal_attempt_by)
          UPDATE powerup_usage SET question_id = <daily_question_id> WHERE id = <row_id>
  → question announced to channel
```

### Overnight Duplicate Prevention

`powerup_used_today` reads `daily_state`, which is cleared at evening — returning `False` for everyone overnight. A DB-backed check is required:

```python
# In jinx() and steal(), before logging overnight:
if self.data_manager.get_pending_powerup(user_id):
    raise PowerUpError("You already have a powerup queued for tomorrow.")
```

New DataManager method:
```python
def get_pending_powerup(self, user_id: str) -> dict | None:
    """Returns the first unapplied overnight powerup for a player, or None."""
    # SELECT * FROM powerup_usage WHERE user_id = ? AND question_id IS NULL LIMIT 1
```

### Decisions for Feature A

**A1. Announcement: Silent.**
Pre-loaded powerups make no announcement when registered or when they activate at morning. Jinx/steal are silent until they go into effect — i.e., until the target next submits a correct answer. Players discover them the same way they discover live powerups.

**A2. Steal streak cost: Deducted immediately at pre-load time.**
The `JBOT_STEAL_STREAK_COST` streak penalty is applied the moment the player calls `/power steal` overnight — same as the live daytime behavior. The commitment is immediate.

**A3. Silence: Applies immediately and persists until hinted.**
When a player pre-loads a jinx overnight, they are silenced immediately (state flag set at pre-load time). At morning hydration the flag is already in effect, so they cannot answer until the hint is sent — identical to a live-day jinx.

**A4. No cancel command.**
Not implemented for now; can be added later if needed.

**A5. Carry-over: Waits for the next question.**
If no question fires the next day (error, admin skip), the pending pre-load remains and activates against the next available question.

**A6. Powerup-used gate: Resolved by design.**
Morning hydration sets all the same state flags (`silenced`, `stealing_from`, etc.) as the live path. `powerup_used_today` returning `True` at question start automatically blocks a second powerup.

**A7. Overnight duplicate prevention: DB-backed check.**
`daily_state` is cleared at evening, so `powerup_used_today` is meaningless overnight. `jinx()` and `steal()` will call `data_manager.get_pending_powerup(user_id)` before logging; if a row is found, raise `PowerUpError("You already have a powerup queued for tomorrow.")`.

---

## Feature B: Retroactive Targeting (Already-Answered Players)

### Proposal

Allow a player to use jinx or steal against a target who has **already answered correctly today**, at a penalty:

| Powerup | Normal target (not yet answered) | Retroactive target (already answered) |
|---|---|---|
| Jinx | Attacker silenced until hint; on target's correct answer, full streak bonus transferred | Attacker silenced until hint (or waived — see **B3**); immediate resolution: **half** streak bonus transferred |
| Steal | Costs `STEAL_STREAK_COST` (default 3) streak days; bonuses transferred when target answers | Costs **5** streak days; immediate resolution: stealable bonuses transferred |

### Proposed Resolution for Retroactive Cases

Since the target has already answered and `on_guess()` won't be called again, resolution must happen immediately at the time of the powerup call (not deferred to `on_guess`):

```python
# Retroactive jinx — called immediately in jinx()
streak_bonus = target_state.bonuses.get("streak", 0)
half = streak_bonus // 2
player_manager.update_score(target_id, -half)
player_manager.update_score(attacker_id, +half)
```

```python
# Retroactive steal — called immediately in steal()
stealable = score_calculator.get_stealable_amount(target_state.bonuses)
player_manager.update_score(target_id, -stealable)
player_manager.update_score(attacker_id, +stealable)
```

### Detection: "Has the target already answered?"

`target_state.is_correct` — set to `True` by `on_guess()` when the target answers correctly. If `True`, apply retroactive rules.

For the simulator (`DailyGameSimulator`), the same flag is used.

### Decisions for Feature B

**B1. Answered-attacker guard: Stays.**
Players who have already answered today cannot use jinx or steal, even retroactively. May be revisited in a future iteration.

**B2. Resolution: Instant.**
The target has already answered, which is normally when resolution fires. For retroactive targets, resolution happens immediately when the powerup is used — no need for the attacker to answer.

**B3. Retroactive jinx silence: Still applies.**
The attacker is silenced (unable to answer until the hint is sent) regardless of whether the target has already answered. The silence is the attacker's cost, not a tactical tool against the target.

**B4. Zero-streak retroactive jinx: No upfront check.**
If the target had no streak bonus, the transfer is zero and the no-effect message fires as it does today. No pre-validation needed.

**B5. Overnight pre-load + retroactive cost: Locked at pre-load cost.**
Because A2 deducts the streak cost immediately at pre-load time, and morning hydration injects the powerup before any guesses are possible, a pre-loaded steal is never in a retroactive position. The 5d cost only applies to steals initiated *after* the target has already answered within the same day.

---

## Interaction Between Features A and B

The most interesting case:

1. Player pre-loads a jinx against Player X overnight (Feature A)
2. Morning question fires; Player X answers within the first 2 minutes (very fast)
3. The jinx was "active" (pre-loaded) but Player X already answered before the attacker acts

Under Feature B retroactive rules, the jinx should still fire at reduced benefit.
Under the current design, the jinx fires normally because it was pre-loaded and the morning hydration sets `target_state.jinxed_by` before Player X answers. **No conflict** — the pre-load would be set in daily_state before any guesses are processed.

However, if the pre-load hydration happens *after* Player X answers (race condition in morning task ordering), Feature B rules would apply.

**Proposed**: Morning hydration of pre-loads occurs **before** any guess processing. Practically, this means the `send_daily_question` task must load pending powerups before announcing the question.

---

## Event Sourcing / Simulator Impact

- **Feature A**: No simulator changes needed. After morning hydration, overnight powerup rows have a real `question_id` and are fetched by `get_powerup_usages_for_question()` as normal. Their `used_at` timestamps are from overnight but sort before any guesses, so they replay first — correct order.

- **Feature B**: `DailyGameSimulator.handle_powerup()` needs to detect retroactive cases. Since events are sorted by timestamp before replay, if a `GuessEvent` for the target appears *before* the `PowerUpEvent` in the sorted list, `target_state.is_correct` will already be `True` when `handle_powerup()` runs. Apply half-bonus (jinx) or retroactive streak cost + immediate resolution (steal).

---

## Config Changes

Proposed new `.env` keys:

```
# Retroactive powerup costs / ratios
JBOT_RETRO_STEAL_STREAK_COST=5        # Streak cost for stealing from already-answered target (default: 5)
JBOT_RETRO_JINX_BONUS_RATIO=0.5      # Fraction of streak bonus attacker gets for retroactive jinx (default: 0.5)
```

Existing keys preserved:
```
JBOT_STEAL_STREAK_COST=3              # Normal (future-target) steal cost
```

---

## Decision Summary

| # | Topic | Decision |
|---|---|---|
| A1 | Pre-load announcement | Silent until effect fires |
| A2 | Steal cost timing | Deducted immediately at pre-load |
| A3 | Jinx silence semantics | Applies immediately; lasts until hint |
| A4 | Cancellation | Not implemented |
| A5 | No-question carry-over | Wait for next question |
| A6 | Powerup-used gate | Resolved by hydration setting state flags |
| B1 | Answered attacker guard | Guard stays; revisit later |
| B2 | Resolution trigger | Immediate on powerup call |
| B3 | Retroactive jinx silence | Attacker still silenced |
| B4 | Zero-streak retroactive jinx | No upfront check; silent no-effect |
| B5 | Overnight steal → retroactive cost | Pre-load locks in 3d cost; 5d never applies to pre-loads |
