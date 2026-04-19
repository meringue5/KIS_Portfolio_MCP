"""Repository functions for raw KIS portfolio data."""

import json
import logging
from datetime import date, datetime
from typing import Any

from kis_mcp_server.db.connection import get_connection
from kis_mcp_server.db.utils import normalize_row, to_float, to_int

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
