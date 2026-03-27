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
CREATE TABLE IF NOT EXISTS "players" (
    id TEXT PRIMARY KEY, -- Corresponds to discord_id
    name TEXT,
    score INTEGER DEFAULT 0, -- Lifetime total score (unchanged for safety)
    season_score INTEGER DEFAULT 0, -- Current season score (reset monthly)
    answer_streak INTEGER DEFAULT 0, -- Current season streak (reset monthly)
    pending_rest_multiplier REAL DEFAULT 0.0,
    -- Lifetime statistics
    lifetime_questions INTEGER DEFAULT 0,
    lifetime_correct INTEGER DEFAULT 0,
    lifetime_first_answers INTEGER DEFAULT 0,
    lifetime_best_streak INTEGER DEFAULT 0,
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

-- This table tracks when a powerup was actually consumed.
CREATE TABLE IF NOT EXISTS powerup_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    powerup_type TEXT NOT NULL,
    target_user_id TEXT,
    question_id INTEGER,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES players (id),
    FOREIGN KEY (target_user_id) REFERENCES players (id),
    FOREIGN KEY (question_id) REFERENCES daily_questions (id)
);

-- This table stores a snapshot of player state at the start of each daily question.
CREATE TABLE IF NOT EXISTS daily_player_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    daily_question_id INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    answer_streak INTEGER NOT NULL,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (daily_question_id) REFERENCES daily_questions (id),
    FOREIGN KEY (player_id) REFERENCES players (id),
    UNIQUE(daily_question_id, player_id)
);

-- SEASONS FEATURE TABLES

-- This table stores season information for monthly competitions.
CREATE TABLE IF NOT EXISTS seasons (
    season_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_name TEXT NOT NULL, -- e.g., "January 2026"
    start_date TEXT NOT NULL, -- ISO8601: "2026-01-01"
    end_date TEXT NOT NULL, -- ISO8601: "2026-01-31"
    is_active INTEGER NOT NULL DEFAULT 0 -- 1 = current season, 0 = past
);

-- This table stores player performance within each season.
CREATE TABLE IF NOT EXISTS season_scores (
    player_id TEXT NOT NULL,
    season_id INTEGER NOT NULL,
    points INTEGER DEFAULT 0,
    questions_answered INTEGER DEFAULT 0,
    correct_answers INTEGER DEFAULT 0,
    first_answers INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    -- Power-up specific stats
    shields_used INTEGER DEFAULT 0,
    double_points_used INTEGER DEFAULT 0,
    -- Challenge progress
    challenge_progress TEXT DEFAULT '{}', -- JSON blob
    -- Placement
    final_rank INTEGER, -- Set when season ends
    trophy TEXT, -- "gold", "silver", "bronze", null
    PRIMARY KEY (player_id, season_id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

-- This table stores monthly challenges for each season.
CREATE TABLE IF NOT EXISTS season_challenges (
    challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    challenge_name TEXT NOT NULL, -- "Speed Demon"
    description TEXT NOT NULL, -- "Answer 10 questions before hint"
    badge_emoji TEXT, -- "⚡"
    completion_criteria TEXT NOT NULL, -- JSON: {"before_hint": 10}
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);
