# Configuration Refactoring Plan

## Problem Statement
The current method of defining "Extra Sources" in the `.env` file (`JBOT_EXTRA_SOURCES`) uses a complex, custom-parsed string format (`type:name:weight:args`). As requirements grow (e.g., adding list-based filters like `clue_values=100|200`), this format becomes:
1.  Hard to read and modify.
2.  Error-prone (easy to miss a colon or comma).
3.  Difficult to extend with structured data (lists, nested objects).

## Proposed Solutions

### Option 1: Dedicated JSON Configuration
Move the source definitions to a `config/sources.json` file.

**Format:**
```json
[
    {
        "type": "gemini",
        "name": "riddle_medium",
        "weight": 20,
        "difficulty": "Medium",
        "points": 100
    },
    {
        "type": "file",
        "name": "jeopardy",
        "weight": 25,
        "clue_values": [100, 200]
    }
]
```

*   **Pros:** Native Python support (`json` module), supports structured data (arrays, bools), strict validation.
*   **Cons:** Standard JSON does not support comments (crucial for documenting logical weights).

### Option 2: TOML Configuration (Recommended)
Use a `config/sources.toml` file. Since the project uses Python 3.11+, `tomllib` is available in the standard library.

**Format:**
```toml
# Centralized dataset paths
[datasets]
jeopardy = "datasets/combined_season1-41.tsv"
knowledge_bowl = "datasets/knowledge_bowl.csv"
5th_grader = "datasets/5th_grader.csv"
riddles_with_hints = "datasets/riddles_with_hints.csv"

# Source definitions
[[source]]
name = "riddle_medium"
type = "gemini"
weight = 20
difficulty = "Medium"
points = 100

[[source]]
name = "jeopardy_easy"
type = "file"
dataset = "jeopardy" # References key in [datasets]
weight = 25
clue_values = [100, 200]
```

*   **Pros:** clear syntax, supports comments (`#`), natively supported in Python 3.11+, strict typing.
*   **Cons:** Slightly more verbose than YAML.

### Option 3: YAML Configuration
Use a `config/sources.yaml` file.

*   **Pros:** Very readable, industry standard for config.
*   **Cons:** Requires an external dependency (`PyYAML`), which adds maintenance overhead.

## Recommendation
**Adopt Option 2 (TOML)**.
It offers the best balance of readability (comments, clean syntax) and maintainability (no external dependencies required for Python 3.11).

## Implementation Plan

1.  **Create Configuration File**:
    *   Create `config/sources.toml` in a new `config/` directory (committed to git).
    *   Migrate ALL existing `.env` source rules and dataset paths into this file.
    *   Use the centralized `[datasets]` section for all dataset file paths.
    *   No template file needed - the actual config will be version controlled.

2.  **Update ConfigReader**:
    *   Modify `src/cfg/main.py`.
    *   Remove `JBOT_EXTRA_SOURCES` parsing logic entirely (clean break, no backward compatibility).
    *   Add method `load_toml_config()` to read `config/sources.toml` using `tomllib`.
    *   Add helper method `get_dataset_path(name)` to retrieve paths from the `[datasets]` section.
    *   **Error Handling**: Crash gracefully with clear error messages if:
        - `config/sources.toml` is missing or malformed
        - A source references a non-existent dataset key
        - TOML syntax is invalid

3.  **Refactor Data Loader**:
    *   Update `data/loader.py` to use `ConfigReader.get_dataset_path()` instead of `.env` keys like `JBOT_JEOPARDY_LOCAL_PATH`.
    *   Remove all hardcoded dataset path lookups from `.env`.

4.  **Update QuestionSelector**:
    *   Ensure the loaded TOML dictionary is correctly converted into `QuestionSource` objects.
    *   For file sources, resolve the `dataset` reference to the actual path using the `[datasets]` section.
    *   Validate that all referenced datasets exist before initializing sources.

5.  **Clean Up `.env`**:
    *   Remove `JBOT_EXTRA_SOURCES` and ALL `*_LOCAL_PATH` variables from `.env` and `.env.template`.
    *   Document the migration in comments or update README if needed.

6.  **Testing**:
    *   Update existing tests in `tests/src/` for `src/cfg/main.py`.
    *   Add new test cases for TOML loading, dataset path resolution, and error handling.
    *   Test graceful crashes for malformed configs and missing dataset references.

## Pre-Implementation Investigation
Before implementation, we will:
1.  Review current `.env.template` to identify all keys being migrated.
2.  Examine existing `JBOT_EXTRA_SOURCES` parsing code in `ConfigReader`.
3.  Analyze how `data/loader.py` currently handles dataset paths.
4.  Review existing tests for `src/cfg/main.py` to understand coverage.

## Implementation Steps
1.  Create `config/sources.toml` with migrated configuration.
2.  Refactor `ConfigReader` in `src/cfg/main.py` to use `tomllib`.
3.  Update `data/loader.py` to use new dataset path resolution.
4.  Update `QuestionSelector` for TOML-based source loading.
5.  Clean up `.env` and `.env.template`.
6.  Update and expand tests for configuration loading.
