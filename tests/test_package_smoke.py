import importlib
import importlib.util
import sys
from pathlib import Path

import pytest


def test_db_schema_initializes_with_configured_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "local")
    monkeypatch.setenv("KIS_DATA_DIR", str(tmp_path))

    import kis_mcp_server.db as kisdb

    kisdb = importlib.reload(kisdb)
    try:
        con = kisdb.get_connection()
        tables = {name for (name,) in con.execute("show tables").fetchall()}
    finally:
        kisdb.close_connection()

    assert {
        "exchange_rate_history",
        "portfolio_daily_snapshots",
        "portfolio_snapshots",
        "price_history",
        "schema_migrations",
        "trade_profit_history",
    }.issubset(tables)
    assert (tmp_path / "local" / "kis_portfolio.duckdb").exists()


def test_relative_data_dir_resolves_from_project_root(monkeypatch):
    monkeypatch.setenv("KIS_DATA_DIR", "var")

    import kis_mcp_server.config as config

    assert config.get_data_dir() == config.PROJECT_ROOT / "var"
    assert config.get_token_dir() == config.PROJECT_ROOT / "var" / "tokens"
    assert config.get_local_db_path() == config.PROJECT_ROOT / "var" / "local" / "kis_portfolio.duckdb"


def test_motherduck_mode_requires_token(monkeypatch):
    monkeypatch.setenv("KIS_DB_MODE", "motherduck")
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)

    import kis_mcp_server.db as kisdb

    kisdb = importlib.reload(kisdb)
    with pytest.raises(RuntimeError, match="MOTHERDUCK_TOKEN"):
        kisdb.get_connection()


def test_root_server_shim_exposes_mcp():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("root_server_shim", root / "server.py")
    server = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(server)

    assert server.mcp.name == "KIS MCP Server"


def test_backup_script_requires_motherduck_token(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "backup_motherduck_script", root / "scripts" / "backup_motherduck.py"
    )
    script = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(script)

    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.setattr(script, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["backup_motherduck.py"])

    assert script.main() == 2
