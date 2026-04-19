"""DuckDB/MotherDuck schema management."""

import logging

import duckdb

logger = logging.getLogger(__name__)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create required raw tables and curated views if they do not exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     VARCHAR PRIMARY KEY,
            applied_at  TIMESTAMP DEFAULT current_timestamp
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            symbol      VARCHAR NOT NULL,
            exchange    VARCHAR NOT NULL,   -- 'KRX', 'NAS', 'NYSE', 'AMS' 등
            date        DATE    NOT NULL,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            adjusted    BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (symbol, exchange, date)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rate_history (
            currency    VARCHAR NOT NULL,   -- 'USD', 'JPY', 'CNY', 'HKD', 'VND'
            date        DATE    NOT NULL,
            period      VARCHAR NOT NULL DEFAULT 'D',  -- D/W/M/Y
            rate        DOUBLE,
            created_at  TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (currency, date, period)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,  -- CANO
            account_type VARCHAR NOT NULL, -- 'ria','isa','irp','pension','brokerage'
            snapshot_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            total_eval_amt BIGINT,         -- 총평가금액 (원화 환산, 없으면 NULL)
            balance_data JSON,             -- API 원본 응답
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS trade_profit_history (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            market_type VARCHAR NOT NULL,  -- 'domestic' | 'overseas'
            start_date  DATE,
            end_date    DATE,
            fetched_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            data        JSON,
            PRIMARY KEY (id)
        )
    """)

    create_curated_views(con)
    logger.info("DB schema initialized")


def create_curated_views(con: duckdb.DuckDBPyConnection) -> None:
    """
    Create lightweight curated views for OLAP-style queries.

    Raw snapshots remain append-only. Views select representative rows for
    analysis without dropping raw ingestion history.
    """
    con.execute("""
        CREATE OR REPLACE VIEW portfolio_daily_snapshots AS
        SELECT
            account_id,
            account_type,
            CAST(snapshot_at AS DATE) AS snap_date,
            arg_max(snapshot_at, snapshot_at) AS snapshot_at,
            arg_max(total_eval_amt, snapshot_at) AS total_eval_amt,
            arg_max(balance_data, snapshot_at) AS balance_data
        FROM portfolio_snapshots
        WHERE total_eval_amt IS NOT NULL
        GROUP BY account_id, account_type, snap_date
    """)
