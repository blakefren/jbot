# JBot Command Refactor Plan

This document outlines a plan to refactor and consolidate JBot's command structure to improve user experience and simplify the command interface.

## 1. Consolidate Game Information Commands

**Observation:** Players currently use multiple commands to get a full picture of the game state. For example, `/when` shows the next event time and the current question, while other commands might show player stats or leaderboard information.

**Suggestion:** Combine game-state-related commands into a single, powerful `/game` command. This command will use subcommands to show specific information.

-   **/game status**: Shows the current question, time until the next event (question or answer), and a summary of the player's personal stats (e.g., current streak).
-   **/game leaderboard**: Displays the current leaderboard.
-   **/game rules**: Provides a summary of the rules for active game modes (e.g., Fight, Power-up).

This approach reduces the number of top-level commands a player needs to remember and provides a more centralized way to get information about the game.

## 2. Group Player-vs-Player Actions

**Observation:** The "Fight Track" will introduce several player-vs-player actions. If implemented as individual commands, they could clutter the main command list.

**Suggestion:** Group all PvP actions under a single `/fight` command group.

-   **/fight attack <player>**: Initiates an attack on another player.
-   **/fight defend**: Activates a defensive maneuver.
-   **/fight status**: Shows the player's current PvP status, including active buffs or debuffs.

This makes the PvP feature set feel more cohesive and is more intuitive for players.

## 3. Create a Unified `player` Command for Self-Management

**Observation:** Players often need to check their own stats, inventory, or settings. These commands might be scattered across different cogs (e.g., `powerup`, `roles`, `coop`).

**Suggestion:** Introduce a `/player` or `/me` command group that consolidates all commands related to a player's own status and items.

-   **/player profile**: Shows a complete player profile, including stats, streak, and team affiliation.
-   **/player powerups**: Lists available power-ups and allows the player to use them.
-   **/player team**: Manages team membership (join, leave, view).

This creates a personal dashboard for each player, making it easy for them to manage their own experience within the game.
