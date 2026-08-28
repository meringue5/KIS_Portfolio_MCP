from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/migrate_v1_v2_history.py"
    spec = importlib.util.spec_from_file_location("migrate_v1_v2_history", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mapping_contract_covers_backup_and_rerun_is_idempotent(tmp_path: Path) -> None:
    module = load_module()
    backup = tmp_path / "backup"
    backup.mkdir()
    fixture = duckdb.connect()
    fixture.execute(
        f"COPY (SELECT '005930'::VARCHAR AS symbol, 'KRX'::VARCHAR AS market, 'Samsung'::VARCHAR AS \"name\", "
        f"''::VARCHAR AS etp_code, timestamp '2026-01-01 12:00:00' AS updated_at) TO '{backup / 'instrument_master.parquet'}' (FORMAT PARQUET)"
    )
    fixture.execute(
        f"COPY (SELECT 'AAPL'::VARCHAR AS symbol, 'NAS'::VARCHAR AS exchange, date '2026-01-02' AS \"date\", "
        f"100.0::DOUBLE AS \"open\", 110.0::DOUBLE AS high, 99.0::DOUBLE AS low, 108.0::DOUBLE AS \"close\", "
        f"1000::BIGINT AS volume, false::BOOLEAN AS adjusted, timestamp '2026-01-03 08:00:00' AS created_at) "
        f"TO '{backup / 'price_history.parquet'}' (FORMAT PARQUET)"
    )
    fixture.execute(
        f"COPY (SELECT 'USD'::VARCHAR AS currency, date '2026-01-02' AS \"date\", 'D'::VARCHAR AS period, "
        f"1450.0::DOUBLE AS rate, timestamp '2026-01-03 08:00:00' AS created_at) "
        f"TO '{backup / 'exchange_rate_history.parquet'}' (FORMAT PARQUET)"
    )
    fixture.close()
    (backup / "manifest.json").write_text(
        json.dumps({"manifest_version": 1, "tables": {name: {"rows": 1} for name in module.INCLUDED}}),
        encoding="utf-8",
    )
    contract, manifest = module.validate_contract(backup)
    assert contract["mapping_id"] == "v1-v2-history-v1"
    assert set(manifest["tables"]) <= {item["source"].removeprefix("main.") for item in contract["objects"]}

    con = duckdb.connect(str(tmp_path / "target.duckdb"))
    MigrationRunner(con).apply()
    first = module.apply(con, backup, "test-v1-v2")
    second = module.apply(con, backup, "test-v1-v2")
    assert first == second
    assert first["source_rows"] == {"instrument_master": 1, "price_history": 1, "exchange_rate_history": 1}
    assert first["target_rows"] == {
        "bronze.source_observations": 3,
        "silver.instruments": 2,
        "silver.price_bars_daily": 1,
        "silver.fx_rates_daily": 1,
    }
    con.close()
