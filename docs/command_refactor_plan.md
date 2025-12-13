# JBot Command Refactor Plan

This document outlines a plan to refactor and consolidate JBot's command structure to improve user experience and simplify the command interface.

## 1. Consolidate Game Information Commands (`/game`)

**Goal:** Centralize game state information while keeping high-frequency commands accessible.

*   **`/game status`**: Replaces `/when`. Shows the current question, time until the next event (question or answer), and a summary of the player's personal stats.
*   **`/game leaderboard`**: Moves `/leaderboard`. Displays the current leaderboard.
*   **`/game rules`**: Provides a summary of the rules for active game modes (e.g., Fight, Power-up).
*   **`/game profile`**: Moves `/history`. Shows a complete player profile, including stats and streak.

**Note:** `/answer` will remain as a top-level command for quick access.

## 2. Group Game Powers (`/power`)

**Goal:** Group all active game abilities (PvP, Co-op, Power-ups) under a single command group.

*   **`/power disrupt <player>`**: Moves `/disrupt`. Initiates an attack on another player.
*   **`/power shield`**: Moves `/shield`. Activates a defensive maneuver.
*   **`/power steal <player>`**: Moves `/steal`. Steals points from another player.
*   **`/power wager <amount>`**: Moves `/wager`. Wager points on the current question.
*   **`/power reveal`**: Moves `/reveal`. Reveal letters in the answer.
*   **`/power reinforce <player>`**: Moves `/reinforce`. Reinforce another player.

## 3. Group Admin Commands (`/admin`)

**Goal:** Group administrative commands to reduce top-level clutter.

*   **`/admin refund`**: Moves `/refund`. Refunds score/streak to a player.
*   **`/admin subscribe`**: Moves `/subscribe`. Sub/unsub from daily questions.
*   **`/admin resend`**: Moves `/resend`. Resend a scheduled message.
*   **`/admin skip`**: Moves `/skip`. Skips the current daily question.
*   **`/admin ping`**: Moves `/ping`. Check bot response time.

## 4. Removals

**Goal:** Remove outdated or unused commands.

*   **`/question`**: Redundant with `/game status` and daily messages.
*   **`/sync`**: Outdated.
*   **`/feature`**: Outdated.
*   **`/teams`**: Outdated.
*   **`/boss_fight`**: Outdated/Unimplemented.
*   **`/update_roles`**: Outdated (see Logic Refactoring).
*   **`/shutdown`**: Outdated.

## 5. Logic Refactoring

*   **`apply_discord_roles`**: The logic from `update_roles` should be moved to an event listener (e.g., end of day processing) rather than being a manual command.

## Summary of Changes

*   **New Top-Level Groups**: `/game`, `/power`, `/admin`.
*   **Keep Top-Level**: `/answer`.
*   **Consolidate**: `/when`, `/disrupt`, `/shield`, `/steal`, `/history`, `/leaderboard`, `/wager`, `/reveal`, `/ping`, `/reinforce`, `/refund`, `/subscribe`, `/resend`, `/skip`.
*   **Remove**: `/question`, `/sync`, `/feature`, `/teams`, `/boss_fight`, `/update_roles`, `/shutdown`.
