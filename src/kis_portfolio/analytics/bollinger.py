"""Bollinger band analytics."""

import duckdb

from kis_portfolio.db.utils import rows_to_dicts


def get_bollinger_bands(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
    exchange: str = "KRX",
    window: int = 20,
    num_std: float = 2.0,
    limit: int = 60,
) -> dict:
    """Calculate Bollinger bands from cached price history."""
    window = max(2, min(int(window), 252))
    num_std = max(0.1, float(num_std))
    limit = max(1, min(int(limit), 250))

    sql = f"""
        WITH price_stats AS (
            SELECT
                symbol,
                exchange,
                date,
                close,
                count(close) OVER (
                    PARTITION BY symbol, exchange
                    ORDER BY date
                    ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
                ) AS observations,
                avg(close) OVER (
                    PARTITION BY symbol, exchange
                    ORDER BY date
                    ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
                ) AS sma,
                stddev(close) OVER (
                    PARTITION BY symbol, exchange
                    ORDER BY date
                    ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
                ) AS std
            FROM price_history
            WHERE symbol = ? AND exchange = ? AND close IS NOT NULL
        )
        SELECT
            symbol,
            exchange,
            date,
            close,
            round(sma, 2) AS sma,
            round(sma + {num_std} * std, 2) AS upper_band,
            round(sma - {num_std} * std, 2) AS lower_band,
            round((close - sma) / nullif(std, 0), 2) AS z_score,
            CASE
                WHEN close > sma + {num_std} * std THEN '과매수'
                WHEN close < sma - {num_std} * std THEN '과매도'
                ELSE '중립'
            END AS signal
        FROM price_stats
        WHERE observations >= {window}
        ORDER BY date DESC
        LIMIT ?
    """
    rows = rows_to_dicts(con.execute(sql, [symbol, exchange, limit]))
    if not rows:
        total_rows = con.execute("""
            SELECT count(*)
            FROM price_history
            WHERE symbol=? AND exchange=? AND close IS NOT NULL
        """, [symbol, exchange]).fetchone()[0]
        return {
            "symbol": symbol,
            "exchange": exchange,
            "count": 0,
            "message": f"데이터가 부족합니다 (현재 {total_rows}개, 최소 {window}개 필요)",
            "data": [],
        }

    return {
        "symbol": symbol,
        "exchange": exchange,
        "window": window,
        "num_std": num_std,
        "count": len(rows),
        "latest": rows[0],
        "data": rows,
    }
