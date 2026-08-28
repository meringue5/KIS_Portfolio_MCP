#!/usr/bin/env python3
"""Build the V2 canonical portfolio ledger from a preserved V1 Parquet backup."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from kis_portfolio.config import PROJECT_ROOT, get_motherduck_database, get_motherduck_token
from kis_portfolio.platform.migrations import MigrationRunner


def q(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def apply(con: duckdb.DuckDBPyConnection, backup: Path, run_id: str) -> dict:
    portfolio = q(backup / "portfolio_snapshots.parquet")
    overseas = q(backup / "overseas_asset_snapshots.parquet")
    holdings = q(backup / "asset_holding_snapshots.parquet")
    overview = q(backup / "asset_overview_snapshots.parquet")
    con.execute("BEGIN")
    try:
        for table, dataset, prefix, path in (
            ("portfolio", "dataset.portfolio-position-observation", "v1-portfolio", portfolio),
            ("overseas", "dataset.portfolio-position-observation", "v1-overseas-asset", overseas),
            ("overview", "dataset.portfolio-daily-state", "v1-overview", overview),
        ):
            con.execute(f"""
                INSERT OR IGNORE INTO bronze.source_observations
                SELECT '{prefix}-' || sha256(id), '{dataset}', 'source.kis-open-api', id,
                       '{prefix}|' || id, timezone('Asia/Seoul', snapshot_at),
                       timezone('Asia/Seoul', snapshot_at), timezone('Asia/Seoul', snapshot_at),
                       sha256(to_json(t)), 'passed', to_json(t), ?, current_timestamp
                FROM read_parquet({path}) t
            """, [run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO bronze.source_observations
            SELECT 'v1-holding-group-' || sha256(group_key), 'dataset.portfolio-position-observation',
                   'source.kis-open-api', group_key, 'v1-holding-group|' || group_key,
                   timezone('Asia/Seoul', snapshot_at), timezone('Asia/Seoul', snapshot_at),
                   timezone('Asia/Seoul', snapshot_at), sha256(to_json(g)), 'passed', to_json(g), ?, current_timestamp
            FROM (
                SELECT CASE WHEN symbol IS NULL
                       THEN overview_snapshot_id || '|' || account_label || '|' || currency || '|cash'
                       ELSE overview_snapshot_id || '|' || account_label || '|' ||
                            coalesce(CASE WHEN market='NASD' THEN 'NAS' ELSE market END,'') || '|' ||
                            symbol || '|' || currency || '|position' END AS group_key,
                       overview_snapshot_id, snapshot_at, account_label, account_type,
                       CASE WHEN market='NASD' THEN 'NAS' ELSE market END AS market,
                       symbol, max(name) AS name, max(asset_subtype) AS asset_subtype,
                       currency, sum(quantity) AS quantity, sum(value_krw) AS value_krw,
                       sum(value_foreign) AS value_foreign, count(*) AS source_row_count
                FROM read_parquet({holdings})
                GROUP BY ALL
            ) g
        """, [run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO silver.accounts
            SELECT sha256('v1-account|' || account_label), account_label, max(account_type), 'KRW',
                   min(timezone('Asia/Seoul', snapshot_at)), NULL,
                   json_object('mapping_id','v1-v2-portfolio-v1','source','main.asset_holding_snapshots')
            FROM read_parquet({holdings}) GROUP BY account_label
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.instruments
            SELECT 'v1|' || market || '|' || symbol, market, symbol, max(name), max(asset_subtype), max(currency),
                   NULL, min(timezone('Asia/Seoul', snapshot_at)), NULL, 'v1_holding',
                   json_object('mapping_id','v1-v2-portfolio-v1','source','main.asset_holding_snapshots')
            FROM (
                SELECT CASE WHEN market='NASD' THEN 'NAS' ELSE market END market, symbol, name,
                       asset_subtype, currency, snapshot_at FROM read_parquet({holdings}) WHERE symbol IS NOT NULL
            ) GROUP BY market, symbol
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.position_snapshots
            SELECT sha256('v1-account|' || account_label), 'v1|' || market || '|' || symbol,
                   timezone('Asia/Seoul', overview_at), sum(quantity), NULL, max(currency),
                   'v1-holding-group-' || sha256(group_key), 'passed'
            FROM (
                SELECT overview_snapshot_id || '|' || account_label || '|' ||
                       CASE WHEN market='NASD' THEN 'NAS' ELSE market END || '|' || symbol || '|' || currency || '|position' group_key,
                       account_label, CASE WHEN market='NASD' THEN 'NAS' ELSE market END market,
                       symbol, currency, o.snapshot_at overview_at, quantity
                FROM read_parquet({holdings}) h JOIN read_parquet({overview}) o ON o.id=h.overview_snapshot_id
                WHERE symbol IS NOT NULL
            ) GROUP BY group_key, account_label, market, symbol, overview_at
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.cash_snapshots
            SELECT sha256('v1-account|' || account_label), currency, timezone('Asia/Seoul', overview_at),
                   sum(value_krw), 'v1-holding-group-' || sha256(group_key), 'passed'
            FROM (
                SELECT h.overview_snapshot_id || '|' || h.account_label || '|' || h.currency || '|cash' group_key,
                       h.account_label, h.currency, o.snapshot_at overview_at, h.value_krw
                FROM read_parquet({holdings}) h JOIN read_parquet({overview}) o ON o.id=h.overview_snapshot_id
                WHERE h.symbol IS NULL
            ) GROUP BY group_key, account_label, currency, overview_at
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO gold.portfolio_daily_state
            WITH latest AS (
                SELECT id, snapshot_at, total_eval_amt_krw,
                       row_number() OVER (PARTITION BY cast(snapshot_at AS DATE) ORDER BY snapshot_at DESC, id DESC) rn
                FROM read_parquet({overview})
            ), grouped AS (
                SELECT h.overview_snapshot_id, l.snapshot_at, h.account_label,
                       CASE WHEN h.symbol IS NULL THEN 'cash|' || h.currency
                            ELSE 'v1|' || CASE WHEN h.market='NASD' THEN 'NAS' ELSE h.market END || '|' || h.symbol END instrument_id,
                       h.currency, sum(h.quantity) quantity, sum(h.value_krw) value_krw,
                       CASE WHEN h.symbol IS NULL THEN 'cash' ELSE 'position' END aggregate_level
                FROM read_parquet({holdings}) h JOIN latest l ON l.id=h.overview_snapshot_id AND l.rn=1
                GROUP BY ALL
            )
            SELECT cast(g.snapshot_at AS DATE), 'v1-latest', sha256('v1-account|' || g.account_label),
                   instrument_id,
                   aggregate_level, CASE WHEN aggregate_level='position' THEN quantity ELSE NULL END,
                   coalesce(value_krw, 0), NULL, NULL, NULL,
                   round(coalesce(value_krw,0) * 100.0 / nullif(l.total_eval_amt_krw,0), 8), timezone('Asia/Seoul', g.snapshot_at),
                   json_object('v1_overview_id', l.id), CASE WHEN value_krw IS NULL THEN 'degraded' ELSE 'passed' END,
                   sha256(l.id || '|' || g.account_label || '|' || instrument_id || '|' || g.currency)
            FROM grouped g JOIN latest l ON l.id=g.overview_snapshot_id AND l.rn=1
        """)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    reconciliation = con.execute(f"""
        WITH latest AS (
            SELECT id, cast(snapshot_at AS DATE) d, total_eval_amt_krw,
                   row_number() OVER (PARTITION BY cast(snapshot_at AS DATE) ORDER BY snapshot_at DESC, id DESC) rn
            FROM read_parquet({overview})
        ), gold AS (
            SELECT evaluation_date d, sum(value_krw) total FROM gold.portfolio_daily_state
            WHERE evaluation_slot='v1-latest' GROUP BY 1
        )
        SELECT count(*), max(abs(g.total-l.total_eval_amt_krw)), sum(CASE WHEN g.total<>l.total_eval_amt_krw THEN 1 ELSE 0 END)
        FROM latest l JOIN gold g USING(d) WHERE l.rn=1
    """).fetchone()
    return {
        "source_rows": {name: con.execute(f"select count(*) from read_parquet({path})").fetchone()[0] for name, path in (("portfolio_snapshots", portfolio),("overseas_asset_snapshots",overseas),("asset_holding_snapshots",holdings),("asset_overview_snapshots",overview))},
        "target_rows": {
            "accounts": con.execute("select count(*) from silver.accounts where provenance->>'mapping_id'='v1-v2-portfolio-v1'").fetchone()[0],
            "positions": con.execute("select count(*) from silver.position_snapshots where source_observation_id like 'v1-holding-group-%'").fetchone()[0],
            "cash": con.execute("select count(*) from silver.cash_snapshots where source_observation_id like 'v1-holding-group-%'").fetchone()[0],
            "daily_state": con.execute("select count(*) from gold.portfolio_daily_state where evaluation_slot='v1-latest'").fetchone()[0],
        },
        "reconciliation": {"days": reconciliation[0], "max_abs_difference_krw": float(reconciliation[1] or 0), "failed_days": int(reconciliation[2] or 0)},
    }


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("backup_dir")
    target=parser.add_mutually_exclusive_group(required=True); target.add_argument("--database"); target.add_argument("--motherduck",action="store_true")
    parser.add_argument("--evidence"); args=parser.parse_args(); backup=Path(args.backup_dir).resolve()
    load_dotenv(PROJECT_ROOT/".env")
    if args.motherduck:
        token=get_motherduck_token();
        if not token: raise RuntimeError("MOTHERDUCK_TOKEN required")
        connection=f"md:{get_motherduck_database()}?motherduck_token={token}"; label=f"md:{get_motherduck_database()}"
    else:
        path=Path(args.database).resolve(); path.parent.mkdir(parents=True,exist_ok=True); connection=str(path); label=str(path)
    con=duckdb.connect(connection)
    try:
        MigrationRunner(con).apply(); result=apply(con,backup,"backfill-v1-v2-portfolio-v1")
        passed=result["source_rows"]["asset_holding_snapshots"]==1619 and result["target_rows"]["accounts"]==5 and result["reconciliation"]["failed_days"]==0
        evidence={"mapping_id":"v1-v2-portfolio-v1","target":label,**result,"passed":passed,"verified_at":datetime.now(UTC).isoformat()}
        if not passed: raise RuntimeError(f"reconciliation failed: {evidence}")
        if args.evidence: Path(args.evidence).write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        print(json.dumps(evidence,indent=2))
    finally: con.close()


if __name__=="__main__": main()
