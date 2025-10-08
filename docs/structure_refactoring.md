# Project Structure Refactoring Plan

This document outlines the plan to refactor the `jbot` project structure for better organization, scalability, and maintainability.

## Proposed Directory Structure

The new structure will organize the codebase by feature and separate source code from configuration and data files.

```
jbot/
├── .github/
├── data/
│   ├── __init__.py
│   └── loader.py         # Logic for loading questions from datasets (replaces `bot/readers`)
├── docs/                 # For project documentation
├── scripts/
│   └── run_tests.bat
├── src/
│   ├── __init__.py
│   ├── cfg/              # Application configuration
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── players.py
│   ├── cogs/
│   │   ├── __init__.py
│   │   ├── admin.py      # Admin and utility commands
│   │   ├── coop.py       # Coop track commands and logic
│   │   ├── fight.py      # Fight track commands and logic
│   │   ├── metrics.py    # Player metrics and stats
│   │   ├── powerup.py    # Power-up track commands and logic
│   │   ├── roles.py      # Role management commands
│   │   └── trivia.py     # Core trivia game commands
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py   # Database connection and query logic
│   │   ├── game_runner.py # Core game loop and state management
│   │   ├── powerup.py    # Power-up logic
│   │   └── roles.py      # Role management logic
│   ├── database/
│   │   ├── dashboard.ipynb # Jupyter notebook for data analysis
│   │   ├── jbot.db
│   │   └── schema.sql
│   └── main.py           # Cog loading and bot initialization
├── tests/                # Tests will be restructured to mirror the `src` layout
├── .env.template
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── run.py                # Main bot entry point
```

## Key Changes and Rationale

1.  **`src` Directory**: All Python source code will be moved into a `src` directory. This separates the application logic from root-level project files (like `README.md`, `.gitignore`, etc.), creating a cleaner project root.

2.  **`run.py` Entry Point**: A `run.py` script at the root level will serve as the main entry point for the application. It will be responsible for setting up paths and launching the bot.

3.  **`cogs` Directory**: To align with the modular design of `discord.py`, all cogs from `bot/cogs/` will be moved to `src/cogs/`. This includes not only the feature tracks (`fight.py`, `powerup.py`, `coop.py`) but also core functionalities like `trivia.py`, `admin.py`, `roles.py`, and `metrics.py`. This makes the features self-contained and easier to manage.

4.  **`core` Directory**: A `src/core` directory will house essential, cross-cutting concerns. This includes the existing `database.py` and the logic from the current `bot/managers/` directory (e.g., `game_runner.py`, `powerup.py`, `roles.py`). This centralizes core business logic.

5.  **`cfg` Directory**: The existing `cfg` directory will be moved to `src/cfg` to keep all source-related configuration within the `src` folder.

6.  **`data` Directory**: A new `data` directory will centralize all logic related to loading, parsing, and handling trivia datasets. The contents of the existing `bot/readers/` directory will be refactored and consolidated into `data/loader.py`, decoupling data management from the core application logic. The `dashboard.ipynb` notebook will also be located here.

7.  **`database` Directory**: A root-level `database` directory will store the database file (`jbot.db`), schema definitions (`schema.sql`), and any migration scripts. This separates persistent data from the application's source code.

8.  **`scripts` Directory**: Utility scripts, such as `run_tests.bat`, will be moved to a `scripts` directory to keep them separate from the main application source.

9.  **`tests` Directory**: The `tests/` directory will be reorganized to mirror the new `src/` layout. This ensures that our test structure remains consistent with the application structure, making it easier to locate and run tests for specific components.

This refactoring will provide a solid foundation for future development, making it easier to add new features, write tests, and navigate the codebase.