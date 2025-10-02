# jbot
A daily bot for group trivia questions and competition.

![alt text](https://github.com/blakefren/jbot/blob/main/media/icon.png?raw=true)

## Setup

Fill out `/cfg/main.cfg` for the features you want to use.

## Daily format

Every day, one trivia question is messaged to the group in the morning, and the answer
in the evening. Players must submit their guess and any actions to the game bot before
the answer is revealed.

There are several settings and game modes that control scoring, player actions, and
question selection.

## Game modes

In any mode, the daily question format is the same, but the game logic
and interaction may vary.

SIMPLE = basic game mode with simple question-answer interaction.
    Players answer the daily question, get 1 point for a correct answer,
    and 0 for incorrect.

POKER = basic game mode, with betting.
    Adds point betting to the simple mode.

POWERUP = cutthroat game mode with power-up actions and more complex scoring.
    - Players can use special commands:
        - `/attack <player_id>`: Reset another player's answer streak (blocked if they have a shield).
        - `/shield`: Activate a shield to block the next attack.
        - `/bet <amount>`: Bet points for the current question. Winnings use diminishing returns: winnings = bet × (100 / (score + 100)), rounded down.
    - Shields and answer streaks are tracked per player.
    - Betting is capped at 25% of your current score (minimum 1 point).
    - These actions are only available in POWERUP mode.

VEGAS = combo of POKER and POWERUP.

SOULSLIKE = a more complex game mode with additional challenges.
    Adds soulslike scoring, limited powers, and boss fights to the simple
    mode.

JEOPARDY = the classic Jeopardy! game mode with categories and clue values.
    Similar to the Jeopardy! calendar game, with a weekly format where
    difficulty increases daily, culminating in a challenging final
    Jeopardy! question.

## Datasets

You'll have to download these yourself and update their paths in `/cfg/`. Some assembly required. No guarantees on licensing, etc.

### Jeopardy!

[Download](https://github.com/jwolle1/jeopardy_clue_dataset) the Jeopardy question bank.

### Synthetic riddles (with hints)

Download [this generated riddle dataset](https://www.kaggle.com/datasets/prajwaldongre/riddles-a-synthetic-riddle-dataset-for-nlp) from Kaggle.

### Knowledge Bowl

Knowledge Bowl offers a dataset here (last accessed 2025-08-10): https://www.kbpractice.com/complete_online_list

### Random dataset

I found [this dataset on Reddit](https://www.reddit.com/r/trivia/comments/3wzpvt/free_database_of_50000_trivia_questions/) containing some questions from *Who Wants to Be a Millionaire*, *Are You Smarter Than a Fifth Grader?*, and some other random questions. Some cleanup/formatting required.

## AI Assistant

This project is being developed with the assistance of an AI programming partner named Sage. Sage's role is to help with coding, suggest improvements, and automate tasks to accelerate development. For more details on Sage's directives and operating procedures, see `.github/instructions/instructions.md`.

## TODOs

* [ ] Core functions
    * [X] File reader
    * [X] Config files
    * [X] Config file readers
    * [X] Run once test script
    * [X] Question bot
    * [X] Daily question
    * [X] log/logger.py
    * [X] main.py
    * [X] Unit tests
    * [X] Add presubmits
    * [ ] Track player metrics (e.g. streaks)
* [X] Interaction
    * [X] Ask for random question
    * [X] Subscribe
    * [X] Time to next event
    * [X] Answering
    * [X] Play reminders
    * [X] Reboot bot from message
    * [X] Score tracking
    * [X] Persistent subscriptions
* [ ] Modes
    * [ ] Simple
    * [ ] Poker
    * [ ] Powerup
    * [ ] Vegas
    * [ ] Soulslike
    * [ ] Jeopardy
* [ ] Questions
    * [X] Jeopardy!
    * [ ] Pop Culture Jeopardy!
    * [ ] Riddles
    * [ ] Test dataset
* [ ] Messaging
    * [X] Discord bot setup
    * [X] Discord API
    * [ ] SMS API
    * [ ] SMS platform integration
* [ ] Bugs
    * [ ] Fix Discord bot shutdown errors
    * [ ] History / scores / metrics still seem off
* [ ] v2
    * [ ] setup.py
    * [ ] Add flavor text by game mode