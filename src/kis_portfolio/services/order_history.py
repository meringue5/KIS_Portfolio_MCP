"""Batch-safe order history collection services."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from kis_portfolio.account_registry import load_account_registry, scoped_account_env
from kis_portfolio.accounts import infer_account_type
from kis_portfolio.services.market_calendar import evaluate_krx_collection_gate
from kis_portfolio.services import kis_api
from kis_portfolio import db as kisdb
from kis_portfolio.db.utils import to_int


logger = logging.getLogger(__name__)
SEOUL_TZ = ZoneInfo("Asia/Seoul")
ORDER_HISTORY_SOURCES = {"auto", "db", "kis_api"}


def resolve_yyyymmdd(value: str = "", *, now: datetime | None = None) -> str:
    """Resolve batch date tokens into YYYYMMDD using Asia/Seoul."""
    token = (value or "today").strip().lower()
    if token == "today":
        current = now.astimezone(SEOUL_TZ) if now else datetime.now(SEOUL_TZ)
        return current.strftime("%Y%m%d")
    return datetime.strptime(token, "%Y%m%d").strftime("%Y%m%d")


def _order_count(raw: dict) -> int:
    rows = raw.get("output1")
    return len(rows) if isinstance(rows, list) else 0


def _current_order_account() -> tuple[str, str, str]:
    account_id = kis_api._current_account_id()
    account_product_code = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    account_type = os.environ.get("KIS_ACCOUNT_LABEL") or infer_account_type(account_id, account_product_code)
    return account_id, account_product_code, account_type


def _pick_value(row: dict, *candidates: str):
    for candidate in candidates:
        for key in (candidate, candidate.lower(), candidate.upper()):
            value = row.get(key)
            if value not in ("", None):
                return value
    return None


def _compact_yyyymmdd(value: str | None) -> str | None:
    if not value:
        return value
    token = str(value)
    return token.replace("-", "")


def _yn_to_bool(value: str | None) -> bool | None:
    if value in ("Y", "y", True):
        return True
    if value in ("N", "n", False):
        return False
    return None


def _normalize_domestic_orders_for_upsert(
    raw: dict,
    *,
    fallback_date: str,
    saved_order_history_id: str | None,
    source: str,
) -> list[dict]:
    rows = raw.get("output1")
    if not isinstance(rows, list):
        return []

    account_id, account_product_code, account_type = _current_order_account()
    normalized = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        order_no = _pick_value(row, "odno")
        order_date = _compact_yyyymmdd(_pick_value(row, "ord_dt") or fallback_date)
        if not order_no or not order_date:
            logger.warning("Skipping domestic order row without order identity: %s", row)
            continue
        normalized.append({
            "account_id": account_id,
            "account_product_code": account_product_code,
            "account_type": account_type,
            "order_date": order_date,
            "order_branch_no": str(_pick_value(row, "ord_gno_brno") or ""),
            "order_no": str(order_no),
            "original_order_no": _pick_value(row, "orgn_odno"),
            "symbol": _pick_value(row, "pdno"),
            "symbol_name": _pick_value(row, "prdt_name", "item_name", "hts_kor_isnm"),
            "side_code": _pick_value(row, "sll_buy_dvsn_cd"),
            "side_name": _pick_value(row, "sll_buy_dvsn_cd_name"),
            "order_type_code": _pick_value(row, "ord_dvsn_cd"),
            "order_type_name": _pick_value(row, "ord_dvsn_name"),
            "order_time": _pick_value(row, "ord_tmd"),
            "order_qty": to_int(_pick_value(row, "ord_qty")),
            "total_order_qty": to_int(_pick_value(row, "tot_ord_qty", "ord_qty")),
            "order_price": to_int(_pick_value(row, "ord_unpr")),
            "avg_price": to_int(_pick_value(row, "avg_prvs", "pchs_avg_pric")),
            "filled_qty": to_int(_pick_value(row, "tot_ccld_qty", "ccld_qty")),
            "filled_amount": to_int(_pick_value(row, "tot_ccld_amt")),
            "pending_qty": to_int(_pick_value(row, "rmn_qty")),
            "cancel_confirm_qty": to_int(_pick_value(row, "cnc_cfrm_qty")),
            "rejected_qty": to_int(_pick_value(row, "rjct_qty")),
            "is_cancelled": _yn_to_bool(_pick_value(row, "cncl_yn")),
            "condition_name": _pick_value(row, "ccld_cndt_name"),
            "exchange_id_code": _pick_value(row, "excg_id_dvsn_cd", "excg_id_dvsn_Cd", "excg_dvsn_cd"),
            "order_orgno": _pick_value(row, "ord_orgno"),
            "last_source": source,
            "last_order_history_id": saved_order_history_id,
            "raw_data": row,
        })
    return normalized


def _format_domestic_order_row(row: dict) -> dict:
    return {
        "order_no": row.get("order_no"),
        "order_branch_no": row.get("order_branch_no") or None,
        "original_order_no": row.get("original_order_no"),
        "symbol": row.get("symbol"),
        "symbol_name": row.get("symbol_name"),
        "order_date": _compact_yyyymmdd(row.get("order_date")),
        "order_time": row.get("order_time"),
        "side": row.get("side_name") or row.get("side_code"),
        "side_code": row.get("side_code"),
        "order_type": row.get("order_type_name") or row.get("order_type_code"),
        "order_type_code": row.get("order_type_code"),
        "order_qty": row.get("order_qty"),
        "total_order_qty": row.get("total_order_qty"),
        "order_price": row.get("order_price"),
        "avg_price": row.get("avg_price"),
        "filled_qty": row.get("filled_qty"),
        "filled_amount": row.get("filled_amount"),
        "pending_qty": row.get("pending_qty"),
        "cancel_confirm_qty": row.get("cancel_confirm_qty"),
        "rejected_qty": row.get("rejected_qty"),
        "is_cancelled": row.get("is_cancelled"),
        "condition_name": row.get("condition_name"),
        "exchange_id_code": row.get("exchange_id_code"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "last_source": row.get("last_source"),
        "last_order_history_id": row.get("last_order_history_id"),
        "raw": row.get("raw_data"),
    }


def _load_domestic_order_rows(start_date: str, end_date: str, *, symbol: str = "") -> list[dict]:
    account_id, account_product_code, _ = _current_order_account()
    rows = kisdb.get_domestic_orders(
        account_id,
        account_product_code,
        start_date,
        end_date,
        symbol=symbol,
    )
    return [_format_domestic_order_row(row) for row in rows]


def _sync_domestic_orders(
    raw: dict,
    *,
    fallback_date: str,
    saved_order_history_id: str | None,
    source: str,
) -> int:
    rows = _normalize_domestic_orders_for_upsert(
        raw,
        fallback_date=fallback_date,
        saved_order_history_id=saved_order_history_id,
        source=source,
    )
    return kisdb.upsert_domestic_orders(rows)


def _resolve_order_history_source(source: str = "") -> str:
    token = (source or "auto").strip().lower()
    if token not in ORDER_HISTORY_SOURCES:
        raise ValueError(f"source must be one of {sorted(ORDER_HISTORY_SOURCES)}")
    return token


def _build_history_response(
    *,
    source: str,
    requested_source: str,
    start_date: str,
    end_date: str,
    symbol: str,
    rows: list[dict],
    raw: dict | None = None,
    fetched_at: str | None = None,
    snapshot_id: str | None = None,
    snapshot_status: str | None = None,
    saved_order_history_id: str | None = None,
    canonical_write_count: int | None = None,
) -> dict:
    payload = {
        "source": source,
        "status": "ok",
        "market_type": "domestic",
        "canonical_store": "domestic_orders",
        "requested_source": requested_source,
        "query": {
            "start_date": start_date,
            "end_date": end_date,
            "symbol": (symbol or "").strip().upper() or None,
        },
        "row_count": len(rows),
        "rows": rows,
    }
    if raw is not None:
        payload["raw"] = raw
    if fetched_at:
        payload["fetched_at"] = fetched_at
    if snapshot_id:
        payload["snapshot_id"] = snapshot_id
    if snapshot_status:
        payload["snapshot_status"] = snapshot_status
    if saved_order_history_id:
        payload["saved_order_history_id"] = saved_order_history_id
    if canonical_write_count is not None:
        payload["canonical_write_count"] = canonical_write_count
    return payload


async def get_domestic_order_history(
    start_date: str,
    end_date: str,
    *,
    symbol: str = "",
    source: str = "auto",
    save_history: bool = True,
) -> dict:
    """Get domestic order history with DB-first cache semantics and optional symbol filtering."""
    resolved_source = _resolve_order_history_source(source)
    account_id, account_product_code, _ = _current_order_account()

    if resolved_source in {"auto", "db"}:
        snapshot = kisdb.get_latest_order_history_snapshot(
            account_id,
            account_product_code,
            "domestic",
            start_date,
            end_date,
        )
        if snapshot:
            rows = _load_domestic_order_rows(start_date, end_date, symbol=symbol)
            if not rows and _order_count(snapshot["data"]) > 0:
                _sync_domestic_orders(
                    snapshot["data"],
                    fallback_date=start_date,
                    saved_order_history_id=snapshot.get("id"),
                    source="order_history_backfill",
                )
                rows = _load_domestic_order_rows(start_date, end_date, symbol=symbol)
            return _build_history_response(
                source="domestic_orders_db",
                requested_source=resolved_source,
                start_date=start_date,
                end_date=end_date,
                symbol=symbol,
                rows=rows,
                raw=snapshot["data"],
                fetched_at=snapshot.get("fetched_at"),
                snapshot_id=snapshot.get("id"),
                snapshot_status="cached",
            )
        if resolved_source == "db":
            return {
                "source": "domestic_orders_db",
                "status": "cache_miss",
                "market_type": "domestic",
                "canonical_store": "domestic_orders",
                "requested_source": resolved_source,
                "query": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "symbol": (symbol or "").strip().upper() or None,
                },
                "row_count": 0,
                "rows": [],
                "message": "No saved domestic order history snapshot found for the requested account/date range.",
            }

    fetched = await kis_api.inquery_order_list(
        start_date,
        end_date,
        save_history=save_history,
        return_metadata=True,
    )
    saved_order_history_id = fetched.get("saved_order_history_id")
    canonical_write_count = _sync_domestic_orders(
        fetched["raw"],
        fallback_date=start_date,
        saved_order_history_id=saved_order_history_id,
        source="kis_api",
    )
    return _build_history_response(
        source="kis_api",
        requested_source=resolved_source,
        start_date=start_date,
        end_date=end_date,
        symbol=symbol,
        rows=_load_domestic_order_rows(start_date, end_date, symbol=symbol),
        raw=fetched["raw"],
        snapshot_id=saved_order_history_id,
        snapshot_status="saved" if saved_order_history_id else "not_saved",
        saved_order_history_id=saved_order_history_id,
        canonical_write_count=canonical_write_count,
    )


async def collect_domestic_order_history(
    date_yyyymmdd: str,
    *,
    now: datetime | None = None,
    close_grace_minutes: int = 5,
) -> dict:
    """Collect and store one-day domestic order history for every configured account."""
    trade_date = resolve_yyyymmdd(date_yyyymmdd)
    gate = evaluate_krx_collection_gate(
        trade_date,
        now=now,
        close_grace_minutes=close_grace_minutes,
    )
    if gate.status == "skipped":
        return {
            "source": "market_calendar",
            "status": "skipped",
            "market_type": "domestic",
            "date": trade_date,
            "count": 0,
            "success_count": 0,
            "error_count": 0,
            "accounts": [],
            "skipped_reason": gate.reason,
            "market_calendar": gate.calendar,
            "now_local": gate.now_local,
        }

    results = []

    for account in load_account_registry():
        try:
            with scoped_account_env(account):
                result = await kis_api.inquery_order_list(
                    trade_date,
                    trade_date,
                    save_history=True,
                    return_metadata=True,
                )
                raw = result["raw"]
                saved_order_history_id = result.get("saved_order_history_id")
                canonical_write_count = _sync_domestic_orders(
                    raw,
                    fallback_date=trade_date,
                    saved_order_history_id=saved_order_history_id,
                    source="batch",
                )
            results.append({
                "status": "ok",
                "account": account.public_dict(),
                "order_count": _order_count(raw),
                "saved_order_history_id": saved_order_history_id,
                "history_status": "saved" if saved_order_history_id else "not_saved",
                "canonical_store": "domestic_orders",
                "canonical_write_count": canonical_write_count,
            })
        except Exception as exc:
            logger.warning("Domestic order history batch failed for %s: %s", account.label, exc)
            results.append({
                "status": "error",
                "account": account.public_dict(),
                "error": str(exc),
            })

    return {
        "source": "kis_api",
        "status": "ok",
        "market_type": "domestic",
        "date": trade_date,
        "count": len(results),
        "success_count": sum(1 for row in results if row["status"] == "ok"),
        "error_count": sum(1 for row in results if row["status"] == "error"),
        "accounts": results,
        "market_calendar": gate.calendar,
        "now_local": gate.now_local,
    }
