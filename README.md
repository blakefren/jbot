# jbot
A daily bot for trivia questions.

## Setup

[Download](https://github.com/jwolle1/jeopardy_clue_dataset) the Jeopardy question bank.

Rename and fill out the template files in `/cfg/`, then test with `run_once.py`.

## Daily format

Every day, one trivia question is messaged to the group in the morning, and the answer
in the evening. Players must submit their guess and any actions to the game bot before
the answer is revealed.

There are several settings and game modes that control scoring, player actions, and
question selection.

## Game modes

In any mode, the daily question format is the sane, but the game logic
and interaction may vary.

SIMPLE = basic game mode with simple question-answer interaction.
    Players answer the daily question, get 1 point for a correct answer,
    and 0 for incorrect.

SQUID_GAME = themed game mode with a specific set of rules.
    Adds more complex scoring and broad power up mechanics to the simple
    mode.

DARK_SOULS = a more complex game mode with additional challenges.
    Adds soulslike scoring, limited powers, and boss fights to the simple
    mode.

JEOPARDY = the classic Jeopardy! game mode with categories and clue values.
    Similar to the Jeopardy! calendar game, with a weekly format where
    difficulty increases daily, culminating in a challenging final
    Jeopardy! question.

## TODOs

* [ ] Core functions
    * [X] File reader
    * [X] Config files
    * [X] Config file readers
    * [X] Run once test script
    * [X] Question bot
    * [X] Daily question
    * [X] log/logger.py
    * [ ] main.py
    * [ ] Add code review requirements
* [ ] Interaction
    * [ ] Score tracking
    * [ ] Answering
* [ ] Modes
    * [ ] Simplified
    * [ ] Squid Game
    * [ ] Dark Souls
    * [ ] Solo/study
* [ ] Reminders
* [ ] Messaging
    * [ ] SMS API
    * [ ] SMS platform integration
    * [X] Discord bot setup
    * [X] Discord API
* [ ] Bugs
    * [ ] Fix shutdown errors
* [ ] Setup
    * [ ] Auto-generate config files on first run