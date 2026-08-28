from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/migrate_v1_v2_portfolio.py"
    spec = importlib.util.spec_from_file_location("migrate_v1_v2_portfolio", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portfolio_migration_aggregates_cash_and_reconciles(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    c = duckdb.connect()
    for name in ("portfolio_snapshots", "overseas_asset_snapshots"):
        c.execute(f"COPY (SELECT '{name}-1' id, timestamp '2026-01-02 16:00:00' snapshot_at) TO '{backup / (name + '.parquet')}' (FORMAT PARQUET)")
    c.execute(f"COPY (SELECT 'overview-1' id, timestamp '2026-01-02 16:00:00' snapshot_at, 150::BIGINT total_eval_amt_krw) TO '{backup / 'asset_overview_snapshots.parquet'}' (FORMAT PARQUET)")
    c.execute(f"""
        COPY (
          SELECT * FROM (VALUES
            ('h1','overview-1',timestamp '2026-01-02 15:59:59','ria','ria','005930','Samsung','KRX','equity','KRW',1.0,100::BIGINT,NULL::DOUBLE),
            ('h2','overview-1',timestamp '2026-01-02 15:59:58','ria','ria',NULL,NULL,'KRW','cash','KRW',NULL,20::BIGINT,NULL::DOUBLE),
            ('h3','overview-1',timestamp '2026-01-02 15:59:57','ria','ria',NULL,NULL,'FX','cash','KRW',NULL,30::BIGINT,NULL::DOUBLE)
          ) t(id,overview_snapshot_id,snapshot_at,account_label,account_type,symbol,name,market,asset_subtype,currency,quantity,value_krw,value_foreign)
        ) TO '{backup / 'asset_holding_snapshots.parquet'}' (FORMAT PARQUET)
    """)
    c.close()
    target = duckdb.connect(str(tmp_path / "target.duckdb"))
    MigrationRunner(target).apply()
    module = load_module()
    first = module.apply(target, backup, "test-portfolio")
    second = module.apply(target, backup, "test-portfolio")
    assert first == second
    assert first["target_rows"] == {"accounts": 1, "positions": 1, "cash": 1, "daily_state": 2}
    assert first["reconciliation"] == {"days": 1, "max_abs_difference_krw": 0.0, "failed_days": 0}
    assert target.execute("select total_value_krw from gold.portfolio_daily_summary").fetchone()[0] == 150
    target.close()
