from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts/reconcile_v2_trade_corrections.py"
    spec = importlib.util.spec_from_file_location("reconcile_v2_trade_corrections", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_buy_pollution_is_preserved_but_corrected_projection_excludes_sell_lot():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    observed = datetime(2026, 1, 3, tzinfo=UTC)
    observation_id = "v1-domestic-order-sell"
    con.execute("""
        INSERT INTO bronze.source_observations(
            observation_id,dataset_id,source_id,source_record_id,idempotency_key,
            effective_at,observed_at,fetched_at,content_hash,quality_status,payload,pipeline_run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, [
        observation_id, "dataset.trade-event", "source.kis-open-api", "sell", "sell-key",
        observed, observed, observed, "hash", "partial_history",
        json.dumps({"side_code": "01", "account_product_code": "01"}), "legacy-run",
    ])
    con.execute("""
        INSERT INTO silver.trade_events VALUES (
            'trade-1','account-1','v1|KRX|005930','buy',?,3,1000,'KRW','2026-01-02|1|100',1,?,'partial_history'
        )
    """, [observed, observation_id])
    con.execute("""
        INSERT INTO silver.purchase_lots VALUES (
            'lot-1','trade-1','account-1','v1|KRX|005930',?,3,3,1000,'KRW','partial_history'
        )
    """, [observed])
    module = load_module()

    assert module.inspect(con) == {
        "source_trade_events": 1,
        "known_side": 1,
        "unknown_side": 0,
        "unknown_product_code": 0,
        "eligible_corrections": 1,
        "base_side_mismatch": 1,
    }
    first = module.apply(con)
    second = module.apply(con)

    assert first == second
    assert first["revision_rows"] == 1
    assert first["current_buy"] == 0
    assert first["current_sell"] == 1
    assert first["suppressed_purchase_lots"] == 1
    assert con.execute("select side from silver.trade_events").fetchone()[0] == "buy"
    assert con.execute("select side from silver.trade_events_current").fetchone()[0] == "sell"
    assert con.execute("select count(*) from silver.purchase_lots").fetchone()[0] == 1
    assert con.execute("select count(*) from silver.purchase_lots_current").fetchone()[0] == 0
    con.close()
