"""
KIS MCP Server — MotherDuck 데이터베이스 레이어

연결 전략:
  - MOTHERDUCK_TOKEN 환경변수 있으면 → MotherDuck (md:kis_portfolio)
  - 없으면 → 로컬 파일 (kis_portfolio.duckdb) 폴백

테이블 구분:
  - price_history      : 주가 이력 캐시 (INSERT OR IGNORE)
  - exchange_rate_history : 환율 이력 캐시 (INSERT OR IGNORE)
  - portfolio_snapshots   : 계좌 잔고 스냅샷 (append-only INSERT)
  - trade_profit_history  : 손익 이력 (append-only INSERT)
"""

import os
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any

import duckdb

logger = logging.getLogger(__name__)

_con: Optional[duckdb.DuckDBPyConnection] = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """싱글톤 DB 연결 반환. 최초 호출 시 스키마 초기화."""
    global _con
    if _con is not None:
        return _con

    token = os.environ.get("MOTHERDUCK_TOKEN", "")
    if token:
        conn_str = f"md:kis_portfolio?motherduck_token={token}"
        logger.info("Connecting to MotherDuck (md:kis_portfolio)")
    else:
        local_path = Path(__file__).resolve().parent / "kis_portfolio.duckdb"
        conn_str = str(local_path)
        logger.info(f"Connecting to local DuckDB: {local_path}")

    _con = duckdb.connect(conn_str)
    _init_schema(_con)
    return _con


def _init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """테이블이 없으면 생성."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            symbol      VARCHAR NOT NULL,
            exchange    VARCHAR NOT NULL,   -- 'KRX', 'NAS', 'NYSE', 'AMS' 등
            date        DATE    NOT NULL,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            adjusted    BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (symbol, exchange, date)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rate_history (
            currency    VARCHAR NOT NULL,   -- 'USD', 'JPY', 'CNY', 'HKD', 'VND'
            date        DATE    NOT NULL,
            period      VARCHAR NOT NULL DEFAULT 'D',  -- D/W/M/Y
            rate        DOUBLE,
            created_at  TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (currency, date, period)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,  -- CANO
            account_type VARCHAR NOT NULL, -- 'ria','isa','irp','pension','brokerage'
            snapshot_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            total_eval_amt BIGINT,         -- 총평가금액 (원화 환산, 없으면 NULL)
            balance_data JSON,             -- API 원본 응답
            PRIMARY KEY (id)
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS trade_profit_history (
            id          VARCHAR NOT NULL DEFAULT gen_random_uuid(),
            account_id  VARCHAR NOT NULL,
            market_type VARCHAR NOT NULL,  -- 'domestic' | 'overseas'
            start_date  DATE,
            end_date    DATE,
            fetched_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            data        JSON,
            PRIMARY KEY (id)
        )
    """)
    logger.info("DB schema initialized")


# ─────────────────────────────────────────────
# 주가 이력 (캐시형)
# ─────────────────────────────────────────────

def upsert_price_history(rows: list[dict], adjusted: bool = False) -> int:
    """
    주가 이력 저장. 동일 (symbol, exchange, date)이면 스킵 (INSERT OR IGNORE).
    adjusted=True이면 수정주가 재동기화로 간주하여 UPDATE.

    rows 각 항목: {symbol, exchange, date(str YYYYMMDD), open, high, low, close, volume}
    반환: 저장된 행 수
    """
    if not rows:
        return 0
    con = get_connection()
    saved = 0
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y%m%d").date()
            if adjusted:
                con.execute("""
                    INSERT INTO price_history (symbol, exchange, date, open, high, low, close, volume, adjusted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)
                    ON CONFLICT (symbol, exchange, date) DO UPDATE SET
                        open=excluded.open, high=excluded.high,
                        low=excluded.low, close=excluded.close,
                        volume=excluded.volume, adjusted=TRUE
                """, [r["symbol"], r["exchange"], d,
                      _f(r.get("open")), _f(r.get("high")),
                      _f(r.get("low")), _f(r.get("close")), _i(r.get("volume"))])
            else:
                con.execute("""
                    INSERT OR IGNORE INTO price_history
                        (symbol, exchange, date, open, high, low, close, volume, adjusted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, FALSE)
                """, [r["symbol"], r["exchange"], d,
                      _f(r.get("open")), _f(r.get("high")),
                      _f(r.get("low")), _f(r.get("close")), _i(r.get("volume"))])
            saved += 1
        except Exception as e:
            logger.warning(f"price_history insert skip: {e}")
    return saved


def get_price_history(symbol: str, exchange: str,
                      start_date: str, end_date: str) -> list[dict]:
    """DB에서 주가 이력 조회. 없으면 빈 리스트."""
    con = get_connection()
    s = datetime.strptime(start_date, "%Y%m%d").date()
    e = datetime.strptime(end_date, "%Y%m%d").date()
    rows = con.execute("""
        SELECT symbol, exchange, date, open, high, low, close, volume, adjusted
        FROM price_history
        WHERE symbol=? AND exchange=? AND date BETWEEN ? AND ?
        ORDER BY date
    """, [symbol, exchange, s, e]).fetchall()
    cols = ["symbol","exchange","date","open","high","low","close","volume","adjusted"]
    return [dict(zip(cols, r)) for r in rows]


def has_price_history(symbol: str, exchange: str,
                      start_date: str, end_date: str) -> bool:
    """해당 기간 데이터가 DB에 완전히 있는지 확인."""
    rows = get_price_history(symbol, exchange, start_date, end_date)
    return len(rows) > 0


# ─────────────────────────────────────────────
# 환율 이력 (캐시형)
# ─────────────────────────────────────────────

def upsert_exchange_rate_history(currency: str, period: str, rows: list[dict]) -> int:
    """
    환율 이력 저장 (INSERT OR IGNORE).
    rows 각 항목: {date(str YYYYMMDD), rate(float)}
    """
    if not rows:
        return 0
    con = get_connection()
    saved = 0
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y%m%d").date()
            con.execute("""
                INSERT OR IGNORE INTO exchange_rate_history (currency, date, period, rate)
                VALUES (?, ?, ?, ?)
            """, [currency.upper(), d, period, _f(r.get("rate"))])
            saved += 1
        except Exception as e:
            logger.warning(f"exchange_rate_history insert skip: {e}")
    return saved


def get_exchange_rate_history(currency: str, start_date: str,
                               end_date: str, period: str = "D") -> list[dict]:
    con = get_connection()
    s = datetime.strptime(start_date, "%Y%m%d").date()
    e = datetime.strptime(end_date, "%Y%m%d").date()
    rows = con.execute("""
        SELECT currency, date, period, rate
        FROM exchange_rate_history
        WHERE currency=? AND period=? AND date BETWEEN ? AND ?
        ORDER BY date
    """, [currency.upper(), period, s, e]).fetchall()
    cols = ["currency","date","period","rate"]
    return [dict(zip(cols, r)) for r in rows]


# ─────────────────────────────────────────────
# 포트폴리오 스냅샷 (누적형)
# ─────────────────────────────────────────────

def insert_portfolio_snapshot(account_id: str, account_type: str,
                               balance_data: Any,
                               total_eval_amt: Optional[int] = None) -> str:
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
                             start_dt: Optional[str] = None,
                             end_dt: Optional[str] = None,
                             limit: int = 100) -> list[dict]:
    """
    계좌 잔고 스냅샷 이력 조회.
    start_dt / end_dt: 'YYYY-MM-DD' 또는 'YYYYMMDD'
    """
    con = get_connection()
    def _parse(s: str) -> str:
        return s if "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:]}"

    where = "WHERE account_id=?"
    params: list = [account_id]
    if start_dt:
        where += " AND snapshot_at >= ?"
        params.append(_parse(start_dt))
    if end_dt:
        where += " AND snapshot_at <= ?"
        params.append(_parse(end_dt) + " 23:59:59")

    rows = con.execute(f"""
        SELECT id, account_id, account_type, snapshot_at, total_eval_amt, balance_data
        FROM portfolio_snapshots {where}
        ORDER BY snapshot_at DESC LIMIT ?
    """, params + [limit]).fetchall()
    cols = ["id","account_id","account_type","snapshot_at","total_eval_amt","balance_data"]
    return [dict(zip(cols, r)) for r in rows]


# ─────────────────────────────────────────────
# 손익 이력 (누적형)
# ─────────────────────────────────────────────

def insert_trade_profit(account_id: str, market_type: str,
                         start_date: str, end_date: str, data: Any) -> str:
    """손익 조회 결과 저장. 항상 INSERT."""
    con = get_connection()
    def _d(s: str) -> date:
        return datetime.strptime(s, "%Y%m%d").date()
    row = con.execute("""
        INSERT INTO trade_profit_history (account_id, market_type, start_date, end_date, data)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
    """, [account_id, market_type, _d(start_date), _d(end_date),
          json.dumps(data, ensure_ascii=False, default=str)]).fetchone()
    return row[0]


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────

def _f(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "")) if v else None
    except Exception:
        return None

def _i(v: Any) -> Optional[int]:
    try:
        return int(str(v).replace(",", "")) if v else None
    except Exception:
        return None
