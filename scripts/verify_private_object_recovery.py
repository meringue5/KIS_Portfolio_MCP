#!/usr/bin/env python3
"""Hash-verify private raw objects referenced by a restored local V2 database."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import duckdb
from google.cloud import storage
from google.oauth2.credentials import Credentials

from kis_portfolio.platform.production_guardrails import GuardrailValidationError
from kis_portfolio.platform.steady_state_operations import verify_private_object_records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("--project", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--use-gcloud-token", action="store_true")
    args = parser.parse_args(argv)
    try:
        credentials = None
        if args.use_gcloud_token:
            token = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            credentials = Credentials(token)
        client = storage.Client(project=args.project, credentials=credentials)
        bucket = client.bucket(args.bucket)
        connection = duckdb.connect(args.database, read_only=True)
        try:
            rows = connection.execute(
                "SELECT content_hash, private_uri, byte_size FROM bronze.raw_object_manifest "
                "ORDER BY content_hash"
            ).fetchall()
        finally:
            connection.close()
        records = [
            {"content_hash": row[0], "private_uri": row[1], "byte_size": row[2]}
            for row in rows
        ]
        prefix = f"gs://{args.bucket}/"

        def load_bytes(uri: str) -> bytes:
            if not uri.startswith(prefix):
                raise GuardrailValidationError(("private object belongs to an unexpected bucket",))
            return bucket.blob(uri[len(prefix):]).download_as_bytes()

        result = verify_private_object_records(records, load_bytes)
    except (GuardrailValidationError, duckdb.Error, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "errors": getattr(exc, "errors", [str(exc)])}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
