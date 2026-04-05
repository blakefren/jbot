# jbot
A daily bot for group trivia questions and competition.

![alt text](https://github.com/blakefren/jbot/blob/main/media/icon.png?raw=true)

## Setup

1.  Ensure you are running **Python 3.14** or later.
2.  Install the required Python packages:
    ```
    pip install -r requirements.txt
    ```
2.  Create a `.env` file in the root directory by copying the `.env.template` file. Fill out the required fields, such as your Discord bot token.
3.  Configure your question sources in `sources.toml`. This file defines which datasets to use, their weights for selection, and dataset-specific settings. See the comments in `sources.toml` for examples.
4.  The database will be created automatically when you run the bot for the first time.

## Running the Bot

Once the setup is complete, you can run the bot with the following command:

```
python run.py
```

## Running with Docker (Recommended)

You can also run the bot using Docker, which simplifies dependency management.

1.  **Build and Start**:
    ```bash
    docker compose up -d
    ```
    This command will build the image and start the container in the background. It automatically loads your `.env` file and persists the `jbot.db` database.

2.  **Manage**:
    *   **Stop**: `docker compose stop`
    *   **View Logs**: `docker compose logs -f`
    *   **Rebuild**: `docker compose up -d --build` (Run this after changing code or requirements)

## Deploying to Railway

The bot can be deployed to [Railway](https://railway.app) with persistent storage for the database and datasets.

### Initial Setup

1.  **Create a Railway project** and connect your GitHub repo.
2.  **Add a Volume** to your service (Settings → Volumes), mounted at `/data`.
3.  **Set environment variables** in Railway (Variables tab). Copy all keys from `.env.template` and set:
    ```
    JBOT_DB_PATH=/data/jbot.db
    JBOT_DATASETS_DIR=/data
    ```

### Uploading Data

Datasets and the database are not in the GitHub repo, so they must be uploaded to the Railway volume separately. A migration script automates this via the Railway CLI.

1.  **Install & authenticate the CLI**:
    ```bash
    scoop install railway     # Windows (via Scoop)
    railway login
    railway link              # Run in the jbot directory, select your project/service
    ```

2.  **Upload data to the volume**:
    ```bash
    python scripts/railway_upload.py                # Upload datasets + database
    python scripts/railway_upload.py --db-only      # Database only
    python scripts/railway_upload.py --datasets-only # Datasets only
    ```

3.  **Redeploy** to pick up the new data:
    ```bash
    railway redeploy
    ```

### Ongoing Management

*   **View logs**: `railway logs`
*   **SSH into container**: `railway ssh`
*   **Re-upload database** (e.g. after local corrections): `python scripts/railway_upload.py --db-only`
*   Railway auto-deploys on push to `main`.

## Daily format

Every day, one trivia question is messaged to the group in the morning, and the answer
in the evening. Players must submit their guess and any actions to the game bot before
the answer is revealed.

There are several settings and game modes that control scoring, player actions, and
question selection.

## Game Features

### Power-ups

*   **Jinx**: Target another player to block their streak bonus for the day. The attacker is silenced until the hint is revealed.
    *   **Command**: `/power jinx <player>`
*   **Steal**: Target another player to steal their try/speed bonuses. Costs the attacker streak days.
    *   **Command**: `/power steal <player>`
*   **Rest**: Skip today's question while freezing your streak. Earn a score multiplier on your next correct answer.
    *   **Command**: `/power rest`

Power-ups can be queued overnight before the daily question is posted. Jinx and steal can also be used retroactively against players who have already answered.

### Scoring Bonuses

*   **Answer Streak**: Earn bonus points for each consecutive day answered correctly. Streaks are a resource — they feed into the streak bonus and are the cost of using `/power steal`.
*   **First Try**: Bonus points for getting the answer right on your first guess.
*   **Fastest Answer**: Bonus points for being among the first players to answer correctly.
*   **Before Hint**: Bonus points for answering correctly before the daily hint is revealed.

### Seasons

Monthly seasons reset scores and track standings independently. The top players at the end of each season earn trophies. Each season also includes a rotating monthly challenge with a bonus objective. Seasons can be enabled or disabled via the `JBOT_ENABLE_SEASONS` flag in `.env`.

## Commands

*   **`/answer`**: Submit your answer to the daily question.
*   **`/game status`**: Check the current game status, next event time, and active question.
*   **`/game leaderboard`**: View the score leaderboard (season or all-time).
*   **`/game profile`**: View your player stats and history.
*   **`/power`**: Use a power-up (jinx, steal, rest).

## Database

The bot uses a SQLite database (`jbot.db`) to store all persistent data, including:
*   Questions and answers
*   Player information
*   Daily guesses
*   Message logs

The database schema is defined in `db/schema.sql`. When the bot is run for the first time, it will create the database file in the root directory.

## Datasets

You'll have to download these yourself and update their paths in `sources.toml`. Some assembly required. No guarantees on licensing, etc.

The `sources.toml` file in the root directory controls:
- Dataset file paths (in the `[datasets]` section)
- Question sources and their selection weights (in `[[source]]` entries)
- Dataset-specific settings (like Jeopardy score substitution)
- AI-generated riddle sources via Gemini

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
