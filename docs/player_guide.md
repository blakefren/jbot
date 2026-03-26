# 🎮 Daily Trivia — Player Guide

Welcome! This covers everything you need to know to play, score, and compete.

---

## 📅 How It Works

A trivia question is posted every morning. Guess as early as you can — answering **early and in fewer tries** earns bonus points. The hint drops at 7 PM PT, and the answer is revealed at 8 PM PT.

```
8:00 AM PT   Question posted
7:00 PM PT   Hint posted — before-hint window closes
8:00 PM PT   Answer revealed, scores & leaderboard posted
```

---

## 💬 How to Answer

Use `/answer <your guess>`. Your reply is **private** — only you see whether you were right or wrong. A correct answer posts a public announcement in the channel.

- You can guess as many times as you want
- Matching is **case-insensitive and fuzzy** — close spelling counts
- Once you answer correctly, you're done **guessing** — but you can still use a power-up

---

## 🏆 Scoring & Bonuses

Each question has a **base value** (usually 100 pts). Bonuses stack on top:

```
Bonus              Pts      Condition
──────────────────────────────────────────────────────────
🎯 First try       +20      Correct on your first guess
   Second try      +10      Correct on your second guess
   Third try        +5      Correct on your third guess
🧠 Before hint     +10      Answered before 7 PM PT
🥇 First correct   +10      First player correct today
🥈 Second correct   +5
🥉 Third correct    +1
🔥 Streak        +5–25      +5 per streak day, capped at +25 (5+ days)
```

A perfect round — first try, before the hint, first correct, with a 5+ day streak — adds **+65** on top of the base.

---

## 🔥 Streaks

Answering correctly every day builds a streak. **Miss a day and your streak resets to 0.** Your streak adds +5 pts per day (max +25), so a 5-day streak is worth as much as a try bonus.

> Streaks are tracked separately from score — even a late, no-bonus correct answer keeps your streak alive. If you don't know the answer, `/power rest` freezes your streak instead of losing it.

---

## ⚡ Power-ups

You get **one power-up per day**. Power-ups can be used at any time **until the answer is revealed at 8 PM PT** — or overnight to preload for the next question.

---

### 😴 `/power rest`

**Skip today without losing your streak.** Your streak is frozen — it won't reset, but it won't grow either.

**Bonus:** Earn a **×1.2 multiplier** on your next correct answer (the morning after).

> Resting makes you untargetable — any jinx or steal queued for you will whiff.

---

### 🤐 `/power jinx @player`

**Cost:** You are **silenced until 7 PM** — you can't answer before the hint drops.
**Effect:** Steal your target's streak bonus when they answer correctly.

**Timing matters:**
- **Target hasn't answered yet** — full streak bonus transfers to you when they do.
- **Target already answered** — you immediately receive **50%** of their streak bonus.

> If your target has no streak, the jinx resolves with no points — but you're still silenced. Choose targets with streaks.

---

### 💰 `/power steal @player`

**Cost:** **3 streak days** deducted from your own streak.
**Effect:** Steal your target's bonuses (try + before-hint + fastest + rest multiplier) when they answer. Their base question value and streak bonus are not stolen.

**Timing matters:**
- **Target hasn't answered yet** — bonuses transfer when they answer.
- **Target already answered** — costs **5 streak days** and transfers immediately.

**Partial steals:** If you have fewer streak days than the cost, you'll steal a proportional share of their bonuses (e.g. 1 day instead of 3 = ~33% of bonuses).

---

### ⚡ Jinx vs. Steal — at a glance

```
                   Jinx                       Steal
───────────────────────────────────────────────────────────────
Your cost          Silenced until hint         3–5 streak days
What you take      Target's streak bonus       Target's try/hint/speed/rest bonuses
Retroactive?       Yes (50% of bonus)          Yes (costs more)
Overnight OK?      Yes                         Yes
Whiffs on rest?    Yes                         Yes (streak cost still applies)
```

---

## 📋 Commands

```
/answer <guess>      Submit a guess (private)
/game status         Time until next event; your score & streak
/game profile        Your personal stats and accuracy
/power rest          Skip today, freeze streak, earn ×1.2 tomorrow
/power jinx @...     Silence yourself; steal their streak bonus
/power steal @...    Pay streak days; steal their bonuses
```

---

## ❓ Questions or Issues?

Ping an **@admin** if something seems off — wrong answer not being accepted, a score looks incorrect, etc. Admins can add alternative correct answers and adjust scores retroactively.
