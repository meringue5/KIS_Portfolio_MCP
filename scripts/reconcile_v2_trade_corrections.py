#!/usr/bin/env python3
"""Dry-run or append corrected V2 domestic trade-event revisions from governed source observations."""

from __future__ import annotations

import argparse
import json

import duckdb
from dotenv import load_dotenv

from kis_portfolio.config import PROJECT_ROOT, get_motherduck_database, get_motherduck_token
from kis_portfolio.platform.migrations import MigrationRunner


SIDE_SQL = "json_extract_string(observation.payload, '$.side_code')"
PRODUCT_SQL = "nullif(trim(json_extract_string(observation.payload, '$.account_product_code')), '')"


def inspect(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    row = connection.execute(f"""
        SELECT
            count(*),
            count_if({SIDE_SQL} IN ('01', '02')),
            count_if({SIDE_SQL} NOT IN ('01', '02') OR {SIDE_SQL} IS NULL),
            count_if({PRODUCT_SQL} IS NULL),
            count_if({SIDE_SQL} IN ('01', '02') AND {PRODUCT_SQL} IS NOT NULL),
            count_if(({SIDE_SQL}='01' AND trade.side<>'sell') OR ({SIDE_SQL}='02' AND trade.side<>'buy'))
        FROM silver.trade_events trade
        JOIN bronze.source_observations observation
          ON observation.observation_id=trade.source_observation_id
        WHERE trade.source_observation_id LIKE 'v1-domestic-order-%'
    """).fetchone()
    return {
        "source_trade_events": row[0],
        "known_side": row[1],
        "unknown_side": row[2],
        "unknown_product_code": row[3],
        "eligible_corrections": row[4],
        "base_side_mismatch": row[5],
    }


def apply(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    before = inspect(connection)
    connection.execute(f"""
        INSERT INTO silver.trade_event_revisions(
            trade_event_revision_id, source_trade_event_id, account_id, market, product_code,
            instrument_id, broker_order_id, executed_at, execution_sequence, revision, side,
            quantity, price, currency, knowledge_at, source_observation_id, correction_reason,
            quality_status, metadata
        )
        SELECT
            sha256('trade-revision-v1|' || trade.trade_event_id),
            trade.trade_event_id,
            trade.account_id,
            'KRX',
            {PRODUCT_SQL},
            trade.instrument_id,
            trade.broker_order_id,
            trade.executed_at,
            'aggregate',
            1,
            CASE {SIDE_SQL} WHEN '01' THEN 'sell' WHEN '02' THEN 'buy' END,
            trade.quantity,
            trade.price,
            trade.currency,
            current_timestamp,
            trade.source_observation_id,
            CASE
                WHEN ({SIDE_SQL}='01' AND trade.side<>'sell') OR ({SIDE_SQL}='02' AND trade.side<>'buy')
                THEN 'legacy_all_buy_repair' ELSE 'v1_import_contract'
            END,
            'pass',
            json_object('source_side_code', {SIDE_SQL}, 'base_side', trade.side)
        FROM silver.trade_events trade
        JOIN bronze.source_observations observation
          ON observation.observation_id=trade.source_observation_id
        WHERE trade.source_observation_id LIKE 'v1-domestic-order-%'
          AND {SIDE_SQL} IN ('01', '02')
          AND {PRODUCT_SQL} IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    after = inspect(connection)
    after.update({
        "revision_rows": connection.execute(
            "SELECT count(*) FROM silver.trade_event_revisions WHERE correction_reason IN ('legacy_all_buy_repair','v1_import_contract')"
        ).fetchone()[0],
        "current_buy": connection.execute(
            "SELECT count(*) FROM silver.trade_events_current WHERE side='buy'"
        ).fetchone()[0],
        "current_sell": connection.execute(
            "SELECT count(*) FROM silver.trade_events_current WHERE side='sell'"
        ).fetchone()[0],
        "suppressed_purchase_lots": connection.execute("""
            SELECT (SELECT count(*) FROM silver.purchase_lots)
                 - (SELECT count(*) FROM silver.purchase_lots_current)
        """).fetchone()[0],
    })
    return after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--motherduck", action="store_true")
    parser.add_argument("--database")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.motherduck == bool(args.database):
        raise RuntimeError("choose exactly one of --motherduck or --database")
    load_dotenv(PROJECT_ROOT / ".env")
    if args.motherduck:
        token = get_motherduck_token()
        if not token:
            raise RuntimeError("MOTHERDUCK_TOKEN required")
        target = f"md:{get_motherduck_database()}?motherduck_token={token}"
        target_label = f"md:{get_motherduck_database()}"
    else:
        target = args.database
        target_label = args.database
    connection = duckdb.connect(target)
    try:
        MigrationRunner(connection).require("0006")
        result = apply(connection) if args.apply else inspect(connection)
        print(json.dumps({
            "status": "applied" if args.apply else "dry_run",
            "target": target_label,
            **result,
        }, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
