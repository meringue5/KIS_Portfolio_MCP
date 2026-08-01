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
            quality_status VARCHAR,
            quality_flags JSON,
            is_complete BOOLEAN,
            overview_data JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS cash_flow (
            idempotency_key VARCHAR NOT NULL,
            event_date DATE NOT NULL,
            account_label VARCHAR NOT NULL,
            flow_type VARCHAR NOT NULL,
            amount_krw BIGINT NOT NULL,
            amount_foreign DOUBLE,
            currency VARCHAR NOT NULL DEFAULT 'KRW',
            note VARCHAR,
            source VARCHAR NOT NULL DEFAULT 'manual',
            source_ref VARCHAR,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (idempotency_key),
            CHECK (flow_type IN ('deposit', 'withdrawal', 'fx_convert', 'dividend', 'tax'))
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            idempotency_key VARCHAR NOT NULL UNIQUE,
            trade_date DATE NOT NULL,
            account_label VARCHAR,
            symbol VARCHAR NOT NULL,
            market VARCHAR,
            side VARCHAR NOT NULL,
            quantity DOUBLE NOT NULL,
            price DOUBLE NOT NULL,
            currency VARCHAR NOT NULL DEFAULT 'KRW',
            trigger_type VARCHAR NOT NULL,
            trigger_detail VARCHAR,
            exit_plan VARCHAR,
            principle_check JSON,
            linked_order_no VARCHAR,
            linked_transaction_hash VARCHAR,
            realized_return_pct DOUBLE,
            note VARCHAR,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (id),
            CHECK (side IN ('buy', 'sell')),
            CHECK (trigger_type IN ('price', 'indicator', 'earnings', 'emotion', 'chatroom', 'mentor'))
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
            account_product_code VARCHAR,
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
        CREATE TABLE IF NOT EXISTS domestic_orders (
            account_id  VARCHAR NOT NULL,  -- CANO
            account_product_code VARCHAR NOT NULL, -- ACNT_PRDT_CD
            account_type VARCHAR NOT NULL, -- 'ria','isa','irp','pension','brokerage'
            order_date  DATE NOT NULL,
            order_branch_no VARCHAR NOT NULL DEFAULT '',
            order_no    VARCHAR NOT NULL,
            original_order_no VARCHAR,
            symbol      VARCHAR,
            symbol_name VARCHAR,
            side_code   VARCHAR,
            side_name   VARCHAR,
            order_type_code VARCHAR,
            order_type_name VARCHAR,
            order_time  VARCHAR,
            order_qty   BIGINT,
            total_order_qty BIGINT,
            order_price BIGINT,
            avg_price   BIGINT,
            filled_qty  BIGINT,
            filled_amount BIGINT,
            pending_qty BIGINT,
            cancel_confirm_qty BIGINT,
            rejected_qty BIGINT,
            is_cancelled BOOLEAN,
            condition_name VARCHAR,
            exchange_id_code VARCHAR,
            order_orgno VARCHAR,
            first_seen_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            last_seen_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            last_source VARCHAR,
            last_order_history_id VARCHAR,
            raw_data    JSON,
            PRIMARY KEY (account_id, account_product_code, order_date, order_branch_no, order_no)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS overseas_order_history (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            account_product_code VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL,
            start_date  DATE,
            end_date    DATE,
            exchange_code VARCHAR,
            symbol      VARCHAR,
            side_code   VARCHAR,
            fill_status_code VARCHAR,
            fetched_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            data        JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS overseas_orders (
            account_id  VARCHAR NOT NULL,
            account_product_code VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL,
            order_date  DATE NOT NULL,
            exchange_code VARCHAR NOT NULL DEFAULT '',
            order_branch_no VARCHAR NOT NULL DEFAULT '',
            order_no    VARCHAR NOT NULL,
            symbol      VARCHAR,
            symbol_name VARCHAR,
            side_code   VARCHAR,
            side_name   VARCHAR,
            order_type_code VARCHAR,
            order_type_name VARCHAR,
            order_time  VARCHAR,
            order_qty   DOUBLE,
            order_price DOUBLE,
            avg_price   DOUBLE,
            filled_qty  DOUBLE,
            filled_amount DOUBLE,
            pending_qty DOUBLE,
            currency    VARCHAR,
            first_seen_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            last_seen_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            last_source VARCHAR,
            last_order_history_id VARCHAR,
            raw_data    JSON,
            PRIMARY KEY (
                account_id, account_product_code, order_date,
                exchange_code, order_branch_no, order_no
            )
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS overseas_transaction_history (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            account_product_code VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL,
            start_date  DATE,
            end_date    DATE,
            exchange_code VARCHAR,
            symbol      VARCHAR,
            side_code   VARCHAR,
            loan_dvsn_cd VARCHAR,
            fetched_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            data        JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS overseas_transactions (
            account_id  VARCHAR NOT NULL,
            account_product_code VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL,
            transaction_hash VARCHAR NOT NULL,
            transaction_date DATE NOT NULL,
            exchange_code VARCHAR NOT NULL DEFAULT '',
            symbol      VARCHAR,
            symbol_name VARCHAR,
            side_code   VARCHAR,
            side_name   VARCHAR,
            transaction_type_code VARCHAR,
            transaction_type_name VARCHAR,
            quantity    DOUBLE,
            price       DOUBLE,
            amount      DOUBLE,
            fee         DOUBLE,
            tax         DOUBLE,
            currency    VARCHAR,
            settlement_amount DOUBLE,
            fx_rate     DOUBLE,
            order_no    VARCHAR,
            first_seen_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            last_seen_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            last_source VARCHAR,
            last_transaction_history_id VARCHAR,
            raw_data    JSON,
            PRIMARY KEY (account_id, account_product_code, transaction_hash)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS overseas_settlement_balance_snapshots (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            account_product_code VARCHAR NOT NULL,
            account_type VARCHAR NOT NULL,
            base_date   DATE,
            wcrc_frcr_dvsn_cd VARCHAR,
            inqr_dvsn_cd VARCHAR,
            fetched_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            data        JSON,
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS market_calendar (
            market      VARCHAR NOT NULL,  -- 'krx'
            trade_date  DATE NOT NULL,
            is_open     BOOLEAN NOT NULL,
            open_time_local VARCHAR,
            close_time_local VARCHAR,
            timezone    VARCHAR NOT NULL DEFAULT 'Asia/Seoul',
            source      VARCHAR,
            note        VARCHAR,
            raw_data    JSON,
            updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (market, trade_date)
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
    _ensure_column(con, "order_history", "account_product_code", "VARCHAR")
    _ensure_column(con, "asset_overview_snapshots", "quality_status", "VARCHAR")
    _ensure_column(con, "asset_overview_snapshots", "quality_flags", "JSON")
    _ensure_column(con, "asset_overview_snapshots", "is_complete", "BOOLEAN")

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
            coalesce(
                arg_max(quality_status, snapshot_at),
                'legacy_unassessed'
            ) AS quality_status,
            coalesce(
                arg_max(quality_flags, snapshot_at),
                CAST('["legacy_cash_semantics_unverified"]' AS JSON)
            ) AS quality_flags,
            coalesce(arg_max(is_complete, snapshot_at), FALSE) AS is_complete,
            arg_max(overview_data, snapshot_at) AS overview_data
        FROM asset_overview_snapshots
        WHERE total_eval_amt_krw IS NOT NULL
        GROUP BY snap_date
    """)

    con.execute("""
        CREATE OR REPLACE VIEW asset_return_daily AS
        WITH snapshot_changes AS (
            SELECT
                snap_date,
                snapshot_at,
                total_eval_amt_krw,
                quality_status,
                is_complete,
                lag(total_eval_amt_krw) OVER (ORDER BY snap_date) AS prev_total_eval_amt_krw
            FROM asset_overview_daily_snapshots
        ),
        daily_flows AS (
            SELECT
                event_date,
                sum(amount_krw) AS net_activity_krw,
                sum(CASE
                    WHEN flow_type IN ('deposit', 'withdrawal') THEN amount_krw
                    ELSE 0
                END) AS net_external_flow_krw
            FROM cash_flow
            GROUP BY event_date
        )
        SELECT
            s.snap_date,
            s.snapshot_at,
            s.total_eval_amt_krw,
            s.prev_total_eval_amt_krw,
            coalesce(f.net_activity_krw, 0) AS net_activity_krw,
            coalesce(f.net_external_flow_krw, 0) AS net_external_flow_krw,
            s.total_eval_amt_krw - s.prev_total_eval_amt_krw AS balance_change_krw,
            s.total_eval_amt_krw - s.prev_total_eval_amt_krw
                - coalesce(f.net_external_flow_krw, 0) AS flow_adjusted_change_krw,
            round(
                ((s.total_eval_amt_krw - coalesce(f.net_external_flow_krw, 0))
                    / nullif(s.prev_total_eval_amt_krw, 0) - 1) * 100,
                4
            ) AS daily_twr_return_pct,
            s.quality_status,
            s.is_complete
        FROM snapshot_changes s
        LEFT JOIN daily_flows f ON f.event_date = s.snap_date
    """)
