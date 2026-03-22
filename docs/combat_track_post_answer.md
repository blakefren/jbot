# Combat Track: Post-Answer Logic — Design Document

**Status:** Implemented
**Proposal:** "Combat Track: Post-Answer Logic" (March 2026)
**Author:** Lex (AI partner)

---

## 1. Overview

This document describes the design for the "Combat Track: Post-Answer Logic" feature, which extends jinx and steal to be usable by attackers who have **already solved today's question** — at the cost of a penalty.

The key shift from the current system is:

| Scenario | Current Behavior | Proposed Behavior |
|---|---|---|
| Attacker solved + `!jinx` | ❌ Blocked ("already answered") | ✅ Allowed; attacker loses `before_hint` + `fastest` bonuses |
| Attacker solved + `!steal` | ❌ Blocked ("already answered") | ✅ Allowed; streak cost by target's status + attacker streak bonus recalculated |
| Resting player + `!jinx`/`!steal` | ✅ Already blocked via `powerup_used_today` | No change needed |
| Target already claimed | ✅ Already blocked with error | Clarify error message text |

---

## 2. Proposed Changes

### 2.1 Late-Day Jinx

**Trigger:** Attacker has already answered today's question correctly (`attacker_state.is_correct is True`).

**Attacker Cost — Simulation-based:**
- Remove the attacker's `before_hint` bonus from `attacker_state.score_earned` and `attacker_state.bonuses`.
- Remove the attacker's `fastest_N` / `fastest` bonus from `attacker_state.score_earned` and `attacker_state.bonuses`.
- This mirrors exactly what a normal attacker loses by being silenced until hint: (a) no `before_hint` bonus because they can't answer yet, and (b) no `fastest` bonus because nearly everyone has answered by the time the hint goes out.
- If the attacker has neither bonus, the late jinx costs them nothing.

**Target Effect:**
- Unchanged from current jinx rules:
  - If target **has already answered**: transfer `int(streak_bonus * retro_jinx_bonus_ratio)` (default 50%) to attacker.
  - If target **hasn't answered yet**: forward jinx — 100% streak loss stripped on resolve.
- Attacker **does** receive the transferred streak bonus from the target.
- Target does **not** lose any fastest bonus — only streak is affected.

**Attacker silencing:** Attacker has already answered so `silenced` is moot. Set `True` for consistency.

**DB `powerup_type` value:** `'jinx_late'` (distinguishes from standard `'jinx'` for simulator and reporting).

**Fastest bonus — no redistribution:**
When a normal jinx silences the attacker, they simply never earn a fastest rank — it doesn't shift down to the next player. The retroactive strip on `jinx_late` mirrors this: the `fastest_N`/`fastest` bonus is removed from the attacker and disappears. The 2nd-fastest player does not become 1st.

**Code changes required:**
- `PowerUpManager.jinx()`: Remove the `attacker_already_answered → error` gate; strip `before_hint` and `fastest_N`/`fastest` bonuses from attacker's state on the late path.
- `DailyGameSimulator.handle_powerup()`: Mirror the same logic.

---

### 2.2 Late-Day Steal

**Trigger:** Attacker has already answered today's question correctly.

Streak cost is determined **solely by the target's answer status**, regardless of whether the attacker has answered:

| Target status | Streak cost | Config key |
|---|---|---|
| Target has NOT yet answered | **3 days** | `JBOT_STEAL_STREAK_COST` (already `3`) |
| Target HAS already answered | **5 days** | `JBOT_RETRO_STEAL_STREAK_COST` (already `5`) |

**Attacker Cost — Simulation-based:**
- Deduct streak days (per table above) from attacker's streak via `player_manager.set_streak()`.
- **Recalculate** the attacker's streak bonus for today based on the new streak:
  - `old_bonus = attacker_state.bonuses.get("streak", 0)`
  - `new_bonus = ScoreCalculator.get_streak_bonus(new_streak_length)`
  - `attacker_state.score_earned -= (old_bonus - new_bonus)`
  - `attacker_state.bonuses["streak"] = new_bonus`
- If the new streak bonus is zero, that's the correct outcome — no floor.

**Reward:**
- Attacker receives `get_stealable_amount(target_state.bonuses)` — same logic as existing retro steal.

**DB `powerup_type` value:** `'steal'` — unchanged. Steal logic is conceptually the same, just unlocked for post-answer attackers.

**Overnight pre-loads:** Not affected. Pre-loads occur before the attacker has answered and use the same `JBOT_STEAL_STREAK_COST` cost as any other forward steal. The `steal_is_preload` / deduct-at-queue-time path is unchanged.

**Code changes required:**
- `PowerUpManager.steal()`: Remove `thief_already_answered → error` gate; apply streak recalculation when attacker has already answered.
- `ScoreCalculator`: Expose `get_streak_bonus(streak_days) -> int` as a public standalone method (currently embedded in `calculate_points`).
- `DailyGameSimulator.handle_powerup()`: Mirror late-day branching + streak bonus recalc.
- No config changes needed (steal costs are already correct in `.env`/`.env.template`; Python fallback defaults of `"2"` in `powerup.py` and `daily_game_simulator.py` are a pre-existing bug to fix separately).

---

### 2.3 Rest Restriction

**Proposal:** Players who have activated `!rest` cannot use `!jinx` or `!steal`.

**Current state:** **Already implemented.** `DailyPlayerState.powerup_used_today` returns `True` if `is_resting`, and both `jinx()` and `steal()` gate on `powerup_used_today`. No code change required.

---

### 2.4 Priority & Privacy (Already Implemented)

| Feature | Current State |
|---|---|
| Ephemeral (private) responses | ✅ Both `/power jinx` and `/power steal` send ephemeral replies |
| First-come, first-served ordering | ✅ `discord.py` processes commands sequentially; first writer wins the `jinxed_by`/`steal_attempt_by` field |
| "Target already claimed" error | ✅ Exists — `target_state.jinxed_by is not None` and `target_state.steal_attempt_by is not None` are checked |

**No changes required** — all three properties are already implemented correctly.

---

## 3. Affected Files

| File | Change Type |
|---|---|
| `src/core/powerup.py` | Remove `already_answered` gates; strip `before_hint` + `fastest` from attacker on late jinx; streak recalc for post-answer steal |
| `src/core/daily_game_simulator.py` | Mirror live logic for event replay |
| `src/core/scoring.py` | Expose `get_streak_bonus(streak_days)` as a public method |
| `tests/src/core/test_powerup.py` | New test cases for late-day paths |

`src/core/state.py`, `src/cogs/power.py`, `db/schema.sql`, and `.env.template` require no changes.

> **⚠️ Duplication TODO:** `DailyGameSimulator` re-implements jinx/steal resolution logic that already exists in `PowerUpManager` rather than delegating to it. This feature adds more of the same. The long-term fix is to extract shared calculation functions that both classes call — tracked as a future refactor, not in scope here.

---

## 4. Open Questions

None — all design decisions resolved. See Section 5.

---

## 5. Resolved Decisions

| Item | Decision |
|---|---|
| Late jinx attacker cost | Strip `before_hint` + `fastest_N`/`fastest` bonuses from attacker (mirrors silencing penalty) |
| Late jinx zero-cost (no bonuses to strip) | Acceptable — intentional design |
| Steal streak cost basis | Target's answer status only (not attacker's) |
| Forward steal cost | 3 days (`JBOT_STEAL_STREAK_COST=3`, unchanged) |
| Retroactive steal cost | 5 days (`JBOT_RETRO_STEAL_STREAK_COST=5`, unchanged) |
| `powerup_type` for late jinx | `'jinx_late'` |
| `powerup_type` for late steal | `'steal'` (unchanged) |
| Attacker receives target's streak bonus on late jinx | Yes |
| `fastest` bonus redistribution on `jinx_late` strip | No — bonus disappears (mirrors normal silencing behavior) |
| Target effect on late jinx | Streak only (same as normal jinx) |
| Negative `score_earned` allowed | Yes, no floor |
| Overnight pre-loads affected by late-day rules | No — entirely separate path |
| Rest blocks attacking | Already implemented via `powerup_used_today` |
