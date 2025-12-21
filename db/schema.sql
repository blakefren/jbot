-- database/schema.sql

-- This table stores all the trivia questions available to the bot.
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_hash TEXT UNIQUE,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    hint_text TEXT,
    category TEXT,
    value INTEGER,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- This table tracks which question was sent on which day.
CREATE TABLE IF NOT EXISTS daily_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    sent_at DATE NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions (id)
);

-- This table stores information about the players.
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY, -- Corresponds to discord_id
    name TEXT,
    score INTEGER DEFAULT 0,
    answer_streak INTEGER DEFAULT 0,
    active_shield BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- This table logs manual score adjustments for players.
CREATE TABLE IF NOT EXISTS score_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    admin_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT,
    adjusted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player_id) REFERENCES players (id),
    FOREIGN KEY (admin_id) REFERENCES players (id)
);

-- This table logs the guesses made by players.
CREATE TABLE IF NOT EXISTS guesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_question_id INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    guess_text TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    guessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_question_id) REFERENCES daily_questions (id),
    FOREIGN KEY (player_id) REFERENCES players (id)
);

-- This table logs all messages sent by the bot.
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL, -- 'incoming' or 'outgoing'
    method TEXT NOT NULL, -- 'Discord', 'SMS', etc.
    recipient_sender TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT, -- 'success', 'failed', etc.
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- This table defines the roles that can be assigned to players.
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
);

-- This table links players to their assigned roles.
CREATE TABLE IF NOT EXISTS player_roles (
    player_id TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (player_id, role_id),
    FOREIGN KEY (player_id) REFERENCES players (id),
    FOREIGN KEY (role_id) REFERENCES roles (id)
);

-- This table stores alternative correct answers for questions.
CREATE TABLE IF NOT EXISTS alternative_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    added_by TEXT NOT NULL, -- Admin ID
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES questions (id)
);

-- This table stores the subscribers for daily questions.
CREATE TABLE IF NOT EXISTS subscribers (
    id TEXT PRIMARY KEY, -- Corresponds to user_id or channel_id
    display_name TEXT NOT NULL,
    is_channel BOOLEAN NOT NULL,
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
