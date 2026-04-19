"""Portfolio time-series analytics."""

import duckdb

from kis_mcp_server.db.utils import rows_to_dicts


def get_portfolio_anomalies(
    con: duckdb.DuckDBPyConnection,
    account_id: str,
    z_threshold: float = 2.0,
    lookback_days: int = 90,
    limit: int = 20,
) -> dict:
    """Detect anomalous daily portfolio value changes."""
    z_threshold = max(0.1, float(z_threshold))
    lookback_days = max(2, min(int(lookback_days), 3650))
    limit = max(1, min(int(limit), 250))

    sql = f"""
        WITH daily_returns AS (
            SELECT
                account_id,
                snap_date,
                total_eval_amt,
                lag(total_eval_amt) OVER (
                    PARTITION BY account_id ORDER BY snap_date
                ) AS prev_total_eval_amt
            FROM portfolio_daily_snapshots
            WHERE account_id = ?
              AND snap_date >= current_date - INTERVAL '{lookback_days} days'
              AND total_eval_amt IS NOT NULL
        ),
        return_stats AS (
            SELECT
                account_id,
                avg(return_pct) AS mean_return,
                stddev(return_pct) AS std_return
            FROM (
                SELECT
                    account_id,
                    (total_eval_amt - prev_total_eval_amt)
                        / nullif(prev_total_eval_amt, 0) * 100 AS return_pct
                FROM daily_returns
                WHERE prev_total_eval_amt IS NOT NULL
            )
            GROUP BY account_id
        )
        SELECT
            d.account_id,
            d.snap_date,
            d.total_eval_amt,
            d.prev_total_eval_amt,
            round(
                (d.total_eval_amt - d.prev_total_eval_amt)
                    / nullif(d.prev_total_eval_amt, 0) * 100,
                2
            ) AS return_pct,
            round((
                ((d.total_eval_amt - d.prev_total_eval_amt)
                    / nullif(d.prev_total_eval_amt, 0) * 100) - s.mean_return
            ) / nullif(s.std_return, 0), 2) AS z_score,
            CASE
                WHEN abs((
                    ((d.total_eval_amt - d.prev_total_eval_amt)
                        / nullif(d.prev_total_eval_amt, 0) * 100) - s.mean_return
                ) / nullif(s.std_return, 0)) >= {z_threshold}
                THEN '이상치'
                ELSE '정상'
            END AS status
        FROM daily_returns d
        JOIN return_stats s ON d.account_id = s.account_id
        WHERE d.prev_total_eval_amt IS NOT NULL
        ORDER BY abs((
            ((d.total_eval_amt - d.prev_total_eval_amt)
                / nullif(d.prev_total_eval_amt, 0) * 100) - s.mean_return
        ) / nullif(s.std_return, 0)) DESC NULLS LAST
        LIMIT ?
    """
    rows = rows_to_dicts(con.execute(sql, [account_id, limit]))
    anomaly_count = sum(1 for row in rows if row.get("status") == "이상치")
    if not rows:
        daily_count = con.execute("""
            SELECT count(*)
            FROM portfolio_daily_snapshots
            WHERE account_id=? AND total_eval_amt IS NOT NULL
        """, [account_id]).fetchone()[0]
        return {
            "account_id": account_id,
            "count": 0,
            "message": f"데이터가 부족합니다 (총평가금액이 있는 일별 스냅샷 {daily_count}일)",
            "data": [],
        }

    return {
        "account_id": account_id,
        "lookback_days": lookback_days,
        "z_threshold": z_threshold,
        "count": len(rows),
        "anomaly_count": anomaly_count,
        "data": rows,
    }


def get_portfolio_trend(
    con: duckdb.DuckDBPyConnection,
    account_id: str,
    short_window: int = 7,
    long_window: int = 30,
    lookback_days: int = 90,
) -> dict:
    """Calculate short/long moving averages over daily portfolio values."""
    short_window = max(2, min(int(short_window), 365))
    long_window = max(short_window, min(int(long_window), 3650))
    lookback_days = max(long_window, min(int(lookback_days), 3650))

    sql = f"""
        WITH trend_rows AS (
            SELECT
                account_id,
                snap_date,
                total_eval_amt,
                count(total_eval_amt) OVER (
                    PARTITION BY account_id
                    ORDER BY snap_date
                    ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW
                ) AS long_observations,
                round(avg(total_eval_amt) OVER (
                    PARTITION BY account_id
                    ORDER BY snap_date
                    ROWS BETWEEN {short_window - 1} PRECEDING AND CURRENT ROW
                ), 0) AS short_sma,
                round(avg(total_eval_amt) OVER (
                    PARTITION BY account_id
                    ORDER BY snap_date
                    ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW
                ), 0) AS long_sma
            FROM portfolio_daily_snapshots
            WHERE account_id = ?
              AND snap_date >= current_date - INTERVAL '{lookback_days} days'
              AND total_eval_amt IS NOT NULL
        )
        SELECT
            account_id,
            snap_date,
            total_eval_amt,
            short_sma,
            long_sma,
            CASE
                WHEN short_sma > long_sma THEN '상승추세'
                WHEN short_sma < long_sma THEN '하락추세'
                ELSE '중립'
            END AS trend
        FROM trend_rows
        WHERE long_observations >= {long_window}
        ORDER BY snap_date DESC
    """
    rows = rows_to_dicts(con.execute(sql, [account_id]))
    if not rows:
        daily_count = con.execute("""
            SELECT count(*)
            FROM portfolio_daily_snapshots
            WHERE account_id=? AND total_eval_amt IS NOT NULL
        """, [account_id]).fetchone()[0]
        return {
            "account_id": account_id,
            "count": 0,
            "message": f"데이터가 부족합니다 (현재 {daily_count}일, 최소 {long_window}일 필요)",
            "data": [],
        }

    return {
        "account_id": account_id,
        "short_window": short_window,
        "long_window": long_window,
        "lookback_days": lookback_days,
        "count": len(rows),
        "latest": rows[0],
        "data": rows,
    }
