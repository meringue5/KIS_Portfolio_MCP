"""Private immutable object-storage boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    uri: str
    content_hash: str
    byte_size: int
    media_type: str
    created: bool


class ObjectStorePort(Protocol):
    def put_bytes(self, payload: bytes, *, dataset_id: str, partition: str, media_type: str) -> StoredObject: ...
    def put_file(self, path: Path, *, dataset_id: str, partition: str, media_type: str) -> StoredObject: ...
    def download(self, uri: str, destination: Path, *, expected_sha256: str | None = None) -> Path: ...
