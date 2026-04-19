import duckdb

from kis_mcp_server.analytics.bollinger import get_bollinger_bands
from kis_mcp_server.analytics.portfolio import get_portfolio_anomalies, get_portfolio_trend
from kis_mcp_server.db.schema import init_schema


def make_connection():
    con = duckdb.connect(":memory:")
    init_schema(con)
    return con


def seed_price_history(con, count=30):
    for day in range(1, count + 1):
        con.execute(
            """
            INSERT INTO price_history (symbol, exchange, date, open, high, low, close, volume)
            VALUES (?, ?, DATE '2024-01-01' + (? * INTERVAL '1 day'), ?, ?, ?, ?, ?)
            """,
            ["005930", "KRX", day - 1, 100 + day, 110 + day, 90 + day, 100 + day, 1000 + day],
        )


def seed_portfolio_snapshots(con, account_id="acct", count=40):
    for day in range(1, count + 1):
        con.execute(
            """
            INSERT INTO portfolio_snapshots
                (account_id, account_type, snapshot_at, total_eval_amt, balance_data)
            VALUES (?, ?, DATE '2024-01-01' + (? * INTERVAL '1 day'), ?, ?)
            """,
            [account_id, "brokerage", day - 1, 1_000_000 + day * 10_000, '{"ok": true}'],
        )


def test_get_bollinger_bands_returns_recent_rows():
    con = make_connection()
    seed_price_history(con)

    result = get_bollinger_bands(con, "005930", "KRX", window=20, limit=3)

    assert result["count"] == 3
    assert result["latest"]["date"] == "2024-01-30"
    assert result["latest"]["signal"] == "중립"


def test_get_bollinger_bands_reports_insufficient_data():
    con = make_connection()
    seed_price_history(con, count=5)

    result = get_bollinger_bands(con, "005930", "KRX", window=20)

    assert result["count"] == 0
    assert "데이터가 부족합니다" in result["message"]


def test_get_portfolio_trend_uses_daily_curated_view():
    con = make_connection()
    seed_portfolio_snapshots(con)

    result = get_portfolio_trend(con, "acct", short_window=7, long_window=30, lookback_days=3650)

    assert result["count"] == 11
    assert result["latest"]["snap_date"] == "2024-02-09"
    assert result["latest"]["trend"] == "상승추세"


def test_get_portfolio_anomalies_returns_ranked_rows():
    con = make_connection()
    seed_portfolio_snapshots(con)

    result = get_portfolio_anomalies(con, "acct", z_threshold=2.0, lookback_days=3650, limit=5)

    assert result["count"] == 5
    assert result["data"][0]["account_id"] == "acct"
