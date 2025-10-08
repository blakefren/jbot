# Project Structure Refactoring Plan

This document outlines the plan to refactor the `jbot` project structure for better organization, scalability, and maintainability.

## Proposed Directory Structure

The new structure will organize the codebase by feature and separate source code from configuration and data files.

```
jbot/
├── .github/
├── data/
│   ├── __init__.py
│   └── loader.py         # Logic for loading questions from datasets
├── docs/                 # For project documentation
├── scripts/
│   └── run_tests.bat
├── src/
│   ├── __init__.py
│   ├── cogs/
│   │   ├── __init__.py
│   │   ├── coop.py       # Coop track commands and logic
│   │   ├── fight.py      # Fight track commands and logic
│   │   └── powerup.py    # Power-up track commands and logic
│   ├── core/
│   │   ├── __init__.py
│   │   └── database.py   # Database connection and query logic
│   └── main.py           # Main bot entry point
├── tests/
├── .env.template
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

## Key Changes and Rationale

1.  **`src` Directory**: All Python source code will be moved into a `src` directory. This separates the application logic from root-level project files (like `README.md`, `.gitignore`, etc.), creating a cleaner project root.

2.  **`cogs` Directory**: To align with the modular design of `discord.py` and our feature tracks, all game logic related to commands will be organized into cogs within `src/cogs/`. Each track (Fight, Power-up, Coop) will have its own file (`fight.py`, `powerup.py`, `coop.py`), making the features self-contained and easier to manage.

3.  **`data` Directory**: A new `data` directory will centralize all logic related to loading, parsing, and handling the various trivia datasets. This decouples data management from the core application logic.

4.  **`scripts` Directory**: Utility scripts, such as `run_tests.bat`, will be moved to a `scripts` directory to keep them separate from the main application source.

5.  **`core` Directory**: A `src/core` directory will house essential, cross-cutting concerns like database management (`database.py`).

This refactoring will provide a solid foundation for future development, making it easier to add new features, write tests, and navigate the codebase.