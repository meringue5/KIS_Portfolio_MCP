"""Portfolio time-series analytics."""

import duckdb

from kis_portfolio.db.utils import rows_to_dicts


def get_latest_portfolio_summary(
    con: duckdb.DuckDBPyConnection,
    account_id: str = "",
    lookback_days: int = 30,
) -> dict:
    """Summarize the latest known portfolio value across accounts."""
    lookback_days = max(1, min(int(lookback_days), 3650))

    account_filter = "AND account_id = ?" if account_id else ""
    params: list = [account_id] if account_id else []
    rows = rows_to_dicts(con.execute(f"""
        WITH ranked AS (
            SELECT
                account_id,
                account_type,
                snap_date,
                snapshot_at,
                total_eval_amt,
                row_number() OVER (
                    PARTITION BY account_id
                    ORDER BY snapshot_at DESC
                ) AS rn
            FROM portfolio_daily_snapshots
            WHERE total_eval_amt IS NOT NULL
              AND snap_date >= current_date - INTERVAL '{lookback_days} days'
              {account_filter}
        )
        SELECT account_id, account_type, snap_date, snapshot_at, total_eval_amt
        FROM ranked
        WHERE rn = 1
        ORDER BY account_type, account_id
    """, params))

    if not rows:
        return {
            "account_id": account_id or "ALL",
            "lookback_days": lookback_days,
            "account_count": 0,
            "total_eval_amt": 0,
            "by_account_type": [],
            "accounts": [],
            "message": "최근 포트폴리오 스냅샷이 없습니다.",
        }

    total_eval_amt = sum(row.get("total_eval_amt") or 0 for row in rows)
    type_totals: dict[str, dict] = {}
    for row in rows:
        account_type = row.get("account_type") or "unknown"
        bucket = type_totals.setdefault(
            account_type,
            {"account_type": account_type, "account_count": 0, "total_eval_amt": 0},
        )
        bucket["account_count"] += 1
        bucket["total_eval_amt"] += row.get("total_eval_amt") or 0

    return {
        "account_id": account_id or "ALL",
        "lookback_days": lookback_days,
        "account_count": len(rows),
        "total_eval_amt": total_eval_amt,
        "latest_snapshot_at": max(row["snapshot_at"] for row in rows if row.get("snapshot_at")),
        "by_account_type": list(type_totals.values()),
        "accounts": rows,
    }


def get_portfolio_daily_change(
    con: duckdb.DuckDBPyConnection,
    account_id: str = "",
    days: int = 14,
) -> dict:
    """Return daily portfolio value changes for one account or all accounts."""
    days = max(2, min(int(days), 3650))
    account_filter = "WHERE account_id = ?" if account_id else ""
    params: list = [account_id, days] if account_id else [days]

    rows = rows_to_dicts(con.execute(f"""
        WITH daily AS (
            SELECT
                snap_date,
                {'account_id,' if account_id else "'ALL' AS account_id,"}
                sum(total_eval_amt) AS total_eval_amt,
                count(DISTINCT account_id) AS account_count
            FROM portfolio_daily_snapshots
            {account_filter}
            GROUP BY snap_date{', account_id' if account_id else ''}
        ),
        changes AS (
            SELECT
                account_id,
                snap_date,
                total_eval_amt,
                lag(total_eval_amt) OVER (ORDER BY snap_date) AS prev_total_eval_amt,
                account_count
            FROM daily
        )
        SELECT
            account_id,
            snap_date,
            total_eval_amt,
            prev_total_eval_amt,
            total_eval_amt - prev_total_eval_amt AS change_amt,
            round(
                (total_eval_amt - prev_total_eval_amt)
                    / nullif(prev_total_eval_amt, 0) * 100,
                2
            ) AS change_pct,
            account_count
        FROM changes
        ORDER BY snap_date DESC
        LIMIT ?
    """, params))

    if not rows:
        return {
            "account_id": account_id or "ALL",
            "days": days,
            "count": 0,
            "latest": None,
            "data": [],
            "message": "일별 포트폴리오 스냅샷이 없습니다.",
        }

    return {
        "account_id": account_id or "ALL",
        "days": days,
        "count": len(rows),
        "latest": rows[0],
        "data": rows,
    }


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
