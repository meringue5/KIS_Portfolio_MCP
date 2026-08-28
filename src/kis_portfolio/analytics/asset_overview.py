"""Analytics over canonical total-asset overview snapshots."""

from __future__ import annotations

import duckdb

from kis_portfolio.application.valuation_change import read_latest_v1_valuation_change
from kis_portfolio.common.values import rows_to_dicts


def get_total_asset_history(
    con: duckdb.DuckDBPyConnection,
    days: int = 30,
    limit: int = 60,
) -> dict:
    days = max(1, min(int(days), 3650))
    limit = max(1, min(int(limit), 3650))
    rows = rows_to_dicts(con.execute(f"""
        SELECT snap_date, snapshot_at, domestic_eval_amt_krw, overseas_stock_eval_amt_krw,
               overseas_cash_amt_krw, overseas_total_asset_amt_krw, total_eval_amt_krw
        FROM asset_overview_daily_snapshots
        WHERE snap_date >= current_date - INTERVAL '{days} days'
        ORDER BY snap_date DESC
        LIMIT ?
    """, [limit]))
    return {
        "days": days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 스냅샷이 없습니다.",
    }


def get_total_asset_daily_change(
    con: duckdb.DuckDBPyConnection,
    days: int = 14,
) -> dict:
    days = max(2, min(int(days), 3650))
    rows = rows_to_dicts(con.execute("""
        WITH changes AS (
            SELECT
                id,
                snap_date,
                snapshot_at,
                total_eval_amt_krw,
                quality_status,
                is_complete,
                lag(total_eval_amt_krw) OVER (ORDER BY snap_date) AS prev_total_eval_amt_krw
            FROM asset_overview_daily_snapshots
        )
        SELECT
            snap_date,
            id AS snapshot_ref,
            snapshot_at,
            total_eval_amt_krw,
            prev_total_eval_amt_krw,
            quality_status,
            is_complete,
            total_eval_amt_krw - prev_total_eval_amt_krw AS change_amt,
            round(
                (total_eval_amt_krw - prev_total_eval_amt_krw)
                    / nullif(prev_total_eval_amt_krw, 0) * 100,
                2
            ) AS change_pct
        FROM changes
        ORDER BY snap_date DESC
        LIMIT ?
    """, [days]))
    contribution = read_latest_v1_valuation_change(con, top_n=5, include_account_breakdown=True)
    return {
        "days": days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "valuation_change_contribution": contribution,
        "message": None if rows else "총자산 일별 스냅샷이 없습니다.",
    }


def get_total_asset_trend(
    con: duckdb.DuckDBPyConnection,
    short_window: int = 7,
    long_window: int = 30,
    lookback_days: int = 90,
) -> dict:
    short_window = max(2, min(int(short_window), 365))
    long_window = max(short_window, min(int(long_window), 3650))
    lookback_days = max(long_window, min(int(lookback_days), 3650))
    rows = rows_to_dicts(con.execute(f"""
        WITH trend_rows AS (
            SELECT
                snap_date,
                total_eval_amt_krw,
                count(total_eval_amt_krw) OVER (
                    ORDER BY snap_date
                    ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW
                ) AS long_observations,
                round(avg(total_eval_amt_krw) OVER (
                    ORDER BY snap_date
                    ROWS BETWEEN {short_window - 1} PRECEDING AND CURRENT ROW
                ), 0) AS short_sma,
                round(avg(total_eval_amt_krw) OVER (
                    ORDER BY snap_date
                    ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW
                ), 0) AS long_sma
            FROM asset_overview_daily_snapshots
            WHERE snap_date >= current_date - INTERVAL '{lookback_days} days'
        )
        SELECT
            snap_date,
            total_eval_amt_krw,
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
    """))
    return {
        "short_window": short_window,
        "long_window": long_window,
        "lookback_days": lookback_days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 추세 분석 데이터가 부족합니다.",
    }


def get_total_asset_allocation_history(
    con: duckdb.DuckDBPyConnection,
    days: int = 30,
) -> dict:
    days = max(1, min(int(days), 3650))
    rows = rows_to_dicts(con.execute(f"""
        SELECT
            snap_date,
            domestic_pct,
            overseas_pct,
            overseas_stock_pct,
            overseas_cash_pct,
            domestic_direct_amt_krw,
            overseas_direct_amt_krw,
            overseas_indirect_amt_krw,
            cash_amt_krw,
            unknown_amt_krw,
            total_eval_amt_krw
        FROM asset_overview_daily_snapshots
        WHERE snap_date >= current_date - INTERVAL '{days} days'
        ORDER BY snap_date DESC
    """))
    return {
        "days": days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 비중 이력이 없습니다.",
    }
