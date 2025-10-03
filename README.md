# jbot
A daily bot for group trivia questions and competition.

![alt text](https://github.com/blakefren/jbot/blob/main/media/icon.png?raw=true)

## Setup

1.  Install the required Python packages:
    ```
    pip install -r requirements.txt
    ```
2.  Fill out `/cfg/main.cfg` for the features you want to use.
3.  Initialize the database by running the setup script:
    ```
    python database/database.py
    ```

## Running the Bot

Once the setup is complete, you can run the bot with the following command:

```
python main.py
```

## Daily format

Every day, one trivia question is messaged to the group in the morning, and the answer
in the evening. Players must submit their guess and any actions to the game bot before
the answer is revealed.

There are several settings and game modes that control scoring, player actions, and
question selection.

## Game Features

The bot's features are organized into three distinct "tracks" that can be enabled or disabled independently, allowing for customized game experiences.

### Attacking & Defending Track

This track adds direct player-vs-player interactions.

*   **Streak Breaker**: An offensive action that allows a player to attack another. If the target answers the daily question incorrectly, their answer streak is reset to zero.
    *   **Command**: `/streak_breaker <player_id>`
    *   **Cost**: 50 points.
*   **Shield**: A defensive action that protects a player from the next incoming attack.
    *   **Command**: `/shield`
    *   **Cost**: 25 points.
*   **Steal**: An offensive action that allows a player to steal half of the points another player has earned *for that day*.
    *   **Command**: `/steal <player_id>`

### Streaks & Buffs Track

This track introduces mechanics that reward consistent play or provide other advantages.

*   **Answer Streaks**: Players build up a "streak" for each consecutive correct answer. This can be used for scoring bonuses or as a target for other players' attacks.
*   **Betting**: Players can bet a portion of their points on whether their answer is correct. Winnings are calculated based on a diminishing returns formula to keep the game balanced.
    *   **Command**: `/bet <amount>`
    *   **Details**: Bets are capped at 25% of a player's current score (minimum 1 point).

### Cooperative Play Track

This track focuses on collaborative features.

*   **Team Up**: Two players can form a temporary alliance for the day. If either player answers correctly, both receive full points.
    *   **Command**: `/team_up <player_id>`
    *   **Cost**: 25 points for each player.

## Database

The bot uses a SQLite database (`jbot.db`) to store all persistent data, including:
*   Questions and answers
*   Player information
*   Daily guesses
*   Message logs

The database schema is defined in `database/schema.sql`. When the bot is run for the first time, it will create the database file in the `database/` directory.

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

This project is being developed with the assistance of an AI programming partner named Sage. Sage's role is to help with coding, suggest improvements, and automate tasks to accelerate development. For more details on Sage's directives and operating procedures, see `.github/copilot-instructions.md`.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## v2 burndown

* [X] Database
    * [X] Design table stucture
    * [X] Migrate each use case
    * [ ] Add metrics
* [ ] Scale up
    * [ ] discord.py cogs
    * [ ] update environment vars: python-dotenv, .env file with flags, etc.
    * [ ] setup.py on first run
    * [ ] CI/CD
* [ ] Cleaner UI
    * [ ] Stop spamming answers: discord.ui.Modal
    * [ ] Don't spam commands: discord.ui.View()
    * [ ] Explore discord.Embed for message formatting
* [ ] Player interactions
    * [X] Attack: streak breaker
    * [X] Attack: steal
    * [X] Defense: shield
    * [ ] Defense: reveal letters in answer
    * [X] Betting: basic bets
    * [ ] Extra points for answering before the hint
    * [ ] Extra points for answering first
    * [ ] Betting: advanced bets
* [ ] Cooperative Play
    * [X] Team Up
* [ ] Questions
    * [ ] Pop Culture Jeopardy!
    * [ ] Test dataset

## Bugs

* [ ] Fix Discord bot shutdown errors
* [ ] History / scores / metrics still seem off

## Future ideas

* [ ] SMS messaging
* [ ] Chatbot hints, guesser, etc.
* [ ] Add more game modes (soulslike, Jeopardy!)
* [ ] Support multi-channel play
* [ ] Cloud hosting
