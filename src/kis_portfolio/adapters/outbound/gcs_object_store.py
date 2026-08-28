"""Content-addressed private GCS implementation of ObjectStorePort."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage

from kis_portfolio.ports.object_store import StoredObject


SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._=-]+$")


class GCSObjectStore:
    def __init__(self, bucket: str, *, client: storage.Client | None = None, prefix: str = "objects") -> None:
        self.bucket_name = bucket
        self.client = client or storage.Client()
        self.bucket = self.client.bucket(bucket)
        self.prefix = prefix.strip("/")

    @staticmethod
    def _segment(value: str) -> str:
        if not value or not SAFE_SEGMENT.fullmatch(value):
            raise ValueError("object path segment contains unsupported characters")
        return value

    def _object_name(self, digest: str, dataset_id: str, partition: str) -> str:
        dataset = self._segment(dataset_id)
        partition = self._segment(partition)
        return f"{self.prefix}/{dataset}/{partition}/sha256/{digest[:2]}/{digest}"

    def put_bytes(self, payload: bytes, *, dataset_id: str, partition: str, media_type: str) -> StoredObject:
        digest = hashlib.sha256(payload).hexdigest()
        name = self._object_name(digest, dataset_id, partition)
        blob = self.bucket.blob(name)
        created = True
        try:
            blob.upload_from_string(payload, content_type=media_type, if_generation_match=0)
        except PreconditionFailed:
            created = False
        return StoredObject(f"gs://{self.bucket_name}/{name}", digest, len(payload), media_type, created)

    def put_file(self, path: Path, *, dataset_id: str, partition: str, media_type: str) -> StoredObject:
        payload = path.read_bytes()
        return self.put_bytes(payload, dataset_id=dataset_id, partition=partition, media_type=media_type)

    def download(self, uri: str, destination: Path, *, expected_sha256: str | None = None) -> Path:
        prefix = f"gs://{self.bucket_name}/"
        if not uri.startswith(prefix):
            raise ValueError("object URI does not belong to the configured bucket")
        blob = self.bucket.blob(uri[len(prefix):])
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(destination))
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            destination.unlink(missing_ok=True)
            raise ValueError("downloaded object SHA-256 does not match manifest")
        return destination
