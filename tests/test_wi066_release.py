from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services import wi066_release
from kis_portfolio.services.wi066_release import WI066ReleaseConfig, run_wi066_release


NOW = datetime(2026, 10, 7, tzinfo=UTC)


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, payload, *, dataset_id, partition, media_type):
        digest = hashlib.sha256(payload).hexdigest()
        uri = f"gs://private/{dataset_id}/{partition}/{digest}"
        self.objects[uri] = bytes(payload)
        return StoredObject(uri, digest, len(payload), media_type, True)

    def put_file(self, source, *, dataset_id, partition, media_type):
        return self.put_bytes(
            source.read_bytes(), dataset_id=dataset_id, partition=partition, media_type=media_type,
        )

    def download(self, uri, destination, *, expected_sha256=None):
        payload = self.objects[uri]
        digest = hashlib.sha256(payload).hexdigest()
        assert expected_sha256 in (None, digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply(through="0019")
    connection.execute(
        "INSERT INTO silver.accounts VALUES ('acct','alpha','brokerage','KRW',?,NULL,'{}')",
        [NOW],
    )
    connection.executemany(
        """
        INSERT INTO gold.portfolio_daily_state(
            evaluation_date,evaluation_slot,account_id,instrument_id,aggregate_level,
            value_krw,as_of,input_watermarks,quality_status,lineage_hash
        ) VALUES (?,?,?,?,?,100,?,'{}',?,?)
        """,
        [
            ("2026-06-20", "v1-latest", "acct", "cash|KRW", "cash", NOW, "passed", "legacy"),
            ("2026-10-07", "kr-1600", "acct", "cash|KRW", "cash", NOW, "pass", "current"),
        ],
    )
    return connection


def test_wi066_release_backs_up_quarantines_restores_and_replays(monkeypatch) -> None:
    connection = _connection()
    store = MemoryStore()
    monkeypatch.setattr(wi066_release, "get_db_mode", lambda: "motherduck")
    monkeypatch.setattr(wi066_release, "get_motherduck_database", lambda: "fixture")
    monkeypatch.setenv("KIS_RELEASE_IMAGE_DIGEST", "sha256:" + "a" * 64)
    monkeypatch.setenv("KIS_RELEASE_GIT_SHA", "b" * 40)

    first = run_wi066_release(
        WI066ReleaseConfig(project="fixture", bucket="private"),
        connection_factory=lambda: connection,
        store_factory=lambda _bucket: store,
    )
    second = run_wi066_release(
        WI066ReleaseConfig(project="fixture", bucket="private"),
        connection_factory=lambda: connection,
        store_factory=lambda _bucket: store,
    )

    assert first["status"] == "succeeded"
    assert first["pre_migration"] == "0019"
    assert first["post_migration"] == "0020"
    assert first["applied_migrations"] == ["0020"]
    assert second["pre_migration"] == second["post_migration"] == "0020"
    assert second["applied_migrations"] == []
    assert first["state_before"] == first["state_after"]
    assert first["summary_evidence"] == {
        "legacy_groups": 1,
        "legacy_quarantined_groups": 1,
        "native_groups": 1,
        "native_valid_groups": 1,
    }
    assert first["source_calls"] == first["data_rows_mutated"] == first["deletions"] == 0
    assert first["view_replaced"] is True
    assert first["pre_backup"]["object_count"] > 0
    assert first["post_backup"]["object_count"] > 0
    assert connection.execute("SELECT max(version) FROM control.schema_migrations").fetchone()[0] == "0020"
    assert connection.execute(
        "SELECT total_value_krw,quality_status FROM gold.portfolio_daily_summary "
        "WHERE evaluation_slot='v1-latest'"
    ).fetchone() == (None, "legacy_unassessed")
    connection.close()
