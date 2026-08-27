"""Machine-readable data object registry for warehouse governance checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataObject:
    name: str
    object_type: str
    layer: str
    target_schema: str
    write_mode: str
    backup_policy: str
    sensitivity: str
    purpose: str
    grain: str
    key: str
    physical_schema: str = "main"


DATA_OBJECTS = (
    DataObject(
        "schema_migrations", "table", "control", "control", "migration ledger",
        "excluded", "internal", "Applied database migration versions.",
        "one row per migration version", "version",
    ),
    DataObject(
        "market_calendar", "table", "control", "control", "upsert",
        "parquet", "internal", "Market open and close calendar used by batch jobs.",
        "one row per market and trade date", "market, trade_date",
    ),
    DataObject(
        "instrument_master", "table", "control", "control", "upsert",
        "parquet", "internal", "KIS instrument master used for classification.",
        "one row per symbol and market", "symbol, market",
    ),
    DataObject(
        "instrument_classification_overrides", "table", "control", "control", "upsert",
        "parquet", "confidential", "Local exposure classification overrides.",
        "one row per symbol and market", "symbol, market",
    ),
    DataObject(
        "portfolio_snapshots", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Domestic and pension balance observations with raw KIS JSON.",
        "one account observation per fetch", "id",
    ),
    DataObject(
        "overseas_asset_snapshots", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas balance and deposit observations with feeder aggregates.",
        "one overseas account observation per overview refresh", "id",
    ),
    DataObject(
        "order_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Domestic order query observations with raw response JSON.",
        "one account and query-range observation per fetch", "id",
    ),
    DataObject(
        "overseas_order_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas order query observations with raw response JSON.",
        "one account and query-filter observation per fetch", "id",
    ),
    DataObject(
        "overseas_transaction_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas transaction query observations with raw response JSON.",
        "one account and query-filter observation per fetch", "id",
    ),
    DataObject(
        "overseas_settlement_balance_snapshots", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Overseas settlement-basis balance observations.",
        "one account and base-date observation per fetch", "id",
    ),
    DataObject(
        "trade_profit_history", "table", "bronze", "bronze", "append-only",
        "parquet", "confidential", "Domestic or overseas profit report observations.",
        "one account, market, and requested-period observation", "id",
    ),
    DataObject(
        "price_history", "table", "silver", "silver", "insert-ignore; adjusted resync updates",
        "parquet", "internal", "Normalized domestic and overseas price history cache.",
        "one symbol, exchange, and market date", "symbol, exchange, date",
    ),
    DataObject(
        "exchange_rate_history", "table", "silver", "silver", "insert-ignore",
        "parquet", "internal", "Normalized exchange-rate history cache.",
        "one currency, date, and period", "currency, date, period",
    ),
    DataObject(
        "asset_overview_snapshots", "table", "silver", "silver", "append-only",
        "parquet", "confidential", "Canonical total-asset aggregate snapshots in KRW.",
        "one canonical portfolio overview per refresh", "id",
    ),
    DataObject(
        "asset_holding_snapshots", "table", "silver", "silver", "append-only",
        "parquet", "confidential", "Normalized holdings and cash rows for an overview snapshot.",
        "one holding or cash row per overview snapshot", "id; overview_snapshot_id is parent",
    ),
    DataObject(
        "domestic_orders", "table", "silver", "silver", "upsert",
        "parquet", "confidential", "Canonical domestic order and fill state.",
        "one KIS domestic order identity", "account_id, account_product_code, order_date, order_branch_no, order_no",
    ),
    DataObject(
        "overseas_orders", "table", "silver", "silver", "upsert",
        "parquet", "confidential", "Canonical overseas order and fill state.",
        "one KIS overseas order identity", "account_id, account_product_code, order_date, exchange_code, order_branch_no, order_no",
    ),
    DataObject(
        "overseas_transactions", "table", "silver", "silver", "upsert",
        "parquet", "confidential", "Canonical normalized overseas transactions.",
        "one stable raw transaction identity", "account_id, account_product_code, transaction_hash",
    ),
    DataObject(
        "portfolio_daily_snapshots", "view", "gold", "gold", "derived view",
        "excluded", "confidential", "Latest domestic or pension account snapshot for each day.",
        "one account and day", "account_id, account_type, snap_date",
    ),
    DataObject(
        "asset_overview_daily_snapshots", "view", "gold", "gold", "derived view",
        "excluded", "confidential", "Latest canonical total-asset overview for each day.",
        "one portfolio and day", "snap_date",
    ),
    DataObject(
        "kis_api_access_tokens", "table", "security", "security", "upsert",
        "excluded", "restricted", "Encrypted short-lived KIS API token cache.",
        "one account, account type, and app-key cache identity", "cache_key",
    ),
    DataObject(
        "auth_users", "table", "security", "security", "upsert",
        "excluded", "restricted", "Authorized MCP owner user records.",
        "one application user", "id; primary_email is unique",
    ),
    DataObject(
        "auth_identities", "table", "security", "security", "upsert",
        "excluded", "restricted", "OAuth provider identities linked to users.",
        "one provider subject", "id; provider, provider_subject is unique",
    ),
    DataObject(
        "oauth_clients", "table", "security", "security", "upsert",
        "excluded", "restricted", "Static and dynamically registered OAuth clients.",
        "one OAuth client", "client_id",
    ),
    DataObject(
        "oauth_grants", "table", "security", "security", "upsert and revoke",
        "excluded", "restricted", "User consent grants for OAuth clients and scopes.",
        "one user, client, and normalized scope", "id; user_id, client_id, scope is unique",
    ),
    DataObject(
        "oauth_authorization_codes", "table", "security", "security", "insert and consume",
        "excluded", "restricted", "Hashed one-time OAuth authorization codes.",
        "one authorization code", "id; code_digest is unique",
    ),
    DataObject(
        "oauth_tokens", "table", "security", "security", "insert and revoke",
        "excluded", "restricted", "Hashed OAuth access and refresh token state.",
        "one issued token", "id; token_digest is unique",
    ),
)


def managed_object_names(object_type: str | None = None) -> tuple[str, ...]:
    return tuple(
        item.name
        for item in DATA_OBJECTS
        if object_type is None or item.object_type == object_type
    )


def backup_table_names() -> tuple[str, ...]:
    return tuple(
        item.name
        for item in DATA_OBJECTS
        if item.object_type == "table" and item.backup_policy == "parquet"
    )


def object_by_name() -> dict[str, DataObject]:
    return {item.name: item for item in DATA_OBJECTS}
