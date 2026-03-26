# Rules & Onboarding Gateway — Feature Plan

**Status**: Planning
**Date Created**: March 21, 2026

## Overview

New players join the server but have no access to game channels until they accept the rules. On bot startup, the bot posts (or rediscovers) a persistent embed in a configured `#rules` channel. Clicking "I Agree & Accept" grants the `players` role, which controls access to all game channels. The `players` role already exists and is used for morning/evening @-mention pings — this feature wires it into channel visibility.

---

## Discord Server Setup (Manual — One Time)

These steps are performed by a server admin, not by the bot.

### 1. Create and configure `#rules`

- Create a channel named `#rules` (or any name you choose).
- **Channel permissions**:
  - `@everyone`: ✅ View Channel, ✅ Read Message History — so anyone joining the server can see the rules.
  - No write permission needed for members.

### 2. Lock game channels behind the `players` role

For every game channel (`#trivia`, `#leaderboard`, etc.):

- Open **Edit Channel → Permissions**.
- `@everyone`: ❌ View Channel (deny).
- `players` role: ✅ View Channel (allow).

### 3. Ensure bot role hierarchy

- The bot's role must be **higher** in the server role list than the `players` role.
- Navigate to **Server Settings → Roles**, drag the bot's role above `players`.
- The bot needs the **Manage Roles** permission.

### 4. Copy the `#rules` channel ID

- Right-click the `#rules` channel → **Copy Channel ID**.
- Paste into `.env` as `JBOT_RULES_CHANNEL_ID`.

---

## Config Changes

### `.env.template` additions

```
# Gateway / Onboarding
JBOT_RULES_CHANNEL_ID=todo
```

`JBOT_RULES_CHANNEL_ID` is the only new key. It is read via `config.get("JBOT_RULES_CHANNEL_ID")` — no new `ConfigReader` methods needed.

The existing `JBOT_PLAYER_ROLE_NAME` (default `"players"`) is reused as-is.

---

## Database Changes

A new `bot_settings` table stores arbitrary key-value bot state, starting with the rules message ID. This avoids flat files and is consistent with the DataManager-only access pattern.

### `db/schema.sql` addition

```sql
CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

### New `DataManager` methods

```python
def get_bot_setting(self, key: str) -> str | None
def set_bot_setting(self, key: str, value: str) -> None
```

These map directly to `SELECT value FROM bot_settings WHERE key = ?` and `INSERT OR REPLACE INTO bot_settings`.

---

## New File: `src/cogs/gateway.py`

Contains two classes:

### `RulesView(discord.ui.View)`

| Attribute | Value |
|---|---|
| `timeout` | `None` (persists across restarts) |
| Button label | "I Agree & Accept" |
| Button style | `discord.ButtonStyle.success` (green) |
| Button `custom_id` | `"gateway:accept"` |

The `custom_id` is required — discord.py matches incoming button interactions to a registered view by this ID. Without it, interactions fail after a restart.

**Button callback logic:**
1. Resolve the `players` role by name from the guild.
2. If the role doesn't exist: respond ephemerally with an error and log a warning.
3. If the member already has the role: respond ephemerally `"You're already a Player!"`.
4. Otherwise: `await member.add_roles(role)`, respond ephemerally `"✅ You are now a Player! Welcome to the game."`, log the acceptance.
5. Catch `discord.Forbidden`: respond ephemerally with a permission error and log.

### `Gateway(commands.Cog)`

**`on_ready` listener** — runs once after bot connects:

1. `bot.add_view(RulesView(bot))` — **must happen before** any message fetch so existing buttons are live.
2. Read `JBOT_RULES_CHANNEL_ID` from config. If missing/not-set: log a warning and return (do not crash).
3. Resolve the channel: `bot.get_channel(int(channel_id))`. If not found: log error and return.
4. Look up `bot_settings.rules_message_id` via `DataManager.get_bot_setting("rules_message_id")`.
5. If an ID is stored: attempt `await channel.fetch_message(id)`.
   - **Success**: message already exists, view is already registered — done.
   - **`discord.NotFound`**: message was deleted; fall through to post a new one.
6. Post new embed + `RulesView(bot)`, save the new message ID via `DataManager.set_bot_setting("rules_message_id", str(message.id))`.

---

## Embed Content

```
Title:  📋 Welcome to jbot!
Color:  discord.Color.blurple()

Field: Daily Routine
  A new trivia question is posted every morning. A hint drops later in
  the day and the answer is revealed in the evening. Check the schedule
  with /game status.

Field: How to Play
  • Use /answer <your guess> to submit. Multiple tries are allowed.
  • Guess before the hint for a bonus. First-try and fastest-answer
    bonuses also apply.
  • Track your score and streak with /game profile.

Field: Power-Ups (if fight/power track is enabled)
  • /power rest   — skip today; your streak is frozen and tomorrow's
                    score gets a multiplier.
  • /power jinx   — silence a rival until the hint.
  • /power steal  — spend streak days to claim a rival's bonuses.

Field: 🔒 Data & Privacy
  By clicking accept, you acknowledge that your guesses and game
  interactions are stored locally in this server's database to improve
  the bot's fuzzy-matching engine and game balance. This data is never
  transmitted to or shared with any third party.
```

---

## Files Modified

| File | Change |
|---|---|
| `db/schema.sql` | Add `bot_settings` table |
| `src/core/data_manager.py` | Add `get_bot_setting`, `set_bot_setting` |
| `.env.template` | Add `JBOT_RULES_CHANNEL_ID=todo` |

## Files Created

| File | Purpose |
|---|---|
| `src/cogs/gateway.py` | `RulesView` + `Gateway` cog |

---

## Edge Cases

| Scenario | Handling |
|---|---|
| `JBOT_RULES_CHANNEL_ID` not set | Log warning, skip — bot continues normally |
| Channel ID set but channel not found | Log error, skip |
| Stored message ID but message deleted | Catch `NotFound`, post fresh message, update stored ID |
| Bot lacks `manage_roles` | Catch `Forbidden` in button callback, ephemeral error to user |
| `players` role not found in guild | Ephemeral error to user, log warning |
| User clicks button again | "You're already a Player!" ephemeral, no-op |
| `on_ready` fires multiple times | `RulesView` re-registered (safe, discord.py deduplicates by `custom_id`) |

---

## Implementation Order

1. `db/schema.sql` — add `bot_settings` table, run `update_schema.py`
2. `src/core/data_manager.py` — add `get_bot_setting` / `set_bot_setting`
3. `.env.template` — add `JBOT_RULES_CHANNEL_ID`
4. `src/cogs/gateway.py` — implement `RulesView` + `Gateway` cog
5. Manual: Discord server channel permission setup
6. Manual: Set `JBOT_RULES_CHANNEL_ID` in `.env`, restart bot
