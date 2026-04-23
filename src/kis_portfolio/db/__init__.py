"""Database package public API."""

from kis_portfolio.db.connection import close_connection, get_connection
from kis_portfolio.db.repository import (
    get_asset_overview_snapshots,
    get_classification_override,
    get_classification_override_map,
    get_exchange_rate_history,
    get_instrument_master,
    get_instrument_master_map,
    get_portfolio_snapshots,
    get_price_history,
    has_price_history,
    insert_asset_holding_snapshots,
    insert_asset_overview_snapshot,
    insert_order_history,
    insert_overseas_asset_snapshot,
    insert_portfolio_snapshot,
    insert_trade_profit,
    upsert_instrument_master,
    upsert_exchange_rate_history,
    upsert_price_history,
)
from kis_portfolio.db.schema import init_schema

__all__ = [
    "close_connection",
    "get_asset_overview_snapshots",
    "get_classification_override",
    "get_classification_override_map",
    "get_connection",
    "get_exchange_rate_history",
    "get_instrument_master",
    "get_instrument_master_map",
    "get_portfolio_snapshots",
    "get_price_history",
    "has_price_history",
    "init_schema",
    "insert_asset_holding_snapshots",
    "insert_asset_overview_snapshot",
    "insert_order_history",
    "insert_overseas_asset_snapshot",
    "insert_portfolio_snapshot",
    "insert_trade_profit",
    "upsert_instrument_master",
    "upsert_exchange_rate_history",
    "upsert_price_history",
]
