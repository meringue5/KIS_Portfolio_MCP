"""DuckDB/MotherDuck schema management."""

import logging

import duckdb

logger = logging.getLogger(__name__)


def _ensure_column(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    con.execute(
        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_definition}"
    )


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
        CREATE TABLE IF NOT EXISTS overseas_asset_snapshots (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL,
            snapshot_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            stock_eval_amt_krw BIGINT,
            cash_amt_krw BIGINT,
            total_asset_amt_krw BIGINT,
            fx_data     JSON,
            balance_data JSON,
            deposit_data JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS asset_overview_snapshots (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            snapshot_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            base_currency VARCHAR NOT NULL DEFAULT 'KRW',
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
            overview_data JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS asset_holding_snapshots (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            overview_snapshot_id VARCHAR NOT NULL,
            snapshot_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            account_label VARCHAR,
            account_type VARCHAR,
            symbol      VARCHAR,
            name        VARCHAR,
            market      VARCHAR,
            basis_category VARCHAR,
            exposure_type VARCHAR,
            exposure_region VARCHAR,
            asset_subtype VARCHAR,
            confidence  VARCHAR,
            quantity    DOUBLE,
            value_krw   BIGINT,
            value_foreign DOUBLE,
            currency    VARCHAR,
            raw_data    JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS instrument_master (
            symbol      VARCHAR NOT NULL,
            market      VARCHAR NOT NULL,
            standard_code VARCHAR,
            name        VARCHAR,
            group_code  VARCHAR,
            etp_code    VARCHAR,
            idx_large_code VARCHAR,
            idx_mid_code VARCHAR,
            idx_small_code VARCHAR,
            raw_data    JSON,
            updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (symbol, market)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS instrument_classification_overrides (
            symbol      VARCHAR NOT NULL,
            market      VARCHAR NOT NULL DEFAULT 'KRX',
            exposure_type VARCHAR NOT NULL,
            exposure_region VARCHAR,
            asset_subtype VARCHAR,
            reason      VARCHAR,
            updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (symbol, market)
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

    con.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL, -- 'ria','isa','irp','pension','brokerage'
            market_type VARCHAR NOT NULL,  -- 'domestic' | future 'overseas'
            start_date  DATE,
            end_date    DATE,
            fetched_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            data        JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS kis_api_access_tokens (
            cache_key           VARCHAR NOT NULL,
            account_id          VARCHAR NOT NULL,
            account_type        VARCHAR NOT NULL,
            app_key_fingerprint VARCHAR NOT NULL,
            token_ciphertext    VARCHAR NOT NULL,
            token_type          VARCHAR,
            issued_at           TIMESTAMP NOT NULL,
            expires_at          TIMESTAMP NOT NULL,
            expires_in          BIGINT,
            response_expiry_raw VARCHAR,
            migrated_from_file  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at          TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (cache_key)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS auth_users (
            id            VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            primary_email VARCHAR NOT NULL UNIQUE,
            display_name  VARCHAR,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS auth_identities (
            id               VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            user_id          VARCHAR NOT NULL,
            provider         VARCHAR NOT NULL,
            provider_subject VARCHAR NOT NULL,
            email            VARCHAR,
            email_verified   BOOLEAN NOT NULL DEFAULT FALSE,
            profile_data     JSON,
            created_at       TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at       TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (id),
            UNIQUE (provider, provider_subject)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id                    VARCHAR NOT NULL,
            client_secret_hash           VARCHAR NOT NULL,
            redirect_uris                JSON NOT NULL,
            grant_types                  JSON NOT NULL,
            response_types               JSON NOT NULL,
            scope                        VARCHAR,
            client_name                  VARCHAR,
            token_endpoint_auth_method   VARCHAR NOT NULL DEFAULT 'client_secret_basic',
            metadata                     JSON,
            client_id_issued_at          TIMESTAMP,
            client_secret_expires_at     TIMESTAMP,
            created_at                   TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at                   TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (client_id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS oauth_grants (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            user_id     VARCHAR NOT NULL,
            client_id   VARCHAR NOT NULL,
            scope       VARCHAR NOT NULL,
            granted_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            revoked_at  TIMESTAMP,
            created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (id),
            UNIQUE (user_id, client_id, scope)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
            id                              VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            user_id                         VARCHAR NOT NULL,
            client_id                       VARCHAR NOT NULL,
            grant_id                        VARCHAR,
            code_digest                     VARCHAR NOT NULL UNIQUE,
            scope                           VARCHAR NOT NULL,
            redirect_uri                    VARCHAR NOT NULL,
            redirect_uri_provided_explicitly BOOLEAN NOT NULL DEFAULT FALSE,
            code_challenge                  VARCHAR NOT NULL,
            resource                        VARCHAR,
            state                           VARCHAR,
            provider                        VARCHAR,
            created_at                      TIMESTAMP NOT NULL DEFAULT current_timestamp,
            expires_at                      TIMESTAMP NOT NULL,
            consumed_at                     TIMESTAMP,
            revoked_at                      TIMESTAMP,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id               VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            user_id          VARCHAR NOT NULL,
            client_id        VARCHAR NOT NULL,
            grant_id         VARCHAR,
            token_type       VARCHAR NOT NULL,
            token_digest     VARCHAR NOT NULL UNIQUE,
            scope            VARCHAR NOT NULL,
            resource         VARCHAR,
            created_at       TIMESTAMP NOT NULL DEFAULT current_timestamp,
            expires_at       TIMESTAMP,
            revoked_at       TIMESTAMP,
            parent_token_id  VARCHAR,
            replaces_token_id VARCHAR,
            PRIMARY KEY (id)
        )
    """)

    _ensure_column(con, "oauth_clients", "metadata", "JSON")
    _ensure_column(con, "oauth_authorization_codes", "resource", "VARCHAR")
    _ensure_column(con, "oauth_tokens", "resource", "VARCHAR")
    _ensure_column(con, "kis_api_access_tokens", "app_key_fingerprint", "VARCHAR")
    _ensure_column(con, "kis_api_access_tokens", "token_ciphertext", "VARCHAR")
    _ensure_column(con, "kis_api_access_tokens", "token_type", "VARCHAR")
    _ensure_column(con, "kis_api_access_tokens", "issued_at", "TIMESTAMP")
    _ensure_column(con, "kis_api_access_tokens", "expires_at", "TIMESTAMP")
    _ensure_column(con, "kis_api_access_tokens", "expires_in", "BIGINT")
    _ensure_column(con, "kis_api_access_tokens", "response_expiry_raw", "VARCHAR")
    _ensure_column(con, "kis_api_access_tokens", "migrated_from_file", "BOOLEAN")
    _ensure_column(con, "kis_api_access_tokens", "created_at", "TIMESTAMP")
    _ensure_column(con, "kis_api_access_tokens", "updated_at", "TIMESTAMP")

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

    con.execute("""
        CREATE OR REPLACE VIEW asset_overview_daily_snapshots AS
        SELECT
            CAST(snapshot_at AS DATE) AS snap_date,
            arg_max(id, snapshot_at) AS id,
            arg_max(snapshot_at, snapshot_at) AS snapshot_at,
            arg_max(base_currency, snapshot_at) AS base_currency,
            arg_max(domestic_eval_amt_krw, snapshot_at) AS domestic_eval_amt_krw,
            arg_max(overseas_stock_eval_amt_krw, snapshot_at) AS overseas_stock_eval_amt_krw,
            arg_max(overseas_cash_amt_krw, snapshot_at) AS overseas_cash_amt_krw,
            arg_max(overseas_total_asset_amt_krw, snapshot_at) AS overseas_total_asset_amt_krw,
            arg_max(total_eval_amt_krw, snapshot_at) AS total_eval_amt_krw,
            arg_max(domestic_pct, snapshot_at) AS domestic_pct,
            arg_max(overseas_pct, snapshot_at) AS overseas_pct,
            arg_max(overseas_stock_pct, snapshot_at) AS overseas_stock_pct,
            arg_max(overseas_cash_pct, snapshot_at) AS overseas_cash_pct,
            arg_max(domestic_direct_amt_krw, snapshot_at) AS domestic_direct_amt_krw,
            arg_max(overseas_direct_amt_krw, snapshot_at) AS overseas_direct_amt_krw,
            arg_max(overseas_indirect_amt_krw, snapshot_at) AS overseas_indirect_amt_krw,
            arg_max(cash_amt_krw, snapshot_at) AS cash_amt_krw,
            arg_max(unknown_amt_krw, snapshot_at) AS unknown_amt_krw,
            arg_max(allocation_data, snapshot_at) AS allocation_data,
            arg_max(classification_summary, snapshot_at) AS classification_summary,
            arg_max(overview_data, snapshot_at) AS overview_data
        FROM asset_overview_snapshots
        WHERE total_eval_amt_krw IS NOT NULL
        GROUP BY snap_date
    """)
