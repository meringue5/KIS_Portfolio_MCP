#!/usr/bin/env python3
"""Transform the allowlisted V1 Parquet backup into V2 and emit reconciliation evidence."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from kis_portfolio.config import PROJECT_ROOT, get_motherduck_database, get_motherduck_token
from kis_portfolio.platform.migrations import MigrationRunner


CONTRACT = PROJECT_ROOT / "governance/migrations/v1-v2-history-v1.toml"
INCLUDED = {"instrument_master", "price_history", "exchange_rate_history"}


def q(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def validate_contract(backup: Path) -> tuple[dict, dict]:
    contract = tomllib.loads(CONTRACT.read_text(encoding="utf-8"))
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    sources = {item["source"].removeprefix("main.") for item in contract["objects"]}
    if set(manifest["tables"]) - sources:
        raise RuntimeError(f"mapping contract misses backup tables: {sorted(set(manifest['tables']) - sources)}")
    transformed = {item["source"].removeprefix("main.") for item in contract["objects"] if item["disposition"] == "transform"}
    if transformed != INCLUDED:
        raise RuntimeError(f"unexpected transform allowlist: {sorted(transformed)}")
    return contract, manifest


def apply(con: duckdb.DuckDBPyConnection, backup: Path, run_id: str) -> dict:
    master = q(backup / "instrument_master.parquet")
    prices = q(backup / "price_history.parquet")
    fx = q(backup / "exchange_rate_history.parquet")
    con.execute("BEGIN")
    try:
        con.execute(f"""
            INSERT OR IGNORE INTO bronze.source_observations
            SELECT 'v1-master-' || sha256(market || '|' || symbol), 'dataset.instrument-master',
                   'source.kis-open-api', market || '|' || symbol, 'v1-master|' || market || '|' || symbol,
                   timezone('Asia/Seoul', updated_at), timezone('Asia/Seoul', updated_at), timezone('Asia/Seoul', updated_at),
                   sha256(to_json(t)), 'passed', to_json(t), ?, current_timestamp
            FROM read_parquet({master}) t
        """, [run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO bronze.source_observations
            SELECT 'v1-price-' || sha256(exchange || '|' || symbol || '|' || date || '|' || adjusted),
                   'dataset.price-bar-daily', 'source.kis-open-api', exchange || '|' || symbol || '|' || date,
                   'v1-price|' || exchange || '|' || symbol || '|' || date || '|' || adjusted,
                   timezone('UTC', cast(date as timestamp)), timezone('Asia/Seoul', created_at), timezone('Asia/Seoul', created_at),
                   sha256(to_json(t)), 'passed', to_json(t), ?, current_timestamp
            FROM read_parquet({prices}) t
        """, [run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO bronze.source_observations
            SELECT 'v1-fx-' || sha256(currency || '|' || date || '|' || period), 'dataset.fx-rate-daily',
                   'source.kis-open-api', currency || '|' || date || '|' || period,
                   'v1-fx|' || currency || '|' || date || '|' || period,
                   timezone('UTC', cast(date as timestamp)), timezone('Asia/Seoul', created_at), timezone('Asia/Seoul', created_at),
                   sha256(to_json(t)), 'passed', to_json(t), ?, current_timestamp
            FROM read_parquet({fx}) t
        """, [run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO silver.instruments
            SELECT 'v1|' || market || '|' || symbol, market, symbol, name,
                   CASE WHEN coalesce(etp_code, '') <> '' THEN 'etp' ELSE 'equity' END, 'KRW', NULL,
                   timezone('Asia/Seoul', updated_at), NULL, 'inferred_v1',
                   json_object('mapping_id','v1-v2-history-v1','source','main.instrument_master')
            FROM read_parquet({master})
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.instruments
            SELECT 'v1|' || exchange || '|' || symbol, exchange, symbol, NULL, 'unknown',
                   CASE WHEN exchange = 'KRX' THEN 'KRW' ELSE 'USD' END,
                   NULL, min(timezone('Asia/Seoul', created_at)), NULL, 'placeholder_v1_price',
                   json_object('mapping_id','v1-v2-history-v1','source','main.price_history')
            FROM read_parquet({prices}) p
            WHERE NOT EXISTS (SELECT 1 FROM silver.instruments i WHERE i.instrument_id='v1|' || p.exchange || '|' || p.symbol)
            GROUP BY exchange, symbol
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.price_bars_daily
            SELECT 'v1|' || exchange || '|' || symbol, date, CASE WHEN adjusted THEN 'adjusted' ELSE 'raw' END,
                   open, high, low, close, volume,
                   'v1-price-' || sha256(exchange || '|' || symbol || '|' || date || '|' || adjusted), 'passed'
            FROM read_parquet({prices})
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.fx_rates_daily
            SELECT currency, 'KRW', date, 'v1_' || period, rate,
                   'v1-fx-' || sha256(currency || '|' || date || '|' || period), 'passed'
            FROM read_parquet({fx})
        """)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    source_rows = {
        "instrument_master": con.execute(f"select count(*) from read_parquet({master})").fetchone()[0],
        "price_history": con.execute(f"select count(*) from read_parquet({prices})").fetchone()[0],
        "exchange_rate_history": con.execute(f"select count(*) from read_parquet({fx})").fetchone()[0],
    }
    return {
        "source_rows": source_rows,
        "target_rows": {
            "bronze.source_observations": con.execute("select count(*) from bronze.source_observations where pipeline_run_id=?", [run_id]).fetchone()[0],
            "silver.instruments": con.execute("select count(*) from silver.instruments where instrument_id like 'v1|%'").fetchone()[0],
            "silver.price_bars_daily": con.execute("select count(*) from silver.price_bars_daily where source_observation_id like 'v1-price-%'").fetchone()[0],
            "silver.fx_rates_daily": con.execute("select count(*) from silver.fx_rates_daily where source_observation_id like 'v1-fx-%'").fetchone()[0],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_dir")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database")
    target.add_argument("--motherduck", action="store_true")
    parser.add_argument("--evidence")
    args = parser.parse_args()
    backup = Path(args.backup_dir).expanduser().resolve()
    contract, manifest = validate_contract(backup)
    load_dotenv(PROJECT_ROOT / ".env")
    if args.motherduck:
        token = get_motherduck_token()
        if not token:
            raise RuntimeError("MOTHERDUCK_TOKEN required")
        connection = f"md:{get_motherduck_database()}?motherduck_token={token}"
        target_label = f"md:{get_motherduck_database()}"
    else:
        path = Path(args.database).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection, target_label = str(path), str(path)
    run_id = "backfill-v1-v2-history-v1"
    con = duckdb.connect(connection)
    try:
        MigrationRunner(con).apply()
        result = apply(con, backup, run_id)
        expected_observations = sum(result["source_rows"].values())
        passed = (
            result["target_rows"]["bronze.source_observations"] == expected_observations
            and result["target_rows"]["silver.price_bars_daily"] == result["source_rows"]["price_history"]
            and result["target_rows"]["silver.fx_rates_daily"] == result["source_rows"]["exchange_rate_history"]
        )
        evidence = {"mapping_id": contract["mapping_id"], "source_manifest_created_at": manifest.get("created_at"), "target": target_label, "run_id": run_id, **result, "passed": passed, "verified_at": datetime.now(UTC).isoformat()}
        if not passed:
            raise RuntimeError(f"reconciliation failed: {evidence}")
        if args.evidence:
            Path(args.evidence).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    finally:
        con.close()


if __name__ == "__main__":
    main()
