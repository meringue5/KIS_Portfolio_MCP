import importlib
import importlib.util
import sys
from pathlib import Path

import pytest
import duckdb


def test_db_schema_initializes_with_configured_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))

    import kis_portfolio.db as kisdb

    kisdb = importlib.reload(kisdb)
    kisdb.close_connection()
    try:
        con = kisdb.get_connection()
        tables = {name for (name,) in con.execute("show tables").fetchall()}
    finally:
        kisdb.close_connection()

    assert {
        "asset_holding_snapshots",
        "asset_return_daily",
        "asset_overview_daily_snapshots",
        "asset_overview_snapshots",
        "domestic_orders",
        "cash_flow",
        "exchange_rate_history",
        "instrument_classification_overrides",
        "instrument_master",
        "kis_api_access_tokens",
        "market_calendar",
        "order_history",
        "overseas_order_history",
        "overseas_orders",
        "overseas_asset_snapshots",
        "overseas_settlement_balance_snapshots",
        "overseas_transaction_history",
        "overseas_transactions",
        "portfolio_daily_snapshots",
        "portfolio_snapshots",
        "price_history",
        "schema_migrations",
        "trade_profit_history",
        "trade_journal",
    }.issubset(tables)
    assert (tmp_path / "local" / "kis_portfolio.duckdb").exists()


def test_db_schema_upgrades_legacy_asset_overview_without_rewriting_rows():
    from kis_portfolio.db.schema import init_schema

    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE asset_overview_snapshots (
            id VARCHAR,
            snapshot_at TIMESTAMP,
            base_currency VARCHAR,
            domestic_eval_amt_krw BIGINT,
            overseas_stock_eval_amt_krw BIGINT,
            overseas_cash_amt_krw BIGINT,
            overseas_total_asset_amt_krw BIGINT,
            total_eval_amt_krw BIGINT,
            domestic_pct DOUBLE,
            overseas_pct DOUBLE,
            overseas_stock_pct DOUBLE,
            overseas_cash_pct DOUBLE,
            domestic_direct_amt_krw BIGINT,
            overseas_direct_amt_krw BIGINT,
            overseas_indirect_amt_krw BIGINT,
            cash_amt_krw BIGINT,
            unknown_amt_krw BIGINT,
            allocation_data JSON,
            classification_summary JSON,
            overview_data JSON
        )
    """)
    con.execute("""
        INSERT INTO asset_overview_snapshots (
            id, snapshot_at, base_currency, total_eval_amt_krw
        ) VALUES ('legacy-row', '2026-06-20 16:00:00', 'KRW', 928000000)
    """)
    con.execute("""
        CREATE VIEW asset_overview_daily_snapshots AS
        SELECT CAST(snapshot_at AS DATE) AS snap_date, total_eval_amt_krw
        FROM asset_overview_snapshots
    """)

    init_schema(con)

    columns = {
        row[0] for row in con.execute("DESCRIBE asset_overview_snapshots").fetchall()
    }
    assert {"quality_status", "quality_flags", "is_complete"}.issubset(columns)
    assert con.execute("SELECT count(*) FROM asset_overview_snapshots").fetchone() == (1,)
    assert con.execute("""
        SELECT quality_status, quality_flags::VARCHAR, is_complete
        FROM asset_overview_daily_snapshots
        WHERE id = 'legacy-row'
    """).fetchone() == (
        "legacy_unassessed",
        '["legacy_cash_semantics_unverified"]',
        False,
    )


def test_db_schema_initialization_retries_write_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))

    import kis_portfolio.db.connection as connection
    from kis_portfolio.db.schema import init_schema as real_init_schema

    connection.close_connection()
    calls = []

    def flaky_init_schema(con):
        calls.append(1)
        if len(calls) == 1:
            raise duckdb.TransactionException("write-write conflict")
        real_init_schema(con)

    monkeypatch.setattr(connection, "init_schema", flaky_init_schema)
    try:
        con = connection.get_connection()
        tables = {name for (name,) in con.execute("show tables").fetchall()}
    finally:
        connection.close_connection()

    assert len(calls) == 2
    assert "portfolio_snapshots" in tables


def test_relative_data_dir_resolves_from_project_root(monkeypatch):
    monkeypatch.setenv("KIS_DATA_DIR", "var")

    import kis_portfolio.config as config

    assert config.get_data_dir() == config.PROJECT_ROOT / "var"
    assert config.get_token_dir() == config.PROJECT_ROOT / "var" / "tokens"
    assert config.get_local_db_path() == config.PROJECT_ROOT / "var" / "local" / "kis_portfolio.duckdb"


def test_motherduck_mode_requires_token(monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "motherduck")
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)

    import kis_portfolio.db as kisdb

    kisdb = importlib.reload(kisdb)
    with pytest.raises(RuntimeError, match="MOTHERDUCK_TOKEN"):
        kisdb.get_connection()


def test_root_server_shim_exposes_mcp():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("root_server_shim", root / "server.py")
    server = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(server)

    assert server.mcp.name == "KIS Portfolio Service"


def test_backup_script_requires_motherduck_token(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "backup_motherduck_script", root / "scripts" / "backup_motherduck.py"
    )
    script = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(script)

    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.setattr(script, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["backup_motherduck.py"])

    assert script.main() == 2


def test_backup_script_skips_tables_missing_before_schema_upgrade(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "backup_motherduck_script_upgrade", root / "scripts" / "backup_motherduck.py"
    )
    script = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(script)

    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE portfolio_snapshots (id VARCHAR)")
    script.TABLES = ("portfolio_snapshots", "cash_flow")

    manifest = script.backup_tables(con, tmp_path / "backup")

    assert manifest["tables"]["portfolio_snapshots"]["rows"] == 0
    assert manifest["skipped_tables"] == ["cash_flow"]
    assert (tmp_path / "backup" / "portfolio_snapshots.parquet").exists()
    assert not (tmp_path / "backup" / "cash_flow.parquet").exists()
