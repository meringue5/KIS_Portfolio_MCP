#!/usr/bin/env python3
"""Build order-grain V2 trade, purchase-lot and initial thread history."""

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
    orders=q(backup/"domestic_orders.parquet"); order_history=q(backup/"order_history.parquet")
    overseas_history=q(backup/"overseas_transaction_history.parquet"); overseas=q(backup/"overseas_transactions.parquet")
    profit=q(backup/"trade_profit_history.parquet")
    con.execute("BEGIN")
    try:
        for dataset,prefix,path,time_col in (
            ("dataset.trade-event","v1-order-history",order_history,"fetched_at"),
            ("dataset.trade-event","v1-overseas-history",overseas_history,"fetched_at"),
            ("dataset.trade-event","v1-trade-profit",profit,"fetched_at"),
        ):
            # Envelope schemas share id but their observation timestamp names can drift; use current_timestamp only as ingestion evidence.
            con.execute(f"""
                INSERT OR IGNORE INTO bronze.source_observations
                SELECT '{prefix}-' || sha256(id), '{dataset}', 'source.kis-open-api', id, '{prefix}|' || id,
                       NULL, current_timestamp, current_timestamp, sha256(to_json(t)), 'historical_envelope',
                       to_json(t), ?, current_timestamp FROM read_parquet({path}) t
            """,[run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO bronze.source_observations
            SELECT 'v1-domestic-order-' || sha256(account_type||'|'||account_product_code||'|'||order_date||'|'||order_branch_no||'|'||order_no),
                   'dataset.trade-event','source.kis-open-api',account_type||'|'||account_product_code||'|'||order_date||'|'||order_branch_no||'|'||order_no,
                   'v1-domestic-order|'||account_type||'|'||account_product_code||'|'||order_date||'|'||order_branch_no||'|'||order_no,
                   timezone('Asia/Seoul',strptime(cast(order_date as varchar)||order_time,'%Y-%m-%d%H%M%S')),
                   timezone('Asia/Seoul',last_seen_at),timezone('Asia/Seoul',last_seen_at),sha256(to_json(t)),
                   CASE WHEN filled_qty<=0 THEN 'deferred_unfilled'
                        WHEN side_code NOT IN ('01','02') OR side_code IS NULL THEN 'deferred_unknown_side'
                        ELSE 'partial_history' END,to_json(t),?,current_timestamp
            FROM read_parquet({orders}) t
        """,[run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO bronze.source_observations
            SELECT 'v1-overseas-transaction-'||sha256(transaction_hash),'dataset.cash-transaction-event','source.kis-open-api',
                   transaction_hash,'v1-overseas-transaction|'||transaction_hash,timezone('UTC',cast(transaction_date as timestamp)),
                   timezone('Asia/Seoul',last_seen_at),timezone('Asia/Seoul',last_seen_at),sha256(to_json(t)),
                   'deferred_missing_side_quantity',to_json(t),?,current_timestamp FROM read_parquet({overseas}) t
        """,[run_id])
        con.execute(f"""
            INSERT OR IGNORE INTO silver.trade_events
            SELECT sha256('v1-trade|'||account_type||'|'||account_product_code||'|KRX|'||symbol||'|'||order_date||'|'||order_time||'|'||order_branch_no||'|'||order_no||'|aggregate'),
                   sha256('v1-account|'||account_type),'v1|KRX|'||symbol,
                   CASE side_code WHEN '01' THEN 'sell' WHEN '02' THEN 'buy' END,
                   timezone('Asia/Seoul',strptime(cast(order_date as varchar)||order_time,'%Y-%m-%d%H%M%S')),
                   filled_qty,CASE WHEN coalesce(avg_price,0)>0 THEN avg_price ELSE order_price END,'KRW',
                   cast(order_date as varchar)||'|'||order_branch_no||'|'||order_no,1,
                   'v1-domestic-order-'||sha256(account_type||'|'||account_product_code||'|'||order_date||'|'||order_branch_no||'|'||order_no),
                   CASE WHEN coalesce(original_order_no,'')<>'' THEN 'inferred_correction' ELSE 'partial_history' END
            FROM read_parquet({orders})
            WHERE filled_qty>0 AND side_code IN ('01','02')
              AND nullif(trim(account_product_code),'') IS NOT NULL
        """)
        con.execute(f"""
            INSERT OR IGNORE INTO silver.trade_event_revisions
            SELECT sha256('trade-revision-v1|'||trade.trade_event_id),trade.trade_event_id,
                   trade.account_id,'KRX',src.account_product_code,trade.instrument_id,
                   trade.broker_order_id,trade.executed_at,'aggregate',1,trade.side,trade.quantity,trade.price,
                   trade.currency,timezone('Asia/Seoul',src.last_seen_at),trade.source_observation_id,
                   'v1_import_contract','pass',json_object('source_side_code',src.side_code,'base_side',trade.side)
            FROM silver.trade_events trade
            JOIN read_parquet({orders}) src
              ON trade.source_observation_id='v1-domestic-order-'||sha256(src.account_type||'|'||src.account_product_code||'|'||src.order_date||'|'||src.order_branch_no||'|'||src.order_no)
            WHERE trade.source_observation_id LIKE 'v1-domestic-order-%' AND src.side_code IN ('01','02')
              AND nullif(trim(src.account_product_code),'') IS NOT NULL
        """)
        con.execute("""
            INSERT OR IGNORE INTO silver.purchase_lots
            SELECT sha256('v1-lot|'||trade_event_id),trade_event_id,account_id,instrument_id,executed_at,
                   quantity,quantity,price,currency,quality_status FROM silver.trade_events
            WHERE source_observation_id LIKE 'v1-domestic-order-%' AND side='buy'
        """)
        con.execute("""
            INSERT OR IGNORE INTO silver.trade_threads
            SELECT sha256('v1-thread|'||lot_id),account_id,instrument_id,opened_at,NULL,NULL,'open',1,
                   json_object('mapping_id','v1-v2-trade-lot-v1','default_grouping','one_thread_per_imported_lot','quality_status',quality_status)
            FROM silver.purchase_lots WHERE trade_event_id IN
              (SELECT trade_event_id FROM silver.trade_events WHERE source_observation_id LIKE 'v1-domestic-order-%')
        """)
        con.execute("""
            INSERT OR IGNORE INTO silver.trade_thread_lots
            SELECT sha256('v1-thread|'||lot_id),lot_id,1,opened_at,'inferred_import_default'
            FROM silver.purchase_lots WHERE trade_event_id IN
              (SELECT trade_event_id FROM silver.trade_events WHERE source_observation_id LIKE 'v1-domestic-order-%')
        """)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    source=con.execute(f"""select count(*),count_if(filled_qty>0),
        count_if(filled_qty>0 and side_code='02'),count_if(filled_qty>0 and side_code='01'),
        count_if(filled_qty>0 and (side_code not in ('01','02') or side_code is null)),
        count_if(filled_qty<=0 or filled_qty is null),count_if(coalesce(original_order_no,'')<>'')
        from read_parquet({orders})""").fetchone()
    target={
        "trade_events":con.execute("select count(*) from silver.trade_events where source_observation_id like 'v1-domestic-order-%'").fetchone()[0],
        "trade_event_revisions":con.execute("select count(*) from silver.trade_event_revisions where correction_reason='v1_import_contract'").fetchone()[0],
        "purchase_lots":con.execute("select count(*) from silver.purchase_lots where trade_event_id in (select trade_event_id from silver.trade_events where source_observation_id like 'v1-domestic-order-%')").fetchone()[0],
        "threads":con.execute("select count(*) from silver.trade_threads where provenance->>'mapping_id'='v1-v2-trade-lot-v1'").fetchone()[0],
        "thread_links":con.execute("select count(*) from silver.trade_thread_lots where linkage_quality='inferred_import_default'").fetchone()[0],
    }
    coverage=con.execute("""
        WITH lots AS (SELECT account_id,instrument_id,sum(original_quantity) q FROM silver.purchase_lots GROUP BY 1,2),
        latest AS (SELECT account_id,instrument_id,quantity,row_number() over(partition by account_id,instrument_id order by as_of desc) rn FROM silver.position_snapshots)
        SELECT count(*),count_if(l.q=p.quantity),count_if(p.quantity IS NULL OR l.q<>p.quantity)
        FROM lots l LEFT JOIN latest p ON p.account_id=l.account_id AND p.instrument_id=l.instrument_id AND p.rn=1
    """).fetchone()
    return {"source_orders":{"rows":source[0],"filled":source[1],"buy":source[2],"sell":source[3],"unknown_side":source[4],"deferred_unfilled":source[5],"corrections":source[6]},"target_rows":target,"position_coverage":{"account_instruments":coverage[0],"matched":coverage[1],"partial_history":coverage[2]}}


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("backup_dir");target=parser.add_mutually_exclusive_group(required=True);target.add_argument("--database");target.add_argument("--motherduck",action="store_true");parser.add_argument("--evidence");args=parser.parse_args()
    backup=Path(args.backup_dir).resolve();load_dotenv(PROJECT_ROOT/".env")
    if args.motherduck:
        token=get_motherduck_token();
        if not token: raise RuntimeError("MOTHERDUCK_TOKEN required")
        connection=f"md:{get_motherduck_database()}?motherduck_token={token}";label=f"md:{get_motherduck_database()}"
    else:
        path=Path(args.database).resolve();path.parent.mkdir(parents=True,exist_ok=True);connection=str(path);label=str(path)
    con=duckdb.connect(connection)
    try:
        MigrationRunner(con).apply();result=apply(con,backup,"backfill-v1-v2-trade-lot-v1")
        known=result["source_orders"]["buy"]+result["source_orders"]["sell"]
        buys=result["source_orders"]["buy"]
        passed=(known==result["target_rows"]["trade_events"]==result["target_rows"]["trade_event_revisions"]
                and buys==result["target_rows"]["purchase_lots"]==result["target_rows"]["threads"]==result["target_rows"]["thread_links"])
        evidence={"mapping_id":"v1-v2-trade-lot-v1","target":label,**result,"passed":passed,"verified_at":datetime.now(UTC).isoformat()}
        if not passed: raise RuntimeError(f"reconciliation failed: {evidence}")
        if args.evidence:Path(args.evidence).write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        print(json.dumps(evidence,indent=2))
    finally:con.close()


if __name__=="__main__":main()
