#!/usr/bin/env python3
"""Upload or restore a V2 Parquet backup through the private GCS object port."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from google.cloud import storage
from google.oauth2.credentials import Credentials

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore


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
    root = Path(args.backup_dir).resolve()
    source_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("manifest_version") != 2:
        raise RuntimeError("only V2 backup manifest version 2 is supported")
    store = _store(args)
    objects = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        result = store.put_file(
            path, dataset_id="backup.v2", partition=root.name,
            media_type="application/json" if path.suffix == ".json" else "application/vnd.apache.parquet",
        )
        objects.append({
            "relative_path": relative, "uri": result.uri, "sha256": result.content_hash,
            "byte_size": result.byte_size,
        })
    index = {
        "backup_manifest_version": 1, "source_backup": root.name,
        "source_manifest_version": source_manifest["manifest_version"], "objects": objects,
    }
    result = store.put_bytes(
        json.dumps(index, sort_keys=True).encode(), dataset_id="backup.v2-index",
        partition=root.name, media_type="application/json",
    )
    print(json.dumps({
        "status": "uploaded", "object_count": len(objects), "byte_size": sum(x["byte_size"] for x in objects),
        "index_uri": result.uri, "index_sha256": result.content_hash,
    }, indent=2))


def restore(args) -> None:
    store = _store(args)
    destination = Path(args.destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError("restore destination must be absent or empty")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kis-v2-index-") as temp_dir:
        index_path = store.download(args.index_uri, Path(temp_dir) / "index.json", expected_sha256=args.index_sha256)
        index = json.loads(index_path.read_text(encoding="utf-8"))
    for item in index["objects"]:
        target = (destination / item["relative_path"]).resolve()
        if destination not in target.parents:
            raise RuntimeError("backup index contains an unsafe relative path")
        store.download(item["uri"], target, expected_sha256=item["sha256"])
    print(json.dumps({
        "status": "restored", "object_count": len(index["objects"]),
        "byte_size": sum(x["byte_size"] for x in index["objects"]), "destination": str(destination),
    }, indent=2))


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
