#!/usr/bin/env python3
"""Upload local data files to a Railway volume via SSH.

Railway SSH doesn't support SCP/SFTP, so this script transfers files by:
1. Creating a tar.gz archive of all data files
2. Base64-encoding it and sending in chunks via `railway ssh`
3. Decoding and extracting on the remote side

Prerequisites:
    1. Install Railway CLI: scoop install railway
    2. Login: railway login
    3. Link project: railway link (in the jbot directory)
    4. Ensure the service is deployed and running

Usage:
    python scripts/railway_upload.py                # Upload datasets + database
    python scripts/railway_upload.py --db-only      # Upload database only
    python scripts/railway_upload.py --datasets-only # Upload datasets only
"""

import argparse
import base64
import io
import os
import subprocess
import sys
import tarfile

VOLUME_MOUNT = "/data"
REMOTE_TMP = "/tmp/jbot_upload.b64"
# 64KB of base64 text per SSH command — well within command-line limits
CHUNK_SIZE = 64 * 1024

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "jbot.db")
DATASETS_DIR = os.path.join(PROJECT_ROOT, "datasets")

# Railway CLI binary — resolved once at import time
RAILWAY_BIN = "railway"


def _find_railway_bin() -> str:
    """Find the railway binary, checking scoop shims if not on PATH."""
    import shutil

    path = shutil.which("railway")
    if path:
        return path

    # Scoop installs to ~/scoop/shims by default
    scoop_path = os.path.join(os.path.expanduser("~"), "scoop", "shims", "railway.exe")
    if os.path.isfile(scoop_path):
        return scoop_path

    return "railway"  # Fall through — will fail with a clear message in check_prerequisites


def run_ssh(command: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command on the Railway service via SSH."""
    result = subprocess.run(
        [RAILWAY_BIN, "ssh", "--", "bash", "-c", command],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        print(f"  ERROR: SSH command failed (exit {result.returncode})")
        print(f"  Command: {command[:120]}...")
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}")
        sys.exit(1)
    return result


def check_prerequisites():
    """Verify Railway CLI is installed, logged in, and linked."""
    global RAILWAY_BIN
    RAILWAY_BIN = _find_railway_bin()

    # Check CLI is available
    try:
        subprocess.run(
            [RAILWAY_BIN, "--version"], capture_output=True, text=True, check=True
        )
    except FileNotFoundError:
        print("ERROR: Railway CLI not found. Install it: scoop install railway")
        sys.exit(1)

    # Check login status
    result = subprocess.run([RAILWAY_BIN, "whoami"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: Not logged in. Run: railway login")
        sys.exit(1)
    print(f"  Logged in as: {result.stdout.strip()}")

    # Check project is linked
    result = subprocess.run([RAILWAY_BIN, "status"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: No project linked. Run: railway link")
        sys.exit(1)
    print(f"  Project status OK")


def collect_files(include_db: bool, include_datasets: bool) -> list[tuple[str, str]]:
    """Collect files to upload. Returns list of (local_path, archive_name) tuples."""
    files = []

    if include_db:
        if not os.path.exists(DB_PATH):
            print(f"WARNING: Database not found at {DB_PATH}, skipping.")
        else:
            size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            print(f"  Database: {DB_PATH} ({size_mb:.1f} MB)")
            files.append((DB_PATH, "jbot.db"))

    if include_datasets:
        if not os.path.isdir(DATASETS_DIR):
            print(f"WARNING: Datasets directory not found at {DATASETS_DIR}, skipping.")
        else:
            for filename in sorted(os.listdir(DATASETS_DIR)):
                filepath = os.path.join(DATASETS_DIR, filename)
                if os.path.isfile(filepath):
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    print(f"  Dataset: {filename} ({size_mb:.1f} MB)")
                    files.append((filepath, f"datasets/{filename}"))

    return files


def create_archive(files: list[tuple[str, str]]) -> bytes:
    """Create a tar.gz archive of the given files."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for local_path, archive_name in files:
            tar.add(local_path, arcname=archive_name)
    return buf.getvalue()


def upload_archive(archive_data: bytes):
    """Upload the archive to the Railway volume via SSH."""
    encoded = base64.b64encode(archive_data).decode("ascii")
    total_chunks = (len(encoded) + CHUNK_SIZE - 1) // CHUNK_SIZE

    print(
        f"\n  Archive size: {len(archive_data) / (1024 * 1024):.1f} MB "
        f"({len(encoded) / (1024 * 1024):.1f} MB base64)"
    )
    print(f"  Sending in {total_chunks} chunks...")

    # Clear any previous upload
    run_ssh(f"rm -f {REMOTE_TMP}")

    for i in range(total_chunks):
        chunk = encoded[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        # Single-quote the chunk — base64 is [A-Za-z0-9+/=\n], safe in single quotes
        run_ssh(f"echo '{chunk}' >> {REMOTE_TMP}")
        progress = (i + 1) / total_chunks * 100
        print(
            f"\r  Progress: {i + 1}/{total_chunks} ({progress:.0f}%)",
            end="",
            flush=True,
        )

    print()  # newline after progress

    # Decode and extract
    print("  Extracting on remote...")
    run_ssh(f"mkdir -p {VOLUME_MOUNT}/datasets")
    run_ssh(f"base64 -d {REMOTE_TMP} | tar xzf - -C {VOLUME_MOUNT}")
    run_ssh(f"rm -f {REMOTE_TMP}")

    # Verify
    print("\n  Remote volume contents:")
    result = run_ssh(f"ls -la {VOLUME_MOUNT}/")
    print(result.stdout)
    result = run_ssh(
        f"ls -la {VOLUME_MOUNT}/datasets/ 2>/dev/null || echo '  (no datasets)'",
        check=False,
    )
    print(result.stdout)


def main():
    parser = argparse.ArgumentParser(description="Upload data files to Railway volume")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--db-only", action="store_true", help="Upload database only")
    group.add_argument(
        "--datasets-only", action="store_true", help="Upload datasets only"
    )
    args = parser.parse_args()

    include_db = not args.datasets_only
    include_datasets = not args.db_only

    print("=== Railway Data Upload ===\n")

    print("Checking prerequisites...")
    check_prerequisites()

    print("\nCollecting files...")
    files = collect_files(include_db, include_datasets)
    if not files:
        print("No files to upload.")
        sys.exit(0)

    print(f"\nCreating archive ({len(files)} files)...")
    archive_data = create_archive(files)

    print("Uploading to Railway volume...")
    upload_archive(archive_data)

    print("=== Upload complete ===")
    print(f"\nEnsure these Railway env vars are set:")
    if include_db:
        print(f"  JBOT_DB_PATH={VOLUME_MOUNT}/jbot.db")
    if include_datasets:
        print(f"  JBOT_DATASETS_DIR={VOLUME_MOUNT}")


if __name__ == "__main__":
    main()
