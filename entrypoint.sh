#!/bin/bash
set -e

# Ensure the data directory exists
mkdir -p $(dirname "$JBOT_DB_PATH")

# 1. Try to restore from the Cloud first
echo "Checking for remote database backup..."
echo "BOOTSTRAP MODE: skipping restore, seeding from local file..."
if [ -f "/app/db/jbot.db" ]; then
    echo "Seeding from local jbot.db..."
    cp /app/db/jbot.db "$JBOT_DB_PATH"
fi

# 3. Start replication and the bot
echo "Starting Litestream replication and Bot..."
exec litestream replicate -config /app/litestream.yml -exec "python run.py"
