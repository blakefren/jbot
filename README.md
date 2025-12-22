# jbot
A daily bot for group trivia questions and competition.

![alt text](https://github.com/blakefren/jbot/blob/main/media/icon.png?raw=true)

## Setup

1.  Install the required Python packages:
    ```
    pip install -r requirements.txt
    ```
2.  Create a `.env` file in the root directory by copying the `.env.template` file. Fill out the required fields, such as your Discord bot token and the paths to your question datasets.
3.  Enable or disable game tracks (Fight, Power-up, Coop) in the `.env` file using the `JBOT_ENABLE_*` flags.
4.  The database will be created automatically when you run the bot for the first time.

## Running the Bot

Once the setup is complete, you can run the bot with the following command:

```
python run.py
```

## Daily format

Every day, one trivia question is messaged to the group in the morning, and the answer
in the evening. Players must submit their guess and any actions to the game bot before
the answer is revealed.

There are several settings and game modes that control scoring, player actions, and
question selection.

## Game Features

The bot's features are organized into three distinct "tracks" that can be enabled or disabled independently via the `.env` file.

### Fight Track

This track adds direct player-vs-player interactions.

*   **Jinx**: An offensive action that prevents a player from earning streak bonuses that day. If the target answers correctly, they still get base points, but the attacker is silenced until the hint is revealed.
    *   **Command**: `/power jinx <player_id>`
    *   **Cost**: No point cost, but attacker is silenced.
*   **Steal**: An offensive action that allows a player to steal some bonuses (First Try, Fastest) the target earns that day.
    *   **Command**: `/power steal <player_id>`
    *   **Cost**: Resets the attacker's answer streak to zero.
*   **Shield**: A defensive action that protects a player from the next incoming attack (Jinx or Steal).
    *   **Command**: `/power shield`
    *   **Cost**: No upfront cost, but -10 points if unused by end of day.

### Power-up Track

This track introduces mechanics that reward consistent play or provide other advantages.

*   **Answer Streaks**: Players build up a "streak" for each consecutive correct answer. This can be used for scoring bonuses or as a target for other players' attacks.
*   **Wager** (Planned): Players can wager a portion of their points on whether their answer is correct.
    *   **Command**: `/power wager <amount>`
*   **Answering First**: The first player to answer the daily question correctly receives a point bonus.
*   **Answering Before the Hint**: Players who answer correctly before the daily hint is revealed receive a point bonus.
*   **Weekly Boss Fight** (Planned): A challenging weekly question with a large point reward.

### Coop Track

This track focuses on collaborative features.

*   **Teamup** (Planned): Two players can form a temporary alliance for the day. If either player answers correctly, both receive full points.
    *   **Command**: `/power teamup <player_id>`
    *   **Cost**: 25 points for each player.
*   **Reveal Answer Letters** (Planned): Players can vote to reveal letters in the answer. Each vote costs points, and the cost increases with each revealed letter.
    *   **Command**: `/power reveal`
*   **Red vs. Blue Teams** (Planned): Players are divided into two teams (either by choice or randomly). The team with the most correct responses at the end of the day gets bonus points.

## Commands

The bot's commands are organized into groups:

*   **`/game`**: General game information.
    *   `/game status`: Check the current game status, next event time, and active question.
    *   `/game leaderboard`: View the score leaderboard.
    *   `/game profile`: View your player stats and history.
    *   `/game rules`: View the currently active rules and enabled features.
*   **`/power`**: Actions related to the Fight, Power-up, and Coop tracks.
*   **`/answer`**: Submit your answer to the daily question.

## Database

The bot uses a SQLite database (`jbot.db`) to store all persistent data, including:
*   Questions and answers
*   Player information
*   Daily guesses
*   Message logs

The database schema is defined in `db/schema.sql`. When the bot is run for the first time, it will create the database file in the root directory.

## Datasets

You'll have to download these yourself and update their paths in `.env`. Some assembly required. No guarantees on licensing, etc.

### Jeopardy!

[Download](https://github.com/jwolle1/jeopardy_clue_dataset) the Jeopardy question bank.

### Synthetic riddles (with hints)

Download [this generated riddle dataset](https://www.kaggle.com/datasets/prajwaldongre/riddles-a-synthetic-riddle-dataset-for-nlp) from Kaggle.

### Knowledge Bowl

Knowledge Bowl offers a dataset here (last accessed 2025-08-10): https://www.kbpractice.com/complete_online_list

### Random dataset

I found [this dataset on Reddit](https://www.reddit.com/r/trivia/comments/3wzpvt/free_database_of_50000_trivia_questions/) containing some questions from *Who Wants to Be a Millionaire*, *Are You Smarter Than a Fifth Grader?*, and some other random questions. Some cleanup/formatting required.

## AI Assistant

This project is being developed with the assistance of an AI programming partner named Lex. Lex's role is to help with coding, suggest improvements, and automate tasks to accelerate development. For more details on Lex's directives and operating procedures, see `.github/copilot-instructions.md`.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
