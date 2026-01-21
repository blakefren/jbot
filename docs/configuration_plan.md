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
    *   Create a default `sources.toml` in a new `config/` directory.
    *   Migrate existing `.env` source rules AND file paths into this file.

2.  **Update ConfigReader**:
    *   Modify `src/cfg/main.py`.
    *   Deprecate `JBOT_EXTRA_SOURCES` parsing logic.
    *   Add method `load_toml_config()` to read the entire file.
    *   Add helper methods to retrieve dataset paths (e.g., `get_dataset_path(name)`).

3.  **Refactor Data Loader**:
    *   Update `data/loader.py` to use `ConfigReader.get_dataset_path()` instead of hardcoded `.env` keys like `JBOT_JEOPARDY_LOCAL_PATH`.

4.  **Update QuestionSelector**:
    *   Ensure the loaded TOML dictionary is correctly converted into `QuestionSource` objects.
    *   For file sources, resolve the `dataset` reference to the actual path using the `[datasets]` section.

5.  **Clean Up `.env`**:
    *   Remove legacy `JBOT_EXTRA_SOURCES` and `*_LOCAL_PATH` variables from `.env` and `.env.template`.

6.  **Backward Compatibility**:
    *   (Optional) Check if `JBOT_EXTRA_SOURCES` exists in `.env` and warn the user, or support both for a transition period.

## Next Steps
If approved, I will:
1.  Create `sources.toml`.
2.  Refactor `ConfigReader` to use `tomllib`.
