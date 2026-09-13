from __future__ import annotations

import hashlib

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services import wi048_s02
from kis_portfolio.services.wi048_s02 import WI048S02Config, run_wi048_s02


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
            source.read_bytes(),
            dataset_id=dataset_id,
            partition=partition,
            media_type=media_type,
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
    MigrationRunner(connection).apply(through="0018")
    connection.execute("""
        CREATE TABLE main.market_calendar(
            market VARCHAR, trade_date DATE, is_open BOOLEAN, open_time_local VARCHAR,
            close_time_local VARCHAR, timezone VARCHAR, source VARCHAR, note VARCHAR,
            raw_data JSON, updated_at TIMESTAMP, PRIMARY KEY(market, trade_date)
        )
    """)
    connection.execute("""
        CREATE TABLE main.instrument_master(
            symbol VARCHAR, market VARCHAR, standard_code VARCHAR, name VARCHAR,
            group_code VARCHAR, etp_code VARCHAR, idx_large_code VARCHAR,
            idx_mid_code VARCHAR, idx_small_code VARCHAR, raw_data JSON,
            updated_at TIMESTAMP, PRIMARY KEY(symbol, market)
        )
    """)
    connection.execute("""
        CREATE TABLE main.instrument_classification_overrides(
            symbol VARCHAR, market VARCHAR, exposure_type VARCHAR, exposure_region VARCHAR,
            asset_subtype VARCHAR, reason VARCHAR, updated_at TIMESTAMP,
            PRIMARY KEY(symbol, market)
        )
    """)
    connection.execute("""
        INSERT INTO main.market_calendar VALUES
        ('krx', DATE '2026-09-11', true, '09:00', '15:30', 'Asia/Seoul', 'fixture', NULL, '{}', current_timestamp)
    """)
    connection.execute("""
        INSERT INTO main.instrument_master VALUES
        ('005930','KRX','KR7005930003','삼성전자','ST',NULL,NULL,NULL,NULL,'{}',current_timestamp)
    """)
    connection.execute("""
        INSERT INTO main.instrument_classification_overrides VALUES
        ('005930','KRX','domestic','KR','equity','fixture',current_timestamp)
    """)
    return connection


def test_wi048_s02_backs_up_transitions_restores_and_replays(monkeypatch) -> None:
    connection = _connection()
    store = MemoryStore()
    monkeypatch.setattr(wi048_s02, "get_db_mode", lambda: "motherduck")
    monkeypatch.setattr(wi048_s02, "get_motherduck_database", lambda: "fixture")
    monkeypatch.setenv("KIS_RELEASE_IMAGE_DIGEST", "sha256:" + "a" * 64)
    monkeypatch.setenv("KIS_RELEASE_GIT_SHA", "b" * 40)

    result = run_wi048_s02(
        WI048S02Config(project="fixture", bucket="private"),
        connection_factory=lambda: connection,
        store_factory=lambda _bucket: store,
    )

    assert result["status"] == "succeeded"
    assert result["pre_migration"] == "0018"
    assert result["post_migration"] == "0019"
    assert result["applied_migrations"] == ["0019"]
    assert result["idempotent_replay"] is True
    assert result["source_calls"] == result["source_mutations"] == result["deletions"] == 0
    assert {item["rows"] for item in result["reference_tables"].values()} == {1}
    assert connection.execute("SELECT count(*) FROM main.market_calendar").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM control.market_calendar").fetchone()[0] == 1
    connection.close()
