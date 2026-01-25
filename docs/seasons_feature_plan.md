# Seasons Feature Plan

**Status**: Planning
**Target**: Major feature release
**Date Created**: January 19, 2026

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
   - **Options for display**:
     - A) Discord role (e.g., "🏆 Jan 2026 Champion") - low visibility, clutters roles
     - B) Trophy emoji in leaderboard next to name - high visibility, permanent record
     - C) Dedicated `/game trophies <player>` command - middle ground
     - D) Combination: Trophy emoji + command for details
   - **Decision**: Option D - emoji on leaderboard (🥇🥈🥉) + `/game trophies` for full history
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

#### `season_daily_scores`
```sql
-- Track daily performance within seasons for event sourcing
CREATE TABLE season_daily_scores (
    player_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    question_date TEXT NOT NULL,         -- ISO8601 date
    points_earned INTEGER DEFAULT 0,
    answered_correctly INTEGER DEFAULT 0,
    -- Event sourcing data
    guess_events TEXT,                   -- JSON array of events
    powerup_events TEXT,                 -- JSON array of events
    PRIMARY KEY (player_id, season_id, question_date),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);
```

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
### Phase 1: Database & Core Infrastructure

1. **Schema Updates** (`db/schema.sql`)
   - Add new tables: `seasons`, `season_scores`, `season_challenges`, `season_daily_scores`
   - Add new columns to `players` table (no column renames)
   - Existing `db/update_schema.py` can handle migration (only adding, not renaming)

2. **DataManager Extensions** (`src/core/data_manager.py`)
   - `get_current_season()` → Season object or None
   - `create_season(name, start_date, end_date)` → season_id
   - `end_season(season_id)` → finalize rankings, award trophies
   - `get_season_scores(season_id, limit)` → list of scores
   - `get_player_season_score(player_id, season_id)` → score data
   - `get_player_all_time_stats(player_id)` → lifetime data (uses `players.score`)
   - `get_player_trophies(player_id)` → list of past trophies with counts
   - `update_season_score(player_id, season_id, **kwargs)`
   - `update_lifetime_stats(player_id, **kwargs)` → updates `players.score` and lifetime_* columns

3. **Configuration** (`.env` / `src/cfg/main.py`)
   ```
   # Season Configuration
   JBOT_ENABLE_SEASONS=true
   JBOT_SEASON_DURATION_DAYS=30
   JBOT_SEASON_AUTO_CREATE=true
   JBOT_SEASON_TROPHY_POSITIONS=3  # Award top 3
   JBOT_BONUS_STREAK_TYPE=season   # Use 'season' streak for point bonuses for fairness
   ```

### Phase 2: Season Manager

4. **Create SeasonManager** (`src/core/season_manager.py`)
   - Singleton pattern like other managers
   - `get_or_create_current_season()` → ensures active season exists
   - `check_season_transition()` → called daily, handles end-of-season
   - `finalize_season(season_id)` → calculate rankings, award trophies
   - `get_season_leaderboard(season_id, limit)` → formatted leaderboard
   - `get_all_time_leaderboard(limit)` → formatted all-time stats
   - `initialize_player_for_season(player_id, season_id)` → create record
   - **Date Handling**: Ensure corrections check `Question.date`, not `Correction.date`.

5. **Integrate with GameRunner** (`src/core/game_runner.py`)
   - Check for season transition during morning routine
   - Initialize season scores for new players
   - Update both season and lifetime stats on answer

### Phase 3: Scoring Integration

6. **Update GuessHandler** (`src/core/guess_handler.py`)
   - Record scores to both `season_daily_scores` and `daily_scores`
   - Update `season_scores` (authoritative for season)
   - Update `players.season_score` (cache)
   - Update `players.score` (accumulative lifetime total)
   - **Streak Logic**:
     - Increment `players.answer_streak` (Resets on season start).
     - Update `players.lifetime_best_streak` if exceeded.
   - On corrections: Use event replay ensuring correct season attribution via date.

7. **Update ScoreCalculator** (`src/core/scoring.py`)
   - Update to accept `streak_val` as parameter (uses seasonal streak)
   - Ensure consistent calculation.

9. **Enhance Game Cog** (`src/cogs/game.py`)
   - `/game leaderboard [all_time:bool=False]` - Enhanced to show season by default
     - Header: "🏆 January 2026 Season - Day 19/31 - Challenge: ⚡ Speed Demon"
     - Trophy emojis for current season leaders + historical count: "🥇 Alice (1,234 pts) 🏆×3"
     - Historical trophy count provides context and bragging rights
   - `/game stats [player] [all_time:bool=False]` - Enhanced to show:
     - Season stats by default (or all-time if flag set)
     - Trophy history at bottom: "Trophies: 🥇×2 🥈×1 🥉×3"
     - Current challenge progress: "⚡ Speed Demon: 3/10 answers before hint"

10. **Minimal Admin Commands** (`src/cogs/admin.py`)
    - `/admin season end` - Manually end current season (emergency/testing)
    - `/admin season info` - Debug season state (shows season_id, dates, active challenges)

### Phase 5: Challenges

11. **Challenge System** (`src/core/challenge_manager.py`)
    - Track challenge progress during season
    - Award badges on completion
    - Display challenge status in `/game season`
    - Auto-select challenge at season start (exclude previous month's)

12. **Challenge Pool** (hardcoded or config)
    - Define 4-6 challenges:
      - "⚡ Speed Demon": Answer 10 questions before hint reveal
      - "🔥 Perfectionist": Achieve a 7-day answer streak
      - "🎯 First Blood": Get 5 first answers this season
      - "🏃 Marathon Runner": Answer 25 questions this season
      - "💯 Ace": Get 15 correct answers this season
      - "🎲 Risk Taker": Answer 5 questions without using hints (future)
    - Random selection algorithm: exclude previous month's challenge

### Phase 6: Display & Polish

13. **Trophy Display**
    - Add trophy emoji to leaderboard for current season top 3
    - Format: `🥇 PlayerName (1,234 pts) 🏆×3` (medal + historical count)
    - Trophy count shows total wins across all seasons
    - Provides context and recognition for consistent performers

14. **Transition Announcements**
    - Bot announces season end in channel
    - Show final leaderboard and trophy winners
    - Welcome message for new season

15. **Testing**
    - Unit tests for SeasonManager
    - Integration tests for season transitions
    - Simulator updates for season boundaries

16. **Historical Season Analysis Tool** (`scripts/backfill_seasons.py`)
    - Analyze existing `daily_scores` data
    - Generate hypothetical seasons from historical data
    - Report: Who would have won each month?
    - Report: Average score gaps, competitive balance metrics
    - Option to actually populate `seasons` and `season_scores` tables with historical data

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
   - Header shows: "🏆 January 2026 Season - Day 19/31 - Challenge: ⚡ Speed Demon"
   - Default display is season stats
   - Trophy emojis for current season top 3 + historical count: "🥇 Alice (1,234 pts) 🏆×3"
   - Historical trophy count provides recognition for consistent performers
   - Command: `/game leaderboard all_time:True` for lifetime stats

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
   - Leaderboard shows trophies: "🥇 Alice (1,234 pts) 🏆×3"
   - `/game trophies @Alice` shows detailed history

### Migration Message

When feature launches, announce:
```
📢 Big Update: Seasons Are Here!

Starting February 1st, we're introducing monthly seasons!

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

Get ready for the February 2026 season! 🎯
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
5. **Display format**: Current season top 3 shown on leaderboard with medals (🥇🥈🥉) + historical trophy count (🏆×3)
6. **Season duration**: Calendar months (Jan 1-31, Feb 1-28, etc.) for intuitive naming; variable length acceptable
7. **Schema safety**: Keep `players.score` as lifetime (no rename). Add `players.season_score` for current season. Use `answer_streak` for season streak (resets monthly).
8. **Command consolidation**: Zero new commands - enhance existing `/game leaderboard` and `/game stats` with `all_time` parameter
9. **Season bootstrap**: Check/create seasons during morning routine, not on bot startup
10. **Testing**: Mock time injection for testing season transitions without waiting for calendar boundaries
11. **Rollout strategy**: Implement with `JBOT_ENABLE_SEASONS=false`, test thoroughly, enable for February 1st launch

## Next Steps

1. ✅ Review and refine this plan (COMPLETE)
2. Build historical analysis tool (`scripts/backfill_seasons.py`)
   - Validate season concept with real data
   - Identify potential issues before implementation
3. Create database migration script
4. Implement Phase 1 (database & infrastructure)
5. Test season creation/transition locally
6. Implement Phase 2-4 (core functionality)
7. Internal testing with test data
8. Announce feature to players
9. Launch with February 2026 season
