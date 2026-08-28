from __future__ import annotations

import hashlib
from pathlib import Path
import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services.v2_recovery import (
    download_v2_backup,
    export_v2_backup,
    restore_v2_backup,
    upload_v2_backup,
)


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, payload, *, dataset_id, partition, media_type):
        digest = hashlib.sha256(payload).hexdigest()
        uri = f"gs://private/{dataset_id}/{partition}/{digest}"
        self.objects[uri] = payload
        return StoredObject(uri, digest, len(payload), media_type, True)

    def put_file(self, path, *, dataset_id, partition, media_type):
        return self.put_bytes(
            Path(path).read_bytes(), dataset_id=dataset_id, partition=partition, media_type=media_type,
        )

    def download(self, uri, destination, *, expected_sha256=None):
        payload = self.objects[uri]
        digest = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("downloaded object SHA-256 does not match manifest")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination


def test_v2_recovery_functions_round_trip_complete_allowlist(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    source.execute(
        "INSERT INTO control.pipeline_definitions VALUES "
        "('pipeline.fixture','1.0.0','approved','fixture-hash','{}',current_timestamp)"
    )
    backup = tmp_path / "backup"
    manifest = export_v2_backup(source, backup, database="fixture")
    source.close()

    store = MemoryStore()
    uploaded = upload_v2_backup(store, backup)
    downloaded = tmp_path / "downloaded"
    download_v2_backup(
        store,
        index_uri=uploaded["index_uri"],
        index_sha256=uploaded["index_sha256"],
        destination=downloaded,
    )
    target = tmp_path / "restored.duckdb"
    restored = restore_v2_backup(downloaded, target)

    assert uploaded["object_count"] == len(manifest["tables"]) + 1
    assert restored["tables"] == len(manifest["tables"])
    check = duckdb.connect(str(target), read_only=True)
    assert check.execute("SELECT definition_hash FROM control.pipeline_definitions").fetchone()[0] == "fixture-hash"
    check.close()


def test_download_rejects_tampered_index_before_restore(tmp_path: Path) -> None:
    store = MemoryStore()
    stored = store.put_bytes(b"{}", dataset_id="backup.v2-index", partition="x", media_type="application/json")
    try:
        download_v2_backup(
            store,
            index_uri=stored.uri,
            index_sha256="0" * 64,
            destination=tmp_path / "restore",
        )
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("tampered index was accepted")
