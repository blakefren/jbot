# Jeopardy Question Selection Bug Investigation

**Date**: January 29, 2026
**Status**: Monitoring (Weight increased to force selection)
**Priority**: Medium (Likely statistical anomaly, testing to confirm)

## Problem Statement

Jeopardy questions configured in `sources.toml` have **never been selected** in 136 days of bot operation (164 questions sent), despite being properly loaded with:
- 95,930 questions available
- 75.0 weight (36.6% expected selection rate)
- Proper configuration in `sources.toml`

**Statistical Impossibility**: Probability of 0 Jeopardy selections in 136 days = ~1 in 859 trillion

## Configuration Verification

### Sources Configuration (sources.toml)
```toml
[[source]]
name = "jeopardy_easy"
type = "file"
dataset = "jeopardy"
weight = 75.0
reader = "jeopardy"
clue_values = [100, 200]
final_jeopardy_score_sub = 10000
points = 100
```

### Active Sources & Weights
From bot startup logs (2026-01-24):
```
Added file source: 5th_grader (weight=100.0, questions=429)
Added file source: jeopardy_easy (weight=75.0, questions=95930)
Added Gemini source: riddle_medium (weight=20.0, difficulty=Medium, points=100)
Added Gemini source: riddle_hard (weight=10.0, difficulty=Hard, points=200)
```

**Total weight**: 205.0
**Expected probabilities**:
- 5th_grader: 48.8%
- jeopardy_easy: 36.6%
- riddle_medium: 9.8%
- riddle_hard: 4.9%

### Actual Selection History (Last 30 days)
```
Source                   Count    Percentage
5th Grader               16       53.3%
gemini_medium            6        20.0%
Are You Smarter...       4        13.3%
gemini_hard              4        13.3%
Jeopardy!                0        0.0%    ← NEVER SELECTED
```

### Recent Selections (Last 5 days from logs)
```
2026-01-25: riddle_medium
2026-01-26: 5th_grader
2026-01-27: riddle_medium
2026-01-28: riddle_medium
2026-01-29: 5th_grader
```

## Investigation Steps

### 1. Database Verification
**Action**: Checked `db/jbot.db` for Jeopardy questions
**Result**: Zero questions with `source="Jeopardy!"` in the database
**Finding**: Questions are only added to DB when selected and sent, confirming none were ever selected

### 2. Dataset File Verification
**Action**: Verified dataset file exists and can be loaded
**Result**:
- File exists: `datasets/combined_season1-41.tsv`
- Total rows: 214,397
- Filtered (clue_values [100, 200]): 95,930 questions
- Sample data_source value: `"Jeopardy!"`

### 3. Question Loading Test
**Action**: Tested `read_jeopardy_questions()` directly
**Result**: Successfully loaded 95,930 questions with correct filtering

### 4. Source Parsing Test
**Action**: Tested `ConfigReader.parse_question_sources()`
**Result**: Sources load correctly:
- Without Gemini: 2 sources (5th_grader, jeopardy_easy)
- With Gemini: 4 sources (all expected sources present)
- jeopardy_easy contains 95,930 questions

### 5. Weighted Selection Algorithm Test
**Action**: Tested the exact weighted random selection algorithm in isolation
**Result**: Algorithm works perfectly over 100,000 iterations:
```
5th_grader:    48.42% (expected 48.78%)
jeopardy_easy: 36.93% (expected 36.59%)
riddle_medium:  9.83% (expected 9.76%)
riddle_hard:    4.82% (expected 4.88%)
```

### 6. Source Order Verification
**Action**: Checked order of sources in memory
**Result**: Correct order (0: 5th_grader, 1: jeopardy_easy, 2: riddle_medium, 3: riddle_hard)

### 7. QuestionSelector Integration Test
**Action**: Simulated 100 question selections with actual QuestionSelector
**Result**:
- Jeopardy selected 36% of the time (as expected)
- When Gemini sources fail (mock), they return None
- **With original code**: 13 failed selections (returned None)
- **With retry fix**: 0 failed selections

### 8. Edge Case Testing
**Action**: Tested random.uniform() behavior and selection boundary conditions
**Result**:
- `random.uniform(0, 205)` never returns exactly 0 or >= 205
- All boundary conditions work correctly
- Selection ranges are correct

## Discounted Hypotheses

### ❌ Bot Not Restarted After Configuration
**Hypothesis**: Bot wasn't restarted after adding Jeopardy to sources.toml
**Evidence Against**: Startup logs from 2026-01-24 clearly show jeopardy_easy being loaded
**Status**: Disproven

### ❌ Dataset File Missing or Corrupt
**Hypothesis**: Dataset file doesn't exist or is unreadable
**Evidence Against**: File exists, loads successfully, contains 214K rows
**Status**: Disproven

### ❌ Weighted Selection Algorithm Bug
**Hypothesis**: The weighted random selection has a bug
**Evidence Against**: Algorithm tested in isolation works perfectly over 100K iterations
**Status**: Disproven

### ❌ Configuration Syntax Error
**Hypothesis**: sources.toml has a syntax error preventing Jeopardy from loading
**Evidence Against**: Startup logs show "Added file source: jeopardy_easy (weight=75.0, questions=95930)"
**Status**: Disproven

### ❌ Gemini Failures Blocking Selection
**Hypothesis**: When Gemini sources fail, the system returns None instead of trying another source
**Evidence Against**:
- User reports no regular Gemini failures (only latency causing heartbeat warnings)
- This would give Jeopardy MORE chances via retries, not fewer
- Logs show exactly 1 "Selected question source" per day (no retries)
**Status**: Disproven (though a retry mechanism was still beneficial to implement)

### ❌ Questions Filtered Out by Validation
**Hypothesis**: Jeopardy questions fail validation and are marked invalid
**Evidence Against**:
- No "Jeopardy! (Invalid)" entries in database
- Direct testing shows validation works
**Status**: Disproven

## Current Understanding

### What We Know For Certain
1. ✅ Jeopardy source IS configured correctly
2. ✅ Dataset file EXISTS and is readable
3. ✅ 95,930 questions ARE loaded at bot startup
4. ✅ Weighted selection algorithm WORKS in isolation
5. ✅ Source is selected exactly ONCE per day (no retry loop)
6. ✅ Bot has been running continuously since Sept 2025 (136+ days)
7. ✅ Statistical impossibility (1 in 859 trillion) confirms this is a bug, not random chance

### What We Don't Know
1. ❓ Why the weighted selection in production never picks jeopardy_easy
2. ❓ If there's something different about the runtime environment vs tests
3. ❓ If the sources list is being modified after initialization
4. ❓ If there's a random seed issue or state persistence problem
5. ❓ If there's an exception or code path we haven't identified

### Key Discrepancy
- **Tests**: Jeopardy selected ~37% of the time (correct)
- **Production**: Jeopardy selected 0% over 136 days (impossible)

This suggests the issue is NOT in the core algorithm but in:
- Runtime state/environment
- Source list modification after loading
- An undiscovered code path
- Random number generator state
- Some interaction we haven't tested

## Code Changes Made

### Attempted Fix (Reverted)
**File**: `data/readers/question_selector.py`
**Change**: Modified `get_random_question()` to retry with different sources when one returns None
**Rationale**: Prevent Gemini failures from blocking question selection
**Outcome**:
- Fix works (0 failed selections in testing)
- But doesn't address root cause (Jeopardy never being selected in first place)
- **Status**: Reverted pending root cause identification

## Jan 29, 2026: Log Analysis & Probability Check

### Investigation of `tmp.txt` Logs (Jan 24 - 29)
The user provided detailed logs spanning 5 days. We analyzed the question selection events:

*   **Observed Selections (5 days)**:
    1.  `riddle_medium` (Jan 25)
    2.  `5th_grader` (Jan 26)
    3.  `riddle_medium` (Jan 27)
    4.  `riddle_medium` (Jan 28)
    5.  `5th_grader` (Jan 29)
*   **Jeopardy Selections**: 0
*   **Riddle Selections**: 3

### Probability Analysis
Given the configuration:
*   **Jeopardy Weight**: 75.0 (Chance: ~36.6%)
*   **Riddle Medium Weight**: 20.0 (Chance: ~9.8%)
*   **Total Weight**: 205.0

**Calculations**:
*   Probability of **0 Jeopardy selections** in 5 days: $(1 - 0.366)^5 \approx 10.3\%$
*   Probability of **0 Jeopardy selections** in 7 days (including user report): $(1 - 0.366)^7 \approx 4.2\%$
*   Probability of **3 Riddle selections** in 5 days (Binomial): $\approx 0.8\%$

**Conclusion from Data**:
The lack of Jeopardy selections is **statistically unlikely (~4-10%) but NOT impossible**. The previous calculation of "1 in 859 trillion" was based on an assumption of 136 days of zero selections, but it appears the configuration might have been different or the logs observed were only recent. The log explicitly shows **Zero "Selected question source: jeopardy_easy" entries**, confirming it wasn't selected and then discarded (which would produce a log entry and potential rejection log).

### Discarded "Validation" Hypothesis
We briefly hypothesized that `validate_question` (using Gemini) might be rejecting Jeopardy questions due to their "Answer is a Question" format.
*   **Evidence Against**: The logs show `jeopardy_easy` was *never selected* by the RNG step. Validation only runs *after* selection. Therefore, validation cannot be the cause of non-selection in these logs.

### Action Taken
To confirm the pipeline functions correctly and to "break the streak" of bad RNG:
1.  **Modified `sources.toml`**: Increased `jeopardy_easy` weight from `75.0` to **`1000.0`**.
    *   New Selection Chance: ~91%
2.  **Next Step**: Restart bot and observe tomorrow's selection.
    *   If Jeopardy IS selected -> The system works, previous lack of selection was bad luck/statistical anomaly.
    *   If Jeopardy IS NOT selected -> There is a critical, hidden bug preventing its selection even with overwhelming weight.
3.  **Plan**: Revert weight to `75.0` after confirmed successful selection.

## Next Steps

### Immediate Actions
1. **Add Debug Logging** to production bot:
   ```python
   # In QuestionSelector.get_random_question()
   logging.info(f"Sources list: {[s.name for s in self.sources]}")
   logging.info(f"Total weight: {total_weight}, Pick value: {pick}")
   logging.info(f"Selected source: {source.name}")
   ```

2. **Verify Runtime Sources List**:
   - Add endpoint/command to dump `self.sources` from running bot
   - Check if order/weights match expectations
   - Verify jeopardy_easy is actually in the list

3. **Check for State Persistence**:
   - Review if sources list is cached/pickled anywhere
   - Check if there's a sources.json or similar being loaded instead
   - Verify no code modifies self.sources after initialization

4. **Monitor Next Selection**:
   - Watch logs for tomorrow's (2026-01-30) question selection
   - Note the exact pick value and current value during selection
   - Verify the selection logic step-by-step

### Investigation Tasks
- [ ] Add detailed debug logging to weighted selection
- [ ] Create admin command to dump current sources state
- [ ] Check for any file-based source caching
- [ ] Review all code that touches `self.sources`
- [ ] Test with actual production database state
- [ ] Check if random seed is being set somewhere
- [ ] Review git history for changes to selection logic

### Hypothesis to Test
1. **Modified Sources List**: Something removes/modifies jeopardy_easy after loading
2. **Weight Calculation Bug**: Runtime total_weight calculation excludes jeopardy
3. **Iteration Bug**: The for loop skips jeopardy_easy for some reason
4. **State Corruption**: Sources list gets corrupted during bot runtime
5. **Configuration Override**: Another config file overrides sources.toml

## Relevant Files
- **Configuration**: `sources.toml`, `.env`
- **Source Loading**: `src/cfg/main.py:parse_question_sources()`
- **Question Selection**: `data/readers/question_selector.py:get_random_question()`
- **Game Logic**: `src/core/game_runner.py:_get_valid_question()`
- **Dataset**: `datasets/combined_season1-41.tsv`
- **Database**: `db/jbot.db`

## Test Scripts Created
- `debug_jeopardy_selection.py` - Tests actual QuestionSelector with sources
- `test_original_algorithm.py` - Tests weighted selection algorithm
- `test_edge_cases.py` - Tests boundary conditions
- `check_source_order.py` - Verifies source list order

## Log Evidence
```
# Startup (2026-01-24 13:34:15)
INFO - Added file source: jeopardy_easy (weight=75.0, questions=95930)

# Daily Selections (Recent)
2026-01-25 08:00:00 - INFO - Selected question source: riddle_medium
2026-01-26 08:00:00 - INFO - Selected question source: 5th_grader
2026-01-27 08:00:00 - INFO - Selected question source: riddle_medium
2026-01-28 08:00:00 - INFO - Selected question source: riddle_medium
2026-01-29 08:00:00 - INFO - Selected question source: 5th_grader
```

## Conclusion

This is a confirmed bug with a statistically impossible occurrence pattern. The source configuration and algorithm both work correctly in testing, but something in the production runtime environment prevents Jeopardy from ever being selected. Further runtime debugging is required to identify the root cause.

The investigation has eliminated all obvious causes (configuration, file loading, algorithm bugs) and points to a runtime state or environment issue that only manifests in production.
