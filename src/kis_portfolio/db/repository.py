"""Repository functions for raw KIS portfolio data."""

import json
import logging
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from kis_portfolio.db.connection import get_connection
from kis_portfolio.db.utils import normalize_row, to_float, to_int

logger = logging.getLogger(__name__)


def upsert_price_history(rows: list[dict], adjusted: bool = False) -> int:
    """
    주가 이력 저장. 동일 (symbol, exchange, date)이면 스킵 (INSERT OR IGNORE).
    adjusted=True이면 수정주가 재동기화로 간주하여 UPDATE.
    """
    if not rows:
        return 0
    con = get_connection()
    saved = 0
    for row in rows:
        try:
            d = datetime.strptime(row["date"], "%Y%m%d").date()
            if adjusted:
                con.execute("""
                    INSERT INTO price_history (symbol, exchange, date, open, high, low, close, volume, adjusted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)
                    ON CONFLICT (symbol, exchange, date) DO UPDATE SET
                        open=excluded.open, high=excluded.high,
                        low=excluded.low, close=excluded.close,
                        volume=excluded.volume, adjusted=TRUE
                    RETURNING 1
                """, [row["symbol"], row["exchange"], d,
                      to_float(row.get("open")), to_float(row.get("high")),
                      to_float(row.get("low")), to_float(row.get("close")), to_int(row.get("volume"))]).fetchone()
                saved += 1
            else:
                inserted = con.execute("""
                    INSERT OR IGNORE INTO price_history
                        (symbol, exchange, date, open, high, low, close, volume, adjusted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, FALSE)
                    RETURNING 1
                """, [row["symbol"], row["exchange"], d,
                      to_float(row.get("open")), to_float(row.get("high")),
                      to_float(row.get("low")), to_float(row.get("close")), to_int(row.get("volume"))]).fetchone()
                if inserted:
                    saved += 1
        except Exception as e:
            logger.warning(f"price_history insert skip: {e}")
    return saved


def get_price_history(symbol: str, exchange: str,
                      start_date: str, end_date: str) -> list[dict]:
    """DB에서 주가 이력 조회. 없으면 빈 리스트."""
    con = get_connection()
    start = datetime.strptime(start_date, "%Y%m%d").date()
    end = datetime.strptime(end_date, "%Y%m%d").date()
    rows = con.execute("""
        SELECT symbol, exchange, date, open, high, low, close, volume, adjusted
        FROM price_history
        WHERE symbol=? AND exchange=? AND date BETWEEN ? AND ?
        ORDER BY date
    """, [symbol, exchange, start, end]).fetchall()
    cols = ["symbol", "exchange", "date", "open", "high", "low", "close", "volume", "adjusted"]
    return [normalize_row(dict(zip(cols, row))) for row in rows]


def has_price_history(symbol: str, exchange: str,
                      start_date: str, end_date: str) -> bool:
    """Return whether there is at least one cached price row in the range."""
    con = get_connection()
    start = datetime.strptime(start_date, "%Y%m%d").date()
    end = datetime.strptime(end_date, "%Y%m%d").date()
    count = con.execute("""
        SELECT count(*)
        FROM price_history
        WHERE symbol=? AND exchange=? AND date BETWEEN ? AND ?
    """, [symbol, exchange, start, end]).fetchone()[0]
    return count > 0


def upsert_exchange_rate_history(currency: str, period: str, rows: list[dict]) -> int:
    """환율 이력 저장 (INSERT OR IGNORE)."""
    if not rows:
        return 0
    con = get_connection()
    saved = 0
    for row in rows:
        try:
            d = datetime.strptime(row["date"], "%Y%m%d").date()
            inserted = con.execute("""
                INSERT OR IGNORE INTO exchange_rate_history (currency, date, period, rate)
                VALUES (?, ?, ?, ?)
                RETURNING 1
            """, [currency.upper(), d, period, to_float(row.get("rate"))]).fetchone()
            if inserted:
                saved += 1
        except Exception as e:
            logger.warning(f"exchange_rate_history insert skip: {e}")
    return saved


def get_exchange_rate_history(currency: str, start_date: str,
                              end_date: str, period: str = "D") -> list[dict]:
    con = get_connection()
    start = datetime.strptime(start_date, "%Y%m%d").date()
    end = datetime.strptime(end_date, "%Y%m%d").date()
    rows = con.execute("""
        SELECT currency, date, period, rate
        FROM exchange_rate_history
        WHERE currency=? AND period=? AND date BETWEEN ? AND ?
        ORDER BY date
    """, [currency.upper(), period, start, end]).fetchall()
    cols = ["currency", "date", "period", "rate"]
    return [normalize_row(dict(zip(cols, row))) for row in rows]


def insert_portfolio_snapshot(account_id: str, account_type: str,
                              balance_data: Any,
                              total_eval_amt: int | None = None) -> str:
    """잔고 스냅샷 저장. 항상 INSERT. 생성된 id 반환."""
    con = get_connection()
    row = con.execute("""
        INSERT INTO portfolio_snapshots (account_id, account_type, total_eval_amt, balance_data)
        VALUES (?, ?, ?, ?)
        RETURNING id
    """, [account_id, account_type, total_eval_amt,
          json.dumps(balance_data, ensure_ascii=False, default=str)]).fetchone()
    return row[0]


def get_portfolio_snapshots(account_id: str,
                            start_dt: str | None = None,
                            end_dt: str | None = None,
                            limit: int = 100) -> list[dict]:
    """계좌 잔고 스냅샷 이력 조회."""
    con = get_connection()

    def parse_date(value: str) -> str:
        return value if "-" in value else f"{value[:4]}-{value[4:6]}-{value[6:]}"

    where = "WHERE account_id=?"
    params: list = [account_id]
    if start_dt:
        where += " AND snapshot_at >= ?"
        params.append(parse_date(start_dt))
    if end_dt:
        where += " AND snapshot_at <= ?"
        params.append(parse_date(end_dt) + " 23:59:59")

    rows = con.execute(f"""
        SELECT id, account_id, account_type, snapshot_at, total_eval_amt, balance_data
        FROM portfolio_snapshots {where}
        ORDER BY snapshot_at DESC LIMIT ?
    """, params + [limit]).fetchall()
    cols = ["id", "account_id", "account_type", "snapshot_at", "total_eval_amt", "balance_data"]
    return [normalize_row(dict(zip(cols, row))) for row in rows]


def insert_trade_profit(account_id: str, market_type: str,
                        start_date: str, end_date: str, data: Any) -> str:
    """손익 조회 결과 저장. 항상 INSERT."""
    con = get_connection()

    def parse_yyyymmdd(value: str) -> date:
        return datetime.strptime(value, "%Y%m%d").date()

    row = con.execute("""
        INSERT INTO trade_profit_history (account_id, market_type, start_date, end_date, data)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
    """, [account_id, market_type, parse_yyyymmdd(start_date), parse_yyyymmdd(end_date),
          json.dumps(data, ensure_ascii=False, default=str)]).fetchone()
    return row[0]


def insert_order_history(
    account_id: str,
    account_product_code: str,
    account_type: str,
    market_type: str,
    start_date: str,
    end_date: str,
    data: Any,
) -> str:
    """주문/체결 조회 결과 저장. 항상 INSERT."""
    con = get_connection()

    def parse_yyyymmdd(value: str) -> date:
        return datetime.strptime(value, "%Y%m%d").date()

    row = con.execute("""
        INSERT INTO order_history (
            account_id, account_product_code, account_type, market_type, start_date, end_date, data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, [
        account_id,
        account_product_code,
        account_type,
        market_type,
        parse_yyyymmdd(start_date),
        parse_yyyymmdd(end_date),
        json.dumps(data, ensure_ascii=False, default=str),
    ]).fetchone()
    return row[0]


def get_latest_order_history_snapshot(
    account_id: str,
    account_product_code: str,
    market_type: str,
    start_date: str,
    end_date: str,
) -> dict | None:
    """Return the most recently fetched raw order-history snapshot for one exact range."""
    con = get_connection()

    def parse_yyyymmdd(value: str) -> date:
        return datetime.strptime(value, "%Y%m%d").date()

    row = con.execute("""
        SELECT id, account_id, account_product_code, account_type, market_type, start_date, end_date, fetched_at, data
        FROM order_history
        WHERE account_id=? AND market_type=? AND start_date=? AND end_date=?
          AND (account_product_code=? OR account_product_code IS NULL)
        ORDER BY
            CASE WHEN account_product_code=? THEN 1 ELSE 0 END DESC,
            fetched_at DESC,
            id DESC
        LIMIT 1
    """, [
        account_id,
        market_type,
        parse_yyyymmdd(start_date),
        parse_yyyymmdd(end_date),
        account_product_code,
        account_product_code,
    ]).fetchone()
    if not row:
        return None
    cols = [
        "id",
        "account_id",
        "account_product_code",
        "account_type",
        "market_type",
        "start_date",
        "end_date",
        "fetched_at",
        "data",
    ]
    return normalize_row(dict(zip(cols, row)))


def upsert_domestic_orders(rows: list[dict]) -> int:
    """Upsert canonical domestic orders keyed by KIS order identity."""
    if not rows:
        return 0

    con = get_connection()
    saved = 0

    for row in rows:
        order_date = row["order_date"]
        if isinstance(order_date, str):
            order_date = datetime.strptime(order_date, "%Y%m%d").date()

        con.execute("""
            INSERT INTO domestic_orders (
                account_id,
                account_product_code,
                account_type,
                order_date,
                order_branch_no,
                order_no,
                original_order_no,
                symbol,
                symbol_name,
                side_code,
                side_name,
                order_type_code,
                order_type_name,
                order_time,
                order_qty,
                total_order_qty,
                order_price,
                avg_price,
                filled_qty,
                filled_amount,
                pending_qty,
                cancel_confirm_qty,
                rejected_qty,
                is_cancelled,
                condition_name,
                exchange_id_code,
                order_orgno,
                last_source,
                last_order_history_id,
                raw_data
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            ON CONFLICT (account_id, account_product_code, order_date, order_branch_no, order_no) DO UPDATE SET
                account_type=excluded.account_type,
                original_order_no=excluded.original_order_no,
                symbol=excluded.symbol,
                symbol_name=excluded.symbol_name,
                side_code=excluded.side_code,
                side_name=excluded.side_name,
                order_type_code=excluded.order_type_code,
                order_type_name=excluded.order_type_name,
                order_time=excluded.order_time,
                order_qty=excluded.order_qty,
                total_order_qty=excluded.total_order_qty,
                order_price=excluded.order_price,
                avg_price=excluded.avg_price,
                filled_qty=excluded.filled_qty,
                filled_amount=excluded.filled_amount,
                pending_qty=excluded.pending_qty,
                cancel_confirm_qty=excluded.cancel_confirm_qty,
                rejected_qty=excluded.rejected_qty,
                is_cancelled=excluded.is_cancelled,
                condition_name=excluded.condition_name,
                exchange_id_code=excluded.exchange_id_code,
                order_orgno=excluded.order_orgno,
                last_seen_at=now(),
                last_source=excluded.last_source,
                last_order_history_id=excluded.last_order_history_id,
                raw_data=excluded.raw_data
        """, [
            row["account_id"],
            row["account_product_code"],
            row["account_type"],
            order_date,
            row.get("order_branch_no", ""),
            row["order_no"],
            row.get("original_order_no"),
            row.get("symbol"),
            row.get("symbol_name"),
            row.get("side_code"),
            row.get("side_name"),
            row.get("order_type_code"),
            row.get("order_type_name"),
            row.get("order_time"),
            row.get("order_qty"),
            row.get("total_order_qty"),
            row.get("order_price"),
            row.get("avg_price"),
            row.get("filled_qty"),
            row.get("filled_amount"),
            row.get("pending_qty"),
            row.get("cancel_confirm_qty"),
            row.get("rejected_qty"),
            row.get("is_cancelled"),
            row.get("condition_name"),
            row.get("exchange_id_code"),
            row.get("order_orgno"),
            row.get("last_source"),
            row.get("last_order_history_id"),
            json.dumps(row.get("raw_data"), ensure_ascii=False, default=str),
        ])
        saved += 1

    return saved


def get_domestic_orders(
    account_id: str,
    account_product_code: str,
    start_date: str,
    end_date: str,
    *,
    symbol: str = "",
) -> list[dict]:
    """Return canonical domestic orders for one account and date range."""
    con = get_connection()
    start = datetime.strptime(start_date, "%Y%m%d").date()
    end = datetime.strptime(end_date, "%Y%m%d").date()

    where = """
        WHERE account_id=?
          AND account_product_code=?
          AND order_date BETWEEN ? AND ?
    """
    params: list[Any] = [account_id, account_product_code, start, end]

    if symbol:
        where += " AND upper(symbol)=?"
        params.append(symbol.upper())

    rows = con.execute(f"""
        SELECT
            account_id,
            account_product_code,
            account_type,
            order_date,
            order_branch_no,
            order_no,
            original_order_no,
            symbol,
            symbol_name,
            side_code,
            side_name,
            order_type_code,
            order_type_name,
            order_time,
            order_qty,
            total_order_qty,
            order_price,
            avg_price,
            filled_qty,
            filled_amount,
            pending_qty,
            cancel_confirm_qty,
            rejected_qty,
            is_cancelled,
            condition_name,
            exchange_id_code,
            order_orgno,
            first_seen_at,
            last_seen_at,
            last_source,
            last_order_history_id,
            raw_data
        FROM domestic_orders
        {where}
        ORDER BY order_date DESC, order_time DESC NULLS LAST, order_no DESC
    """, params).fetchall()
    cols = [
        "account_id",
        "account_product_code",
        "account_type",
        "order_date",
        "order_branch_no",
        "order_no",
        "original_order_no",
        "symbol",
        "symbol_name",
        "side_code",
        "side_name",
        "order_type_code",
        "order_type_name",
        "order_time",
        "order_qty",
        "total_order_qty",
        "order_price",
        "avg_price",
        "filled_qty",
        "filled_amount",
        "pending_qty",
        "cancel_confirm_qty",
        "rejected_qty",
        "is_cancelled",
        "condition_name",
        "exchange_id_code",
        "order_orgno",
        "first_seen_at",
        "last_seen_at",
        "last_source",
        "last_order_history_id",
        "raw_data",
    ]
    return [normalize_row(dict(zip(cols, row))) for row in rows]


def upsert_market_calendar_rows(rows: list[dict]) -> int:
    """Upsert market calendar rows keyed by market and trade_date."""
    if not rows:
        return 0

    con = get_connection()
    saved = 0
    for row in rows:
        trade_date = row["trade_date"]
        if isinstance(trade_date, str):
            trade_date = datetime.strptime(trade_date, "%Y%m%d").date()
        con.execute("""
            INSERT INTO market_calendar (
                market, trade_date, is_open, open_time_local, close_time_local,
                timezone, source, note, raw_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (market, trade_date) DO UPDATE SET
                is_open=excluded.is_open,
                open_time_local=excluded.open_time_local,
                close_time_local=excluded.close_time_local,
                timezone=excluded.timezone,
                source=excluded.source,
                note=excluded.note,
                raw_data=excluded.raw_data,
                updated_at=current_timestamp
        """, [
            row["market"],
            trade_date,
            row["is_open"],
            row.get("open_time_local"),
            row.get("close_time_local"),
            row.get("timezone", "Asia/Seoul"),
            row.get("source"),
            row.get("note"),
            json.dumps(row.get("raw_data"), ensure_ascii=False, default=str),
        ])
        saved += 1
    return saved


def get_market_calendar_entry(market: str, trade_date: str) -> dict | None:
    """Return one market calendar row by market and date."""
    con = get_connection()
    parsed = datetime.strptime(trade_date, "%Y%m%d").date()
    row = con.execute("""
        SELECT market, trade_date, is_open, open_time_local, close_time_local,
               timezone, source, note, raw_data, updated_at
        FROM market_calendar
        WHERE market=? AND trade_date=?
    """, [market, parsed]).fetchone()
    if not row:
        return None
    cols = [
        "market",
        "trade_date",
        "is_open",
        "open_time_local",
        "close_time_local",
        "timezone",
        "source",
        "note",
        "raw_data",
        "updated_at",
    ]
    return normalize_row(dict(zip(cols, row)))


def count_market_calendar_rows(market: str, year: int) -> int:
    """Count market calendar rows for one market/year."""
    con = get_connection()
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    return con.execute("""
        SELECT count(*)
        FROM market_calendar
        WHERE market=? AND trade_date BETWEEN ? AND ?
    """, [market, start, end]).fetchone()[0]


def insert_overseas_asset_snapshot(
    account_id: str,
    account_type: str,
    stock_eval_amt_krw: int | None,
    cash_amt_krw: int | None,
    total_asset_amt_krw: int | None,
    fx_data: Any,
    balance_data: Any,
    deposit_data: Any,
) -> str:
    """Store overseas account snapshot used for canonical asset overview."""
    con = get_connection()
    row = con.execute("""
        INSERT INTO overseas_asset_snapshots (
            account_id, account_type, stock_eval_amt_krw, cash_amt_krw,
            total_asset_amt_krw, fx_data, balance_data, deposit_data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, [
        account_id,
        account_type,
        stock_eval_amt_krw,
        cash_amt_krw,
        total_asset_amt_krw,
        json.dumps(fx_data, ensure_ascii=False, default=str),
        json.dumps(balance_data, ensure_ascii=False, default=str),
        json.dumps(deposit_data, ensure_ascii=False, default=str),
    ]).fetchone()
    return row[0]


def insert_asset_overview_snapshot(
    totals: dict,
    allocation: dict,
    classification_summary: dict,
    overview_data: Any,
) -> str:
    """Store canonical total-asset overview snapshot."""
    con = get_connection()
    row = con.execute("""
        INSERT INTO asset_overview_snapshots (
            base_currency,
            domestic_eval_amt_krw,
            overseas_stock_eval_amt_krw,
            overseas_cash_amt_krw,
            overseas_total_asset_amt_krw,
            total_eval_amt_krw,
            domestic_pct,
            overseas_pct,
            overseas_stock_pct,
            overseas_cash_pct,
            domestic_direct_amt_krw,
            overseas_direct_amt_krw,
            overseas_indirect_amt_krw,
            cash_amt_krw,
            unknown_amt_krw,
            allocation_data,
            classification_summary,
            overview_data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, [
        overview_data.get("base_currency", "KRW"),
        totals.get("domestic_eval_amt_krw"),
        totals.get("overseas_stock_eval_amt_krw"),
        totals.get("overseas_cash_amt_krw"),
        totals.get("overseas_total_asset_amt_krw"),
        totals.get("total_eval_amt_krw"),
        allocation.get("domestic_pct"),
        allocation.get("overseas_pct"),
        allocation.get("overseas_stock_pct"),
        allocation.get("overseas_cash_pct"),
        classification_summary.get("amounts", {}).get("domestic_direct"),
        classification_summary.get("amounts", {}).get("overseas_direct"),
        classification_summary.get("amounts", {}).get("overseas_indirect"),
        classification_summary.get("amounts", {}).get("cash"),
        classification_summary.get("amounts", {}).get("unknown"),
        json.dumps(allocation, ensure_ascii=False, default=str),
        json.dumps(classification_summary, ensure_ascii=False, default=str),
        json.dumps(overview_data, ensure_ascii=False, default=str),
    ]).fetchone()
    return row[0]


def insert_asset_holding_snapshots(overview_snapshot_id: str, rows: list[dict]) -> int:
    """Store normalized holdings for one canonical overview snapshot."""
    if not rows:
        return 0
    con = get_connection()
    saved = 0
    for row in rows:
        con.execute("""
            INSERT INTO asset_holding_snapshots (
                overview_snapshot_id, account_label, account_type, symbol, name,
                market, basis_category, exposure_type, exposure_region, asset_subtype,
                confidence, quantity, value_krw, value_foreign, currency, raw_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            overview_snapshot_id,
            row.get("account_label"),
            row.get("account_type"),
            row.get("symbol"),
            row.get("name"),
            row.get("market"),
            row.get("basis_category"),
            row.get("exposure_type"),
            row.get("exposure_region"),
            row.get("asset_subtype"),
            row.get("confidence"),
            row.get("quantity"),
            row.get("value_krw"),
            row.get("value_foreign"),
            row.get("currency"),
            json.dumps(row.get("raw_data"), ensure_ascii=False, default=str),
        ])
        saved += 1
    return saved


def get_asset_overview_snapshots(
    start_dt: str | None = None,
    end_dt: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return canonical total-asset snapshots."""
    con = get_connection()
    where = ""
    params: list[Any] = []
    if start_dt or end_dt:
        clauses = []
        if start_dt:
            clauses.append("snapshot_at >= ?")
            params.append(start_dt if "-" in start_dt else f"{start_dt[:4]}-{start_dt[4:6]}-{start_dt[6:]}")
        if end_dt:
            clauses.append("snapshot_at <= ?")
            params.append((end_dt if "-" in end_dt else f"{end_dt[:4]}-{end_dt[4:6]}-{end_dt[6:]}") + " 23:59:59")
        where = "WHERE " + " AND ".join(clauses)

    rows = con.execute(f"""
        SELECT *
        FROM asset_overview_snapshots
        {where}
        ORDER BY snapshot_at DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    cols = [desc[0] for desc in con.description]
    return [normalize_row(dict(zip(cols, row))) for row in rows]


def upsert_instrument_master(rows: list[dict]) -> int:
    """Upsert KRX instrument master metadata used for ETF/REIT classification."""
    if not rows:
        return 0
    con = get_connection()
    with tempfile.TemporaryDirectory(prefix="kis-master-stage-") as tmp_dir:
        stage_path = Path(tmp_dir) / "instrument_master.ndjson"
        with stage_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                payload = {
                    "symbol": row.get("symbol"),
                    "market": row.get("market", "KRX"),
                    "standard_code": row.get("standard_code"),
                    "name": row.get("name"),
                    "group_code": row.get("group_code"),
                    "etp_code": row.get("etp_code"),
                    "idx_large_code": row.get("idx_large_code"),
                    "idx_mid_code": row.get("idx_mid_code"),
                    "idx_small_code": row.get("idx_small_code"),
                    "raw_data": json.dumps(row, ensure_ascii=False, default=str),
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

        con.execute("""
            CREATE OR REPLACE TEMP TABLE instrument_master_stage AS
            SELECT
                CAST(symbol AS VARCHAR) AS symbol,
                COALESCE(NULLIF(CAST(market AS VARCHAR), ''), 'KRX') AS market,
                CAST(standard_code AS VARCHAR) AS standard_code,
                CAST(name AS VARCHAR) AS name,
                NULLIF(CAST(group_code AS VARCHAR), '') AS group_code,
                NULLIF(CAST(etp_code AS VARCHAR), '') AS etp_code,
                NULLIF(CAST(idx_large_code AS VARCHAR), '') AS idx_large_code,
                NULLIF(CAST(idx_mid_code AS VARCHAR), '') AS idx_mid_code,
                NULLIF(CAST(idx_small_code AS VARCHAR), '') AS idx_small_code,
                CAST(raw_data AS JSON) AS raw_data
            FROM read_ndjson_auto(?)
            WHERE COALESCE(NULLIF(CAST(symbol AS VARCHAR), ''), '') <> ''
        """, [str(stage_path)])

        con.execute("""
            INSERT INTO instrument_master (
                symbol, market, standard_code, name, group_code,
                etp_code, idx_large_code, idx_mid_code, idx_small_code, raw_data
            )
            SELECT
                symbol, market, standard_code, name, group_code,
                etp_code, idx_large_code, idx_mid_code, idx_small_code, raw_data
            FROM instrument_master_stage
            ON CONFLICT (symbol, market) DO UPDATE SET
                standard_code = excluded.standard_code,
                name = excluded.name,
                group_code = excluded.group_code,
                etp_code = excluded.etp_code,
                idx_large_code = excluded.idx_large_code,
                idx_mid_code = excluded.idx_mid_code,
                idx_small_code = excluded.idx_small_code,
                raw_data = excluded.raw_data,
                updated_at = now()
        """)
        saved = con.execute("SELECT COUNT(*) FROM instrument_master_stage").fetchone()[0]
        con.execute("DROP TABLE IF EXISTS instrument_master_stage")
    return saved


def get_instrument_master(symbol: str, market: str = "KRX") -> dict | None:
    """Fetch one instrument master row."""
    con = get_connection()
    row = con.execute("""
        SELECT symbol, market, standard_code, name, group_code,
               etp_code, idx_large_code, idx_mid_code, idx_small_code, raw_data, updated_at
        FROM instrument_master
        WHERE symbol=? AND market=?
    """, [symbol, market]).fetchone()
    if not row:
        return None
    cols = [
        "symbol", "market", "standard_code", "name", "group_code",
        "etp_code", "idx_large_code", "idx_mid_code", "idx_small_code", "raw_data", "updated_at",
    ]
    return normalize_row(dict(zip(cols, row)))


def get_instrument_master_map(symbols: list[str], market: str = "KRX") -> dict[str, dict]:
    """Fetch multiple instrument master rows keyed by symbol."""
    if not symbols:
        return {}
    con = get_connection()
    placeholders = ",".join("?" for _ in symbols)
    rows = con.execute(f"""
        SELECT symbol, market, standard_code, name, group_code,
               etp_code, idx_large_code, idx_mid_code, idx_small_code, raw_data, updated_at
        FROM instrument_master
        WHERE market=? AND symbol IN ({placeholders})
    """, [market] + symbols).fetchall()
    cols = [
        "symbol", "market", "standard_code", "name", "group_code",
        "etp_code", "idx_large_code", "idx_mid_code", "idx_small_code", "raw_data", "updated_at",
    ]
    return {
        row[0]: normalize_row(dict(zip(cols, row)))
        for row in rows
    }


def get_classification_override(symbol: str, market: str = "KRX") -> dict | None:
    """Fetch one classification override row."""
    con = get_connection()
    row = con.execute("""
        SELECT symbol, market, exposure_type, exposure_region, asset_subtype, reason, updated_at
        FROM instrument_classification_overrides
        WHERE symbol=? AND market=?
    """, [symbol, market]).fetchone()
    if not row:
        return None
    cols = [
        "symbol", "market", "exposure_type", "exposure_region",
        "asset_subtype", "reason", "updated_at",
    ]
    return normalize_row(dict(zip(cols, row)))


def get_classification_override_map(symbols: list[str], market: str = "KRX") -> dict[str, dict]:
    """Fetch multiple classification overrides keyed by symbol."""
    if not symbols:
        return {}
    con = get_connection()
    placeholders = ",".join("?" for _ in symbols)
    rows = con.execute(f"""
        SELECT symbol, market, exposure_type, exposure_region, asset_subtype, reason, updated_at
        FROM instrument_classification_overrides
        WHERE market=? AND symbol IN ({placeholders})
    """, [market] + symbols).fetchall()
    cols = [
        "symbol", "market", "exposure_type", "exposure_region",
        "asset_subtype", "reason", "updated_at",
    ]
    return {
        row[0]: normalize_row(dict(zip(cols, row)))
        for row in rows
    }
