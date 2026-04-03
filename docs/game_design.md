# jbot — Game Design Document

## Purpose

jbot is a daily group trivia game for a small, recurring community of players — a mashup of Wordle, Jeopardy!, and Squid Game. A question is posted each morning; players have until the evening to answer. The answer is revealed at the end of the day, alongside scores and a leaderboard.

The game is designed to reward **consistency over any single brilliant performance**. A player who answers correctly every day — even slowly, even after the hint — will outperform an irregular player who occasionally nails it first-try and fast. Streaks are the primary mechanism for this: they accumulate value over time and make every player's daily participation feel meaningful.

Power-ups layer a competitive, strategic dimension on top of that baseline. They give skilled or daring players ways to extend their advantage — or close the gap on leaders — while never being so powerful that they override the core streak economy.

---

## Design Principles

### 1. Trivia is the core

Every other mechanic exists to make the trivia more engaging, not to replace it. Answering the daily question correctly is how the most points are earned. Questions span a wide range — Jeopardy-style recall, general knowledge, and AI-generated riddles — so "good at trivia" is deliberately broad.

### 2. Consistency beats perfection

No single bonus is large enough to overcome a multi-week streak advantage. The highest single-question bonus a player can earn is meaningful, but not insurmountable. Players who show up every day build a durable advantage.

### 3. Every day is a fresh decision

Even with their streak on the line, players make interesting decisions each day:
- *Do I guess before the hint and risk burning tries?*
- *Do I rest today to protect my streak and bank a multiplier?*
- *Is today a good day to use my jinx or steal — or should I preload it tonight before the next question?*

These decisions create engagement beyond the question itself.

### 4. Maximize player agency

Players have as much control as possible within each day. Guesses are unlimited — the only penalty for wrong answers is a smaller try bonus. The hint is designed to get players one step away from the right answer, not just to confirm they already know it. Power-ups can target any registered player, including those who have already answered. Players can even preload power-ups overnight, locking in their strategy before the next question is revealed.

### 5. The game is social and competitive

All gameplay happens in a single public channel by design. Players see each other reaching the answer in real time. Power-up effects play out publicly. Leaderboard standings shift throughout the day. The channel is meant to generate conversation — celebration, commiseration, and trash talk are all part of the experience.

### 6. Fun for players who are bad at trivia

Speed and knowledge aren't everything. The fastest, most knowledgeable players are also the biggest targets for power-ups — their large streaks and bonuses make them attractive marks for steal and jinx. Season resets level the playing field periodically, giving less consistent or frankly weaker trivia players a fresh shot at the top. A player doesn't need to be brilliant to be competitive; they need to be consistent and strategic.

### 7. Power-ups have meaningful costs

All three power-ups require the player to give something up. Rest freezes your streak — no increment today. Jinx silences you before the hint. Steal costs streak days, which are also score. This prevents power-ups from being "obviously good" choices and keeps their usage interesting.

### 8. Attacking players take on risk

Jinx and steal can fail or produce nothing — if the target never answers, or answers with no stealable bonuses, the attacker still paid their cost. This is by design: forward attacks (used before the target has answered) are cheaper precisely *because* they carry this risk.

### 9. Transparency over secrecy for effects

When a power-up takes effect — a jinx transfers a bonus, a steal completes, a rest cancels an attack — the outcome is announced publicly. Everyone sees what happened, even if they don't know who launched the attack. This keeps the game feel fair and legible.

### 10. Retroactive corrections don't distort history

Admins can add accepted answers after the fact. When they do, all scores for that day are recalculated as if the new answer had always been valid. Players who were robbed of credit get it retroactively. No manual adjustments needed.

---

## The Daily Loop

### Morning
The question is posted to the game channel. The leaderboard is posted simultaneously. Players are @-mentioned with a morning ping.

### Guessing
Players submit guesses at any time. Each guess is private — only the guesser sees their correct/incorrect feedback. When a player answers correctly, a **public announcement** is made: the player's name, how many tries it took, and the points they earned. The standings shift in real-time throughout the day.

Players get unlimited wrong guesses, but only the first few correct-try milestones earn bonus points. Getting it right on a later attempt still earns base points — just no try bonus.

### Reminder / Hint Reveal
The hint is revealed in a reminder message. This is also a **deadline**: the before-hint window closes at this moment. Players who answer after the hint can still earn all other bonuses, but not the before-hint bonus.

### Evening / Answer Reveal
The answer is revealed. Scores are finalized. The evening leaderboard posts with **badges** showing each player's notable achievements for the day. Streaks reset for players who didn't answer. The day ends.

### Overnight
Players can use power-ups overnight to preload them for the next day's question. The target and power-up type are locked in, but effects don't apply until morning — at which point the preloaded power-up behaves identically to one placed first thing in the morning.

---

## Scoring

Scores are built from a base question value plus bonuses. Harder questions are worth more base points. Bonuses stack and reward different kinds of skill and consistency: answering on fewer tries, answering before the hint is revealed, being among the first players to answer correctly that day, and maintaining an answer streak. A skilled, consistent player can earn all of them on a good day.

The streak bonus is the dominant long-term scoring driver. It scales with the player's consecutive-day streak, up to a cap, and is earned on every correct answer once a streak is established. A streak of 0 or 1 earns no streak bonus; the bonus kicks in at 2+ consecutive days.

---

## Streaks

A streak counts consecutive days with at least one correct answer. Missing a day (without resting) resets it to 0.

Streaks play multiple roles simultaneously:

- **Scoring multiplier**: The streak bonus adds points every day.
- **Steal fuel**: Steal costs streak days. A bigger streak means more purchasing power.
- **Attack surface**: A large streak makes a player an attractive target — both for jinx (which targets their streak bonus) and steal (which costs the thief streak days, but is more valuable when the target has earned big bonuses).
- **Rest protection**: Players can freeze their streak for a day to avoid a reset.

This multi-role tension is intentional: growing a streak is good, but large streaks also invite attacks and create pressure around days a player isn't confident about.

---

## Power-Ups

Each player has **one power-up per day**. Power-ups are not rechargeable mid-day; using any one locks the player out of the others for the rest of that day.

See [powerup_mechanics.md](powerup_mechanics.md) for the full behavior specification.

### 😴 Rest

Skip today without losing your streak. Your streak is frozen — neither incremented nor reset. A score multiplier is stored and applied to your next correct answer on any future day. Today's answer is privately revealed to you.

Rest also acts as a **shield**: any pending incoming jinx or steal against you is cancelled when you rest. The attacker's costs are not refunded.

### 🤐 Jinx

Silence yourself until the hint reveal. Steal the target's streak bonus.

Jinxing costs the attacker their before-hint and fastest-answer eligibility for the day (either by being silenced if they haven't answered yet, or by having those bonuses stripped if they have). In exchange, the attacker receives a portion of the target's streak bonus — full amount if the target hasn't answered yet, a reduced fraction if they already have.

### 💰 Steal

Pay streak days to receive the target's non-streak bonuses (try bonus, before-hint, fastest-answer bonuses, rest multiplier bonus).

Steal costs more streak days when used after the target has already answered (retroactive). If the thief doesn't have enough streak days to cover the full cost, they pay all they have and receive a proportional fraction of the stolen bonuses.

### Timing Asymmetry

Both jinx and steal distinguish between **forward** (target hasn't answered) and **retroactive** (target already answered) use:

- **Forward**: Cheaper cost, but no guarantee the target answers or earns bonuses. Higher risk, higher ceiling.
- **Retroactive**: Higher cost, but the outcome is known. Lower risk, lower ceiling.

This asymmetry creates interesting timing decisions for both attackers and potential targets.

---

## Seasons

When seasons are enabled, the leaderboard defaults to **season score** — points earned since the season began. Lifetime scores are tracked separately and never reset.

### Season Lifecycle

1. A season runs for a defined period (calendar month by default).
2. At the end of a season, final standings are announced and trophies are awarded to the top finishers.
3. A new season begins. Season scores and streaks reset to 0, but lifetime stats are preserved.
4. A reminder is posted a few days before season end showing current standings.

### Trophies

Top finishers earn a permanent trophy (🥇🥈🥉) recorded on their lifetime profile. Trophies accumulate across seasons. Ties at any position are honored — two players tied for first both earn 🥇.

### Seasonal Challenge

Each season has a randomly selected **community challenge** — a goal all players share, such as maintaining a 7-day streak, answering before the hint 10 times, or being the first to answer 5 times. The challenge encourages varied play styles and gives a secondary achievement to pursue alongside score. Progress is visible on player profiles.

### What Resets vs. What Persists

| Resets at Season End | Persists |
|---|---|
| Season score | Lifetime score |
| Current streak | Best-ever streak |
| — | Lifetime correct answers |
| — | Trophies |
| — | Season challenge progress (finalized) |

---

## Leaderboard

The leaderboard is posted automatically each morning (alongside the question) and each evening (alongside the answer reveal). Players can also request it at any time via command.

The morning leaderboard shows current standings and each player's active streak. The evening leaderboard adds **badges** — per-player indicators showing what each player did that day (fastest, before-hint, streak bonus, power-ups used). Badges give the leaderboard a narrative quality and let players scan at a glance whose day was notable.

Players whose streak will reset tonight (they didn't answer today) are marked on the evening leaderboard so everyone can see who's at risk.

---

## Questions

Questions are drawn from a weighted pool of sources. Sources include pre-curated dataset files (Jeopardy archives, general trivia, quiz show databases) and AI-generated riddles. The selection is weighted random — harder sources appear less frequently than easier ones.

Questions are not repeated. Answer matching is fuzzy and case-insensitive — minor spelling variations count as correct. Admins can add additional accepted answers retroactively.

Each question has an optional hint, revealed at the reminder. If no hint is provided with the question, the bot generates one using AI. The goal of the hint is to get a player who's close one step further — not just to confirm they already know it.

---

## Player Onboarding

New players must accept the server rules before gaining access to game channels. This gate ensures players have at least seen the rules before participating.

---

## Open Design Questions

These are areas where the current design has known gaps, ambiguities, or potential future decisions. They are documented here to inform future design work — not necessarily to be resolved immediately.

- **Overnight preload cost**: Preloading a power-up overnight carries the most risk of any timing — the question isn't known, the target might not answer, and the attacker is committed. The current cost structure doesn't reflect this. The intended risk ordering from highest to lowest is: preload → forward → retroactive. A lower overnight cost (relative to forward) would make preloading feel appropriately risky-but-rewarded rather than just strictly worse than waiting.
