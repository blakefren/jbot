#!/usr/bin/env python3
"""Upload local data files to a Railway volume via SSH.

Railway SSH doesn't support SCP/SFTP, so this script transfers files by:
1. Creating a tar.gz archive of all data files
2. Piping it through a single ``railway ssh`` connection (base64-encoded)
3. Decoding and extracting on the remote side

If stdin piping is not supported by the Railway CLI version, the script
falls back to sending base64 chunks via individual SSH commands.

Prerequisites:
    1. Install Railway CLI: scoop install railway
    2. Login: railway login
    3. Link project: railway link (in the jbot directory)
    4. Ensure the service is deployed and running

Usage:
    python scripts/railway_upload.py                # Upload datasets + database
    python scripts/railway_upload.py --db-only      # Upload database only
    python scripts/railway_upload.py --datasets-only # Upload datasets only
    python scripts/railway_upload.py --chunked       # Force chunked upload mode
"""

import argparse
import base64
import io
import os
import subprocess
import sys
import tarfile

VOLUME_MOUNT = "/data"
REMOTE_TMP = "/tmp/jbot_upload.tar.gz"
# 512KB of base64 text per SSH command for chunked fallback
CHUNK_SIZE = 512 * 1024

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
    """Verify Railway CLI is installed, logged in, linked, and SSH reachable."""
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

    # Check SSH connectivity
    print("  Testing SSH connection...")
    result = run_ssh("echo SSH_OK", check=False)
    if result.returncode != 0 or "SSH_OK" not in result.stdout:
        stderr = result.stderr.strip() if result.stderr else ""
        print("ERROR: Cannot SSH into the service.")
        print("  The service may be crash-looping or not yet deployed.")
        if stderr:
            print(f"  stderr: {stderr}")
        print("\n  Tips:")
        print("  - Check service logs: railway logs")
        print("  - Ensure the service has at least one successful deploy")
        sys.exit(1)
    print("  SSH connection OK")


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


def upload_archive(archive_data: bytes, force_chunked: bool = False):
    """Upload the archive to the Railway volume via SSH.

    Primary approach: pipe base64-encoded data through stdin of a single
    ``railway ssh`` connection.  If that fails (or --chunked is set),
    falls back to sending base64 text via individual SSH echo commands.
    """
    encoded = base64.b64encode(archive_data)

    print(
        f"\n  Archive size: {len(archive_data) / (1024 * 1024):.1f} MB "
        f"({len(encoded) / (1024 * 1024):.1f} MB base64)"
    )

    # Ensure target directories exist
    run_ssh(f"mkdir -p {VOLUME_MOUNT}/datasets")

    if not force_chunked:
        ok = _upload_stdin_pipe(archive_data, encoded)
        if not ok:
            print("\n  Falling back to chunked upload...")
            _upload_chunked(encoded)
    else:
        _upload_chunked(encoded)

    # Extract
    print("  Extracting on remote...")
    run_ssh(f"tar xzf {REMOTE_TMP} -C {VOLUME_MOUNT}")
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


def _upload_stdin_pipe(archive_data: bytes, encoded: bytes) -> bool:
    """Try piping base64 data through stdin of a single SSH connection.

    Returns True on success, False if piping is not supported.
    """
    print("  Uploading via stdin pipe (single connection)...")
    try:
        result = subprocess.run(
            [
                RAILWAY_BIN,
                "ssh",
                "--",
                "sh",
                "-c",
                f"base64 -d > {REMOTE_TMP}",
            ],
            input=encoded + b"\n",
            capture_output=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        print("  ERROR: stdin pipe timed out after 600s")
        return False

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        print(f"  stdin pipe returned exit {result.returncode}")
        if stderr:
            print(f"  stderr: {stderr}")
        return False

    # Verify transferred size matches
    result = run_ssh(f"wc -c < {REMOTE_TMP}", check=False)
    if result.returncode != 0:
        print("  Could not verify remote file size")
        return False

    remote_size = int(result.stdout.strip())
    if remote_size != len(archive_data):
        print(f"  Size mismatch: local={len(archive_data)}, remote={remote_size}")
        run_ssh(f"rm -f {REMOTE_TMP}", check=False)
        return False

    print(f"  Transfer verified ({remote_size:,} bytes)")
    return True


def _upload_chunked(encoded: bytes):
    """Upload by sending base64 chunks via individual SSH commands."""
    encoded_str = encoded.decode("ascii")
    total_chunks = (len(encoded_str) + CHUNK_SIZE - 1) // CHUNK_SIZE

    print(f"  Sending in {total_chunks} chunks...")

    # Clear any previous partial upload
    run_ssh(f"rm -f /tmp/jbot_upload.b64")

    for i in range(total_chunks):
        chunk = encoded_str[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        # Base64 alphabet is [A-Za-z0-9+/=], safe inside single quotes
        run_ssh(f"printf '%s' '{chunk}' >> /tmp/jbot_upload.b64")
        progress = (i + 1) / total_chunks * 100
        print(
            f"\r  Progress: {i + 1}/{total_chunks} ({progress:.0f}%)",
            end="",
            flush=True,
        )

    print()  # newline after progress

    # Decode base64 to tar.gz
    run_ssh(f"base64 -d /tmp/jbot_upload.b64 > {REMOTE_TMP}")
    run_ssh("rm -f /tmp/jbot_upload.b64")


def main():
    parser = argparse.ArgumentParser(description="Upload data files to Railway volume")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--db-only", action="store_true", help="Upload database only")
    group.add_argument(
        "--datasets-only", action="store_true", help="Upload datasets only"
    )
    parser.add_argument(
        "--chunked",
        action="store_true",
        help="Force chunked upload mode (slower but more compatible)",
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
    upload_archive(archive_data, force_chunked=args.chunked)

    print("=== Upload complete ===")
    print(f"\nEnsure these Railway env vars are set:")
    if include_db:
        print(f"  JBOT_DB_PATH={VOLUME_MOUNT}/jbot.db")
    if include_datasets:
        print(f"  JBOT_DATASETS_DIR={VOLUME_MOUNT}")


if __name__ == "__main__":
    main()
