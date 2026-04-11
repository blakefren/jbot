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
