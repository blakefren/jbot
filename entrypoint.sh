#!/bin/bash
set -e

# Ensure the data directory exists
mkdir -p $(dirname "$JBOT_DB_PATH")

LITESTREAM_CONFIG=/app/litestream.yml
REPLICA_CHECK_ATTEMPTS=3
REPLICA_CHECK_DELAY=30

# An existing local database is never touched, so S3 is not needed to restart.
if [ -f "$JBOT_DB_PATH" ]; then
    echo "Local database found at $JBOT_DB_PATH."
elif [ "${JBOT_ALLOW_EMPTY_START:-0}" = "1" ]; then
    echo "WARNING: JBOT_ALLOW_EMPTY_START=1 set; skipping the replica check." >&2
    echo "Litestream will replicate this new empty database over any remote history." >&2
else
    # No local database: only start empty when the replica is confirmed to have no history.
    # Litestream exits non-zero when S3 is unreachable, so an outage cannot look like a fresh start.
    ltx_output=$(mktemp)
    attempt=1
    until litestream ltx -level all -config "$LITESTREAM_CONFIG" "$JBOT_DB_PATH" > "$ltx_output" 2>&1; do
        if [ "$attempt" -ge "$REPLICA_CHECK_ATTEMPTS" ]; then
            cat "$ltx_output" >&2
            echo "Could not reach the Litestream replica after $REPLICA_CHECK_ATTEMPTS attempts; refusing to start with an empty database." >&2
            echo "Set JBOT_ALLOW_EMPTY_START=1 only if you intend to replace the remote history." >&2
            exit 1
        fi
        echo "Replica check failed (attempt $attempt/$REPLICA_CHECK_ATTEMPTS); retrying in ${REPLICA_CHECK_DELAY}s..." >&2
        sleep "$REPLICA_CHECK_DELAY"
        attempt=$((attempt + 1))
    done

    # The first line of ltx output is the header; any further line is a backup file.
    history_files=$(tail -n +2 "$ltx_output" | grep -c . || true)
    rm -f "$ltx_output"

    if [ "$history_files" -gt 0 ]; then
        echo "Remote history found; restoring..."
        litestream restore -if-db-not-exists -config "$LITESTREAM_CONFIG" "$JBOT_DB_PATH"
    else
        echo "No remote history; the bot will start a new empty database."
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
