# Power-Up Mechanics

## Overview

The power-up system allows players to influence scoring through three abilities: **Rest**, **Jinx**, and **Steal**. Each has multiple interaction paths depending on when the attacker and target have answered relative to the power-up being used, and they interact with each other when combined on the same day.

This document defines the **expected** behavior for every interaction path. Use it as the source of truth when auditing or modifying the implementation.

---

## Architecture

```
Discord Command (/power jinx, /power steal, /power rest)
         │
         ▼
┌────────────────────┐
│   PowerUpManager   │  Orchestrates live play. Owns daily_state, calls DB,
│   (powerup.py)     │  reads config, builds Discord messages.
└────────┬───────────┘
         │ delegates logic to
         ▼
┌────────────────────┐
│   PowerUpEngine    │  Pure stateless logic. Mutates DailyPlayerState only.
│  (powerup_engine)  │  No DB access, no Discord, no config reads.
└────────────────────┘
         │ reads/writes
         ▼
┌────────────────────┐
│  DailyPlayerState  │  In-memory per-player state for the current round.
│    (state.py)      │  Discarded at end of day.
└────────────────────┘

Replay path (corrections/end-of-day):
┌─────────────────────────┐
│  DailyGameSimulator     │  Replays GuessEvents + PowerUpEvents from DB in
│ (daily_game_simulator)  │  chronological order using the same PowerUpEngine.
└─────────────────────────┘

Persistence:
┌────────────────────┐
│  powerup_usage     │  DB table. One row per power-up activation.
│  (schema.sql)      │  question_id is NULL for overnight pre-loads.
└────────────────────┘
```

### Key Classes

| Class | Responsibility |
|---|---|
| `PowerUpEngine` | Stateless logic — all mutation of `DailyPlayerState` |
| `PowerUpManager` | Live-game orchestration — DB writes, Discord messages, config |
| `DailyPlayerState` | In-memory state per player per round |
| `DailyGameSimulator` | Replay engine — uses `PowerUpEngine` for corrections |
| `ScoreCalculator` | Bonus computation, `pop_stealable_bonuses()` |

---

## `powerup_usage` Table

```sql
powerup_type TEXT      -- see values below
question_id  INTEGER   -- NULL for overnight pre-loads; set at hydration
target_user_id TEXT    -- NULL for rest
attacker_user_id TEXT
```

### `powerup_type` values

| Value | When Written |
|---|---|
| `rest` | Player invokes `/power rest` during active question |
| `rest_wakeup` | Rest multiplier applied at next correct guess |
| `jinx` | Daytime jinx where the attacker has not yet answered (early-forward and early-retroactive) |
| `jinx_late` | Jinx when the attacker has already answered today |
| `jinx_preload` | Overnight jinx before question goes live |
| `steal` | Daytime steal (all timing variants) |
| `steal_preload` | Overnight steal before question goes live |

---

## Common Rules

These apply to all three power-ups unless a path explicitly overrides them.

1. **One power-up per day**: A player cannot use a second power-up on the same day.
2. **No self-targeting**: Jinx and steal require a different player as the target.
3. **One attack type per target**: A player cannot be jinxed twice in one day; cannot be stolen from twice in one day.
4. **Target must be a registered player**.
5. **Power-up events are persisted**: Every activation writes a row to `powerup_usage`.
6. **Attacking powerups are private**: Powerup activations that attack players are silent/ephemeral to maintain secrecy for the attacker.
7. **Public bot responses go directly to the channel**: Bot messages in response to power-up commands or effects are sent as new channel messages, not as replies to the invoking player's message (so other players don't see who used the command).
8. **Powerup effects are transparent**: Public bot messages tag both the attacker and target, and informs them of all point and bonus adjustments. Targeting remains private.

---

## Design Principles

These principles govern how power-up costs and effects are structured. Use them to evaluate proposed changes and resolve ambiguity in edge cases.

### 1. Attacker timing symmetry (Early ≡ Late)

An attacker's net cost and gain must be identical whether they use a power-up before or after answering their own question. The implementation differs — early attackers are blocked from earning certain bonuses; late attackers have already-earned bonuses stripped — but the net result must be the same. This ensures there is no strategically optimal window for an attacker to act.

### 2. Forward is cheaper than Retroactive (risk vs. guarantee)

Forward power-ups (target hasn't answered) carry risk: the target might not answer, might rest, or might earn no bonuses. This risk is rewarded with lower cost and/or higher potential return. Retroactive power-ups (target already answered) eliminate that risk, so they cost more and/or yield proportionally less.

| | Forward | Retroactive |
|---|---|---|
| **JINX** | 100% of target's streak bonus transferred (if target answers) | 50% of streak bonus (`JBOT_RETRO_JINX_BONUS_RATIO`), transferred immediately |
| **STEAL** | Lower streak cost (`JBOT_STEAL_STREAK_COST`, default 3) | Higher streak cost (`JBOT_RETRO_STEAL_STREAK_COST`, default 5) |

### 3. Streak as a strategic resource

Streaks serve multiple roles simultaneously — and the tension between those roles is the core meta-game driver:

- **Scoring**: The streak bonus rewards consistent daily play.
- **Steal fuel**: Stealing requires streak days as payment. A larger streak means more purchasing power for high-value steals.
- **Attack surface**: A large streak bonus makes a player an attractive jinx target; a high streak count makes them an attractive steal target.
- **Rest gives control**: Players can freeze their streak to avoid a reset on days they don't know the answer, trading today's score for a future multiplier.

The system is designed so that players *must* build and maintain a streak to be competitive — but are naturally incentivized to manage it carefully, not let it grow without bound. Rest is the pressure-release valve that gives players agency over this tradeoff.

> These principles apply to the two **offensive** power-ups (Jinx and Steal). REST has no early/late dimension and is not subject to Principles 1 or 2.

---

## Terminology

These terms describe when events occur relative to a player answering, and are used throughout the rest of this document.

| Term | Applies To | Meaning |
|---|---|---|
| **Early** | Attacker | The attacker has **not** yet answered today |
| **Late** | Attacker | The attacker **has** already answered today |
| **Forward** | Target | The target has **not** yet answered today |
| **Retroactive** | Target | The target **has** already answered today |

The four combinations — **early-forward**, **early-retroactive**, **late-forward**, **late-retroactive** — describe every possible timing scenario for an offensive power-up.

---

## Overnight Pre-loads and Hydration

Players can invoke `/power jinx` or `/power steal` **overnight** (when no question is active). The activation is stored immediately, but the effects are not applied until the morning question begins.

**At command time (overnight)**:
- The power-up is logged to `powerup_usage` with `question_id = NULL`.
- The attacker's power-up slot is consumed for the next day.
- For steal: the streak cost is **not** deducted yet.

**At morning hydration** (before the question is announced):
- All overnight rows are promoted to the new `question_id`.
- Jinx and steal are activated against fresh daily state exactly as they would be in the **early-forward** daytime path.

After hydration, the day proceeds identically to any other early-forward jinx or steal. There is no special overnight resolution logic.

> The only distinction of an overnight pre-load versus placing the same power-up first thing in the morning is that the slot and the target are locked in before the question is revealed.

---

## REST

### Purpose
Skip today's question. Freeze your streak (no reset). Apply a multiplier to your **next day's** correct answer score.

### When Available
- Question is active (not overnight).
- Player has not answered correctly today.
- Player has not used any power-up today.

### Behavior

1. The player's streak is **frozen** — neither incremented nor reset.
2. A score multiplier (`JBOT_REST_MULTIPLIER`) is stored and applied to the player's next correct answer on any future day as a bonus: `round(points × (multiplier − 1.0))`.
3. Any **incoming jinx** is cancelled, with a public announcement. The jinxer's costs remain paid — if early, they stay silenced until the hint; if late, any bonuses already stripped as the jinx cost are not refunded.
4. Any **incoming steal** is cancelled, with a public announcement. The thief's streak cost is **not refunded** — it was paid when the steal was initiated (or at morning hydration) and is forfeit.
5. A private message reveals today's answer to the resting player.

### Expected Behavior

| Scenario | Expected Result |
|---|---|
| Rest with no incoming attacks | Streak frozen, multiplier stored, answer revealed privately |
| Rest with incoming jinx | Jinx cancelled (public announcement), jinxer still pays their cost (silenced if early; bonuses forfeited if late) |
| Rest with incoming steal | Steal cancelled (public announcement), thief's streak cost is forfeit |
| Player tries to rest after answering | Blocked — already answered today |
| Player tries to rest after using a power-up | Blocked — power-up already used today |

---

## JINX

### Purpose
Silence **yourself** (the attacker) until the hint is sent. Steal the target's streak bonus when they answer.

### When Available
- Attacker has not used a power-up today.
- Target has not already been jinxed today.
- Target is not resting today.
- Target and attacker are different players.

### Attacker Silence

Once jinx is activated, the attacker **cannot answer** until the hint has been sent. After the hint, they may answer normally.

### Behavior by Timing

The outcome depends on whether the **attacker** (Early vs. Late) and the **target** (Forward vs. Retroactive) have answered. See the [Terminology](#terminology) section.

| | **Forward** (target not yet answered) | **Retroactive** (target already answered) |
|---|---|---|
| **Early** (attacker not yet answered) | Attacker silenced. Target's full streak bonus is transferred to the attacker when the target answers. | Attacker silenced. 50% of target's streak bonus transferred immediately. |
| **Late** (attacker already answered) | Attacker's `before_hint` + all fastest bonuses are stripped as a cost. Target's full streak bonus transferred when the target answers. | Attacker's `before_hint` + all fastest bonuses stripped. 50% of target's streak bonus transferred immediately. |

> **Streak transfer amount**: Full (100%) for forward targets; partial (50%, `JBOT_RETRO_JINX_BONUS_RATIO`) for retroactive targets.

> **Late cost**: If the attacker earned none of those bonuses, the cost is 0 but the jinx still applies. The attacker is still silenced, but since they've already answered, it has no practical effect.

> **On timing symmetry**: Jinx enforces early ≡ late symmetry by mechanism rather than identical outcome. An early attacker is *prevented* from earning `before_hint` and fastest bonuses while jinxing (via silence); a late attacker has those bonuses *stripped*. In both cases the attacker cannot keep those bonuses while jinxing. In practice, an early attacker who was not going to earn those bonuses anyway (e.g. would have answered after the hint regardless) pays no effective cost — exactly the same as a late attacker who earned none. See [Principle 1](#1-attacker-timing-symmetry-early--late).

> **Overnight pre-load**: Resolved at morning hydration as early-forward. See [Overnight Pre-loads and Hydration](#overnight-pre-loads-and-hydration).

### Expected Behavior

| Scenario | Expected Result |
|---|---|
| Target never answers | Attacker was silenced / bonuses stripped; no streak bonus to transfer |
| Target answers but earns no streak bonus | Attacker was silenced / bonuses stripped; transfer has no effect — no error raised |
| Target rests after being jinxed | Jinx cancelled; no transfer occurs; attacker's silence is **not** lifted |
| Retroactive jinx, target has no streak bonus | Blocked — nothing to steal, power-up slot preserved |
| Second jinx attempt on same target | Blocked — target already jinxed |

---

## STEAL

### Purpose
Pay a streak cost upfront to receive all non-streak bonuses earned by the target.

### When Available
- Attacker has not used a power-up today.
- Target has not already had a steal attempted on them today.
- Target is not resting today.
- Attacker has at least 1 streak day (something to pay).
- Target and attacker are different players.

### What Is Stealable

All bonuses **except the streak bonus**: try bonuses, before-hint bonus, fastest-answer bonuses, and rest bonuses.

### Streak Cost

The streak cost is deducted from the thief immediately when the steal is set up (or at morning hydration for overnight pre-loads).

| Timing | Cost |
|---|---|
| Forward steal (target hasn't answered) | `JBOT_STEAL_STREAK_COST` (default 3) |
| Retroactive steal (target has answered) | `JBOT_RETRO_STEAL_STREAK_COST` (default 5) |

### Partial Steal

If the thief's streak is less than the cost, they pay all remaining streak days and receive a proportional fraction of the bonuses (`thief_streak / cost`). This applies to **both** forward and retroactive steals.

### Behavior by Timing

The outcome depends on whether the **attacker** (Early vs. Late) and the **target** (Forward vs. Retroactive) have answered. See the [Terminology](#terminology) section.

| | **Forward** (target not yet answered) | **Retroactive** (target already answered) |
|---|---|---|
| **Early** (attacker not yet answered) | Normal cost deducted. When target answers, non-streak bonuses transferred to thief (scaled by steal ratio if partial). | Higher cost deducted. Non-streak bonuses transferred immediately (scaled by steal ratio if partial). |
| **Late** (attacker already answered) | Normal cost deducted; thief's previously-earned streak bonus is **recalculated downward** to reflect the reduced streak, if below the max. Bonuses transferred when target answers. | Higher cost deducted; streak bonus recalculated. Non-streak bonuses transferred immediately. |

> **Late additional effect**: Because the thief already answered and earned a streak bonus, reducing their streak may retroactively lower that bonus (e.g. if cost is 5d but player has 7d streak and earned the max +25 bonus, they will drop to 2d streak and +10 bonus). Their total score may decrease even before any bonuses are transferred.

> **Design principle — attacker timing symmetry**: "Streak cost" intentionally includes both the streak days lost and any resulting streak bonus reduction. An early steal deducts streak before the thief answers, so the bonus is naturally lower; a late steal deducts after, so the bonus is corrected down. The net cost is the same either way — consistent with the [attacker timing symmetry](#1-attacker-timing-symmetry-early--late) principle.

> **Overnight pre-load**: Resolved at morning hydration as early-forward. See [Overnight Pre-loads and Hydration](#overnight-pre-loads-and-hydration).

### Expected Behavior

| Scenario | Expected Result |
|---|---|
| Target never answers (early steal) | Thief paid streak days; no bonuses transferred |
| Target never answers (late steal) | Thief paid streak days and streak bonus reduced; no bonuses transferred — same net loss as early steal by design |
| Target answers but has no stealable bonuses | Thief paid streak cost; nothing transferred |
| Target rests | Steal cancelled; thief's streak cost is forfeit |
| Partial steal (streak < cost) | Thief pays all remaining streak; receives proportional fraction of bonuses |
| Second steal attempt on same target | Blocked — steal already attempted on this target today |

---

## Interaction Matrix

Here we explicitly define some more complex interactions for multiple power-ups involving the same player(s) on the same day:

> **Reminder**: early/late is based on the attacker's answer status; forward/retro is based on the target's. See [Terminology](#terminology).

| Situation | Outcome | Order |
|---|---|---|
| Jinxed or stolen-from player rests | Attack cancelled and cost forfeit/maintained; player gets rest multiplier | jinx/steal -> rest (whiffs jinx/steal) |
| Rested player targeted by jinx or steal | Attempt blocked — no actions taken or costs paid | rest -> jinx/steal (blocked) |
| Players A and B both try to jinx target C | Second attempt blocked — C already jinxed | A jinx C -> B jinx C (blocked) |
| Players A and B both try to steal from target C | Second attempt blocked — steal already attempted on C | A steals from C -> B steal from C (blocked) |
| Player A jinxes B while Player C steals from B | Both attacks coexist — bonus pools don't overlap. A gets B's streak bonus (100% if forward jinx, 50% if retroactive); C gets all non-streak bonuses. B keeps only base score (plus the remaining 50% streak bonus if jinx was retroactive). | Any order; both resolve at B's answer (or immediately if retroactive) |
| Player A forward steals from B, who early jinxes C | B paid jinx silence cost, A only gets remaining bonuses | A steal from B -> B jinxes C -> B answer |
| Player A forward steals from B, who late jinxes C | A took B's bonuses, so B pays no jinx-late bonus costs | A steals from B -> B answer -> B jinxes C |
| Player A retro steals from B, who early jinxes C | A takes relevant/remaining bonuses from B (depends on B correctness, speed, etc.) | B jinxes C -> B answers -> A steals from B |
| Player A retro steals from B, who late jinxes C | A takes relevant/remaining bonuses from B (remaining depend on B correctness, speed, etc.), but won't get jinx-late cost bonuses from B  | B answers -> B jinxes C -> A steals from B |
| Player A forward jinxes B, who early steals from C | B paid streak cost for steal; A gets streak bonus based on streak at B answer time | A jinx B -> B steal from C -> B answer |
| Player A forward jinxes B, who late steals from C | A gets streak bonus based on streak at B answer time; B streak cost deducted at steal time but no streak bonus revision as it was already taken by A | A jinx B -> B answer -> B steal from C |
| Player A retro jinxes B, who early steals from C | B pays streak cost at steal time, B streak bonus calculated at answer but (reduced amount) taken by A | B steal from C -> B answer -> A jinx B |
| Player A retro jinxes B, who late steals from C | B gets streak bonus at answer but may be revised down at steal, then A takes remaining at jinx | B answer -> B steal from C -> A jinx B |

---

## Simulator (Replay) Behavior

The `DailyGameSimulator` replays `powerup_usage` rows in chronological order using the same `PowerUpEngine`. This ensures retroactive corrections (e.g. answer changes via `/admin add_answer`) recalculate scores accurately.

### Event Dispatch

| `powerup_type` DB value | Behavior |
|---|---|
| `rest` | Rest applied; pending attacks cancelled |
| `jinx` | Jinx applied (forward or retroactive based on target state at replay time) |
| `jinx_preload` | Preload jinx applied — sets flags only, no retroactive transfer check |
| `jinx_late` | Late-day cost stripped, then jinx applied |
| `steal`, `steal_preload` | Steal applied using snapshotted initial streak |
| `rest_wakeup` | Skipped — already applied to the DB at live time |

### Streak Deduction Replay

Because steal streak costs are persisted to the DB at live time, the simulator avoids double-deducting by tracking the cost in state and applying it only to bonus calculations during replay, not to the DB snapshot.

### No `steal_late` type

Unlike `jinx_late`, there is no separate `steal_late` DB type. The late-day streak bonus recalculation for steal is inferred at replay time from whether `thief_state.is_correct` is true when `apply_steal` is dispatched — exactly as it is in live play. `jinx_late` requires a distinct type because the simulator must strip the attacker's bonuses as a cost *before* applying the jinx; steal has no analogous pre-application cost step.

---

## Config Reference

| Key | Default | Effect |
|---|---|---|
| `JBOT_REST_MULTIPLIER` | `1.2` | Score multiplier applied on the resting player's next correct answer |
| `JBOT_STEAL_STREAK_COST` | `3` | Streak days deducted for a forward steal |
| `JBOT_RETRO_STEAL_STREAK_COST` | `5` | Streak days deducted for a retroactive steal |
| `JBOT_RETRO_JINX_BONUS_RATIO` | `0.5` | Fraction of streak bonus transferred in a retroactive jinx |

---

## Code Review Checklist

- [ ] Does every activation path write a row to `powerup_usage`?
- [ ] Does overnight pre-load defer streak deduction to morning hydration?
- [ ] Does `PowerUpEngine` contain zero DB calls, Discord calls, or config reads?
- [ ] Does `PowerUpManager` delegate all state mutation to `PowerUpEngine`?
- [ ] Do public bot responses go to the channel directly (not as replies to player messages)?
- [ ] Does rest cancel attacks with a public announcement?
- [ ] Is the partial steal ratio applied consistently for both forward and retroactive steals?
- [ ] Does a late-day steal recalculate and apply the attacker's streak bonus delta to the DB?
- [ ] Are `rest_wakeup` events skipped in simulator replay?
- [ ] Does the simulator use the snapshotted initial streak (not the current DB value) for steal replay?
