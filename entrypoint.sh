#!/bin/bash
set -e

# Ensure the data directory exists
mkdir -p $(dirname "$JBOT_DB_PATH")

# 1. Try to restore from the Cloud first
echo "Checking for remote database backup..."
if litestream restore -if-db-not-exists -config /app/litestream.yml "$JBOT_DB_PATH"; then
    echo "Restore successful or database already exists."
else
    echo "No remote backup found. Looking for local seed..."
    # 2. If no cloud backup exists, look for a seed file
    if [ -f "/app/db/jbot.db" ]; then
        echo "Seeding cloud with local jbot.db..."
        cp /app/db/jbot.db "$JBOT_DB_PATH"
    fi
fi

# 3. Sync question datasets from S3 (skips files that already exist locally)
echo "Syncing datasets from S3..."
if python /app/scripts/sync_datasets.py; then
    echo "Dataset sync complete."
else
    echo "Dataset sync failed — bot may be missing question files." >&2
    exit 1
fi

# 4. Start replication and the bot
echo "Starting Litestream replication and Bot..."
exec litestream replicate -config /app/litestream.yml -exec "python run.py"
