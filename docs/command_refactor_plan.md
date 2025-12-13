# JBot Command Refactor Plan

This document outlines a plan to refactor and consolidate JBot's command structure to improve user experience and simplify the command interface.

## 1. Consolidate Game Information Commands (`/game`)

**Goal:** Centralize game state information while keeping high-frequency commands accessible.

*   **`/game status`**: Replaces `/when`. Shows the current question, time until the next event (question or answer), and a summary of the player's personal stats.
*   **`/game leaderboard`**: Moves `/leaderboard`. Displays the current leaderboard.
*   **`/game rules`**: Provides a summary of the rules for active game modes (e.g., Fight, Power-up).

**Note:** `/answer` will remain as a top-level command for quick access. `/question` will be removed entirely.

## 2. Group Player-vs-Player Actions (`/fight`)

**Goal:** Group all PvP actions under a single command group to reduce clutter.

*   **`/fight disrupt <player>`**: Moves `/disrupt`. Initiates an attack on another player.
*   **`/fight shield`**: Moves `/shield`. Activates a defensive maneuver.
*   **`/fight steal <player>`**: Moves `/steal`. Steals points from another player.

## 3. Create a Unified Player Command (`/player`)

**Goal:** Consolidate commands related to a player's own status and management.

*   **`/player profile`**: Moves `/history`. Shows a complete player profile, including stats and streak.
*   **`/player team`**: Moves `/teams`. Manages team membership (join, leave, view).
*   **`/player stats`**: (Optional) Alias for profile or specific stat view.

## Summary of Changes

*   **New Top-Level Groups**: `/game`, `/fight`, `/player`.
*   **Keep Top-Level**: `/answer`.
*   **Consolidate**: `/when`, `/disrupt`, `/shield`, `/steal`, `/history`, `/teams`, `/leaderboard`.
*   **Remove**: `/question`.
