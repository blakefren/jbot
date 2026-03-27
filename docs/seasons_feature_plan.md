# Seasons Feature Plan

**Status**: In Progress — Infrastructure complete, wiring remaining
**Target**: April 1, 2026 launch
**Date Created**: January 19, 2026
**Last Updated**: March 26, 2026

## Overview

Implement a monthly seasons system to create recurring competitive cycles while maintaining all-time player statistics. This addresses the leaderboard stagnation problem where new players face a ~100-day gap to catch up with leaders.

## Design Decisions

### Core Mechanics

1. **Season Duration**: Monthly
   - **Decision**: Calendar months (Jan 1-31, Feb 1-28, etc.) for intuitive naming and player communication
   - Variable length (28-31 days) acceptable - minimal fairness impact
   - Config option: `JBOT_SEASON_MODE=calendar|rolling` for future flexibility

1b. **Player Table Schema Strategy**: Explicit separation of Season vs. Lifetime
   - **Crucial Change**: Keep existing `score` column as lifetime tracker (no rename for safety).
   - **New Structure**:
     - `players.score`: **Unchanged** - continues as all-time accumulated total.
     - `players.season_score`: **New column** - cache of current season total (reset monthly).
     - `players.answer_streak`: **Current Season Correct Streak** (resets monthly).
   - **Rationale**: Avoiding column rename eliminates migration risk. The `score` column name is slightly less explicit but safer for a major feature release.

2. **Point Reset**: Season points start at 0
   - Season points start at 0
   - All-time points continue accumulating
   - **Streaks**: Reset to 0 at season start.

3. **Leaderboard Display**:
   - Default: Show current season stats
   - Optional: Toggle to all-time view via parameter
   - Both views available via `/game leaderboard` or `/game stats`

4. **Trophy/Badge System**:
   - End-of-season awards for top 3 players
   - **Decision**: No separate trophies command. Season placement medals (🥇🥈🥉) and historical trophy count (🏆×3) are surfaced in `/game leaderboard all_time:True` and `/game stats @player all_time:True`. Default leaderboard stays clean.
   - Multiple players can share same trophy placement (ties allowed)

5. **Monthly Challenges**:
   - One challenge auto-selected each season from predefined pool
   - Pool of 4-6 challenges, random selection (no repeat from previous month)
   - Examples: "Speed Demon: Answer 10 questions before hint"
   - Award special badges (separate from placement trophies)
   - Track challenge progress during season

### Power-Up & Streak Behavior

**Simplified Streak System**:
- **Season Streak** (`players.answer_streak`):
    - **Resets** on season change (to 0).
    - Represents "Consecutive correct answers *this season*".
    - Used for: Point multipliers/bonuses.
    - **Note**: Max possible streak value is ~31. This is acceptable design; high streaks are rare due to difficulty anyway.

**Season Variables**:
- **Season Score**: Resets to 0.
- **Season Power-up Counts**: Reset (fair playing field).
- **Attack/Defend Balances**: Reset.

**Preserved**:
- **All-time statistics** (total questions answered, total points, etc.)
- **Lifetime Best Streak** (New tracker for historical bragging rights).
- Player account data (join date, preferences)
- Historical season records

### Mid-Season Joins

- New players can join any time during a season
- They compete for remaining days of the season
- No handicap or bonus for joining late (player agency)
- **Future consideration**: "Rookie of the Season" award for best new player?

## Database Schema Changes

### New Tables

#### `seasons`
```sql
CREATE TABLE seasons (
    season_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_name TEXT NOT NULL,           -- e.g., "January 2026"
    start_date TEXT NOT NULL,            -- ISO8601: "2026-01-01"
    end_date TEXT NOT NULL,              -- ISO8601: "2026-01-31"
    is_active INTEGER NOT NULL DEFAULT 0 -- 1 = current season, 0 = past
);
```

#### `season_scores`
```sql
CREATE TABLE season_scores (
    player_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    points INTEGER DEFAULT 0,
    questions_answered INTEGER DEFAULT 0,
    correct_answers INTEGER DEFAULT 0,
    first_answers INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    -- Power-up specific stats
    shields_used INTEGER DEFAULT 0,
    double_points_used INTEGER DEFAULT 0,
    -- Challenge progress
    challenge_progress TEXT DEFAULT '{}',  -- JSON blob
    -- Placement
    final_rank INTEGER,                   -- Set when season ends
    trophy TEXT,                           -- "gold", "silver", "bronze", null
    PRIMARY KEY (player_id, season_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);
```

#### `season_challenges`
```sql
CREATE TABLE season_challenges (
    challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    challenge_name TEXT NOT NULL,        -- "Speed Demon"
    description TEXT NOT NULL,           -- "Answer 10 questions before hint"
    badge_emoji TEXT,                    -- "⚡"
    completion_criteria TEXT NOT NULL,   -- JSON: {"before_hint": 10}
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);
```

#### ~~`season_daily_scores`~~ — REMOVED

**Decision**: Dropped. The `guess_events`/`powerup_events` JSON blobs would have duplicated rows already in `guesses` and `powerup_usage` — a sync liability with no benefit. Per-day season breakdowns are derivable via date-range JOIN on `seasons.start_date/end_date`. `season_scores` handles aggregates; `DailyGameSimulator` already reads from the raw tables for replay.

> **Done**: Removed from `db/schema.sql` and dropped from `jbot.db` (was empty).

### Modified Tables

#### `players` - Migration to Season/Lifetime Split
```sql
-- 1. Keep existing 'score' as lifetime score (NO RENAME for safety)
-- DECISION: players.score remains unchanged, represents lifetime total

-- 2. Add columns for Current Season Cache
ALTER TABLE players ADD COLUMN season_score INTEGER DEFAULT 0;
-- Note: 'answer_streak' is reused as the Current Season Streak (resets monthly).

-- 3. Add other lifetime stats
ALTER TABLE players ADD COLUMN lifetime_questions INTEGER DEFAULT 0;
ALTER TABLE players ADD COLUMN lifetime_correct INTEGER DEFAULT 0;
ALTER TABLE players ADD COLUMN lifetime_first_answers INTEGER DEFAULT 0;
ALTER TABLE players ADD COLUMN lifetime_best_streak INTEGER DEFAULT 0;
```

**Migration Strategy (Safe Mode)**:
1. **Backup**: Backup database before running `update_schema.py`.
2. **Analysis**: Run `scripts/backfill_seasons.py` (dry run) first to verify logic.
3. **Migration Steps**:
   - `players.score` remains unchanged (already lifetime total).
   - New columns auto-initialize to 0 via DEFAULT constraints.
   - `UPDATE players SET answer_streak = 0` (reset for season 1).
   - Existing `update_schema.py` can handle this (only adding columns, no renames).
### Phase 1: Database & Core Infrastructure ✅ COMPLETE

1. ✅ **Schema Updates** (`db/schema.sql`)
   - All new tables added: `seasons`, `season_scores`, `season_challenges`
   - `season_daily_scores` removed — dropped from `db/schema.sql` and `jbot.db` (table was empty; see Database Schema Changes for rationale)
   - All new `players` columns added: `season_score`, `lifetime_questions`, `lifetime_correct`, `lifetime_first_answers`, `lifetime_best_streak`

2. ✅ **DataManager Extensions** (`src/core/data_manager.py`)
   - All season methods implemented: `get_current_season`, `create_season`, `end_season`, `get_season_scores`, `get_player_season_score`, `get_player_trophies`, `update_season_score`, `update_lifetime_stats`, `reset_all_player_season_scores`, `finalize_season_rankings`, and more

3. ✅ **Configuration** (`.env.template` / `src/cfg/main.py`)
   - All `JBOT_SEASON_*` keys present in `.env.template`
   - All getters implemented in `src/cfg/main.py`: `is_seasons_enabled()`, `get_season_mode()`, `get_season_auto_create()`, `get_season_trophy_positions()`, etc.

### Phase 2: Season Manager ✅ COMPLETE

4. ✅ **SeasonManager created** (`src/core/season_manager.py`)
   - `get_or_create_current_season()`, `check_season_transition()`, `finalize_season()`, `get_season_leaderboard()`, `get_all_time_leaderboard()`, `initialize_player_for_season()` all implemented
   - Data models in `src/core/season.py`: `Season`, `SeasonScore`, `SeasonChallenge` dataclasses
   - Unit tests in `tests/src/core/test_season_manager.py` and `tests/src/core/test_season.py`

5. ✅ **Integrate SeasonManager with GameRunner** (`src/core/game_runner.py`)
   - `SeasonManager` instantiated in `__init__` via `self.data_manager` + `self.config` (no constructor signature change)
   - `check_season_transition()` called at the top of `set_daily_question()` — runs on every morning task, prep task, and mid-day restart
   - Disabled cleanly when `JBOT_ENABLE_SEASONS=False` (no-ops without touching DB)
   - GameRunner tests updated: `is_seasons_enabled.return_value = False` in `setUp`; 3 new tests cover init, enabled path, and disabled path

### Phase 3: Scoring Integration ❌ NOT STARTED

6. ❌ **Update GuessHandler** (`src/core/guess_handler.py`) — **TODO**
   - Wire in `SeasonManager` instance
   - On correct answer: update `season_scores` table and `players.season_score` cache
   - On correct answer: update `players.score` (lifetime) and `lifetime_*` stat columns
   - **Streak logic**: increment `players.answer_streak`; update `players.lifetime_best_streak` if exceeded
   - On corrections: replay via `DailyGameSimulator` using `Question.date` for correct season attribution

7. ❌ **Update ScoreCalculator** (`src/core/scoring.py`) — **TODO**
   - Verify `streak_val` parameter already uses seasonal streak; no change if it reads from `players.answer_streak` already

### Phase 4: Discord Commands ❌ NOT STARTED

8. ❌ **Enhance Game Cog** (`src/cogs/game.py`) — **TODO**
   - `/game leaderboard` (default — current season):
     - Header: "🏆 April 2026 Season - Day X/30 - Challenge: ⚡ Speed Demon"
     - Plain season standings — **no medal decorations** (preserves existing leaderboard format)
   - `/game leaderboard all_time:True` (all-time view):
     - Lifetime points + historical trophy count: "Alice (12,340 pts total) 🏆×3"
     - Past season medal tallies shown per player
   - `/game stats [player] [all_time:bool=False]` — season stats by default
     - All-time view: "Trophies: 🥇×2 🥈×1 🥉×3"
     - Challenge progress: "⚡ Speed Demon: 3/10 answers before hint"

9. ❌ **Admin Command** (`src/cogs/admin.py`) — **TODO**
    - Single `@admin.command(name="season")` with optional flags — no nested subgroup needed:
      ```
      /admin season [end:bool=False] [force:bool=False]
      ```
      - **Default** (no flags): shows season info — season_id, name, start/end dates, day X/N, active challenge, player count
      - **`end:True`**: ends the current season (finalize rankings, award trophies, create next season)
        - **Mid-day guard**: if `game_runner.daily_question_id` is not None, block with an error: *"A question is active — ending the season now would freeze out players who haven't answered yet. Wait until after the answer is revealed, or use `force:True` to override."*
        - **`force:True`**: skips the mid-day guard for testing/emergency. Log a warning. Season ends with whatever scores are currently in `season_scores`.

### Phase 5: Challenges ✅ COMPLETE

10. ✅ **ChallengeManager created** (`src/core/challenge_manager.py`)
    - Challenge progress tracking, badge awarding, auto-selection with rotation implemented

11. ✅ **Challenge Pool defined** (in `challenge_manager.py`)
    - 6 challenges implemented with rotation algorithm (excludes previous month's challenge)

### Phase 6: Display & Polish ❌ NOT STARTED

12. ❌ **Trophy Display** (part of game.py work above) — **TODO**
    - Leaderboard format: `🥇 PlayerName (1,234 pts) 🏆×3`

13. ❌ **Transition Announcements** — **TODO**
    - Season-end announcement with final leaderboard and trophy winners
    - New-season welcome message
    - Reminder message N days before season end

14. **Testing**
    - ✅ Unit tests for `SeasonManager` (`tests/src/core/test_season_manager.py`)
    - ✅ Unit tests for `Season` dataclasses (`tests/src/core/test_season.py`)
    - ❌ Integration tests for `GameRunner` + `GuessHandler` season wiring — **TODO**
    - ❌ End-to-end season transition test — **TODO**

15. ✅ **Historical Season Analysis Tool** (`scripts/backfill_seasons.py`)
    - Supports `--dry-run` (analysis) and `--populate` (writes to DB) modes
    - Reconstructs hypothetical monthly seasons from historical `daily_scores` data

## Edge Cases & Considerations

### Season Transitions

**Q**: What happens to in-flight daily questions during season transition?
**A**: Day belongs to season it started in. If morning question is Jan 31, it counts toward January season even if answered Feb 1.

**Q**: What if no one plays during a season?
**A**: Season still exists, just has no scores. No trophies awarded.

**Q**: Can we retroactively create seasons for historical data?
**A**: Yes, via admin commands. Useful for data analysis but trophies only for future seasons.

### Player Experience

**Q**: Do players lose their current streak on season reset?
**A**: **Yes**. `players.answer_streak` tracks the *current season's* consecutive correct answers. When a new season starts, everyone starts fresh at 0. This ensures fair scoring bonuses for the new monthly race.

**Q**: How do we prevent confusion between season and all-time stats?
**A**: Clear labeling in all displays. Default to season stats (what matters for current competition).

**Q**: What about players who join at end of season?
**A**: They compete for the time remaining. Could show "days active this season" to provide context.

**Q**: What happens if players tie for a trophy position?
**A**: Ties are allowed. If Alice and Bob both have 1,234 points, both get 🥇. Next player gets 🥉 (no 🥈).

### Technical

**Q**: How does correction handling work across seasons?
**A**: Corrections are attributed to the `Question.date`. If a correction is made on Feb 1 for a Jan 31 question, the points update the January season (possibly changing the winner) and do NOT affect the February season score.

**Q**: What if season config changes mid-season?
**A**: Config changes apply to future seasons. Current season uses config from creation.

**Q**: How do we handle timezone issues for month boundaries?
**A**: Use bot's configured timezone (same as daily question timing). Month = calendar month in bot's timezone.

**Q**: Are variable-length months (28-31 days) fair?
**A**: Yes, impact is minimal (~10% variance) and random. February being shorter might help new players catch up faster. Players compete on consistency over the available days.

## Configuration Options

### Required Settings
```
JBOT_ENABLE_SEASONS=true/false          # Master toggle
```

### Optional Settings (with defaults)
```
JBOT_SEASON_MODE=calendar               # calendar (monthly) or rolling (N-day periods)
JBOT_SEASON_DURATION_DAYS=30            # Length if mode=rolling (ignored for calendar)
JBOT_SEASON_AUTO_CREATE=true            # Auto-create next season
JBOT_SEASON_TROPHY_POSITIONS=3          # How many get trophies (1st, 2nd, 3rd)
JBOT_SEASON_ANNOUNCE_END=true           # Announce season end in channel
JBOT_SEASON_ANNOUNCE_START=true         # Announce new season start
JBOT_SEASON_REMINDER_DAYS=3             # Days before end to remind about season ending
```

## Player-Facing Changes

### What Players See

1. **Leaderboard Changes**:
   - **Default** (`/game leaderboard`): Current season standings. Header shows "🏆 April 2026 Season - Day X/30 - Challenge: ⚡ Speed Demon". Plain rankings — no medal decoration (preserves existing format).
   - **All-time** (`/game leaderboard all_time:True`): Lifetime points + historical trophy counts, e.g. "Alice (12,340 pts total) 🏆×3"

2. **Stats Command Enhanced**:
   - `/game stats @player` shows season stats, trophy history, and challenge progress
   - Trophy history displayed as: "Trophies: 🥇×2 🥈×1 🥉×3" (all-time count)
   - Challenge progress: "⚡ Speed Demon: 3/10 answers before hint"
   - Command: `/game stats @player all_time:True` for lifetime stats

3. **Announcements**:
   - "🎉 New Season Starting! January 2026 begins tomorrow. All points reset - may the best player win!"
   - "🏁 Season Ending! 3 days left in January 2026. Current leaders: @Alice (1st), @Bob (2nd)..."
   - "🏆 Season Complete! Congratulations to January 2026 winners: 🥇 @Alice, 🥈 @Bob, 🥉 @Charlie"

4. **Trophy Display**:
   - Trophy history visible in `/game leaderboard all_time:True` and `/game stats @player all_time:True`
   - No separate `/game trophies` command

### Migration Message

When feature launches, announce:
```
📢 Big Update: Seasons Are Here!

Starting April 1st, we're introducing monthly seasons!

What's changing:
✅ Points reset each month for fresh competition
✅ Trophies awarded to top 3 players each season
✅ New players have a real chance to win!
✅ All-time stats still tracked (use /game leaderboard all_time:true)

What's staying the same:
✅ Daily questions and gameplay
✅ Power-ups and fight mechanics
✅ Your Answer Streak (resets only on miss or new season)
✅ Your total lifetime stats are preserved

Get ready for the April 2026 season! 🎯
```

## Success Metrics

- Increased engagement from mid-tier players
- More competitive monthly races
- New player retention improvement
- Community excitement around season endings

## Future Enhancements

1. **Weekly mini-seasons** (optional mode)
2. **Special seasonal rules** (e.g., "Double Points March")
3. **Team seasons** (when coop track is implemented)
4. **Season achievements** (beyond challenges)
5. **Season preview/teaser** (announce next season's theme)
6. **Placement rewards** (not just top 3, e.g., top 10 get special badge)

## Decisions Made

1. **Trophy emoji**: 🥇🥈🥉 (medal emojis)
2. **Challenge selection**: Auto-select from pool of 4-6, random each month, no repeats from previous month
3. **Historical seasons**: Build backfill tool (`scripts/backfill_seasons.py`) to analyze and optionally populate historical data
4. **Tie-breaking**: No tie-breaking needed. Multiple players can share trophy positions (e.g., two 🥇 winners)
5. **Display format**: Default leaderboard shows season standings with no medal decoration (preserves existing format). All-time leaderboard shows lifetime points + historical trophy count (🏆×3). No separate `/game trophies` command.
6. **Season duration**: Calendar months (Jan 1-31, Feb 1-28, etc.) for intuitive naming; variable length acceptable
7. **Schema safety**: Keep `players.score` as lifetime (no rename). Add `players.season_score` for current season. Use `answer_streak` for season streak (resets monthly).
8. **Command consolidation**: Zero new top-level commands. Enhance existing `/game leaderboard` and `/game stats` with `all_time` parameter. Admin uses single `/admin season [end:bool] [force:bool]` — info by default, `end:True` ends the season (blocked mid-day unless `force:True`). No `/game trophies` command — trophy history lives in the all-time views.
9. **Season bootstrap**: Check/create seasons during morning routine, not on bot startup
10. **Testing**: Mock time injection for testing season transitions without waiting for calendar boundaries
11. **Rollout strategy**: Implement with `JBOT_ENABLE_SEASONS=false`, test thoroughly, enable for April 1st launch

## Next Steps (Target: April 1, 2026)

1. ✅ Review and refine this plan
2. ✅ Build historical analysis tool (`scripts/backfill_seasons.py`)
3. ✅ Database schema and migration (`db/schema.sql` + `update_schema.py`)
4. ✅ Implement Phase 1 — DataManager, models, config
5. ✅ Implement Phase 2 — SeasonManager, ChallengeManager
6. ✅ Unit tests for core season logic
7. ✅ **Wire SeasonManager into GameRunner** — `check_season_transition()` in `set_daily_question()`; GameRunner tests updated
8. ❌ **Wire season score recording into GuessHandler** (season + lifetime stat updates)
9. ❌ **Update game.py** — season leaderboard, stats, trophy display
10. ❌ **Update admin.py** — `/admin season` command (`info` default, `end:True` flag)
11. ❌ **Transition announcements** — end-of-season, new-season welcome, reminder
12. ❌ Integration tests for wiring layer
13. ❌ Enable `JBOT_ENABLE_SEASONS=True`, run `db/update_schema.py` on production DB
14. ❌ Announce feature to players and launch April 2026 season
