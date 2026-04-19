"""Database connection management."""

import logging

import duckdb

from kis_portfolio.config import (
    get_db_mode,
    get_local_db_path,
    get_motherduck_database,
    get_motherduck_token,
)
from kis_portfolio.db.schema import init_schema

logger = logging.getLogger(__name__)

_con: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a singleton DB connection. Initialize schema on first use."""
    global _con
    if _con is not None:
        return _con

    mode = get_db_mode()
    if mode == "motherduck":
        token = get_motherduck_token()
        if not token:
            raise RuntimeError(
                "KIS_DB_MODE=motherduck requires MOTHERDUCK_TOKEN. "
                "Set MOTHERDUCK_TOKEN or use KIS_DB_MODE=local explicitly."
            )
        database = get_motherduck_database()
        conn_str = f"md:{database}?motherduck_token={token}"
        logger.info(f"Connecting to MotherDuck (md:{database})")
    elif mode == "local":
        local_path = get_local_db_path()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        conn_str = str(local_path)
        logger.info(f"Connecting to local DuckDB: {local_path}")
    else:
        raise ValueError("KIS_DB_MODE must be 'motherduck' or 'local'")

    _con = duckdb.connect(conn_str)
    init_schema(_con)
    return _con


def close_connection() -> None:
    """Close the singleton connection, primarily for tests."""
    global _con
    if _con is not None:
        _con.close()
        _con = None
