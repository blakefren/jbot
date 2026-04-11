#!/usr/bin/env python3
"""
Download question dataset files from S3-compatible storage at startup.

Reuses the Litestream S3 credentials and bucket. Dataset files are expected
under a "dataset/" prefix in the bucket (at the same level as jbot.db).

Files are downloaded once and skipped if they already exist locally, so
subsequent restarts are fast. To force a re-download, delete the local files.

Environment variables (all required for sync to run):
  LITESTREAM_BUCKET           — S3 bucket name
  LITESTREAM_ENDPOINT         — S3-compatible endpoint URL
  LITESTREAM_ACCESS_KEY_ID    — S3 access key
  LITESTREAM_SECRET_ACCESS_KEY — S3 secret key
  JBOT_DATASETS_DIR           — local base directory (datasets/ subfolder used)
                                 Defaults to the project root if unset.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

S3_DATASET_PREFIX = "datasets/"


def sync_datasets() -> bool:
    """
    Download missing dataset files from S3 to the local datasets directory.

    Returns True if sync ran (or was skipped because files exist), False if
    credentials are missing (local-dev mode) or an error occurred.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.error("boto3 is not installed — cannot sync datasets from S3.")
        return False

    bucket = os.environ.get("LITESTREAM_BUCKET")
    endpoint = os.environ.get("LITESTREAM_ENDPOINT")
    access_key = os.environ.get("LITESTREAM_ACCESS_KEY_ID")
    secret_key = os.environ.get("LITESTREAM_SECRET_ACCESS_KEY")

    if not all([bucket, endpoint, access_key, secret_key]):
        logger.info(
            "S3 credentials not fully configured — skipping dataset sync "
            "(expected in local development)."
        )
        return True

    # Resolve local destination: <JBOT_DATASETS_DIR>/datasets/
    base_dir = os.environ.get(
        "JBOT_DATASETS_DIR",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    local_dir = os.path.join(base_dir, "datasets")
    os.makedirs(local_dir, exist_ok=True)

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        response = s3.list_objects_v2(Bucket=bucket, Prefix=S3_DATASET_PREFIX)
        objects = response.get("Contents", [])

        if not objects:
            logger.warning(
                "No objects found at s3://%s/%s — datasets will not be available.",
                bucket,
                S3_DATASET_PREFIX,
            )
            return True

        downloaded = 0
        skipped = 0
        for obj in objects:
            key = obj["Key"]
            filename = os.path.basename(key)
            if not filename:
                # Skip directory-like entries (keys ending with /)
                continue

            local_path = os.path.join(local_dir, filename)
            if os.path.exists(local_path):
                logger.debug("Dataset already exists, skipping: %s", filename)
                skipped += 1
                continue

            logger.info("Downloading dataset: %s → %s", key, local_path)
            s3.download_file(bucket, key, local_path)
            downloaded += 1

        logger.info(
            "Dataset sync complete. Downloaded: %d, Skipped (already present): %d",
            downloaded,
            skipped,
        )
        return True

    except (BotoCoreError, ClientError) as exc:
        logger.error("Failed to sync datasets from S3: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    success = sync_datasets()
    sys.exit(0 if success else 1)
