# jbot
A daily bot for Jeopardy! questions.

It messages the group the category and answer at 8AM, and the question at 8PM.

## Setup

[Download](https://github.com/jwolle1/jeopardy_clue_dataset) the Jeopardy question bank.

Rename and fill out the template files in `/cfg/`, then test with `run_once.py`.

## TODOs

* [ ] Core functions
    * [X] File reader
    * [X] Config files
    * [X] Config file readers
    * [X] Run once test script
    * [X] Question bot
    * [X] Daily question
    * [X] log/logger.py
    * [ ] setup.py
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