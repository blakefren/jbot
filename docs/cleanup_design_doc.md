# Cleanup & Refactoring Design Doc

**Date**: March 23, 2026
**Status**: Draft — Iterating

This document catalogues duplicated logic, split responsibilities, and other cleanup opportunities identified across the `jbot` codebase. Issues are grouped by theme and roughly prioritized by impact.

---

## 1. Extract `PowerUpEngine` — Separate Logic from Application (High Priority)

**The problem**: `DailyGameSimulator.handle_powerup()` reimplements — almost line-for-line — the live power-up resolution logic already in `PowerUpManager`. Every time a rule changes (e.g. retro jinx ratio, steal streak cost, whiff-on-rest), it must be updated in two places.

The duplicated paths include:
- Jinx resolution (normal and retroactive)
- Late-day jinx (bonus stripping)
- Streak-cost deduction for steal (normal, retro, preload)
- Streak-bonus recalculation after steal
- Rest whiff (clearing pending jinx/steal)
- `steal_is_preload` guard logic

**Decided approach — extract `PowerUpEngine`:**

Create `src/core/powerup_engine.py` containing a single class: `PowerUpEngine`. It holds only config-driven constants and pure state-mutation methods. It is completely stateless — callers own the `daily_state` dict, passing it in. The engine simply reads and mutates `DailyPlayerState` objects within it.

```python
# src/core/powerup_engine.py  (sketch — not final API)

class PowerUpEngine:
    """
    Pure power-up state logic. No daily_state ownership, no DB access.
    Callers (PowerUpManager for live play, DailyGameSimulator for replay)
    own their own daily_state dicts and pass them in.
    """

    def __init__(self, config: ConfigReader):
        self.score_calculator = ScoreCalculator(config)
        self.steal_streak_cost = int(config.get("JBOT_STEAL_STREAK_COST", "3"))
        self.retro_steal_streak_cost = int(config.get("JBOT_RETRO_STEAL_STREAK_COST", "5"))
        self.retro_jinx_bonus_ratio = float(config.get("JBOT_RETRO_JINX_BONUS_RATIO", "0.5"))
        self.rest_multiplier = float(config.get("JBOT_REST_MULTIPLIER", "1.2"))

    def _get_state(self, daily_state: dict, player_id: str) -> DailyPlayerState:
        if player_id not in daily_state:
            daily_state[player_id] = DailyPlayerState()
        return daily_state[player_id]

    def apply_jinx(self, daily_state: dict, attacker_id: str, target_id: str) -> None:
        """Set jinx state; if target already answered, resolve retroactively."""
        ...

    def resolve_jinx_on_correct(self, daily_state: dict, target_id: str) -> int:
        """Transfer streak bonus from jinxed target to attacker. Returns stolen amount."""
        ...

    def apply_steal(self, daily_state: dict, thief_id: str, target_id: str,
                    initial_streak: int, is_preload: bool = False) -> int:
        """Set steal state with streak deduction. Returns streak points deducted."""
        ...

    def resolve_steal_on_correct(self, daily_state: dict, target_id: str) -> int:
        """Transfer stealable bonuses to thief when target answers. Returns stolen amount."""
        ...

    def apply_rest(self, daily_state: dict, player_id: str) -> None:
        """Mark player resting; whiff any pending attacks."""
        ...

    def strip_late_day_jinx_cost(self, daily_state: dict, player_id: str) -> int:
        """Strip before_hint and fastest bonuses as late-day jinx cost. Returns amount deducted."""
        ...

    def recalculate_streak_bonus(self, daily_state: dict, player_id: str, new_streak: int) -> None:
        """Recalculate and apply streak bonus after a steal reduces the thief's streak."""
        ...
```

`PowerUpManager` sheds its inline logic and delegates to the engine, keeping only DB writes and live-state bookkeeping:

```python
class PowerUpManager:
    def __init__(self, player_manager, data_manager, config=None):
        _config = config or ConfigReader()
        self.engine = PowerUpEngine(_config)
        self.daily_state: dict[str, DailyPlayerState] = {}
        # DB + emoji config as before...

    def jinx(self, attacker_id, target_id, question_id):
        # validation + DB write as before
        self.engine.apply_jinx(self.daily_state, attacker_id, target_id)
        # return message
```

`DailyGameSimulator` also sheds its inline logic, accepts the engine as a dependency, and drives it with its own isolated `daily_state`:

```python
class DailyGameSimulator:
    def __init__(self, ..., config):
        self.daily_state = defaultdict(DailyPlayerState)
        self.engine = PowerUpEngine(config)

    def handle_powerup(self, event: PowerUpEvent):
        # Just routing — all logic in engine
        self.engine.apply_jinx(self.daily_state, event.user_id, event.target_user_id)
```

**On isolation (admin vs. live play)**:

This is safe by design. `PowerUpEngine` is stateless — it holds no `daily_state` itself. Each scope that needs it creates its own isolated `daily_state` dict and passes it in:

| Scope | `daily_state` owner | Engine instance |
|-------|--------------------|--------------------|
| Live play | `PowerUpManager` | Shared (from `PowerUpManager`) |
| Mid-day restore | `DailyGameSimulator` (ephemeral) → copied to `PowerUpManager` via `restore_daily_state` | Fresh |
| Admin retroactive correction | `DailyGameSimulator` (ephemeral) → results applied to DB only | Fresh |

A simulator run for admin corrections creates its own fresh `daily_state`, processes events, writes DB deltas, and is discarded. It never touches `PowerUpManager.daily_state`. The only intentional transfer point is `GameRunner.restore_game_state()` → `powerup_manager.restore_daily_state()`, which remains explicit and deliberate.

---

## 2. `GuessHandler` Recreated on Every Guess (Medium Priority)

**The problem**: `GameRunner.handle_guess()` instantiates a fresh `GuessHandler` for every single guess, which queries `alternative_answers` from the database each time.

```python
# game_runner.py — called for every guess attempt
def handle_guess(self, player_id, player_name, guess):
    guess_handler = GuessHandler(...)   # DB hit every call
    return guess_handler.handle_guess(player_id, player_name, guess)
```

**Proposed fix**: Construct `GuessHandler` once per question day (alongside the rest of the day's setup in `set_daily_question`) and hold it on `GameRunner`. Tear it down in `end_daily_game`. This also makes `GuessHandler` consistent in lifecycle with `PowerUpManager`.

---

## 3. Unify `on_guess` with a `GuessContext` Dataclass (Medium Priority)

**The problem**: `GuessHandler.handle_guess()` uses a triple-nested `try/except TypeError` to call `manager.on_guess()` with progressively fewer arguments. This exists for backward compatibility with old manager signatures but has accumulated significant complexity.

```python
# guess_handler.py — three cascading fallbacks
try:
    msgs = manager.on_guess(pid, name, guess, correct, pts, bonuses, bonus_msgs, tracker, question_id=qid)
except TypeError:
    try:
        msgs = manager.on_guess(pid, name, guess, correct, pts, bonuses, bonus_msgs)
    except TypeError:
        ...
```

The `BaseManager` ABC declares `on_guess(player_id, player_name, guess, is_correct)`, which doesn't match any current implementation.

**Decided fix — `GuessContext` dataclass + single canonical signature**:

```python
# src/core/events.py or a new src/core/guess_context.py

@dataclass
class GuessContext:
    player_id: str
    player_name: str
    guess: str
    is_correct: bool
    points_earned: int = 0
    bonus_values: dict[str, int] = field(default_factory=dict)
    bonus_messages: list[str] = field(default_factory=list)
    question_id: int | None = None
```

`GuessContext` is mutable — managers that adjust the final score (steal deduction, rest wakeup bonus) update `ctx.points_earned` directly, replacing the `points_tracker` dict. `on_guess` returns only the list of messages to append.

```python
# BaseManager
def on_guess(self, ctx: GuessContext) -> list[str]: ...

# PowerUpManager
def on_guess(self, ctx: GuessContext) -> list[str]:
    if ctx.is_correct:
        ctx.points_earned += rest_bonus  # replaces points_tracker mutation
    return messages
```

Remove all fallback `try/except TypeError`. If a manager doesn't conform, it's a bug.

**On `BaseManager` vs Protocol**: `BaseManager` is currently an ABC with an abstract `on_guess`. Given that the managers dict is populated by string key (not type-checked), a `typing.Protocol` is more honest about the actual contract — but this is optional and can be deferred until there's a second use case for it.

---

## 4. `ConfigReader` Instantiated Ad-Hoc Throughout the Codebase (Medium Priority)

**The problem**: `ConfigReader()` is called independently in `GameRunner`, `GuessHandler`, `PowerUpManager`, `ScoreCalculator`, and `discord.py`. The instructions already call this out as "a known issue." Every class that needs config creates its own reader, preventing centralized control (e.g. test injection, config validation in one place).

**Proposed fix**: A single `ConfigReader` is created at the bot entrypoint (`main.py`) and threaded down via constructor injection. This unblocks clean test overrides (`config = MockConfig({"JBOT_BONUS_STREAK_PER_DAY": "5"}, ...)`).

The config is already being passed through `GameRunner` → `DailyGameSimulator`, so the pattern already exists at the top. The remaining non-injected sites just need to accept it as a constructor arg (with a fallback default for backward compat).

---

## 5. Leaderboard Badge Logic — Remove Duplication (Medium Priority)

**The problem**: `GameRunner.get_scores_leaderboard()` contains ~80 lines of raw DB queries and manual loops to reconstruct which players got which bonuses today (fastest, before-hint, first-try, powerup badges). The bonus key strings (`"first_try"`, `"before_hint"`, `"fastest"`, etc.) are hardcoded independently from `ScoreCalculator`, so new bonus types need to be wired in two places.

**Decided approach — DB remains source of truth, but remove duplication**:

The leaderboard stays DB-driven. The fix is narrower:
1. Introduce string constants for bonus keys in `ScoreCalculator` (e.g. `ScoreCalculator.KEY_FIRST_TRY = "first_try"`). The leaderboard references these constants instead of hardcoded strings.
2. Extract the badge-building loops into a helper method (e.g. `_build_daily_badges(daily_question_id) -> dict[str, list]`) to separate concerns within `GameRunner`.
3. If a new bonus is added, one place (`ScoreCalculator`) defines the key, and the leaderboard will automatically pick it up if it iterates the constants.

This is intentionally a smaller change than re-routing through `daily_state`. The leaderboard's DB queries already provide the data; the goal is just to stop the string literals from drifting.

---

## 6. `DailyPlayerState` Has Dual Naming (Low Priority)

**The problem**: `DailyPlayerState` has `score_earned`/`bonuses` as the primary fields, plus `earned_today`/`bonuses_today` as property aliases. This creates ambiguity — callers use both names interchangeably, making grep/refactoring harder.

```python
# state.py
score_earned: int = 0
bonuses: dict[str, int] = ...

@property
def earned_today(self): return self.score_earned   # alias
@property
def bonuses_today(self): return self.bonuses        # alias
```

**Proposed fix**: Standardize on one name (suggest `score_earned`/`bonuses` since they are the field names) and remove the aliases. The aliases exist to "match PowerUpManager naming conventions" per the comment, so this also implies harmonizing what PowerUpManager calls them.

---

## 7. `AnswerChecker` Instantiated Independently in Multiple Places (Low Priority)

Both `DailyGameSimulator.__init__` and `GuessHandler.__init__` create their own `AnswerChecker` instances. Since `AnswerChecker` is stateless, one shared instance is fine. This is a minor cleanup, but consistent with the injection pattern being established.

---

## 8. Hint Timestamp Normalization Duplicated (Low Priority)

The same `datetime.fromisoformat(ts)` guard pattern for hint timestamps appears independently in:
- `DailyGameSimulator.__init__`
- `GameRunner.restore_game_state`
- `GameRunner._fetch_daily_events`

A small `parse_timestamp(ts) -> datetime | None` utility (or a method on `DataManager`) would keep this in one place.

---

## 9. `points_tracker` Mutable Dict as Implicit Out-Param (Low Priority)

**The problem**: Score adjustments made by power-up managers (steal, rest wakeup) are communicated back to `GuessHandler` via a mutable dict `{"earned": points_earned}`. Each `on_guess` call may mutate it. This is effectively a mutable reference passing pattern and is easy to misuse or miss.

**Proposed fix**: Return a delta from `on_guess` (`int`), or return a structured result object. Alternatively, if `PowerUpManager` owns more of the scoring adjustments, `points_tracker` may become unnecessary.

---

## 10. `GameEvent.is_correct` Field is Never Set (Cosmetic)

`GuessEvent` has an `is_correct: bool = False` field, per the comment "Populated during simulation." In practice, the simulator never sets it — correctness is recalculated from event data on replay. The field is dead and potentially misleading.

---

## Summary Table

| # | Issue | Location(s) | Impact | Effort | Status |
|---|-------|-------------|--------|--------|--------|
| 1 | Extract `PowerUpEngine` — remove sim/manager duplication | `daily_game_simulator.py`, `powerup.py` | High | High | Approach decided |
| 2 | `GuessHandler` recreated per-guess | `game_runner.py`, `guess_handler.py` | Medium | Low | Approach decided |
| 3 | `on_guess` multi-signature fallback + `GuessContext` | `guess_handler.py`, `base_manager.py` | Medium | Medium | Approach decided |
| 4 | `ConfigReader` scattered ad-hoc instantiation | Multiple | Medium | Medium | Approach decided |
| 5 | Leaderboard badge key constants + helper extraction | `game_runner.py` | Medium | Low | Approach decided |
| 6 | `DailyPlayerState` dual naming | `state.py` | Low | Low | Pending |
| 7 | `AnswerChecker` instantiated in multiple places | `daily_game_simulator.py`, `guess_handler.py` | Low | Trivial | Pending |
| 8 | Hint timestamp normalization duplicated | `daily_game_simulator.py`, `game_runner.py` | Low | Trivial | Pending |
| 9 | `points_tracker` mutable dict → `GuessContext.points_earned` | `guess_handler.py`, `powerup.py` | Low | Medium | Resolved by #3 |
| 10 | `GuessEvent.is_correct` dead field | `events.py` | Cosmetic | Trivial | Pending |

**Implementation order**: #1 → #2 + #3 + #4 together → #5 → remaining low/trivial

---

## Decisions Log

| Question | Decision |
|----------|----------|
| `GuessContext.points_earned` mutability | Managers mutate `ctx.points_earned` directly (current pattern). The main argument for explicit returns would be easier traceability in tests and debugging, but it adds a second return value to every `on_guess` implementation — not worth the churn. Decided: keep mutable. |
| `PowerUpEngine` file location | New file: `src/core/powerup_engine.py`. Keeps dependency direction unambiguous. |
| `GuessContext` module | In `src/core/events.py` alongside `GuessEvent`/`PowerUpEvent`. |
| `ConfigReader` in `power.py` cog | Fix it as part of the #4 batch. The cog reads config at class-definition time (inside the decorator arg), which means it fires on import. The fix is to move the config read into `__init__` and reference `self.steal_streak_cost` in the description, or just hardcode the default since it's display-only. |

**All design questions resolved. Ready for implementation.**
