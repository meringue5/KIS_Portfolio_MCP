"""Database connection management."""

import logging
import time
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

REQUIRED_RUNTIME_TABLES = frozenset({
    "portfolio_snapshots",
    "asset_overview_snapshots",
    "price_history",
})


def _verify_runtime_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Fail closed when a managed production schema was not migrated.

    This query is intentionally read-only. Schema creation and migration belong
    to the release job, never a serving identity or cold start.
    """
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    available = {str(row[0]) for row in rows}
    missing = sorted(REQUIRED_RUNTIME_TABLES - available)
    if missing:
        raise RuntimeError(
            "Managed MotherDuck schema is incomplete; run the migration job before startup: "
            + ", ".join(missing)
        )


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a singleton DB connection and verify its managed schema."""
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
    try:
        if mode == "local":
            for attempt in range(3):
                try:
                    init_schema(_con)
                    break
                except duckdb.TransactionException as exc:
                    if "write-write conflict" not in str(exc).lower() or attempt == 2:
                        raise
                    time.sleep(0.2 * (attempt + 1))
        else:
            _verify_runtime_schema(_con)
    except Exception:
        _con.close()
        _con = None
        raise
    return _con


def close_connection() -> None:
    """Close the singleton connection, primarily for tests."""
    global _con
    if _con is not None:
        _con.close()
        _con = None
