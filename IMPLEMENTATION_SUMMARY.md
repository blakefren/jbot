# Seasons Feature Implementation - Phase 1 Complete

## Summary

Phase 1 infrastructure for the seasons feature has been implemented. This includes the database schema, core data models, managers, and analysis tools. **No database migrations have been run** - all changes are ready for review.

## Files Created

### 1. Analysis Tool
- **`scripts/backfill_seasons.py`** - Historical data analysis tool
  - Analyzes existing `guesses` and `daily_questions` data
  - Generates "what if" reports showing who would have won each historical month
  - Provides competitive balance metrics
  - Can optionally populate seasons tables with historical data (after schema migration)
  - Usage: `python scripts/backfill_seasons.py --dry-run`

### 2. Data Models
- **`src/core/season.py`** - Season-related dataclasses
  - `Season` - Represents a competitive season (monthly cycle)
  - `SeasonScore` - Player performance within a season
  - `SeasonChallenge` - Monthly challenge configuration
  - All include `from_db_row()` class methods for easy database integration

### 3. Core Managers
- **`src/core/season_manager.py`** - Season lifecycle management
  - `get_or_create_current_season()` - Ensures active season exists
  - `check_season_transition()` - Handles month-to-month transitions
  - `finalize_season()` - Calculates rankings and awards trophies
  - `get_season_leaderboard()` / `get_all_time_leaderboard()` - Leaderboard generation
  - Supports both "calendar" (monthly) and "rolling" (N-day) modes

- **`src/core/challenge_manager.py`** - Monthly challenge system
  - Auto-selects challenges from predefined pool
  - Avoids repeating previous month's challenge
  - Tracks player progress toward completion
  - 6 predefined challenges: Speed Demon, Perfectionist, First Blood, Marathon Runner, Ace, Sharpshooter

## Files Modified

### 1. Database Schema (`db/schema.sql`)
**Players Table - New Columns:**
```sql
season_score INTEGER DEFAULT 0           -- Current season score
lifetime_questions INTEGER DEFAULT 0     -- Total questions answered all-time
lifetime_correct INTEGER DEFAULT 0       -- Total correct answers all-time
lifetime_first_answers INTEGER DEFAULT 0 -- Total first answers all-time
lifetime_best_streak INTEGER DEFAULT 0   -- Best streak ever achieved
```
**Note:** `score` column remains unchanged (lifetime total), `answer_streak` reused for season streak

**New Tables:**
- `seasons` - Season definitions (name, start/end dates, active status)
- `season_scores` - Player performance per season (points, stats, trophies)
- `season_challenges` - Monthly challenge definitions
- `season_daily_scores` - Event sourcing data for corrections

### 2. Player Model (`src/core/player.py`)
- Added new fields to dataclass: `season_score`, `lifetime_questions`, `lifetime_correct`, `lifetime_first_answers`, `lifetime_best_streak`
- Updated `to_dict()` and `from_dict()` methods

### 3. DataManager (`src/core/data_manager.py`)
**Updated Methods:**
- `load_players()` - Now loads new season/lifetime fields
- `get_player()` - Queries new columns
- `create_player()` - Initializes new columns to 0

**New Season Methods (24 total):**
- Season CRUD: `get_current_season()`, `create_season()`, `get_season_by_id()`, `get_all_seasons()`, `end_season()`
- Scoring: `get_season_scores()`, `get_player_season_score()`, `update_season_score()`, `increment_season_stat()`
- Trophies: `get_player_trophies()`, `get_trophy_counts()`, `finalize_season_rankings()`
- Challenges: `get_season_challenge()`, `create_season_challenge()`
- Lifecycle: `initialize_player_season_score()`, `update_lifetime_stats()`, `increment_lifetime_stat()`

### 4. Configuration (`.env.template` and `src/cfg/main.py`)
**New Config Keys:**
```
JBOT_ENABLE_SEASONS=False               # Master toggle (default: disabled)
JBOT_SEASON_MODE=calendar               # "calendar" or "rolling"
JBOT_SEASON_DURATION_DAYS=30            # For rolling mode
JBOT_SEASON_AUTO_CREATE=True
JBOT_SEASON_TROPHY_POSITIONS=3
JBOT_SEASON_ANNOUNCE_END=True
JBOT_SEASON_ANNOUNCE_START=True
JBOT_SEASON_REMINDER_DAYS=3
```

**New ConfigReader Methods:**
- `is_seasons_enabled()`, `get_season_mode()`, `get_season_duration_days()`, etc.

## Next Steps (For You to Execute)

### 1. Review This Implementation
- Check schema changes in [db/schema.sql](db/schema.sql)
- Review data models in [src/core/season.py](src/core/season.py)
- Verify manager logic in [src/core/season_manager.py](src/core/season_manager.py)

### 2. Run Analysis Tool (Recommended)
```bash
python scripts/backfill_seasons.py --dry-run
```
This will generate a report showing:
- Who would have won each historical month
- Competitive balance metrics (score gaps between 1st and 2nd place)
- Trophy case (players with most wins)

The report will be saved to `scripts/season_analysis_report.txt`

**Note:** The script looks for the database at `db/jbot.db`

### 3. Apply Database Migration
**IMPORTANT: Backup your database first!**

```bash
# Backup
copy db\jbot.db db\jbot.db.backup_pre_seasons

# Run migration (will prompt for confirmation)
python db/update_schema.py
```

This will:
- Add new columns to `players` table (all DEFAULT 0, safe)
- Create 4 new tables: `seasons`, `season_scores`, `season_challenges`, `season_daily_scores`

### 4. Verify Migration
```bash
python db/verify_schema.py
```

### 5. Test Locally
- Bot should start normally with `JBOT_ENABLE_SEASONS=False`
- No behavior changes until feature is enabled

## Not Yet Implemented (Phase 2-6)

Still needed before the feature is functional:
- **GuessHandler integration** - Update scoring to track both season and lifetime
- **GameRunner integration** - Check for season transitions during morning routine
- **ScoreCalculator updates** - Use season streak for bonuses
- **Cog enhancements** - Update `/game leaderboard` and `/game stats` commands
- **Admin commands** - Add `/admin season` commands
- **Announcements** - Season start/end/reminder messages
- **Event replay** - Ensure corrections work across season boundaries
- **Testing** - Unit tests for all new components

## Design Decisions Made

1. **Schema Safety**: Kept `players.score` as lifetime (no column rename) to avoid migration risk
2. **Trophy Display**: Show historical trophy count on leaderboard: "🥇 Alice (1,234 pts) 🏆×3"
3. **Season Bootstrap**: Check/create seasons during morning routine, not on bot startup
4. **Testing**: Mock time injection for testing season transitions
5. **Rollout**: Implement with `JBOT_ENABLE_SEASONS=False`, enable for February 1st launch

## Database Migration Safety

The migration is **low-risk** because:
- ✅ No column renames (only additions with DEFAULT values)
- ✅ Existing `update_schema.py` handles this automatically
- ✅ New tables start empty
- ✅ No data transformation required
- ✅ Easily reversible (drop new tables, remove new columns)

However, **still backup your database** before running migration.

## Questions?

Let me know if you:
- Find any issues in the implementation
- Want changes to the design decisions
- Need clarification on any component
- Are ready to proceed to Phase 2 (integration)
