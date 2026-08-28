from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from kis_portfolio.platform.migrations import MigrationRunner


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts/sync_v2_instrument_classification.py"
    spec = importlib.util.spec_from_file_location("sync_v2_instrument_classification", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_held_scope_classification_and_route_sync_are_idempotent():
    con = duckdb.connect(":memory:")
    MigrationRunner(con).apply()
    con.execute("""CREATE TABLE main.instrument_master(
        symbol VARCHAR,market VARCHAR,group_code VARCHAR,standard_code VARCHAR,name VARCHAR
    )""")
    con.execute("""CREATE TABLE main.instrument_classification_overrides(
        symbol VARCHAR,market VARCHAR,exposure_type VARCHAR,exposure_region VARCHAR,
        asset_subtype VARCHAR,reason VARCHAR
    )""")
    observed = datetime(2026, 8, 28, 7, tzinfo=UTC)
    con.execute("INSERT INTO silver.accounts VALUES ('a','a','REAL','KRW',?,NULL,'{}')", [observed])
    instruments = [
        ("v1|KRX|0019K0", "KRX", "0019K0", "TIME fixture", "KRW"),
        ("v1|KRX|0185L0", "KRX", "0185L0", "TIME route only", "KRW"),
        ("v1|NAS|NVDA", "NAS", "NVDA", "NVIDIA", "USD"),
    ]
    for instrument_id, market, symbol, name, currency in instruments:
        con.execute(
            "INSERT INTO silver.instruments VALUES (?,?,?,?,? ,?,NULL,?,NULL,'unknown','{}')",
            [instrument_id, market, symbol, name, "unknown", currency, observed],
        )
        con.execute(
            "INSERT INTO silver.position_snapshots VALUES ('a',?,?,1,NULL,?,'obs','pass')",
            [instrument_id, observed, currency],
        )
    con.execute("INSERT INTO main.instrument_master VALUES ('0019K0','KRX','E','KR70019K0009','TIME fixture')")
    module = _module()

    dry = module.inspect(con)
    assert dry == {
        "held_instruments": 3,
        "classification_counts": {"etf": 2, "unknown": 1},
        "exact_routes_for_held": 2,
        "registered_routes": 14,
        "production_network_profiles": 0,
    }
    first = module.apply(con)
    second = module.apply(con)
    assert first == second
    assert first["instrument_version_rows"] == 3
    assert first["route_rows"] == 14
    assert con.execute("select count(*) from bronze.source_observations").fetchone()[0] == 3
    assert con.execute("select asset_type from silver.instruments where instrument_id='v1|KRX|0185L0'").fetchone()[0] == "etf"
    con.close()
