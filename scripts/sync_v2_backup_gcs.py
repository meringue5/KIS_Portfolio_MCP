#!/usr/bin/env python3
"""Upload or restore a V2 Parquet backup through the private GCS object port."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from google.cloud import storage
from google.oauth2.credentials import Credentials

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore
from kis_portfolio.services.v2_recovery import download_v2_backup, upload_v2_backup


def _store(args) -> GCSObjectStore:
    credentials = None
    if args.use_gcloud_token:
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True,
        ).stdout.strip()
        credentials = Credentials(token)
    client = storage.Client(project=args.project, credentials=credentials)
    return GCSObjectStore(args.bucket, client=client, prefix="recovery")


def upload(args) -> None:
    print(json.dumps(upload_v2_backup(_store(args), Path(args.backup_dir)), indent=2))


def restore(args) -> None:
    result = download_v2_backup(
        _store(args), index_uri=args.index_uri, index_sha256=args.index_sha256,
        destination=Path(args.destination),
    )
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--use-gcloud-token", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("upload")
    up.add_argument("backup_dir")
    down = sub.add_parser("restore")
    down.add_argument("--index-uri", required=True)
    down.add_argument("--index-sha256", required=True)
    down.add_argument("destination")
    args = parser.parse_args()
    upload(args) if args.command == "upload" else restore(args)


if __name__ == "__main__":
    main()
