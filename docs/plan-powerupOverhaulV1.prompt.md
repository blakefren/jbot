# Powerup System Overhaul v1 — Implementation Plan

## Overview

**Goals**: Ship two phases of powerup improvements to increase player engagement and balance:
- **Phase 1**: Remove streak bonus cap, update Steal formula to percentage-based
- **Phase 2**: Variable Steal costs—players choose 1-5 streak days to spend, each day = 10% steal

**Deferred**: Phase 3 (Jinx lockout + EMP) requires architectural work; schedule after v1 is live and tested.

**Target Timeline**: 1-2 weeks design + development + testing

---

## Phase 1: Streak Cap Removal + Steal Percentage (Low Risk)

### Goals
- Uncap streak bonuses so high-streak players accumulate 50+ point bonuses
- Boost Steal impact without UI complexity—fixed 25% of target's total score earned
- Reuse existing simulator logic (no new state)

### Implementation Steps

#### Task 1.1: Remove Streak Bonus Cap
**File**: `src/cfg/main.py`
- Locate any streak cap check in bonus getters (e.g., `JBOT_BONUS_STREAK_CAP` constant)
- Remove the cap or set it to `None`
- Verify ConfigReader loads without defaults that re-apply the cap

**File**: `src/core/scoring.py`
- Find the `calculate_points()` method or similar where streak bonus is applied
- Remove any `min(streak_bonus, JBOT_BONUS_STREAK_CAP)` clamping
- Streak bonus is now `streak_bonus_per_day * streak_length` (unbounded)

**Expected Result**: A 10-day streak yields `10 × (JBOT_BONUS_STREAK_PER_DAY)` points. If `JBOT_BONUS_STREAK_PER_DAY=5`, that's 50 points (vs. capped at 25 before).

#### Task 1.2: Update Steal Formula to % of Total Score
**File**: `src/core/powerup_engine.py`
- Locate `resolve_steal_on_correct()` method
- **Current logic** (example):
  ```python
  stealable_amount = (
      target_state.bonuses.get(ScoreCalculator.KEY_FASTEST, 0) +
      target_state.bonuses.get(ScoreCalculator.KEY_BEFORE_HINT, 0)
  )
  # ... excludes streak
  ```
- **New logic**:
  ```python
  # Steal 25% of target's total score earned (includes all bonuses)
  stealable_amount = int(target_state.score_earned * 0.25)
  ```
- Apply to **both** paths:
  - Forward steal (on target's correct answer): `resolve_steal_on_correct()` called from `on_guess`
  - Retroactive steal (immediate transfer): Within `apply_steal()` when `target_state.is_correct` is true

**Expected Result**: On a 90-point day (30 base + 25 streak + 20 fastest + 15 before-hint), Steal takes 22.5 pts (≈ 25% of 90).

#### Task 1.3: Update Tests
**File**: `tests/src/core/test_powerup_engine.py`
- Update all Steal resolution tests to expect 25% of `score_earned` instead of flat bonuses
- Example assertion: `assert stolen_amount == int(target_score_earned * 0.25)`
- Test both forward and retroactive paths
- Test edge case: target answered but has 0 bonuses → 0 steal

#### Task 1.4: Verify with Simulation
**File**: `scripts/simulate_powerups.py` (optional but recommended)
- Run 100+ day simulation with new Steal formula
- Check distribution: Do Thieves win more often? Do Resters still compete?
- Verify no balance regression

**Command**:
```bash
python scripts/simulate_powerups.py --days 100 --num_players 10
```

**Success Criteria**: Simulation shows Steal is now meaningfully powerful (avg 20-30 pts per steal vs. 10-15 before).

---

## Phase 2: Variable Steal Costs (Medium Risk)

### Goals
- Let players choose how much streak to spend (1-5 days)
- Each day = 10% steal (max 50% with 5 days)
- Maintain existing balance for default 3-day steals (30%)
- Preserve simulator replay accuracy with stored costs

### Implementation Steps

#### Task 2.1: Database Schema Migration
**File**: `db/schema.sql`
- Add column to `powerup_usage` table:
  ```sql
  ALTER TABLE powerup_usage ADD COLUMN cost_amount INTEGER DEFAULT NULL;
  ```
- Semantics: `cost_amount` = number of streak days the player chose to spend (1-5, or NULL for other powerup types)

**Migrate Local DB**:
```bash
python db/update_schema.py
python db/verify_schema.py
```

**Migration Notes**:
- Old rows (rest, jinx, etc.) will have `cost_amount = NULL` — that's fine, only used for steal/steal_preload
- For replay: if `cost_amount is NULL` for a steal, default to config value (`JBOT_STEAL_STREAK_COST`)

#### Task 2.2: UI Validation in Power Cog
**File**: `src/cogs/power.py`
- Locate `/power steal <target>` command handler
- Add optional parameter with validation:
  ```python
  @app_commands.describe(
      days="Streak days to spend (1-5). Default is 3."
  )
  async def steal(self, interaction, target: discord.User, days: int = 3):
      # Validate range
      if not 1 <= days <= 5:
          await interaction.response.send_message(
              f"Invalid streak cost. Must be 1-5 days (you have {player.answer_streak}).",
              ephemeral=True
          )
          return

      # Pass days to PowerUpManager
      message = self.powerup_manager.steal(
          thief_id=...,
          target_id=...,
          question_id=...,
          cost_amount=days  # NEW PARAM
      )
  ```
- Update command help text to explain 1-5 range

#### Task 2.3: PowerUpManager & PowerUpEngine Variable Cost Logic
**File**: `src/core/powerup.py`
- Update `PowerUpManager.steal()` method signature:
  ```python
  def steal(
      self,
      thief_id: str,
      target_id: str,
      question_id: int = None,
      cost_amount: int = None,  # NEW
  ) -> str:
  ```
- Default `cost_amount = None` means use config value `self.engine.steal_streak_cost`
- Pass `cost_amount` to engine calls:
  ```python
  deducted, stealable_amount, bonus_delta = self.engine.apply_steal(
      self.daily_state,
      thief_id,
      target_id,
      engine_streak,
      cost_amount=cost_amount  # NEW
  )
  ```
- Log the cost:
  ```python
  self.data_manager.log_powerup_usage(
      thief_id, "steal", target_id, question_id, cost_amount=cost_amount
  )
  ```

**File**: `src/core/powerup_engine.py`
- Update `apply_steal()` signature:
  ```python
  def apply_steal(
      self,
      daily_state: dict[str, DailyPlayerState],
      thief_id: str,
      target_id: str,
      initial_streak: int,
      cost_amount: int = None,  # NEW
  ) -> tuple[int, int, int]:
  ```
- Inside method:
  ```python
  if cost_amount is None:
      cost_amount = self.steal_streak_cost if not target_state.is_correct else self.retro_steal_streak_cost

  # Calculate steal ratio: 1 day = 10%, 2 days = 20%, ..., 5 days = 50%
  steal_pct = min(0.5, cost_amount * 0.1)  # Cap at 50%
  thief_state.steal_ratio = steal_pct

  # Rest of logic uses steal_pct for stealable amount calculation
  ```

- Update `resolve_steal_on_correct()` to use `steal_ratio` from state:
  ```python
  stealable_amount = int(target_state.score_earned * thief_state.steal_ratio)
  ```

#### Task 2.4: DailyGameSimulator Replay Logic
**File**: `src/core/daily_game_simulator.py`
- Update `handle_powerup()` method:
  ```python
  elif ptype == "steal" or ptype == "steal_preload":
      if target_id:
          player = self.initial_player_states.get(user_id)
          initial_streak = player.answer_streak if player else 0

          # NEW: Read cost_amount from event (stored in DB during live play)
          cost_amount = event.cost_amount if hasattr(event, 'cost_amount') else None

          self.engine.apply_steal(
              self.daily_state,
              user_id,
              target_id,
              initial_streak,
              cost_amount=cost_amount
          )
  ```
- This ensures replay uses the *chosen* cost from live play, not the config default

#### Task 2.5: Update Tests
**File**: `tests/src/core/test_powerup_engine.py`
- Add test cases for variable costs:
  ```python
  def test_steal_variable_cost_1_day(self):
      # 1 day = 10% steal
      stolen = engine.apply_steal(..., cost_amount=1)
      assert stolen_amount == int(target_score * 0.1)

  def test_steal_variable_cost_5_day(self):
      # 5 days = 50% steal
      stolen = engine.apply_steal(..., cost_amount=5)
      assert stolen_amount == int(target_score * 0.5)
  ```
- Test replay: create a powerup_usage row with `cost_amount=2`, replay, verify 20% steal

#### Task 2.6: Simulation & Balance Validation
**File**: `scripts/simulate_powerups.py`
- Update `ProceduralStrategy.decide_action()` to vary steal costs:
  ```python
  if p_type == "steal":
      cost_days = random.randint(1, 5)  # Random 1-5
      events.append(PowerUpEvent(..., cost_amount=cost_days))
  ```
- Run simulation: `python scripts/simulate_powerups.py --days 100`
- Verify:
  - Thieves who spend 5 days win more (higher risk, higher reward)
  - Thieves who spend 1 day lose slightly (low risk, low reward)
  - Average powerup ROI is positive for spending 3-5 days

---

## Phase 1+2 Verification Checklist

- [ ] Streak cap removed; streaks 6+ days yield >30 pt bonuses
- [ ] Steal formula updated: 25% of `score_earned` (Phase 1), then variable 10-50% by days (Phase 2)
- [ ] Database migration applied: `cost_amount` column exists
- [ ] Old powerup_usage rows have `cost_amount = NULL` (safe to replay)
- [ ] `/power steal` command accepts optional `days` parameter (1-5)
- [ ] Validation: rejects invalid range with helpful error
- [ ] PowerUpEngine methods accept and apply `cost_amount` parameter
- [ ] DailyGameSimulator replays stored `cost_amount` correctly
- [ ] Unit tests pass: steal % math verified for 1/3/5 days
- [ ] Integration test: replay a steal event with custom cost, verify final score
- [ ] Simulation: 100+ days, check Thief/Rester balance, ROI distribution
- [ ] Manual test: Local game with variable steals, verify UI messages clear
- [ ] Backward compatibility: Old powerup rows (preload, etc.) still work

---

## Deployment Plan

### Pre-deployment
1. Run full test suite: `python -m unittest discover`
2. Run simulation with 500+ days to stress-test
3. Backup production DB: `python db/restore_db.py` (ensures fresh copy)

### Deployment
1. Merge to `main` with clear commit message: "feat: Phase 1+2 powerup overhaul—variable steal costs, uncapped streaks"
2. GitHub Actions CI runs all tests
3. Auto-deploy to Railway (if configured)

### Post-deployment
1. Announce in Discord: "Powerups update live! Steals now scale with your score (variable 1-5 days). Streaks unlimited. Try it out!"
2. Monitor for 24-48h: check for crashes, report issues
3. Collect player feedback: "Is 50% max steal too strong? Should we dial to 30%?"
4. Iterate Phase 2 if needed before Phase 3

---

## Deferred: Phase 3 Architecture Notes

**Not in v1**, but document for later:

### Jinx Clock-Based Lockout (Requires Time-Aware Simulator)
- **Problem**: Current simulator replays guesses as point calculations (deterministic). Lockout is time-dependent.
- **Model Choice**: Clock-based (e.g., 10am-1pm UTC) ← user preference
- **Implementation Options**:
  - **(A) Event-based**: Store lockout as `(lockout_start, lockout_end)` events in DB, replay checks if guess is within window
  - **(B) Time-aware simulator**: Refactor simulator to track `current_time`, check during guess dispatch
  - **(C) Lockout flag in DB**: Mark locked-out players at lockout time, replay checks flag (loses real-time accuracy)

### EMP (Retroactive Wipeout)
- New state: `DailyPlayerState.is_wiped` flag
- On EMP: wipe prior answer, allow resubmit within X minutes or forfeit
- Simulator: new `emp` event type, logic to handle resubmit window

### Same-Day Retaliation Prevention
- Track attacker IDs in `DailyPlayerState.was_attacked_by: {attacker_id: timestamp}`
- Before powerup activation: check if target was attacked; if yes and < 24h, prevent retaliation powerup
- DB: log attack timestamp in `powerup_usage`

### Cost Refunds (50% if target never answers)
- End-of-day sweep: for each Steal/Jinx, check `target.is_correct`
- If not correct, refund `cost_amount * 0.5` to attacker's streak pool

**Recommendation**: Post-v1, create detailed design doc (Confluence/Markdown), then spike lockout model choice.

---

## Questions for Refinement

1. **Steal percentage**: Is 25% (Phase 1) and up to 50% (Phase 2) correct, or should we scale differently?
   - Example: 1 day = 5%, 5 days = 25% (more conservative)?
   - Or: 1 day = 15%, 5 days = 75% (more aggressive)?

2. **Retroactive steal costs**: Should retroactive costs also be variable (1-5 days), or stay fixed (5 days max)?
   - Proposed: variable 1-5, but retroactive always costs more than forward
   - Alternative: keep retroactive fixed, only forward is variable

3. **Default steal cost**: When player doesn't specify, default to 3 days (current) or something else?
   - Proposed: 3 days (matches current `JBOT_STEAL_STREAK_COST`)

4. **Player comms**: How to explain variable costs to players?
   - Proposed in-game help: "/power steal @target [days] — Spend 1-5 streak days. Each day steals 10% of their score."

5. **Simulation frequency**: Run 100-day or 500-day sim before shipping?
   - Proposed: 500-day to catch edge cases

---

## Files Modified (Summary)

| Phase | File | Changes |
|-------|------|---------|
| 1 | `src/cfg/main.py` | Remove streak cap |
| 1 | `src/core/scoring.py` | Unbounded streak bonus calc |
| 1 | `src/core/powerup_engine.py` | Steal % formula (25% of score_earned) |
| 1 | `tests/src/core/test_powerup_engine.py` | Update steal assertions |
| 2 | `db/schema.sql` | Add `cost_amount` column to `powerup_usage` |
| 2 | `src/cogs/power.py` | `/power steal` UI validation (1-5 days) |
| 2 | `src/core/powerup.py` | Pass `cost_amount` to engine |
| 2 | `src/core/powerup_engine.py` | Apply variable ratio |
| 2 | `src/core/daily_game_simulator.py` | Replay `cost_amount` from events |
| 2 | `tests/src/core/test_powerup_engine.py` | Add variable cost test cases |

---

## Success Metrics

**After 1 week live**:
- ✅ No crashes related to powerups
- ✅ Steals are used more frequently (track via `/admin stats`)
- ✅ High-streak players report feel more vulnerable (feedback)
- ✅ Thieves using varied costs (1/3/5 mix observed)
- ✅ No exploits found (cost refunds, retroactive edge cases)

**After 2 weeks live**:
- ✅ Player sentiment: "Powerups feel more impactful"
- ✅ Balance feedback collected (adjust % in Phase 2.2 if needed)
- ✅ Ready to design Phase 3 based on live data
