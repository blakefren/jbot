# Remote Logging & Error Visibility Proposal

## Problem Statement
Currently, bot errors and logs are only visible via the host's console or local log files. This makes it difficult to monitor the bot's health remotely or be notified of critical failures without manual intervention.

## Option 1: Discord Channel Logging (User Proposal)
The idea is to route `WARNING`, `ERROR`, and `CRITICAL` logs to a specific Discord channel via valid `discord.py` methods or Webhooks.

### Pros
*   **Convenience**: Errors appear where the team already hangs out.
*   **Zero Cost**: No external services required.
*   **Immediate Notification**: Push notifications via Discord mobile app.

### Cons
*   **Rate Limits**: Discord API has strict rate limits. An error loop could trigger a ban or lost logs.
*   **Recursion Risks**: If the logging fails (e.g., Discord is down), trying to log that failure to Discord causes a loop.
*   **Searchability**: Discord search is not optimized for log filtering.
*   **Noise**: A cascade of errors can render the channel useless.

---

## Option 2: Sentry (Long-Term Goal)
Sentry is an industry-standard error tracking tool with a generous free tier for developers.

### Pros
*   **Intelligent Grouping**: Does not spam you. 100 identical errors become 1 "issue".
*   **Context**: captures local variables, stack traces, and breadcrumbs automatically.
*   **Alerts**: Can alert via Email or **Discord Webhook** only on *new* issues.
*   **Performance**: Zero impact on bot strictness (async transport).

### Cons
*   **Setup**: Requires setting up an account and adding a dependency (`sentry-sdk`).

---

## Option 3: GitHub Issues (User Alternative)
Automatically create a GitHub Issue when a `CRITICAL` or `ERROR` log occurs.

### Pros
*   **Workflow Integration**: Errors directly enter the development backlog.
*   **Tracking**: Allows assigning, discussion, and tracking state (Open/Closed).
*   **Deduplication**: Can check if an issue already exists before creating one.

### Cons
*   **Complexity**: Implementing robust deduplication (hashing stack traces, searching existing issues) is non-trivial. Re-implementing features Sentry provides out-of-the-box.
*   **Latency**: Not a real-time alerting mechanism; you won't get a phone buzz.
*   **Auth**: Requires managing a GitHub Personal Access Token (PAT) with write access.
*   **Rate Limits**: GitHub API rate limits are strict.

### Implementation Sketch for Option 3
1.  Generate a unique hash for the error (e.g., `md5(exception_type + stack_trace_location)`).
2.  Search repo for open issues with this hash in the body/title.
3.  **If exists**: Add a comment incrementing the count.
4.  **If new**: Create a new issue with the stack trace and label `bot-error`.

---

## Option 4: Local File + Simple Web Server
Expose the log file via a tiny HTTP server on the host.

### Pros
*   Full logs available.
*   No external dependency.

### Cons
*   Requires opening ports/firewall on the host.
*   Security risk if not authenticated.
*   No push notifications.

---

## Updated Recommended Strategy (Current Plan)
Given the goal is **immediate visibility** with a **temporary** solution before a potential Sentry migration:

### **Phase 1: Discord Webhook (The "Now" Solution)**
This is the simplest implementation that solves the immediate "visibility" problem without over-engineering.

1.  **Mechanism**: Custom `logging.Handler` in Python.
2.  **Destination**: dedicated `#bot-logs` channel via **Webhook URL** (avoids bot token dependencies).
3.  **Format**:
    *   **Level**: `ERROR` and `CRITICAL` only.
    *   **Content**: Brief error message + Start of stack trace (truncated to <2000 chars).
    *   **Rate Limit**: Simple cooldown (e.g., max 1 alert per 5 minutes to prevent loop spam).

### **Why not GitHub Issues yet?**
While valuable, building a custom "GitHub Issue Deduplicator" is significant effort (~4-8 hours to get right) that is entirely thrown away when migrating to Sentry (which does exactly this). Discord Webhooks provide the *notification* immediately with minimal code (<50 lines).

### Implementation Checklist
1.  [ ] Create a Webhook in Discord Channel settings.
2.  [ ] Add `DISCORD_WEBHOOK_URL` to `.env`.
3.  [ ] Create `src/core/logging_handlers.py` with `DiscordWebhookHandler`.
4.  [ ] Attach handler in `src/logging_config.py`.
