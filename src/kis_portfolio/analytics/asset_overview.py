"""Analytics over canonical total-asset overview snapshots."""

from __future__ import annotations

import os

import duckdb

from kis_portfolio.common.values import rows_to_dicts


def _freshness(con: duckdb.DuckDBPyConnection) -> dict:
    threshold_days = max(1, int(os.environ.get("KIS_SNAPSHOT_STALE_AFTER_DAYS", "2")))
    latest_date, latest_at, age_days = con.execute("""
        SELECT max(snap_date), max(snapshot_at), date_diff('day', max(snap_date), current_date)
        FROM asset_overview_daily_snapshots
    """).fetchone()
    stale = latest_date is not None and age_days > threshold_days
    missing = latest_date is None
    return {
        "status": "missing" if missing else ("stale" if stale else "fresh"),
        "latest_snapshot_at": latest_at.isoformat() if latest_at else None,
        "age_days": age_days,
        "threshold_days": threshold_days,
        "warning": (
            "총자산 스냅샷이 없습니다."
            if missing
            else (
                f"마지막 총자산 스냅샷이 {age_days}일 전입니다. 배치 상태를 확인하세요."
                if stale else None
            )
        ),
    }


def _with_quality(con: duckdb.DuckDBPyConnection, payload: dict, rows: list[dict]) -> dict:
    freshness = _freshness(con)
    row_statuses = sorted({row.get("quality_status") for row in rows if row.get("quality_status")})
    degraded_rows = sum(1 for row in rows if row.get("quality_status") not in (None, "ok"))
    payload["status"] = "degraded" if freshness["status"] != "fresh" or degraded_rows else "ok"
    payload["data_quality"] = {
        "freshness": freshness,
        "row_quality_statuses": row_statuses,
        "degraded_row_count": degraded_rows,
    }
    return payload


def get_total_asset_history(
    con: duckdb.DuckDBPyConnection,
    days: int = 30,
    limit: int = 60,
) -> dict:
    days = max(1, min(int(days), 3650))
    limit = max(1, min(int(limit), 3650))
    rows = rows_to_dicts(con.execute(f"""
        SELECT snap_date, snapshot_at, domestic_eval_amt_krw, overseas_stock_eval_amt_krw,
               overseas_cash_amt_krw, overseas_total_asset_amt_krw, total_eval_amt_krw,
               quality_status, quality_flags, is_complete
        FROM asset_overview_daily_snapshots
        WHERE snap_date >= current_date - INTERVAL '{days} days'
        ORDER BY snap_date DESC
        LIMIT ?
    """, [limit]))
    return _with_quality(con, {
        "days": days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 스냅샷이 없습니다.",
    }, rows)


def get_total_asset_daily_change(
    con: duckdb.DuckDBPyConnection,
    days: int = 14,
) -> dict:
    days = max(2, min(int(days), 3650))
    rows = rows_to_dicts(con.execute("""
        WITH changes AS (
            SELECT
                snap_date,
                total_eval_amt_krw,
                quality_status,
                is_complete,
                lag(total_eval_amt_krw) OVER (ORDER BY snap_date) AS prev_total_eval_amt_krw
            FROM asset_overview_daily_snapshots
        )
        SELECT
            snap_date,
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
    return _with_quality(con, {
        "days": days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 일별 스냅샷이 없습니다.",
    }, rows)


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
                quality_status,
                is_complete,
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
            quality_status,
            is_complete,
            CASE
                WHEN short_sma > long_sma THEN '상승추세'
                WHEN short_sma < long_sma THEN '하락추세'
                ELSE '중립'
            END AS trend
        FROM trend_rows
        WHERE long_observations >= {long_window}
        ORDER BY snap_date DESC
    """))
    return _with_quality(con, {
        "short_window": short_window,
        "long_window": long_window,
        "lookback_days": lookback_days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 추세 분석 데이터가 부족합니다.",
    }, rows)


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
            total_eval_amt_krw,
            quality_status,
            quality_flags,
            is_complete
        FROM asset_overview_daily_snapshots
        WHERE snap_date >= current_date - INTERVAL '{days} days'
        ORDER BY snap_date DESC
    """))
    return _with_quality(con, {
        "days": days,
        "count": len(rows),
        "latest": rows[0] if rows else None,
        "data": rows,
        "message": None if rows else "총자산 비중 이력이 없습니다.",
    }, rows)


def get_asset_return_history(
    con: duckdb.DuckDBPyConnection,
    days: int = 90,
) -> dict:
    """Return flow-adjusted daily changes and chain-linked TWR."""
    days = max(2, min(int(days), 3650))
    rows = rows_to_dicts(con.execute(f"""
        SELECT *
        FROM asset_return_daily
        WHERE snap_date >= current_date - INTERVAL '{days} days'
        ORDER BY snap_date
    """))
    valid_returns = [
        row["daily_twr_return_pct"]
        for row in rows
        if row.get("daily_twr_return_pct") is not None
        and row.get("is_complete")
        and row.get("quality_status") == "ok"
    ]
    chained = 1.0
    for value in valid_returns:
        chained *= 1 + float(value) / 100
    payload = {
        "days": days,
        "count": len(rows),
        "valid_return_days": len(valid_returns),
        "twr_return_pct": round((chained - 1) * 100, 4) if valid_returns else None,
        "data": list(reversed(rows)),
        "message": None if rows else "현금흐름 조정 수익률 데이터가 없습니다.",
    }
    return _with_quality(con, payload, rows)
