# Database Access Architecture

## Overview

The jbot project follows a strict architectural pattern where **DataManager is the ONLY class that directly accesses the database**. This document outlines this pattern and the reasoning behind it.

## Architecture

```
┌─────────────────┐
│  Discord Cogs   │
│  (trivia,       │
│   admin, etc.)  │
└────────┬────────┘
         │
         ├────────────────────┐
         │                    │
         ▼                    ▼
┌────────────────┐   ┌────────────────┐
│ PlayerManager  │   │  DataManager   │◄──── ONLY class with DB access
│                │   │                │
│ (business      │──►│ (data access   │
│  logic)        │   │  layer)        │
└────────────────┘   └────────┬───────┘
                              │
                              ▼
                     ┌────────────────┐
                     │    Database    │
                     │   (SQLite)     │
                     └────────────────┘
```

## Key Principles

### 1. Single Database Access Point

**DataManager is the sole entry point for all database operations.**

- All SQL queries are written and executed in DataManager methods
- The database instance (`_db`) is private (prefixed with `_`)
- No other classes should import or use `Database` directly

### 2. Separation of Concerns

- **DataManager**: Handles all database I/O, SQL queries, and data persistence
- **PlayerManager**: Contains business logic for player operations (uses DataManager)
- **Cogs**: Handle Discord interactions and game flow (use PlayerManager and DataManager)

### 3. Benefits

- **Single Source of Truth**: All database logic is in one place
- **Easier Testing**: Mock DataManager methods instead of database calls
- **Easier Refactoring**: If we change databases, only DataManager needs updates
- **Better Error Handling**: Centralized error handling for DB operations
- **Consistent Data Access**: All queries follow the same patterns

## Implementation Details

### DataManager Design

```python
class DataManager:
    """
    Handles all database interactions for the bot.
    This is the ONLY class that should directly access the database.
    """

    def __init__(self, db: "Database"):
        # Private attribute - prevents direct access
        self._db = db

    # All database operations are methods here
    def get_player(self, player_id: str) -> Optional[Player]:
        query = "SELECT ..."
        result = self._db.execute_query(query, (player_id,))
        # ... process and return
```

### What NOT to Do

❌ **Don't do this:**
```python
# In a cog or manager class
from db.database import Database

class SomeCog:
    def __init__(self, db: Database):
        self.db = db  # WRONG - direct DB access

    def some_method(self):
        self.db.execute_query("SELECT ...")  # WRONG
```

✅ **Do this instead:**
```python
# In a cog or manager class
from src.core.data_manager import DataManager

class SomeCog:
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager

    def some_method(self):
        self.data_manager.get_player(player_id)  # CORRECT
```

## Testing

### Unit Tests

When testing DataManager itself:
```python
class TestDataManager(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")  # Test uses real DB instance
        self.data_manager = DataManager(self.db)

    def test_something(self):
        # Access the private _db for mocking if needed
        self.data_manager._db.execute_query = MagicMock(...)
```

### Integration Tests

When testing other components that use DataManager:
```python
def test_player_manager(self):
    # Mock DataManager methods, not database
    mock_data_manager = MagicMock()
    mock_data_manager.get_player.return_value = Player(...)

    player_manager = PlayerManager(mock_data_manager)
    # Test player manager logic
```

## Future-Proofing

### Adding New Database Operations

When you need a new database operation:

1. **Add a method to DataManager** with a clear, descriptive name
2. Write the SQL query inside that method
3. Return the appropriate data type (Player, list[dict], etc.)
4. Document the method with docstrings

Example:
```python
def get_players_with_streak_above(self, min_streak: int) -> list[Player]:
    """
    Retrieves all players with an answer streak above the specified minimum.

    Args:
        min_streak: The minimum streak value

    Returns:
        List of Player objects matching the criteria
    """
    query = "SELECT * FROM players WHERE answer_streak > ?"
    records = self._db.execute_query(query, (min_streak,))
    return [self._record_to_player(r) for r in records]
```

### Migrating to a Different Database

If we ever need to switch from SQLite to PostgreSQL, MySQL, etc.:

1. Update the `Database` class to use the new DB driver
2. Update DataManager's SQL queries (if syntax differs)
3. **No other code needs to change** - the rest of the application is decoupled

## Checklist for Code Reviews

When reviewing code that touches data:

- [ ] Does it import `Database`? (Should only be in DataManager)
- [ ] Does it call `._db` directly? (Should only be inside DataManager)
- [ ] Does it execute SQL queries? (Should be encapsulated in DataManager methods)
- [ ] Are new DB operations added as DataManager methods?
- [ ] Is the DataManager documentation updated?

## Enforcement

### Private Attribute

The `_db` attribute is marked as private (prefix `_`) to signal it should not be accessed outside the class. While Python doesn't enforce true private access, this convention serves as a strong indicator.

### Import Checking

Periodically run:
```bash
# Check for Database imports outside of DataManager
grep -r "from db.database import Database" src/ --exclude="*data_manager.py"
```

If any matches appear in production code (outside tests), they should be removed.

## Summary

**Remember**: If you need to access the database, add a method to DataManager. Never access the database directly from cogs or other managers.

This pattern keeps our codebase maintainable, testable, and adaptable to future changes.
