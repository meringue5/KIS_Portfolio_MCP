from unittest.mock import MagicMock

import pytest

from kis_portfolio.db import connection


def test_motherduck_runtime_verifies_schema_without_running_ddl(monkeypatch):
    fake = MagicMock()
    fake.execute.return_value.fetchall.return_value = [
        ("portfolio_snapshots",), ("asset_overview_snapshots",), ("price_history",),
    ]
    monkeypatch.setattr(connection, "_con", None)
    monkeypatch.setattr(connection, "get_db_mode", lambda: "motherduck")
    monkeypatch.setattr(connection, "get_motherduck_token", lambda: "redacted")
    monkeypatch.setattr(connection, "get_motherduck_database", lambda: "db")
    monkeypatch.setattr(connection.duckdb, "connect", lambda _: fake)
    ddl = MagicMock()
    monkeypatch.setattr(connection, "init_schema", ddl)
    try:
        assert connection.get_connection() is fake
        ddl.assert_not_called()
    finally:
        connection._con = None


def test_motherduck_runtime_fails_closed_when_migration_is_missing(monkeypatch):
    fake = MagicMock()
    fake.execute.return_value.fetchall.return_value = [("portfolio_snapshots",)]
    monkeypatch.setattr(connection, "_con", None)
    monkeypatch.setattr(connection, "get_db_mode", lambda: "motherduck")
    monkeypatch.setattr(connection, "get_motherduck_token", lambda: "redacted")
    monkeypatch.setattr(connection, "get_motherduck_database", lambda: "db")
    monkeypatch.setattr(connection.duckdb, "connect", lambda _: fake)
    with pytest.raises(RuntimeError, match="migration job"):
        connection.get_connection()
    assert fake.close.called
    connection._con = None
