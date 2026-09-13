from __future__ import annotations

import tomllib
from pathlib import Path

import duckdb

from kis_portfolio.db.catalog import v2_backup_table_names, v2_object_by_qualified_name
from kis_portfolio.platform.migrations import MigrationRunner
from kis_portfolio.services.v1_main_transition import transition_v1_reference_data


ROOT = Path(__file__).resolve().parents[1]


def _legacy_sources(connection: duckdb.DuckDBPyConnection) -> None:
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
        ('krx', DATE '2026-09-11', true, '09:00', '15:30', 'Asia/Seoul', 'fixture', NULL, '{}', TIMESTAMP '2026-09-01')
    """)
    connection.execute("""
        INSERT INTO main.instrument_master VALUES
        ('005930', 'KRX', 'KR7005930003', '삼성전자', 'ST', NULL, NULL, NULL, NULL, '{}', TIMESTAMP '2026-09-01')
    """)
    connection.execute("""
        INSERT INTO main.instrument_classification_overrides VALUES
        ('005930', 'KRX', 'domestic', 'KR', 'equity', 'fixture', TIMESTAMP '2026-09-01')
    """)


def test_reference_transition_is_preservation_first_reconciled_and_idempotent() -> None:
    connection = duckdb.connect(":memory:")
    MigrationRunner(connection).apply()
    _legacy_sources(connection)

    plan = transition_v1_reference_data(connection)
    assert plan["status"] == "planned" and plan["side_effects"] == "none"
    assert connection.execute("SELECT count(*) FROM control.market_calendar").fetchone()[0] == 0

    first = transition_v1_reference_data(connection, apply=True)
    second = transition_v1_reference_data(connection, apply=True)
    assert first["status"] == second["status"] == "reconciled"
    assert all(item["unreconciled_source_rows"] == 0 for item in first["objects"])
    assert connection.execute("SELECT count(*) FROM main.market_calendar").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM control.market_calendar").fetchone()[0] == 1
    assert connection.execute("SELECT name FROM control.instrument_master").fetchone()[0] == "삼성전자"
    connection.close()


def test_transition_control_tables_are_governed_backup_objects() -> None:
    objects = v2_object_by_qualified_name()
    backups = set(v2_backup_table_names())
    for name in (
        "control.market_calendar",
        "control.instrument_master",
        "control.instrument_classification_overrides",
    ):
        assert objects[name].object_type == "table"
        assert name in backups


def test_manifest_keeps_drift_archive_only_and_v2_runtime_off_main() -> None:
    manifest = tomllib.loads(
        (ROOT / "governance/project/v1-main-transition.toml").read_text(encoding="utf-8")
    )
    assert manifest["production_apply_approved"] is True
    assert manifest["deletion_approved"] is False
    assert {row["object"] for row in manifest["archive_dispositions"]} == {
        "main.cash_flow", "main.trade_journal", "main.asset_return_daily",
    }
    runtime_files = (
        "src/kis_portfolio/services/v2_collection.py",
        "src/kis_portfolio/services/total_asset_digest.py",
        "src/kis_portfolio/application/portfolio_performance.py",
        "src/kis_portfolio/services/wi029_s05.py",
        "src/kis_portfolio/remote.py",
    )
    for relative in runtime_files:
        assert "main." not in (ROOT / relative).read_text(encoding="utf-8"), relative
