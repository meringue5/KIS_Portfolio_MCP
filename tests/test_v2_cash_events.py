from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from kis_portfolio.adapters.outbound.v2_warehouse import V2WarehouseRepository
from kis_portfolio.db.catalog import v2_backup_table_names
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.ports.source import SourceEnvelope


ROOT = Path(__file__).resolve().parents[1]
BASE_TIME = datetime(2026, 8, 28, 1, tzinfo=UTC)


def _record(
    repository: V2WarehouseRepository,
    *,
    source_record_id: str,
    event_type: str,
    amount: str,
    knowledge_at: datetime = BASE_TIME,
) -> str:
    envelope = SourceEnvelope(
        "source.kis-open-api",
        source_record_id,
        BASE_TIME,
        knowledge_at,
        {"source_event_code": f"KIS-{source_record_id}"},
        f"hash-{source_record_id}",
        "pass",
    )
    observation_id = repository.record_observation(
        "dataset.cash-transaction-event", envelope, "cash-fixture-run"
    )
    return repository.record_cash_flow(
        {
            "account_id": "account-1",
            "source_record_id": source_record_id,
            "source_event_code": f"KIS-{source_record_id}",
            "event_type": event_type,
            "effective_at": BASE_TIME,
            "settled_at": BASE_TIME + timedelta(days=2),
            "knowledge_at": knowledge_at,
            "amount": amount,
            "currency": "KRW",
            "provenance": {"fixture": source_record_id},
        },
        observation_id,
    )


def test_cash_event_categories_remain_distinct_and_balance_delta_is_not_inferred() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = V2WarehouseRepository(con)
    categories = {
        "owner_deposit": "100000",
        "internal_transfer_in": "50000",
        "trade_settlement_out": "-70000",
        "fee": "-100",
        "tax": "-20",
        "dividend": "3000",
        "unknown": "1",
    }
    for event_type, amount in categories.items():
        event_id = _record(
            repository,
            source_record_id=event_type,
            event_type=event_type,
            amount=amount,
        )
        # Exact replay is idempotent and does not append another classification.
        assert _record(
            repository,
            source_record_id=event_type,
            event_type=event_type,
            amount=amount,
        ) == event_id

    assert dict(con.execute(
        "SELECT event_type, amount FROM silver.cash_flow_events_current"
    ).fetchall()) == {key: Decimal(value) for key, value in categories.items()}
    assert repository.table_count("silver.cash_flow_events") == len(categories)
    assert repository.table_count("silver.cash_flow_event_revisions") == len(categories)

    # A cash balance observation remains a snapshot; there is no balance-delta event synthesis.
    balance_observation = repository.record_observation(
        "dataset.portfolio-position-observation",
        SourceEnvelope(
            "source.kis-open-api", "balance-only", BASE_TIME, BASE_TIME,
            {"amount": "999999"}, "balance-hash", "pass",
        ),
        "cash-fixture-run",
    )
    repository.upsert_cash(
        {"account_id": "account-1", "currency": "KRW", "as_of": BASE_TIME, "amount": "999999"},
        balance_observation,
    )
    assert repository.table_count("silver.cash_flow_events") == len(categories)
    con.close()


def test_cash_classification_revision_is_point_in_time_and_immutable() -> None:
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    repository = V2WarehouseRepository(con)
    event_id = _record(
        repository,
        source_record_id="ambiguous-1",
        event_type="unknown",
        amount="-70000",
    )
    correction_at = BASE_TIME + timedelta(days=1)
    revision_id = repository.append_cash_flow_classification(
        event_id,
        {
            "expected_prior_revision": 1,
            "event_type": "trade_settlement_out",
            "knowledge_at": correction_at,
            "linked_trade_event_id": "trade-1",
            "link_quality": "reconciled",
            "correction_reason": "matched_broker_settlement",
            "provenance": {"review": "fixture"},
        },
    )

    before = repository.get_cash_flow_as_of(event_id, correction_at - timedelta(microseconds=1))
    after = repository.get_cash_flow_as_of(event_id, correction_at)
    assert before and before["event_type"] == "unknown" and before["revision"] == 1
    assert after and after["event_type"] == "trade_settlement_out" and after["revision"] == 2
    assert after["linked_trade_event_id"] == "trade-1"
    assert con.execute(
        "SELECT event_type FROM silver.cash_flow_events WHERE cash_flow_event_id=?", [event_id]
    ).fetchone()[0] == "unknown"
    assert con.execute(
        "SELECT cash_flow_event_revision_id FROM silver.cash_flow_event_revisions WHERE revision=2"
    ).fetchone()[0] == revision_id

    with pytest.raises(ValueError, match="expected_prior_revision"):
        repository.append_cash_flow_classification(
            event_id,
            {
                "expected_prior_revision": 1,
                "event_type": "fee",
                "knowledge_at": correction_at + timedelta(hours=1),
            },
        )
    with pytest.raises(ValueError, match="cannot move backwards"):
        repository.append_cash_flow_classification(
            event_id,
            {"event_type": "fee", "knowledge_at": BASE_TIME - timedelta(seconds=1)},
        )
    with pytest.raises(ValueError, match="immutable monetary fact"):
        _record(
            repository,
            source_record_id="ambiguous-1",
            event_type="unknown",
            amount="-1",
        )
    with pytest.raises(ValueError, match="requires linked_trade_event_id"):
        repository.append_cash_flow_classification(
            event_id,
            {
                "event_type": "trade_settlement_out",
                "knowledge_at": correction_at + timedelta(hours=1),
                "link_quality": "reconciled",
            },
        )
    con.close()


def test_cash_event_revisions_survive_complete_v2_backup_restore(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    MigrationRunner(source).apply()
    repository = V2WarehouseRepository(source)
    event_id = _record(
        repository,
        source_record_id="restore-1",
        event_type="dividend",
        amount="1234",
    )
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    manifest: dict[str, object] = {
        "manifest_version": 2,
        "tables": {},
        "object_bytes_included": False,
    }
    for qualified in v2_backup_table_names():
        schema, table = qualified.split(".", 1)
        directory = backup_dir / schema
        directory.mkdir(exist_ok=True)
        path = directory / f"{table}.parquet"
        quoted_path = "'" + str(path).replace("'", "''") + "'"
        source.execute(f"COPY (SELECT * FROM {qualified}) TO {quoted_path} (FORMAT PARQUET)")
        manifest["tables"][qualified] = {
            "rows": source.execute(f"SELECT count(*) FROM {qualified}").fetchone()[0],
            "path": f"{schema}/{table}.parquet",
        }
    source.close()
    (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    target = tmp_path / "restored.duckdb"
    completed = subprocess.run(
        [sys.executable, "scripts/restore_v2_backup.py", str(backup_dir), "--database", str(target)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert f"tables={len(v2_backup_table_names())}" in completed.stdout
    restored = duckdb.connect(str(target), read_only=True)
    assert restored.execute(
        "SELECT cash_flow_event_id, event_type, amount FROM silver.cash_flow_events_current"
    ).fetchone() == (event_id, "dividend", Decimal("1234"))
    assert restored.execute("SELECT count(*) FROM silver.cash_flow_event_revisions").fetchone()[0] == 1
    restored.close()
