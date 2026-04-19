"""Database package public API."""

from kis_portfolio.db.connection import close_connection, get_connection
from kis_portfolio.db.repository import (
    get_exchange_rate_history,
    get_portfolio_snapshots,
    get_price_history,
    has_price_history,
    insert_portfolio_snapshot,
    insert_trade_profit,
    upsert_exchange_rate_history,
    upsert_price_history,
)
from kis_portfolio.db.schema import init_schema

__all__ = [
    "close_connection",
    "get_connection",
    "get_exchange_rate_history",
    "get_portfolio_snapshots",
    "get_price_history",
    "has_price_history",
    "init_schema",
    "insert_portfolio_snapshot",
    "insert_trade_profit",
    "upsert_exchange_rate_history",
    "upsert_price_history",
]
