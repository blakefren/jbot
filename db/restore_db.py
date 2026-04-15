#!/usr/bin/env python3
"""
Restore the production database from Litestream S3 replication.

Reads credentials from .env, deletes any existing output file, then invokes
the litestream binary to restore the latest DB snapshot.

Usage:
    python db/restore_db.py [output_path]

    output_path  — where to write the restored DB (default: ./jbot_restore.db)

Environment variables (loaded from .env):
    LITESTREAM_BUCKET            — S3 bucket name
    LITESTREAM_ENDPOINT          — S3-compatible endpoint URL
    LITESTREAM_ACCESS_KEY_ID     — S3 access key
    LITESTREAM_SECRET_ACCESS_KEY — S3 secret key

The litestream binary must be on PATH or set LITESTREAM_BIN to its full path.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from db/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

REQUIRED_VARS = [
    "LITESTREAM_BUCKET",
    "LITESTREAM_ENDPOINT",
    "LITESTREAM_ACCESS_KEY_ID",
    "LITESTREAM_SECRET_ACCESS_KEY",
]

# Remote DB path as configured in litestream.yml / Railway
REMOTE_DB_PATH = "/data/jbot.db"


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("jbot_restore.db")

    # Validate env vars
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        print(f"ERROR: missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    # Find litestream binary
    litestream_bin = os.environ.get("LITESTREAM_BIN") or shutil.which("litestream")
    if not litestream_bin:
        print(
            "ERROR: litestream binary not found. Add it to PATH or set LITESTREAM_BIN."
        )
        sys.exit(1)

    # Archive existing output file (litestream refuses to overwrite)
    if output.exists():
        backups_dir = output.parent / "db" / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        archived = backups_dir / f"{output.stem}_{timestamp}{output.suffix}"
        print(f"Archiving existing file to: {archived}")
        output.rename(archived)

    # Write a temporary config file
    config_path = PROJECT_ROOT / "litestream-restore.yml"
    config_path.write_text(
        f"access-key-id: {os.environ['LITESTREAM_ACCESS_KEY_ID']}\n"
        f"secret-access-key: {os.environ['LITESTREAM_SECRET_ACCESS_KEY']}\n"
        "\n"
        "dbs:\n"
        f"  - path: {REMOTE_DB_PATH}\n"
        "    replicas:\n"
        "      - type: s3\n"
        f"        bucket: {os.environ['LITESTREAM_BUCKET']}\n"
        "        path: jbot.db\n"
        f"        endpoint: {os.environ['LITESTREAM_ENDPOINT']}\n"
    )

    print(f"Restoring from s3://{os.environ['LITESTREAM_BUCKET']}/jbot.db ...")
    try:
        result = subprocess.run(
            [
                litestream_bin,
                "restore",
                "-config",
                str(config_path),
                "-o",
                str(output),
                REMOTE_DB_PATH,
            ],
            check=True,
        )
        print(f"Restore complete: {output.resolve()}")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: litestream restore failed (exit code {e.returncode})")
        sys.exit(e.returncode)
    finally:
        # Clean up the temp config so credentials don't linger on disk
        config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
