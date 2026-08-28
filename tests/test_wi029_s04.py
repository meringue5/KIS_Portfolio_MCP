from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services import wi029_s04


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, payload, *, dataset_id, partition, media_type):
        digest = hashlib.sha256(payload).hexdigest()
        uri = f"gs://private/{dataset_id}/{partition}/{digest}"
        self.objects.setdefault(uri, payload)
        return StoredObject(uri, digest, len(payload), media_type, True)

    def put_file(self, path, *, dataset_id, partition, media_type):
        return self.put_bytes(
            Path(path).read_bytes(), dataset_id=dataset_id,
            partition=partition, media_type=media_type,
        )

    def download(self, uri, destination, *, expected_sha256=None):
        payload = self.objects[uri]
        assert expected_sha256 in {None, hashlib.sha256(payload).hexdigest()}
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination


def test_wi029_s04_verifies_zero_external_path_and_private_round_trip(monkeypatch) -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    store = MemoryStore()
    monkeypatch.setattr(wi029_s04, "GCSObjectStore", lambda *_args, **_kwargs: store)
    result = wi029_s04.verify_wi029_s04(
        connection, project="fixture-project", bucket="private-bucket"
    )
    assert result["status"] == "verified"
    assert result["migration"] == "0013"
    assert result["uploaded_object_count"] == result["backup_table_count"] + 1
    assert result["downloaded_object_count"] == result["uploaded_object_count"]
    assert result["restored_table_count"] == result["backup_table_count"]
    assert result["external_rule_count"] == 0
    assert result["telegram_claim_count"] == 0
    connection.close()
