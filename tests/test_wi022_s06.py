from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.object_store import StoredObject
from kis_portfolio.services.position_reconstruction_runtime import (
    build_reconstruction_execution_plan,
)
from kis_portfolio.services.wi022_s06 import WI022S06Config, WI022S06PhaseError, run_wi022_s06
from kis_portfolio.services import wi022_s06


START = datetime(2023, 8, 28, tzinfo=UTC)
CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, payload: bytes, *, dataset_id: str, partition: str, media_type: str) -> StoredObject:
        digest = hashlib.sha256(payload).hexdigest()
        uri = f"memory://{dataset_id}/{partition}/{digest}"
        created = uri not in self.objects
        self.objects[uri] = payload
        return StoredObject(uri, digest, len(payload), media_type, created)

    def put_file(self, path: Path, *, dataset_id: str, partition: str, media_type: str) -> StoredObject:
        return self.put_bytes(
            path.read_bytes(),
            dataset_id=dataset_id,
            partition=partition,
            media_type=media_type,
        )

    def download(self, uri: str, destination: Path, *, expected_sha256: str | None = None) -> Path:
        payload = self.objects[uri]
        digest = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("hash mismatch")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination


def _connection(path: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(path))
    MigrationRunner(connection).apply()
    connection.execute(
        """
        INSERT INTO silver.position_snapshots(
            account_id,instrument_id,as_of,quantity,average_cost,cost_currency,
            source_observation_id,quality_status
        ) VALUES ('account-1','instrument-1',?,3,100,'KRW','position-observation','pass')
        """,
        [CUTOFF - timedelta(hours=2)],
    )
    for event_id, side, quantity, day in (
        ("buy-1", "buy", 5, 1),
        ("sell-1", "sell", 2, 2),
    ):
        connection.execute(
            """
            INSERT INTO silver.trade_event_revisions(
                trade_event_revision_id,source_trade_event_id,account_id,market,product_code,
                instrument_id,broker_order_id,executed_at,execution_sequence,revision,side,
                quantity,price,currency,knowledge_at,source_observation_id,correction_reason,
                quality_status,metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?)
            """,
            [event_id, f"source-{event_id}", "account-1", "KRX", "01", "instrument-1",
             f"order-{event_id}", START + timedelta(days=day), "1", side, quantity, 100,
             "KRW", CUTOFF - timedelta(hours=1), f"observation-{event_id}", "fixture",
             "pass", "{}"],
        )
    return connection


def _config(connection: duckdb.DuckDBPyConnection, *, execution_hash: str | None = None) -> WI022S06Config:
    plan = build_reconstruction_execution_plan(connection, start_at=START, cutoff_at=CUTOFF)
    return WI022S06Config(
        start_at=START,
        cutoff_at=CUTOFF,
        expected_execution_hash=execution_hash or plan.execution_hash,
        project="fixture-project",
        bucket="fixture-private-bucket",
        expected_partitions=1,
        expected_held_partitions=1,
        expected_trade_history_partitions=1,
        expected_trade_only_partitions=0,
        expected_position_rows=1,
        expected_trade_rows=2,
        expected_coverage_rows=0,
        expected_eligible_partitions=0,
        expected_exception_partitions=1,
    )


def _release_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wi022_s06, "get_db_mode", lambda: "motherduck")
    monkeypatch.setattr(wi022_s06, "get_motherduck_database", lambda: "fixture")
    monkeypatch.setenv("KIS_RELEASE_IMAGE_DIGEST", "sha256:" + "a" * 64)
    monkeypatch.setenv("KIS_RELEASE_GIT_SHA", "b" * 40)


def test_wi022_s06_applies_only_exception_then_proves_idempotency_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _connection(tmp_path / "source.duckdb")
    config = _config(connection)
    store = MemoryStore()
    _release_environment(monkeypatch)

    result = run_wi022_s06(
        config,
        connection_factory=lambda: connection,
        store_factory=lambda _bucket: store,
    )

    assert result["status"] == "succeeded"
    assert result["source_calls"] == 0
    assert result["first_apply"]["exception_identities_inserted"] == 1
    assert result["first_apply"]["exception_revisions_inserted"] == 1
    assert sum(result["idempotent_replay"].values()) == 0
    assert result["reconciliation"]["current_open_exceptions"] == 1
    assert result["reconciliation"]["current_episode_identities"] == 0
    assert result["table_row_deltas"]["control.reconstruction_exceptions"] == 1
    assert result["table_row_deltas"]["control.reconstruction_exception_revisions"] == 1
    assert result["evidence_uri"].startswith("memory://backup.wi022-s06-evidence/")
    connection.close()


def test_wi022_s06_hash_drift_stops_before_backup_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _connection(tmp_path / "source.duckdb")
    config = _config(connection, execution_hash="0" * 64)
    store = MemoryStore()
    _release_environment(monkeypatch)

    with pytest.raises(WI022S06PhaseError) as captured:
        run_wi022_s06(
            config,
            connection_factory=lambda: connection,
            store_factory=lambda _bucket: store,
        )

    assert captured.value.phase == "plan_gate"
    assert captured.value.cause_type == "RuntimeError"
    assert not store.objects
    assert connection.execute("SELECT count(*) FROM control.reconstruction_exceptions").fetchone()[0] == 0
    connection.close()
